import json

from app.agents.base import AgentResult, adk_agent
from app.core.config import get_settings
from app.services.gemini import generate_json_any

ADK_AGENT = adk_agent("quiz_generation_agent", "Generate MCQ, true/false, and short-answer quizzes.")


class QuizGenerationAgent:
    name = "Quiz Generation Agent"

    def generate(self, topic: str, difficulty: str = "Medium", count: int = 8) -> AgentResult:
        settings = get_settings()
        # Try AI provider with automatic fallback (Gemini -> Ollama -> Template)
        try:
            prompt = f"""
Based on this lesson topic: "{topic}"
Difficulty: {difficulty}
Generate {count} assessment questions.

Return ONLY valid JSON:
{{
  "title": "...",
  "difficulty": "{difficulty}",
  "questions": [
    {{
      "type": "multiple_choice",
      "question": "...",
      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
      "answer": "A",
      "explanation": "..."
    }}
  ]
}}
"""
            data = generate_json_any(prompt, task_type="quiz")

            if isinstance(data, dict) and data.get("questions"):
                return AgentResult(self.name, {
                    "title": data.get("title") or f"{topic} Knowledge Check",
                    "difficulty": data.get("difficulty") or difficulty,
                    "questions": data["questions"],
                })
        except Exception:
            pass

        questions = []
        for idx in range(1, count + 1):
            if idx % 3 == 1:
                questions.append({
                    "type": "multiple_choice",
                    "question": f"Which statement best describes {topic} concept {idx}?",
                    "options": ["A) Core principle", "B) Unrelated fact", "C) Historical note", "D) Formatting choice"],
                    "answer": "A",
                    "explanation": "The core principle is the most accurate description.",
                    "difficulty": difficulty,
                })
            elif idx % 3 == 2:
                questions.append({
                    "type": "true_false",
                    "question": f"{topic} can be reinforced through examples and feedback.",
                    "answer": "True",
                    "explanation": "Examples and feedback improve retention.",
                    "difficulty": difficulty,
                })
            else:
                questions.append({
                    "type": "short_answer",
                    "question": f"Give one practical use of {topic}.",
                    "answer": "A correct answer connects the concept to a real learning task.",
                    "explanation": "Look for a real-world application of the concept.",
                    "difficulty": difficulty,
                })
        return AgentResult(self.name, {"title": f"{topic} Knowledge Check", "difficulty": difficulty, "questions": questions})

    @staticmethod
    def dumps(data: dict) -> str:
        return json.dumps(data, ensure_ascii=False)
