from collections import defaultdict
from sqlalchemy.orm import Session
from app.agents.base import AgentResult, adk_agent
from app.models.models import EmotionLog

ADK_AGENT = adk_agent("student_engagement_agent", "Calculate attention, engagement, participation, and disengagement signals.")
POSITIVE = {"happy": 1.0, "surprise": 0.82, "neutral": 0.72, "sad": 0.35, "angry": 0.28, "fear": 0.25, "disgust": 0.2}


class StudentEngagementAgent:
    name = "Student Engagement Agent"

    def calculate(self, db: Session, session_id: int) -> AgentResult:
        logs = db.query(EmotionLog).filter(EmotionLog.session_id == session_id).order_by(EmotionLog.timestamp).all()
        if not logs:
            return AgentResult(self.name, {"engagement_percentage": 0, "attention_timeline": [], "participation": {}, "disengaged": True})
        scores = [POSITIVE.get(log.emotion, 0.55) * max(log.confidence, 0.2) for log in logs]
        engagement = round(sum(scores) / len(scores) * 100, 2)
        by_student = defaultdict(list)
        timeline = []
        for log, score in zip(logs, scores):
            by_student[log.student_id].append(score)
            timeline.append({"timestamp": log.timestamp.isoformat(), "score": round(score * 100, 2), "emotion": log.emotion})
        participation = {str(student_id): round(sum(items) / len(items) * 100, 2) for student_id, items in by_student.items()}
        return AgentResult(self.name, {
            "engagement_percentage": engagement,
            "attention_timeline": timeline,
            "participation": participation,
            "disengaged": engagement < 62,
        })
