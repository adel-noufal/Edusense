"""
report_data.py — Deterministic session metrics + data-sufficiency assessment
for reports, recommendations, and CSV export.

All values here are computed in code from stored rows — never from the LLM —
so downstream agents only ever see verified facts.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.models import EmotionLog, SessionRegistration
from app.services.attendance_service import (
    calculate_session_attended_duration,
    calculate_student_attended_duration,
)


def clamp_duration(minutes: float | int | None) -> tuple[float, bool]:
    """
    Clamp a computed attended duration to the configured sanity cap.
    Returns (clamped_minutes, was_capped). Broken/negative values -> 0.
    """
    if minutes is None:
        return 0.0, False
    try:
        value = float(minutes)
    except (TypeError, ValueError):
        return 0.0, False
    if value < 0:
        value = 0.0
    cap = float(get_settings().report_max_attended_minutes)
    capped = value > cap
    if capped:
        value = cap
    # match attendance_service convention: int when whole, else 1-decimal float
    minutes = round(value, 1)
    return (int(minutes) if float(minutes).is_integer() else minutes), capped


def assess_session_data(db: Session, session_id: int) -> dict:
    """
    Decide whether a session has enough data for AI insights/scores.

    Sufficient = at least `report_min_participants` registered attendees AND
    `report_min_emotion_samples` emotion frames AND `report_min_attended_minutes`
    of attended time. Returns a dict describing what is present/missing.
    """
    settings = get_settings()
    participants = db.query(SessionRegistration).filter_by(session_id=session_id).count()
    samples = db.query(EmotionLog).filter_by(session_id=session_id).count()
    raw_minutes = calculate_session_attended_duration(db, session_id)
    attended, capped = clamp_duration(raw_minutes)

    checks = {
        "participants": {"value": participants, "required": settings.report_min_participants,
                         "ok": participants >= settings.report_min_participants},
        "emotion_samples": {"value": samples, "required": settings.report_min_emotion_samples,
                            "ok": samples >= settings.report_min_emotion_samples},
        "attended_minutes": {"value": attended, "required": settings.report_min_attended_minutes,
                             "ok": attended >= settings.report_min_attended_minutes},
    }
    missing = [name for name, c in checks.items() if not c["ok"]]
    return {
        "sufficient": not missing,
        "missing": missing,
        "checks": checks,
        "emotion_samples": samples,
        "participants": participants,
        "attended_minutes": attended,
        "raw_attended_minutes": raw_minutes,
        "duration_capped": capped,
        "cap_minutes": float(settings.report_max_attended_minutes),
    }


def insufficient_data_message(assessment: dict) -> str:
    """Human-readable explanation of exactly what data is missing."""
    labels = {
        "participants": "student participation records",
        "emotion_samples": "emotion samples (webcam frames)",
        "attended_minutes": "attended session time",
    }
    parts = [labels[m] for m in assessment.get("missing", [])]
    if not parts:
        return "Not enough data yet."
    return (
        "Not enough data yet — missing: " + ", ".join(parts) + ". "
        "Run a live session with students' webcams enabled to collect this data."
    )


def session_metrics(db: Session, session_id: int, assessment: dict | None = None) -> dict:
    """
    Compact, LLM-safe facts dict for recommendation grounding.
    Contains ONLY deterministic values — pass this verbatim to the model.
    """
    if assessment is None:
        assessment = assess_session_data(db, session_id)

    logs = (
        db.query(EmotionLog)
        .filter(EmotionLog.session_id == session_id)
        .order_by(EmotionLog.timestamp)
        .all()
    )
    from collections import Counter
    dist_counts = Counter(l.emotion for l in logs)
    total = max(len(logs), 1)
    distribution = {e: round(c * 100 / total, 1) for e, c in dist_counts.items()}

    # Per-student attendance rollup
    regs = db.query(SessionRegistration).filter_by(session_id=session_id).all()
    students = []
    for reg in regs:
        mins, _ = clamp_duration(calculate_student_attended_duration(db, session_id, reg.student_id))
        students.append({"student_id": reg.student_id, "attended_minutes": mins})

    return {
        "session_id": session_id,
        "emotion_samples": assessment["emotion_samples"],
        "participants": assessment["participants"],
        "attended_minutes": assessment["attended_minutes"],
        "scheduled_cap_minutes": assessment["cap_minutes"],
        "duration_capped": assessment["duration_capped"],
        "emotion_distribution_pct": distribution,
        "students": students,
        "timeline_points": len(logs),
    }
