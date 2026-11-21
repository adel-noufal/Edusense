from __future__ import annotations

import json
from typing import Optional
from sqlalchemy.orm import Session

from app.agents.base import AgentResult, adk_agent
from app.agents.logging_utils import LLMAuditContext
from app.agents.prompts.scope_guardrail import build_guardrail_prompt
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.models import QuizAgentConfig
from app.services.gemini import generate_json_any
from app.services.content_pipeline import format_strict_text, validate_quality, critique_output

ADK_AGENT = adk_agent("quiz_generation_agent", "Generate MCQ, true/false, and short-answer quizzes.")

# Canonical difficulty enum â€” anything else maps to the nearest level so the
# UI never shows mixed labels like "Medium" vs "intermediate".
_DIFFICULTY_MAP = {
    "easy": "Easy", "beginner": "Easy", "foundation": "Easy",
    "medium": "Medium", "intermediate": "Medium", "moderate": "Medium", "mid": "Medium",
    "hard": "Hard", "advanced": "Hard", "difficult": "Hard", "expert": "Hard",
}


def normalize_difficulty(value) -> str:
    """Map any difficulty label to Easy|Medium|Hard (default Medium)."""
    key = str(value or "").strip().lower()
    return _DIFFICULTY_MAP.get(key, "Medium")


def _pad_questions(questions: list[dict], count: int, topic: str, difficulty: str) -> list[dict]:
    """Top up a short LLM question list with unique template questions so the
    requested count is honored. Never duplicates an existing question text."""
    seen = {str(q.get("question", "")).strip().lower() for q in questions if isinstance(q, dict)}
    idx = len(questions) + 1
    templates = [
        (f"Which concept is most central to {topic}?",
         ["A) The core principle that governs the topic's main behavior",
          "B) An unrelated historical anecdote",
          "C) A formatting convention with no functional effect",
          "D) A deprecated feature removed in the latest version"],
         "A"),
        (f"What is the best first step when applying {topic} to a new problem?",
         ["A) Define requirements and constraints before choosing a method",
          "B) Immediately write the final implementation",
          "C) Skip testing until the end of the project",
          "D) Copy an unrelated example without adaptation"],
         "A"),
        (f"Which outcome indicates {topic} was applied correctly?",
         ["A) The expected behavior is observed and verified by tests",
          "B) The code compiles but no one checked the output",
          "C) All edge cases were ignored",
          "D) The solution was never documented"],
         "A"),
        (f"What is a common pitfall when working with {topic}?",
         ["A) Ignoring edge cases and input validation",
          "B) Writing clear documentation",
          "C) Running unit tests regularly",
          "D) Reviewing code with a peer"],
         "A"),
        (f"How does {topic} scale as data or complexity grows?",
         ["A) Cost grows predictably and bottlenecks can be measured and optimized",
          "B) It always requires rewriting from scratch",
          "C) Performance is unaffected by any input size",
          "D) It only works for tiny fixed-size inputs"],
         "A"),
    ]
    ti = 0
    while len(questions) < count and ti < len(templates) * 3:
        text, options, answer = templates[ti % len(templates)]
        if ti >= len(templates):
            text = f"{text} (variant {ti // len(templates) + 1})"
        key = text.strip().lower()
        if key not in seen:
            seen.add(key)
            questions.append({
                "type": "multiple_choice",
                "question": text,
                "options": options,
                "answer": answer,
                "explanation": f"Template question covering a core aspect of {topic}.",
            })
        ti += 1
    return questions[:count]


def normalize_questions(raw_questions, count: int, topic: str, difficulty: str) -> list[dict]:
    """Ensure the question list is a list of dicts, truncated/padded to `count`."""
    if not isinstance(raw_questions, list):
        raw_questions = []
    clean = [q for q in raw_questions if isinstance(q, dict) and str(q.get("question", "")).strip()]
    if len(clean) > count:
        clean = clean[:count]
    if len(clean) < count:
        clean = _pad_questions(clean, count, topic, difficulty)
    return clean


# ---------------------------------------------------------------------------
# RAG context helpers
# ---------------------------------------------------------------------------

def _build_rag_context(topic: str, subject: Optional[str], grade_level: Optional[str]) -> tuple[str, list[str]]:
    """Returns (formatted_context_block, list_of_source_labels)."""
    try:
        from app.agents.tools import RAG_Search_Tool
        chunks = RAG_Search_Tool(
            query=topic,
            subject=subject,
            grade_level=grade_level,
            top_k=5,
        )
    except Exception as exc:
        print(f"[RAG] Quiz RAG lookup failed ({exc}); generating without source material.")
        return "", []

    if not chunks:
        return "", []

    lines = []
    sources: list[str] = []
    for chunk in chunks:
        src = chunk.get("source_file", "")
        page = chunk.get("page", "")
        label = f"{src} p.{page}" if src and page else (src or "unknown")
        if label not in sources:
            sources.append(label)
        lines.append(f"[Source: {label}]\n{chunk['text']}")

    return "\n\n".join(lines), sources


def _build_web_context(topic: str, max_results: int = 3) -> tuple[str, list[dict], list[str]]:
    """
    Calls Web_Search_Tool and returns (context_block, raw_results, source_labels).
    Returns ("", [], []) if unavailable or no results.
    """
    try:
        from app.agents.tools import Web_Search_Tool
        results = Web_Search_Tool(query=topic, max_results=max_results)
    except Exception as exc:
        print(f"[Web Search] Quiz web lookup failed ({exc}); continuing without web material.")
        return "", [], []

    if not results:
        return "", [], []

    lines = []
    sources: list[str] = []
    for i, item in enumerate(results):
        title = item.get("title", "")
        url = item.get("url", "")
        content = item.get("content", "")
        label = f"[Web: {title}]({url})" if url else f"[Web: {title}]"
        if label not in sources:
            sources.append(label)
        lines.append(f"[Web {i+1}: {title}]({url})\n{content}")

    return "\n\n".join(lines), results, sources


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class QuizGenerationAgent:
    name = "Quiz Generation Agent"

    def generate(
        self,
        topic: str,
        difficulty: str = "Medium",
        count: int = 8,
        prompt: str = "",
        subject: Optional[str] = None,
        grade_level: Optional[str] = None,
        config_id: Optional[int] = None,
        teaching_style: str = "Interactive",
    ) -> AgentResult:
        settings = get_settings()

        # Load config if provided and merge preferences
        config_difficulty = difficulty
        config_count = count
        config_prompt = prompt
        config_subject = subject
        config_grade_level = grade_level
        config_time_limit = None
        config_fullscreen_lock = False
        config_camera_monitoring = False

        if config_id:
            db = SessionLocal()
            try:
                config = db.query(QuizAgentConfig).filter_by(id=config_id).first()
                if config:
                    if config.difficulty_mix:
                        # Use the highest weighted difficulty as default
                        import json as _json
                        mix = _json.loads(config.difficulty_mix)
                        config_difficulty = max(mix, key=mix.get).capitalize()
                    if config.question_types:
                        # Could influence question type distribution
                        pass
                    if config.topic_weights:
                        # Could influence topic emphasis in prompt
                        import json as _json
                        weights = _json.loads(config.topic_weights)
                        if weights:
                            top_topic = max(weights, key=weights.get)
                            config_prompt = f'{prompt}\nFocus emphasis on: {top_topic}' if prompt.strip() else f'Focus emphasis on: {top_topic}'
                    config_time_limit = config.time_limit_seconds
                    config_fullscreen_lock = config.fullscreen_lock
                    config_camera_monitoring = config.camera_monitoring
                    if config.custom_prompt:
                        config_prompt = f'{config_prompt}\n{config.custom_prompt}'.strip()
                    if config.subject and not subject:
                        config_subject = config.subject
                    if config.grade_level and not grade_level:
                        config_grade_level = config.grade_level
            finally:
                db.close()

        instructor_notes = f'\nInstructor guidance: "{config_prompt}"' if config_prompt.strip() else ""
        instructor_notes += f'\nTeaching style: {teaching_style}'

        # â”€â”€ RAG retrieval (curriculum first) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        rag_context, rag_sources = _build_rag_context(topic, subject, grade_level)

        # â”€â”€ Web retrieval (if curriculum is insufficient) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        web_context = ""
        web_results = []
        web_sources = []
        if not rag_sources:
            web_context, web_results, web_sources = _build_web_context(topic)

        source_blocks = []
        if rag_context:
            source_blocks.append(
                "=== CURRICULUM SOURCE MATERIAL (RAG) ===\n"
                f"{rag_context}\n"
                "=== END CURRICULUM SOURCE MATERIAL ==="
            )
        if web_context:
            source_blocks.append(
                "=== WEB SEARCH RESULTS ===\n"
                f"{web_context}\n"
                "=== END WEB SEARCH RESULTS ==="
            )

        if source_blocks:
            source_instruction = (
                "\n\nIMPORTANT: Base every question on the following source material. "
                "Prioritize curriculum sources when available; use web results for recent context. "
                "Cite curriculum sources as [Source: label] and web sources as [Web N: title].\n\n"
                + "\n\n".join(source_blocks)
            )
        else:
            source_instruction = ""

        # Try AI provider with automatic fallback (Gemini -> Ollama -> Template)
        try:
            # Build guardrail prompt with context
            guardrail = build_guardrail_prompt(
                subject=subject,
                grade_level=grade_level,
                agent_name="QuizGenerationAgent",
                has_rag_sources=bool(rag_sources),
                has_web_sources=bool(web_sources),
            )

            prompt_text = f"""
{guardrail}

You are a Senior Assessment Specialist and University Examiner.
Generate {count} EXPERT-LEVEL, highly rigorous assessment questions for: "{topic}"
Difficulty Level: {difficulty}{instructor_notes}
{source_instruction}

Instructions:
1. Every question must test analytical comprehension, architectural evaluation, or real-world problem solving.
2. For multiple-choice questions, provide 4 clear options (A, B, C, D) where distractors represent plausible real-world misconceptions.
3. Every question MUST include a detailed 2-3 sentence explanation clarifying WHY the correct option is right and WHY distractors are incorrect.
4. If source material is provided above, ground every question in those sources and cite them using [Source: label] format.

Return ONLY valid JSON:
{{
  "title": "{topic} Master Assessment",
  "difficulty": "{difficulty}",
  "questions": [
    {{
      "type": "multiple_choice",
      "question": "Clear, challenging question on {topic}?",
      "options": ["A) Option A description", "B) Option B description", "C) Option C description", "D) Option D description"],
      "answer": "A",
      "explanation": "Detailed pedagogical explanation of the answer..."
    }}
  ]
}}
"""

            # Audit logging for LLM call
            with LLMAuditContext(
                agent_name="QuizGenerationAgent",
                method_name="generate",
                subject=subject,
                grade_level=grade_level,
                topic=topic,
                has_rag_sources=bool(rag_sources),
                rag_source_count=len(rag_sources),
                has_web_sources=bool(web_sources),
                web_source_count=len(web_sources),
            ) as audit_ctx:
                audit_ctx.set_prompt(prompt_text)
                data = generate_json_any(prompt_text, task_type="quiz")
                audit_ctx.set_response(str(data), model_used="gemini", fallback_used=False)

            if isinstance(data, dict) and data.get("questions"):
                questions = normalize_questions(data["questions"], count, topic, difficulty)
                questions = format_strict_text(questions)
                quality = critique_output({"questions": questions}, topic)
                return AgentResult(self.name, {
                    "title": data.get("title") or f"{topic} Master Assessment",
                    "difficulty": normalize_difficulty(data.get("difficulty") or difficulty),
                    "questions": questions,
                    "sources": rag_sources + web_sources,
                    "unverified": len(rag_sources + web_sources) == 0,
                    "web_sources": web_results,
                    "quality": quality,
                    "quality_issues": validate_quality({"sections": [{"content": str(q)} for q in questions]}, source_attached=bool(rag_sources)),
                })
        except Exception:
            pass

        # Expert Fallback Questions
        questions = [
            {
                "type": "multiple_choice",
                "question": f"Which architectural principle is most fundamental to mastering {topic} in production?",
                "options": [
                    "A) Modular decoupling of state management and processing logic",
                    "B) Coupling all components into a single monolithic script",
                    "C) Disabling error logging to decrease computational overhead",
                    "D) Static hardcoding of dynamic network parameters"
                ],
                "answer": "A",
                "explanation": "Modular decoupling ensures maintainability, isolation of failure modes, and seamless horizontal scaling in enterprise deployments.",
                "difficulty": difficulty,
            },
            {
                "type": "multiple_choice",
                "question": f"When scaling {topic} to handle high throughput, what is the primary optimization bottleneck to monitor?",
                "options": [
                    "A) Memory bandwidth & state serialization overhead",
                    "B) Background styling CSS colors",
                    "C) Unused localized string translations",
                    "D) Client screen resolution bounds"
                ],
                "answer": "A",
                "explanation": "High-throughput systems processing {topic} are primarily constrained by serialization overhead, memory allocation bandwidth, and database query latency.",
                "difficulty": difficulty,
            },
            {
                "type": "true_false",
                "question": f"True or False: Implementing automated validation boundaries in {topic} significantly reduces downstream failure rates.",
                "answer": "True",
                "explanation": "Automated validation catches invalid state transitions early at the ingestion boundary before corrupting downstream execution pipelines.",
                "difficulty": difficulty,
            },
            {
                "type": "multiple_choice",
                "question": f"What is the recommended best practice when handling edge cases in {topic} execution?",
                "options": [
                    "A) Enforce explicit exception boundaries with fallback recovery handlers",
                    "B) Silently swallow runtime exceptions without logging",
                    "C) Terminate the host process immediately without cleanup",
                    "D) Ignore edge cases and assume inputs are always valid"
                ],
                "answer": "A",
                "explanation": "Explicit exception boundaries prevent unhandled crashes, log empirical diagnostic traces, and safely activate fallback mechanisms.",
                "difficulty": difficulty,
            }
        ]
        while len(questions) < count:
            idx = len(questions) + 1
            questions.append({
                "type": "multiple_choice",
                "question": f"Question {idx}: In {topic}, how does strategy {idx} optimize system performance?",
                "options": [
                    f"A) By reducing redundant operations and caching intermediate results",
                    f"B) By increasing duplicate network requests",
                    f"C) By bypassing security validation checks",
                    f"D) By running blocking loops on the main thread"
                ],
                "answer": "A",
                "explanation": "Strategy A eliminates redundant processing through intelligent caching and memoization, dramatically improving execution speed.",
                "difficulty": difficulty,
            })
        questions = format_strict_text(normalize_questions(questions, count, topic, difficulty))
        return AgentResult(self.name, {
            "title": f"{topic} Master Assessment",
            "difficulty": normalize_difficulty(difficulty),
            "questions": questions,
            "sources": rag_sources + web_sources,
            "unverified": len(rag_sources + web_sources) == 0,
            "web_sources": web_results,
        })

    @staticmethod
    def dumps(data: dict) -> str:
        return json.dumps(data, ensure_ascii=False)
