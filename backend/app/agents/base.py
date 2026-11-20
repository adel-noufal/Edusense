import json
import random
from dataclasses import dataclass

from app.agents.prompts.scope_guardrail import (
    check_topic_in_scope,
    ensure_clean_user_answer,
    get_refusal_message,
)
from app.core.config import get_settings
from app.services.gemini import generate_content, generate_via_ollama


@dataclass
class AgentResult:
    name: str
    data: dict

    @property
    def unverified(self) -> bool:
        """Returns True if the result was generated without RAG source verification."""
        return self.data.get("unverified", True)


class LocalLLM:
    def generate(self, prompt: str, task_type: str = "general",
                 temperature: float | None = None,
                 max_output_tokens: int | None = None) -> str:
        settings = get_settings()
        # 1. Try Gemini (Online) first
        if settings.gemini_api_key and settings.ai_provider in ("auto", "gemini"):
            try:
                return generate_content(
                    prompt, task_type=task_type,
                    temperature=temperature, max_output_tokens=max_output_tokens,
                )
            except Exception as exc:
                print(f"[AI Fallback] Gemini text generation unavailable ({exc}). Switching to Ollama...")

        # 2. Try Ollama (Offline) next
        if settings.ai_provider in ("auto", "gemini", "ollama"):
            try:
                return generate_via_ollama(prompt)
            except Exception as exc:
                print(f"[AI Fallback] Ollama text generation unavailable ({exc}). Using template...")

        # 3. Final local template fallback
        return self._template(prompt)


    def _template(self, prompt: str, subject: str | None = None, grade_level: str | None = None,
                  query: str | None = None) -> str:
        """
        Template fallback with scope guardrail check.
        If query is off-topic for the declared subject/grade, return refusal message.
        """
        # Scope check for off-topic queries (no LLM required)
        # Prefer an explicit `query` (the raw user question) when the caller has it —
        # parsing it back out of a fully-built prompt is fragile and was the source
        # of prompt-text leaking into user-facing fallback answers.
        query_for_check = (query or "").strip() or prompt
        if not query:
            # If prompt contains "Current Question:" or "QUESTION:", extract the actual question
            for marker in ["Current Question:", "Student question:", "QUESTION:", "Question:"]:
                if marker in query_for_check:
                    query_for_check = query_for_check.split(marker, 1)[1]
                    break
        # Never carry instruction scaffolding into the user-facing answer: cut the
        # extracted text at the first line break or known instruction phrase, and
        # drop bracketed scaffolding tags entirely.
        for cut in [
            "\n", "Use ONLY", "Be concise", "Answer:", "===", "If the sources",
            "Current Question", "Student question", "Conversation History", "Rules:", "- ",
        ]:
            idx = query_for_check.find(cut)
            if idx > 0:
                query_for_check = query_for_check[:idx]
        _lines = [
            ln.strip() for ln in query_for_check.split("\n")
            if ln.strip() and not ln.strip().startswith("[")
        ]
        query_for_check = " ".join(_lines).strip()
        # Collapse whitespace and cap length so a runaway extraction can never
        # produce a wall of prompt text.
        query_for_check = " ".join(query_for_check.split())[:200]

        in_scope, refusal = check_topic_in_scope(query_for_check, subject, grade_level)
        if not in_scope:
            return refusal

        tone = random.choice(["clear", "interactive", "visual", "practice-oriented"])
        # Never echo raw prompt/instruction text back to the user — only the
        # extracted question/topic may appear in the fallback answer.
        topic_text = query_for_check if query_for_check else "this topic"
        answer = (
            f"Here's a {tone} explanation to help you study {topic_text}. "
            "For a detailed answer, please try again when the AI service is available, "
            "or consult your course materials and instructor."
        )
        return ensure_clean_user_answer(answer)


def adk_agent(name: str, description: str):
    try:
        from google.adk.agents import Agent
        return Agent(name=name, description=description, instruction=description)
    except Exception:
        return {"name": name, "description": description, "runtime": "local-fallback"}

