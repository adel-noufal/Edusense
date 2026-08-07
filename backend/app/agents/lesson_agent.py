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
You are an award-winning University Professor and Senior Curriculum Designer.
Create an EXPERT-LEVEL, highly comprehensive, and masterfully structured lesson on: "{topic}"

Teaching style: {request.teaching_style}
Language: {request.language}
Duration: {request.duration} minutes
Instructor notes: {request.additional_notes or "None"}
Extra guidance: {request.prompt}

Instructions:
1. Provide deep, rigorous, and practical explanations. Avoid generic filler words.
2. Structure slides like a senior presentation designer with clear titles, bullet points, visual diagram descriptions, and instructor speaking notes.
3. Include real-world industrial case studies, step-by-step mechanisms, and practical code/math examples.

Return ONLY valid JSON matching this structure:
{{
  "title": "Mastering {topic}",
  "overview": "Comprehensive 3-paragraph executive introduction to {topic}, covering core theory, architectural mechanics, and industry significance.",
  "learning_objectives": [
    "Synthesize the foundational principles of {topic}.",
    "Analyze the structural workflow and mathematical/algorithmic mechanisms.",
    "Implement real-world solutions and evaluate efficiency tradeoffs."
  ],
  "outline": ["1. Architectural Foundations", "2. Core Mechanics & Formulas", "3. Industry Case Studies", "4. Practical Implementation", "5. Strategic Synthesis"],
  "sections": [
    {{
      "heading": "1. Architectural Foundations of {topic}",
      "content": "Detailed, highly articulate multi-paragraph explanation of core principles...",
      "example": "Real-world production case study detailing practical application..."
    }},
    {{
      "heading": "2. Core Mechanics & Technical Pipeline",
      "content": "Step-by-step breakdown of how {topic} operates under the hood...",
      "example": "Concrete code snippet or mathematical formulation..."
    }},
    {{
      "heading": "3. Advanced Strategies & Performance Tradeoffs",
      "content": "Deep dive into performance optimization, edge cases, and best practices...",
      "example": "Comparative evaluation matrix showing performance gains..."
    }}
  ],
  "slides": [
    {{
      "title": "1. Introduction to {topic}",
      "content": "• Core Definition: Foundational concept breakdown\n• Industry Value: Why leading organizations adopt this approach\n• Key Objective: What learners will master by the end of this module",
      "diagram": "Concept Architecture Diagram: Input -> Processing Core -> Output State",
      "notes": "Welcome class! Start by highlighting the real-world impact of {topic} before diving into technical details."
    }},
    {{
      "title": "2. Underlying Mechanics & Pipeline",
      "content": "• Step 1: Initialization and feature preparation\n• Step 2: Core processing pipeline & state transformation\n• Step 3: Validation, error checking, and result delivery",
      "diagram": "Flowchart: [Raw Data] -> [Preprocessing] -> [Core Engine] -> [Validated Output]",
      "notes": "Focus on step 2 here—make sure students understand how the transformation happens under the hood."
    }},
    {{
      "title": "3. Practical Case Study & Implementation",
      "content": "• Real-World Scenario: Solving enterprise scaling challenges\n• Key Implementation Details: Critical parameters & configurations\n• Best Practices: Avoid common pitfalls and anti-patterns",
      "diagram": "System Blueprint: Microservice Architecture & API Integration",
      "notes": "Use this slide to connect theory to practice. Walk through the code/configuration line by line."
    }},
    {{
      "title": "4. Summary & Strategic Takeaways",
      "content": "• Foundational Insight: Core theoretical takeaway\n• Operational Strategy: How to apply this immediately\n• Next Steps: Advanced topics and practical exercises",
      "diagram": "Summary Matrix: Strengths vs. Considerations",
      "notes": "Wrap up by asking 2-3 quick questions to check student comprehension."
    }}
  ],
  "script": "Professional, engaging, word-for-word lecture script for the instructor...",
  "summary": "Master executive summary synthesizing all core learnings of {topic}.",
  "key_points": [
    "Foundational understanding of {topic} architecture.",
    "Mastery of operational workflows and implementation steps.",
    "Ability to evaluate tradeoffs and optimize performance."
  ]
}}
"""
            data = generate_json_any(prompt, task_type="lesson")

            if isinstance(data, dict):
                slides = data.get("slides") or [
                    {
                        "title": section.get("heading", f"Section {index + 1}"),
                        "content": section.get("content", ""),
                        "diagram": section.get("example", "Concept Diagram"),
                        "notes": f"Instructor guide for {section.get('heading', 'this topic')}."
                    }
                    for index, section in enumerate(data.get("sections") or [])
                ]
                return AgentResult(self.name, {
                    "topic": data.get("title") or f"Mastering {topic}",
                    "language": request.language,
                    "style": request.teaching_style,
                    "duration": request.duration,
                    "overview": data.get("overview", f"An expert masterclass on {topic}."),
                    "learning_objectives": data.get("learning_objectives") or [
                        f"Master the core theoretical foundation of {topic}.",
                        f"Analyze system architecture and implementation mechanics.",
                        f"Apply {topic} to solve real-world engineering and educational challenges."
                    ],
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

        # Expert Fallback Template
        objectives = [
            f"Understand the core architecture and mathematical principles of {topic}.",
            f"Evaluate real-world case studies and practical implementation steps.",
            f"Analyze performance tradeoffs, common pitfalls, and optimization strategies."
        ]
        slides = [
            {
                "title": f"1. Executive Overview: {topic}",
                "content": f"• Foundational Definition: Core principles of {topic}\n• Industry Significance: Why top organizations leverage this concept\n• Primary Goal: Achieving structural mastery and analytical clarity",
                "diagram": f"High-Level Architecture: [Input Context] ➔ [{topic} Engine] ➔ [Optimized Outcome]",
                "notes": f"Begin the session by connecting {topic} to real-world industrial applications."
            },
            {
                "title": f"2. Core Mechanics & Technical Pipeline",
                "content": "• Phase 1: Data preparation & initialization\n• Phase 2: Algorithmic transformation & optimization loop\n• Phase 3: Validation, metric evaluation, and deployment",
                "diagram": "Process Pipeline: [Data Source] ➔ [Transformation Core] ➔ [Validation Check]",
                "notes": "Emphasize Phase 2 during lecture—this is where the primary computational transformation occurs."
            },
            {
                "title": f"3. Production Case Study & Implementation",
                "content": "• Enterprise Context: Solving real-world scale challenges\n• Critical Parameters: Essential configuration patterns\n• Tradeoff Analysis: Balancing performance vs. system complexity",
                "diagram": "System Blueprint: Component Interaction & Data Flow",
                "notes": "Walk through the configuration step-by-step so students can reproduce the setup."
            },
            {
                "title": "4. Synthesis & Key Takeaways",
                "content": "• Theoretical Mastery: Core principles internalized\n• Operational Blueprint: Practical roadmap for implementation\n• Next Steps: Advanced topics and hands-on laboratory exercises",
                "diagram": "Mastery Matrix: Core Competencies Checklist",
                "notes": "Conclude with an interactive knowledge check."
            }
        ]
        return AgentResult(self.name, {
            "topic": f"Mastering {topic}",
            "language": request.language,
            "style": request.teaching_style,
            "duration": request.duration,
            "overview": f"A comprehensive masterclass on {topic}, detailing theoretical foundations, architectural mechanisms, real-world case studies, and performance optimization strategies.",
            "learning_objectives": objectives,
            "outline": [slide["title"] for slide in slides],
            "sections": [
                {
                    "heading": f"1. Architectural Principles of {topic}",
                    "content": f"The foundational core of {topic} relies on clear architectural abstractions and structured domain mechanics. By decoupling system components into modular layers, practitioners achieve optimal efficiency and maintainability.",
                    "example": f"Enterprise Case Study: Implementing {topic} to streamline data processing pipelines."
                },
                {
                    "heading": f"2. Operational Mechanics & Technical Pipeline",
                    "content": f"Under the hood, {topic} executes a multi-stage transformation process. Stage 1 initializes boundary parameters, Stage 2 applies domain-specific transformations, and Stage 3 verifies correctness through automated validation matrices.",
                    "example": f"Code Implementation: Production configuration pattern for {topic}."
                },
                {
                    "heading": "3. Optimization Strategies & Best Practices",
                    "content": f"To maximize efficiency when deploying {topic}, engineers prioritize resource allocation, bottleneck reduction, and proactive error handling. Adhering to these industry standards minimizes latency and enhances robustness.",
                    "example": "Benchmarking results comparing legacy approaches against optimized architectures."
                }
            ],
            "script": f"Welcome everyone to today's deep dive into {topic}. We will start with the high-level architecture before examining the underlying code and deployment best practices...",
            "slides": slides,
            "summary": f"Learners now possess a thorough understanding of {topic}, spanning theoretical fundamentals, hands-on implementation steps, and production optimization techniques.",
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

