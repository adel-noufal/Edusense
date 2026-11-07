import json
import random
from dataclasses import dataclass

from app.agents.prompts.scope_guardrail import check_topic_in_scope, get_refusal_message
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
    def generate(self, prompt: str) -> str:
        settings = get_settings()
        # 1. Try Gemini (Online) first
        if settings.gemini_api_key and settings.ai_provider in ("auto", "gemini"):
            try:
                return generate_content(prompt)
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


    def _template(self, prompt: str, subject: str | None = None, grade_level: str | None = None) -> str:
        """
        Template fallback with scope guardrail check.
        If query is off-topic for the declared subject/grade, return refusal message.
        """
        # Scope check for off-topic queries (no LLM required)
        # Try to extract query from prompt for scope checking
        query_for_check = prompt
        # If prompt contains "Current Question:" or "QUESTION:", extract the actual question
        for marker in ["Current Question:", "QUESTION:", "Question:"]:
            if marker in prompt:
                query_for_check = prompt.split(marker)[-1].split("\n")[0].strip()
                break

        in_scope, refusal = check_topic_in_scope(query_for_check, subject, grade_level)
        if not in_scope:
            return refusal

        tone = random.choice(["clear", "interactive", "visual", "practice-oriented"])
        return f"Generated local {tone} educational content for: {prompt[:240]}"


def adk_agent(name: str, description: str):
    try:
        from google.adk.agents import Agent
        return Agent(name=name, description=description, instruction=description)
    except Exception:
        return {"name": name, "description": description, "runtime": "local-fallback"}

