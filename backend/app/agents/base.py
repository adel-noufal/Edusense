import json
import random
from dataclasses import dataclass

from app.core.config import get_settings
from app.services.gemini import generate_content, generate_via_ollama


@dataclass
class AgentResult:
    name: str
    data: dict


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


    def _template(self, prompt: str) -> str:
        tone = random.choice(["clear", "interactive", "visual", "practice-oriented"])
        return f"Generated local {tone} educational content for: {prompt[:240]}"


def adk_agent(name: str, description: str):
    try:
        from google.adk.agents import Agent
        return Agent(name=name, description=description, instruction=description)
    except Exception:
        return {"name": name, "description": description, "runtime": "local-fallback"}

