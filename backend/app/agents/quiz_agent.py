import json

from app.agents.base import AgentResult, adk_agent
from app.core.config import get_settings
from app.services.gemini import generate_json_any

ADK_AGENT = adk_agent("quiz_generation_agent", "Generate MCQ, true/false, and short-answer quizzes.")


class QuizGenerationAgent:
    name = "Quiz Generation Agent"

    def generate(self, topic: str, difficulty: str = "Medium", count: int = 8, prompt: str = "") -> AgentResult:
        settings = get_settings()
        instructor_notes = f'\nInstructor guidance: "{prompt}"' if prompt.strip() else ""
        # Try AI provider with automatic fallback (Gemini -> Ollama -> Template)
        try:
            prompt_text = f"""
You are a Senior Assessment Specialist and University Examiner.
Generate {count} EXPERT-LEVEL, highly rigorous assessment questions for: "{topic}"
Difficulty Level: {difficulty}{instructor_notes}

Instructions:
1. Every question must test analytical comprehension, architectural evaluation, or real-world problem solving.
2. For multiple-choice questions, provide 4 clear options (A, B, C, D) where distractors represent plausible real-world misconceptions.
3. Every question MUST include a detailed 2-3 sentence explanation clarifying WHY the correct option is right and WHY distractors are incorrect.

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
            data = generate_json_any(prompt_text, task_type="quiz")

            if isinstance(data, dict) and data.get("questions"):
                return AgentResult(self.name, {
                    "title": data.get("title") or f"{topic} Master Assessment",
                    "difficulty": data.get("difficulty") or difficulty,
                    "questions": data["questions"],
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
        return AgentResult(self.name, {"title": f"{topic} Master Assessment", "difficulty": difficulty, "questions": questions[:count]})

    @staticmethod
    def dumps(data: dict) -> str:
        return json.dumps(data, ensure_ascii=False)
