from app.agents.base import AgentResult, LocalLLM, adk_agent
from app.core.config import get_settings
from app.services.gemini import generate_json_any

ADK_AGENT = adk_agent("lesson_generation_agent", "Generate lesson outlines, scripts, slides, images, and diagrams.")


class LessonGenerationAgent:
    name = "Lesson Generation Agent"

    def generate(self, request) -> AgentResult:
        topic = request.topic
        settings = get_settings()

        # Try AI provider with automatic fallback (Gemini -> Ollama -> Template)
        try:
            prompt = f"""
Generate a detailed lesson about: "{topic}"
Teaching style: {request.teaching_style}
Language: {request.language}
Duration: {request.duration} minutes
Instructor notes: {request.additional_notes or "None"}
Extra guidance: {request.prompt}

Return ONLY valid JSON in this format:
{{
  "title": "...",
  "overview": "...",
  "learning_objectives": ["...", "..."],
  "outline": ["...", "..."],
  "sections": [
    {{ "heading": "...", "content": "...", "example": "..." }}
  ],
  "slides": [
    {{ "title": "...", "content": "...", "diagram": "..." }}
  ],
  "script": "...",
  "summary": "...",
  "key_points": ["...", "..."]
}}
"""
            data = generate_json_any(prompt, task_type="lesson")

            if isinstance(data, dict):
                slides = data.get("slides") or [
                    {
                        "title": section.get("heading", f"Section {index + 1}"),
                        "content": section.get("content", ""),
                        "diagram": section.get("example", "Example"),
                    }
                    for index, section in enumerate(data.get("sections") or [])
                ]
                return AgentResult(self.name, {
                    "topic": data.get("title") or topic,
                    "language": request.language,
                    "style": request.teaching_style,
                    "duration": request.duration,
                    "overview": data.get("overview", ""),
                    "learning_objectives": data.get("learning_objectives") or [],
                    "outline": data.get("outline") or [slide["title"] for slide in slides],
                    "sections": data.get("sections") or [],
                    "script": data.get("script") or data.get("overview") or "",
                    "slides": slides,
                    "summary": data.get("summary", ""),
                    "key_points": data.get("key_points") or [],
                    "images": [],
                })
        except Exception:
            pass

        llm = LocalLLM()
        objectives = [
            f"Explain the core idea of {topic}.",
            f"Apply {topic} through guided examples.",
            f"Evaluate understanding with a short knowledge check.",
        ]
        slides = [
            {"title": f"{topic}: Big Picture", "content": "Definition, why it matters, and a relatable example.", "diagram": "Concept map"},
            {"title": "Key Concepts", "content": "Three essential ideas with visual cues.", "diagram": "Flow diagram"},
            {"title": "Worked Example", "content": "Step-by-step demonstration with common mistakes.", "diagram": "Annotated process"},
            {"title": "Practice", "content": "Learners solve a short task and compare answers.", "diagram": "Checklist"},
        ]
        script = llm.generate(f"{request.teaching_style} {request.language} lesson script about {topic}: {request.prompt}")
        return AgentResult(self.name, {
            "topic": topic,
            "language": request.language,
            "style": request.teaching_style,
            "duration": request.duration,
            "overview": f"A practical introduction to {topic}.",
            "learning_objectives": objectives,
            "outline": [slide["title"] for slide in slides],
            "sections": [
                {"heading": slide["title"], "content": slide["content"], "example": slide["diagram"]}
                for slide in slides
            ],
            "script": script,
            "slides": slides,
            "summary": f"Learners now understand the essentials of {topic}.",
            "key_points": objectives,
            "images": [],
        })

    def simplify_from_recommendation(self, topic: str, recommendations: list[str]) -> AgentResult:
        return AgentResult(self.name, {
            "topic": topic,
            "simplified_version": f"A slower, example-first explanation of {topic}.",
            "alternative_explanations": ["Use an everyday analogy.", "Show a visual sequence.", "Break the task into three small decisions."],
            "additional_examples": recommendations[:3],
        })

