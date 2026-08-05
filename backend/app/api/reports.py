import json
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.agents.emotion_agent import EmotionAnalysisAgent
from app.agents.engagement_agent import StudentEngagementAgent
from app.agents.workflow import EduSenseAgentWorkflow
from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.models import EmotionLog, Feedback, Profile, Quiz, Report, Session as ClassSession, SessionRegistration, User
from app.schemas.schemas import FeedbackIn

router = APIRouter(tags=["Reports and Feedback"])
workflow = EduSenseAgentWorkflow()
engagement_agent = StudentEngagementAgent()
emotion_agent = EmotionAnalysisAgent()


def _session_report_payload(db: Session, item: ClassSession) -> dict:
    attendees = db.query(SessionRegistration).filter_by(session_id=item.id).all()
    quizzes = db.query(Quiz).filter_by(session_id=item.id).all()
    emotion_logs = db.query(EmotionLog).filter_by(session_id=item.id).order_by(EmotionLog.timestamp).all()
    emotion_counts = Counter(log.emotion for log in emotion_logs)
    dominant_emotions = [name for name, _ in emotion_counts.most_common(3)]
    engagement = engagement_agent.calculate(db, item.id).data
    distribution = emotion_agent.distributions(db, item.id).data
    stored_reports = db.query(Report).filter_by(session_id=item.id).order_by(Report.generated_at.desc()).all()
    has_students = len(attendees) > 0
    return {
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "date": item.date,
        "start_time": item.start_time,
        "duration": item.duration,
        "status": item.status,
        "attendee_count": len(attendees),
        "has_students": has_students,
        "no_students_message": None if has_students else "No student attended yet.",
        "emotion_samples": len(emotion_logs),
        "quiz_count": len(quizzes),
        "engagement_percentage": engagement.get("engagement_percentage", 0),
        "dominant_emotions": dominant_emotions,
        "emotion_distribution": distribution.get("distribution", {}),
        "reports": [
            {
                "id": report.id,
                "summary": report.summary,
                "generated_at": report.generated_at,
                "pdf_path": report.pdf_path,
            }
            for report in stored_reports
        ],
    }


def _student_report_payload(db: Session, item: ClassSession, student: User) -> dict:
    profile = db.query(Profile).filter(Profile.user_id == student.id).first()
    logs = (
        db.query(EmotionLog)
        .filter(EmotionLog.session_id == item.id, EmotionLog.student_id == student.id)
        .order_by(EmotionLog.timestamp)
        .all()
    )
    emotion_counts = Counter(log.emotion for log in logs)
    dominant_emotion = emotion_counts.most_common(1)[0][0] if emotion_counts else "neutral"
    average_confidence = round(sum(log.confidence for log in logs) / len(logs), 3) if logs else 0
    quizzes = db.query(Quiz).filter_by(session_id=item.id).order_by(Quiz.created_at.desc()).all()
    from app.models.models import SessionNote
    notes = db.query(SessionNote).filter_by(session_id=item.id, student_id=student.id).all()
    return {
        "student": {
            "id": student.id,
            "name": student.name,
            "email": student.email,
            "avatar": getattr(profile, "avatar", None),
            "phone": getattr(profile, "phone", None),
            "university": getattr(profile, "university", None),
            "department": getattr(profile, "department", None),
        },
        "attendance": {
            "registered": db.query(SessionRegistration).filter_by(session_id=item.id, student_id=student.id).first() is not None,
            "emotion_samples": len(logs),
            "dominant_emotion": dominant_emotion,
            "average_confidence": average_confidence,
        },
        "analysis": {
            "summary": (
                f"{student.name} has {len(logs)} emotion samples in this session. "
                f"Dominant emotion: {dominant_emotion}. "
                f"Average confidence: {round(average_confidence * 100, 1)}%."
            ),
            "reactions": [{"emotion": name, "count": count} for name, count in emotion_counts.most_common()],
            "timeline": [
                {
                    "emotion": log.emotion,
                    "confidence": log.confidence,
                    "timestamp": log.timestamp,
                }
                for log in logs
            ],
            "notes": [{"id": n.id, "note": n.note, "created_at": n.created_at.isoformat()} for n in notes],
        },
        "quizzes": [
            {
                "id": quiz.id,
                "title": quiz.title,
                "difficulty": quiz.difficulty,
                "created_at": quiz.created_at,
                "question_count": len(json.loads(quiz.questions_json)),
            }
            for quiz in quizzes
        ],
    }


@router.get("/reports")
def list_reports(db: Session = Depends(get_db), _: User = Depends(require_role("instructor"))):
    return db.query(Report).order_by(Report.generated_at.desc()).all()


@router.post("/reports/{session_id}")
def create_report(session_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    # Fetch session to get title for personalised report
    session_obj = db.query(ClassSession).filter_by(id=session_id, instructor_id=user.id).first()
    if not session_obj:
        raise HTTPException(404, "Session not found")
    loop = workflow.improvement_loop(
        db,
        session_id,
        topic=session_obj.title,
        instructor_name=user.name,
        session_title=session_obj.title,
    )
    report = Report(session_id=session_id, summary=loop["report"]["summary"], pdf_path=loop["report"]["pdf_path"])
    db.add(report)
    db.commit()
    loop["report"]["id"] = report.id
    return loop


@router.get("/reports/sessions")
def report_sessions(db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    sessions = (
        db.query(ClassSession)
        .filter(ClassSession.instructor_id == user.id)
        .order_by(ClassSession.date.desc(), ClassSession.start_time.desc())
        .all()
    )
    return [_session_report_payload(db, item) for item in sessions]


@router.get("/reports/sessions/{session_id}")
def report_session_detail(session_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    item = db.query(ClassSession).filter_by(id=session_id, instructor_id=user.id).first()
    if not item:
        raise HTTPException(404, "Session not found")

    attendee_rows = (
        db.query(User)
        .join(SessionRegistration, SessionRegistration.student_id == User.id)
        .filter(SessionRegistration.session_id == item.id)
        .order_by(User.name)
        .all()
    )
    has_students = len(attendee_rows) > 0
    attendees = []
    for student in attendee_rows:
        details = _student_report_payload(db, item, student)
        attendees.append(
            {
                "id": student.id,
                "name": student.name,
                "email": student.email,
                "avatar": details["student"]["avatar"],
                "emotion_samples": details["attendance"]["emotion_samples"],
                "dominant_emotion": details["attendance"]["dominant_emotion"],
                "average_confidence": details["attendance"]["average_confidence"],
            }
        )

    return {
        "session": _session_report_payload(db, item),
        "has_students": has_students,
        "no_students_message": None if has_students else "No student attended yet.",
        "attendees": attendees,
        "quizzes": [
            {
                "id": quiz.id,
                "title": quiz.title,
                "difficulty": quiz.difficulty,
                "created_at": quiz.created_at,
                "question_count": len(json.loads(quiz.questions_json)),
            }
            for quiz in db.query(Quiz).filter_by(session_id=item.id).order_by(Quiz.created_at.desc()).all()
        ],
        "database_links": [
            {"table": "sessions", "filter": f"id = {item.id}"},
            {"table": "session_registrations", "filter": f"session_id = {item.id}"},
            {"table": "emotion_logs", "filter": f"session_id = {item.id}"},
            {"table": "quizzes", "filter": f"session_id = {item.id}"},
            {"table": "reports", "filter": f"session_id = {item.id}"},
        ],
    }


@router.get("/reports/sessions/{session_id}/students/{student_id}")
def report_student_detail(
    session_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor")),
):
    item = db.query(ClassSession).filter_by(id=session_id, instructor_id=user.id).first()
    if not item:
        raise HTTPException(404, "Session not found")
    student = db.query(User).filter_by(id=student_id, role="student").first()
    if not student:
        raise HTTPException(404, "Student not found")
    return _student_report_payload(db, item, student)


@router.post("/feedback")
def create_feedback(payload: FeedbackIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    feedback = Feedback(user_id=user.id, message=payload.message)
    db.add(feedback)
    db.commit()
    return {"message": "Feedback received"}
