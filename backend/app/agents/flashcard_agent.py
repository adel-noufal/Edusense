from app.agents.base import AgentResult, adk_agent
from app.core.config import get_settings
from app.services.gemini import generate_json_any

ADK_AGENT = adk_agent("flashcard_generation_agent", "Generate study flashcards from educational topics.")


class FlashcardGenerationAgent:
    name = "Flashcard Generation Agent"

    def generate(self, topic: str, count: int = 10, language: str = "English") -> AgentResult:
        settings = get_settings()
        # Try AI provider with automatic fallback (Gemini -> Ollama -> Template)
        try:
            prompt = f"""
Create {count} study flashcards about: "{topic}"
Language: {language}

Return ONLY valid JSON:
{{
  "title": "...",
  "cards": [
    {{ "front": "question or term", "back": "answer or explanation" }}
  ]
}}
"""
            data = generate_json_any(prompt, task_type="flashcard")

            if isinstance(data, dict) and data.get("cards"):
                return AgentResult(self.name, {
                    "title": data.get("title") or f"{topic} Flashcards",
                    "topic": topic,
                    "language": language,
                    "cards": data["cards"][:count],
                })
        except Exception:
            pass

        cards = [
            {"front": f"What is a core idea in {topic}?", "back": f"A foundational concept learners should remember about {topic}."},
            {"front": f"Give one example of {topic}.", "back": "A practical example that connects theory to real use."},
            {"front": f"Why does {topic} matter?", "back": "It helps learners solve problems and build deeper understanding."},
        ]
        while len(cards) < count:
            cards.append({
                "front": f"Quick check {len(cards) + 1}: {topic}",
                "back": f"Review the key concept #{len(cards) + 1} for {topic}.",
            })
        return AgentResult(self.name, {
            "title": f"{topic} Flashcards",
            "topic": topic,
            "language": language,
            "cards": cards[:count],
        })
