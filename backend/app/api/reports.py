import csv
import io
import json
from collections import Counter
from fastapi import Request
from fastapi.responses import Response

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.agents.emotion_agent import EmotionAnalysisAgent
from app.agents.engagement_agent import StudentEngagementAgent
from app.agents.workflow import EduSenseAgentWorkflow
from app.api.deps import get_current_user, require_role
from app.core.audit import log_audit_event, log_report_access, log_student_data_access, log_session_access
from app.db.session import get_db
from app.models.models import EmotionLog, Feedback, Profile, Quiz, Report, Session as ClassSession, SessionRegistration, User
from app.services.attendance_service import calculate_session_attended_duration, calculate_student_attended_duration
from app.services.report_data import clamp_duration
from app.services.session_archive import visible_sessions
from app.services.timefmt import iso_z
from app.schemas.schemas import FeedbackIn

router = APIRouter(tags=["Reports and Feedback"])
workflow = EduSenseAgentWorkflow()
engagement_agent = StudentEngagementAgent()
emotion_agent = EmotionAnalysisAgent()


def _session_report_payload(db: Session, item: ClassSession) -> dict:
    from app.services.report_data import assess_session_data, clamp_duration, insufficient_data_message
    attendees = db.query(SessionRegistration).filter_by(session_id=item.id).all()
    quizzes = db.query(Quiz).filter_by(session_id=item.id).all()
    emotion_logs = db.query(EmotionLog).filter_by(session_id=item.id).order_by(EmotionLog.timestamp).all()
    emotion_counts = Counter(log.emotion for log in emotion_logs)
    dominant_emotions = [name for name, _ in emotion_counts.most_common(3)]
    engagement = engagement_agent.calculate(db, item.id).data
    distribution = emotion_agent.distributions(db, item.id).data
    stored_reports = db.query(Report).filter_by(session_id=item.id).order_by(Report.generated_at.desc()).all()
    has_students = len(attendees) > 0
    raw_attended = calculate_session_attended_duration(db, item.id)
    actual_attended_duration, duration_capped = clamp_duration(raw_attended)
    assessment = assess_session_data(db, item.id)
    return {
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "date": item.date,
        "start_time": item.start_time,
        "duration": actual_attended_duration,
        "attended_duration": actual_attended_duration,
        "scheduled_duration": item.duration,
        "duration_capped": duration_capped,
        "status": item.status,
        "attendee_count": len(attendees),
        "has_students": has_students,
        "no_students_message": None if has_students else "No student attended yet.",
        "sufficient_data": assessment["sufficient"],
        "insufficient_data_message": None if assessment["sufficient"] else insufficient_data_message(assessment),
        "data_assessment": {
            "sufficient": assessment["sufficient"],
            "missing": assessment["missing"],
            "emotion_samples": assessment["emotion_samples"],
            "participants": assessment["participants"],
            "attended_minutes": assessment["attended_minutes"],
        },
        "emotion_samples": len(emotion_logs),
        "quiz_count": len(quizzes),
        "engagement_percentage": engagement.get("engagement_percentage") if assessment["sufficient"] else None,
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
    reg = db.query(SessionRegistration).filter_by(session_id=item.id, student_id=student.id).first()
    student_attended_duration = calculate_student_attended_duration(db, item.id, student.id)
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
            "registered": reg is not None,
            "attended": getattr(reg, "attended", False) if reg else False,
            "duration": student_attended_duration,
            "attended_duration": student_attended_duration,
            "emotion_samples": len(logs),
            "dominant_emotion": dominant_emotion,
            "average_confidence": average_confidence,
        },
        "analysis": {
            "summary": (
                f"{student.name} attended for {student_attended_duration} min with {len(logs)} emotion samples in this session. "
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
            "notes": [{"id": n.id, "note": n.note, "created_at": iso_z(n.created_at)} for n in notes],
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
def list_reports(request: Request, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    # Audit: instructor listing all reports
    log_audit_event(db, action="list_reports", user=user, resource_type="report", request=request)
    return db.query(Report).order_by(Report.generated_at.desc()).all()


@router.post("/reports/{session_id}")
def create_report(session_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
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

    # Audit: instructor generating report
    log_session_access(db, user, session_id, action="generate_report", request=request, details={"report_id": report.id})

    return loop


@router.get("/reports/sessions")
def report_sessions(request: Request, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    sessions = (
        visible_sessions(db, ClassSession)
        .filter(
            ClassSession.instructor_id == user.id,
            ClassSession.status == "ended",  # Only show completed sessions in Reports
        )
        .order_by(ClassSession.date.desc(), ClassSession.start_time.desc())
        .all()
    )

    # Audit: instructor listing their session reports
    log_audit_event(db, action="list_session_reports", user=user, resource_type="session", request=request)

    return [_session_report_payload(db, item) for item in sessions]


@router.get("/reports/sessions/{session_id}")
def report_session_detail(session_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    item = db.query(ClassSession).filter_by(id=session_id, instructor_id=user.id).first()
    if not item:
        raise HTTPException(404, "Session not found")

    # Audit: instructor accessing session report with student data
    log_session_access(db, user, session_id, action="read_session_report", request=request)

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
                "duration": details["attendance"]["duration"],
                "attended_duration": details["attendance"]["attended_duration"],
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


# ─── CSV Export ───────────────────────────────────────────────────────────────

_CSV_HEADERS = {
    "en": {
        "section": "Section", "field": "Field", "value": "Value",
        "student": "Student", "email": "Email", "attended_min": "Attended (min)",
        "samples": "Emotion Samples", "dominant": "Dominant Emotion",
        "minute": "Minute", "emotion": "Emotion", "count": "Count", "pct": "Pct %",
    },
    "ar": {
        "section": "القسم", "field": "الحقل", "value": "القيمة",
        "student": "الطالب", "email": "البريد الإلكتروني", "attended_min": "الحضور (دقيقة)",
        "samples": "عينات المشاعر", "dominant": "المشاعر السائدة",
        "minute": "الدقيقة", "emotion": "المشاعر", "count": "العدد", "pct": "النسبة %",
    },
}


def _csv_session_report(db: Session, item: ClassSession, lang: str = "en") -> str:
    """Build a UTF-8-BOM CSV: session summary + per-student attendance +
    emotion distribution + per-minute emotion buckets (downsampled timeline)."""
    h = _CSV_HEADERS.get(lang, _CSV_HEADERS["en"])
    out = io.StringIO()
    writer = csv.writer(out)

    payload = _session_report_payload(db, item)
    assessment = payload["data_assessment"]

    writer.writerow([h["section"], h["field"], h["value"]])
    summary_rows = [
        ("Session", "title", item.title),
        ("Session", "date", str(item.date)),
        ("Session", "status", item.status),
        ("Session", "scheduled_duration_min", item.duration if item.duration is not None else "No limit"),
        ("Session", "attended_duration_min", payload["attended_duration"]),
        ("Session", "duration_capped", payload["duration_capped"]),
        ("Session", "participants", assessment["participants"]),
        ("Session", "emotion_samples", assessment["emotion_samples"]),
        ("Session", "sufficient_data", assessment["sufficient"]),
        ("Session", "engagement_pct", payload["engagement_percentage"] if payload["engagement_percentage"] is not None else "N/A"),
    ]
    if payload["insufficient_data_message"]:
        summary_rows.append(("Session", "insufficient_data", payload["insufficient_data_message"]))
    writer.writerows(summary_rows)
    writer.writerow([])

    # Per-student attendance
    writer.writerow([h["section"], h["student"], h["email"], h["attended_min"], h["samples"], h["dominant"]])
    regs = db.query(SessionRegistration).filter_by(session_id=item.id).all()
    student_ids = [r.student_id for r in regs]
    users = {u.id: u for u in db.query(User).filter(User.id.in_(student_ids)).all()} if student_ids else {}
    for reg in regs:
        u = users.get(reg.student_id)
        logs = db.query(EmotionLog).filter_by(session_id=item.id, student_id=reg.student_id).all()
        counts = Counter(l.emotion for l in logs)
        dominant = counts.most_common(1)[0][0] if counts else ""
        from app.services.attendance_service import calculate_student_attended_duration
        mins, _ = clamp_duration(calculate_student_attended_duration(db, item.id, reg.student_id))
        writer.writerow([
            "Student",
            u.name if u else f"student-{reg.student_id}",
            u.email if u else "",
            mins,
            len(logs),
            dominant,
        ])
    writer.writerow([])

    # Emotion distribution
    writer.writerow([h["section"], h["emotion"], h["count"], h["pct"]])
    dist = payload["emotion_distribution"]
    for emo in ("happy", "neutral", "sad", "angry", "surprise", "fear", "disgust"):
        writer.writerow(["Emotion Distribution", emo, dist.get(emo, 0.0)])
    writer.writerow([])

    # Per-minute emotion buckets (aggregated timeline — safe for long sessions)
    logs = db.query(EmotionLog).filter_by(session_id=item.id).order_by(EmotionLog.timestamp).all()
    if logs:
        writer.writerow([h["section"], h["minute"], h["emotion"], h["count"], h["pct"]])
        base = logs[0].timestamp
        buckets: dict[int, Counter] = {}
        for log in logs:
            minute_idx = int((log.timestamp - base).total_seconds() // 60)
            buckets.setdefault(minute_idx, Counter())[log.emotion] += 1
        for minute_idx in sorted(buckets):
            counts = buckets[minute_idx]
            total = sum(counts.values())
            for emo, cnt in counts.most_common():
                writer.writerow(["Emotion Timeline", minute_idx, emo, cnt, round(cnt * 100 / total, 1)])

    # UTF-8 BOM so Excel opens Arabic text correctly
    return "﻿" + out.getvalue()


@router.get("/reports/sessions/{session_id}/export.csv")
def export_session_csv(
    session_id: int,
    lang: str = "en",
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor")),
):
    item = db.query(ClassSession).filter_by(id=session_id, instructor_id=user.id).first()
    if not item:
        raise HTTPException(404, "Session not found")
    csv_text = _csv_session_report(db, item, lang=lang if lang in ("en", "ar") else "en")
    filename = f"session-{session_id}-report.csv"
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/sessions/{session_id}/export.pdf")
def export_session_pdf(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor")),
):
    from fastapi.responses import StreamingResponse
    item = db.query(ClassSession).filter_by(id=session_id, instructor_id=user.id).first()
    if not item:
        raise HTTPException(404, "Session not found")
    payload = _session_report_payload(db, item)
    assessment = payload["data_assessment"]
    from app.services.export import _pdf_doc
    blocks = [
        ("Session Summary", [
            f"Title: {item.title}",
            f"Date: {item.date}",
            f"Status: {item.status}",
            f"Attended Duration: {payload['attended_duration']} min",
            f"Participants: {assessment['participants']}",
            f"Emotion Samples: {assessment['emotion_samples']}",
            f"Engagement Score: {payload['engagement_percentage']}%" if payload['engagement_percentage'] is not None else "Engagement: N/A",
        ]),
        ("Emotion Distribution", [
            f"{emo.capitalize()}: {payload['emotion_distribution'].get(emo, 0.0)}%"
            for emo in ("happy", "neutral", "sad", "angry", "surprise", "fear", "disgust")
        ])
    ]
    if payload.get("ai_summary"):
        blocks.append(("AI Teaching Recommendations", [payload["ai_summary"]]))
    buf = _pdf_doc(f"Session Report — {item.title}", blocks)
    filename = f"session-{session_id}-report.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/sessions/{session_id}/students/{student_id}")
def report_student_detail(
    session_id: int,
    student_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor")),
):
    item = db.query(ClassSession).filter_by(id=session_id, instructor_id=user.id).first()
    if not item:
        raise HTTPException(404, "Session not found")
    student = db.query(User).filter_by(id=student_id, role="student").first()
    if not student:
        raise HTTPException(404, "Student not found")

    # Audit: instructor accessing individual student report
    log_student_data_access(db, user, student_id, action="read_student_report", request=request, details={"session_id": session_id})

    return _student_report_payload(db, item, student)


@router.post("/feedback")
def create_feedback(payload: FeedbackIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    feedback = Feedback(user_id=user.id, message=payload.message)
    db.add(feedback)
    db.commit()
    return {"message": "Feedback received"}
