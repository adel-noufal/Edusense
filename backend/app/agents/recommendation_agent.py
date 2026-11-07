from app.agents.base import AgentResult, LocalLLM, adk_agent
from app.core.config import get_settings

ADK_AGENT = adk_agent("recommendation_agent", "Analyze emotion and engagement reports and recommend instructional improvements.")


class RecommendationAgent:
    name = "Recommendation Agent"

    def recommend(self, engagement: dict, emotions: dict) -> AgentResult:
        score = engagement.get("engagement_percentage", 0)
        dominant_low = sorted(emotions.get("distribution", {}).items(), key=lambda item: item[1], reverse=True)[:2]
        recommendations = []
        if score < get_settings().engagement_threshold:
            recommendations.extend([
                "Slow down the lesson pace and pause after difficult concepts.",
                "Add an interactive activity or quick poll in the next 5 minutes.",
                "Generate a simplified explanation with a visual analogy.",
                "Create reinforcement questions for low-confidence learners.",
            ])
        else:
            recommendations.extend([
                "Maintain the current pace and add one challenge question.",
                "Use student examples to convert engagement into participation.",
            ])
        explanation = LocalLLM().generate(f"Recommend improvements for engagement={score}, emotions={dominant_low}")
        return AgentResult(self.name, {"score": score, "dominant_emotions": dominant_low, "recommendations": recommendations, "rationale": explanation})
