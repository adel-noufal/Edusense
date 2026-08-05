from sqlalchemy.orm import Session
from app.agents.emotion_agent import EmotionAnalysisAgent
from app.agents.engagement_agent import StudentEngagementAgent
from app.agents.lesson_agent import LessonGenerationAgent
from app.agents.quiz_agent import QuizGenerationAgent
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.report_agent import ReportGenerationAgent
from app.models.models import Session as ClassSession, SessionRegistration, User


class EduSenseAgentWorkflow:
    def __init__(self):
        self.emotions = EmotionAnalysisAgent()
        self.engagement = StudentEngagementAgent()
        self.recommendations = RecommendationAgent()
        self.lessons = LessonGenerationAgent()
        self.quizzes = QuizGenerationAgent()
        self.reports = ReportGenerationAgent()

    def improvement_loop(
        self,
        db: Session,
        session_id: int,
        topic: str = "current lesson",
        instructor_name: str = "Instructor",
        session_title: str = "Session",
    ) -> dict:
        # Determine if any students have attended (have emotion logs or registrations)
        from app.models.models import EmotionLog
        has_students = db.query(SessionRegistration).filter_by(session_id=session_id).count() > 0

        emotion_report = self.emotions.distributions(db, session_id).data
        engagement_report = self.engagement.calculate(db, session_id).data
        recommendation_report = self.recommendations.recommend(engagement_report, emotion_report).data
        improved_lesson = self.lessons.simplify_from_recommendation(topic, recommendation_report["recommendations"]).data
        reinforcement_quiz = self.quizzes.generate(topic, "Adaptive", 6).data
        report = self.reports.build(
            session_id,
            engagement_report,
            emotion_report,
            recommendation_report,
            instructor_name=instructor_name,
            session_title=session_title,
            has_students=has_students,
        ).data
        return {
            "emotion_report": emotion_report,
            "engagement_report": engagement_report,
            "recommendations": recommendation_report,
            "improved_lesson": improved_lesson,
            "reinforcement_quiz": reinforcement_quiz,
            "report": report,
        }
