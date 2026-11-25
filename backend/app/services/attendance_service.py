from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.models import AuditLog, EmotionLog, SessionRegistration, utcnow


def calculate_student_attended_duration(db: Session, session_id: int, student_id: int) -> float:
    """
    Calculate actual attended duration in minutes for a student in a session.

    Resolution order:
    1. SessionRegistration joined_at and left_at timestamps.
    2. EmotionLog heartbeats (first and last frame captured for this student).
    3. AuditLog timestamps (actions: mark_attendance, join_live, leave_live, leave_session).

    Returns minutes as an int (if whole number) or float rounded to 1 decimal place.
    """
    spans: list[float] = []

    # 1. SessionRegistration timestamps
    reg = db.query(SessionRegistration).filter_by(session_id=session_id, student_id=student_id).first()
    if reg and getattr(reg, "joined_at", None):
        j_at = reg.joined_at
        l_at = getattr(reg, "left_at", None) or j_at
        delta = (l_at - j_at).total_seconds()
        if delta > 0:
            spans.append(delta)

    # 2. EmotionLog heartbeats (continuous frame analysis during live session)
    logs = (
        db.query(EmotionLog)
        .filter(EmotionLog.session_id == session_id, EmotionLog.student_id == student_id)
        .order_by(EmotionLog.timestamp.asc())
        .all()
    )
    if logs:
        first_ts = logs[0].timestamp
        last_ts = logs[-1].timestamp
        delta = (last_ts - first_ts).total_seconds()
        if delta > 0:
            spans.append(delta)
        elif len(logs) == 1:
            # Single heartbeat sample represents at least 60s active attendance window
            spans.append(60.0)

    # 3. AuditLog join/leave entries
    audit_joins = (
        db.query(AuditLog)
        .filter(
            AuditLog.user_id == student_id,
            AuditLog.action.in_(["mark_attendance", "join_live", "join_session"]),
        )
        .order_by(AuditLog.created_at.asc())
        .all()
    )
    matching_joins = []
    for a in audit_joins:
        if str(a.resource_id) == str(session_id) or (a.details_json and f'"session_id": {session_id}' in a.details_json):
            matching_joins.append(a.created_at)

    audit_leaves = (
        db.query(AuditLog)
        .filter(
            AuditLog.user_id == student_id,
            AuditLog.action.in_(["leave_live", "leave_session"]),
        )
        .order_by(AuditLog.created_at.asc())
        .all()
    )
    matching_leaves = []
    for a in audit_leaves:
        if str(a.resource_id) == str(session_id) or (a.details_json and f'"session_id": {session_id}' in a.details_json):
            matching_leaves.append(a.created_at)

    if matching_joins:
        earliest_join = matching_joins[0]
        latest_leave = matching_leaves[-1] if matching_leaves else None
        if latest_leave and latest_leave > earliest_join:
            spans.append((latest_leave - earliest_join).total_seconds())
        elif logs and logs[-1].timestamp > earliest_join:
            spans.append((logs[-1].timestamp - earliest_join).total_seconds())

    if not spans:
        if not reg or not reg.attended:
            return 0
        return 0

    max_seconds = max(spans)
    minutes = round(max_seconds / 60.0, 1)
    return int(minutes) if minutes.is_integer() else minutes


def calculate_session_attended_duration(db: Session, session_id: int) -> float:
    """
    Calculate actual attended duration of the session in minutes across all attendees.
    Uses:
    1. Total span of EmotionLog heartbeats across all students.
    2. Maximum individual attended duration among registered attendees.
    """
    spans: list[float] = []

    logs = (
        db.query(EmotionLog)
        .filter(EmotionLog.session_id == session_id)
        .order_by(EmotionLog.timestamp.asc())
        .all()
    )
    if logs:
        first_ts = logs[0].timestamp
        last_ts = logs[-1].timestamp
        delta = (last_ts - first_ts).total_seconds()
        if delta > 0:
            spans.append(delta)
        elif len(logs) == 1:
            spans.append(60.0)

    attendees = db.query(SessionRegistration).filter_by(session_id=session_id).all()
    for att in attendees:
        dur_mins = calculate_student_attended_duration(db, session_id, att.student_id)
        if dur_mins > 0:
            spans.append(dur_mins * 60.0)

    if not spans:
        return 0

    max_seconds = max(spans)
    minutes = round(max_seconds / 60.0, 1)
    return int(minutes) if minutes.is_integer() else minutes
