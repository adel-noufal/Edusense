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
        attended_duration: float | int | None = None,
        scheduled_duration: int | None = None,
    ) -> dict:
        # Determine if any students have attended (have emotion logs or registrations)
        from app.models.models import EmotionLog
        from app.services.attendance_service import calculate_session_attended_duration
        has_students = db.query(SessionRegistration).filter_by(session_id=session_id).count() > 0

        if attended_duration is None:
            attended_duration = calculate_session_attended_duration(db, session_id)
        if scheduled_duration is None:
            s_obj = db.query(ClassSession).filter(ClassSession.id == session_id).first()
            if s_obj:
                scheduled_duration = s_obj.duration

        emotion_report = self.emotions.distributions(db, session_id).data
        engagement_report = self.engagement.calculate(db, session_id).data

        from app.services.report_data import assess_session_data, clamp_duration, insufficient_data_message, session_metrics
        assessment = assess_session_data(db, session_id)
        attended_duration, duration_capped = clamp_duration(attended_duration)
        metrics = session_metrics(db, session_id, assessment)
        metrics["sufficient_data"] = assessment["sufficient"]

        recommendation_report = self.recommendations.recommend(
            engagement_report, emotion_report, metrics=metrics
        ).data
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
            attended_duration=attended_duration,
            scheduled_duration=scheduled_duration,
            sufficient_data=assessment["sufficient"],
            insufficient_message=insufficient_data_message(assessment),
            duration_capped=duration_capped,
        ).data
        report["data_assessment"] = {
            "sufficient": assessment["sufficient"],
            "missing": assessment["missing"],
            "emotion_samples": assessment["emotion_samples"],
            "participants": assessment["participants"],
            "attended_minutes": assessment["attended_minutes"],
            "duration_capped": duration_capped,
        }
        return {
            "emotion_report": emotion_report,
            "engagement_report": engagement_report,
            "recommendations": recommendation_report,
            "improved_lesson": improved_lesson,
            "reinforcement_quiz": reinforcement_quiz,
            "report": report,
        }
