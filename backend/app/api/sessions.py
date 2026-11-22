from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session as DbSession
from pydantic import BaseModel
from typing import Optional
import asyncio
import base64
import uuid
from pathlib import Path
from collections import Counter
from app.api.deps import get_current_user, require_role
from app.core.audit import log_audit_event, log_session_access, log_student_data_access, log_admin_action
from app.db.session import get_db
from app.models.models import (
    AIGeneration,
    EmotionLog,
    Quiz,
    Report,
    Session,
    SessionRegistration,
    SessionResource,
    User,
    SessionNote,
)
from app.schemas.schemas import SessionIn, SessionOut, NoteCreate
from app.services.status import session_status, effective_status
from app.services.email import _send_email_sync, send_session_live_email
from app.core.config import get_settings
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["Sessions"])
SHARE_DIR = Path(__file__).resolve().parents[1] / "static" / "live"
RESOURCE_DIR = Path(__file__).resolve().parents[1] / "static" / "resources"


class ShareFrameIn(BaseModel):
    image: str


from datetime import datetime, timezone, timedelta

def refresh_status(item: Session, db: DbSession):
    # Persist effective-status transitions so stale rows self-heal on read.
    from app.services.status import effective_status
    eff = effective_status(item)
    if eff == "ended" and item.status not in ("ended", "completed", "finished"):
        item.status = "ended"
        db.add(item)
        return
    if eff == "missed" and item.status != "missed":
        item.status = "missed"
        db.add(item)
        return
    if item.status in ("ended", "ongoing", "missed", "cancelled", "canceled"):
        return
    # If in 15-minute preparation mode, check if 15 minutes passed
    if item.status == "preparing" and item.prep_start_time:
        prep_dt = item.prep_start_time
        if prep_dt.tzinfo is None:
            prep_dt = prep_dt.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= prep_dt + timedelta(minutes=15):
            item.status = "ongoing"
            db.add(item)
            return
    # Sessions only move to ongoing when explicitly started by instructor via POST /{id}/start
    pass


def reconcile_session_statuses(db: DbSession) -> int:
    """Startup/periodic sweep: persist effective status for every session.
    Returns the number of rows transitioned."""
    from app.services.status import effective_status
    changed = 0
    sessions = db.query(Session).all()
    for item in sessions:
        before = item.status
        refresh_status(item, db)
        if item.status != before:
            changed += 1
    if changed:
        db.commit()
    return changed


def serialize_browse_session(item: Session, user: User, registrations: list[SessionRegistration], db: DbSession = None) -> dict:
    related = [registration for registration in registrations if registration.session_id == item.id]
    attendee_ids = {registration.student_id for registration in related}
    seats_left = max(item.max_students - len(attendee_ids), 0) if item.max_students is not None else None
    is_registered = user.id in attendee_ids
    instructor_name = None
    if db:
        inst = db.query(User).filter(User.id == item.instructor_id).first()
        if inst:
            instructor_name = inst.name
    return {
        "id": item.id,
        "instructor_id": item.instructor_id,
        "instructor_name": instructor_name,
        "title": item.title,
        "description": item.description,
        "date": item.date,
        "start_time": item.start_time,
        "duration": item.duration,
        "max_students": item.max_students,
        "status": item.status,
        "effective_status": effective_status(item),
        "prep_start_time": item.prep_start_time.isoformat() if item.prep_start_time else None,
        "registration_count": len(attendee_ids),
        "available_seats": seats_left,
        "is_registered": is_registered,
        "can_register": effective_status(item) in {"upcoming", "live"} and (is_registered or seats_left is None or seats_left > 0),
    }


def _get_session_linked_content(session_id: int, db: DbSession) -> list[dict]:
    linked = []
    gens = db.query(AIGeneration).filter_by(session_id=session_id).order_by(AIGeneration.created_at.desc()).all()
    for g in gens:
        if g.type == "quiz":
            continue  # quizzes are listed from the quizzes table below
        linked.append({
            "id": g.id,
            "content_id": g.id,
            "type": g.type,
            "topic": g.topic,
            "created_at": g.created_at.isoformat() if g.created_at else None,
        })
    quizzes = db.query(Quiz).filter_by(session_id=session_id).order_by(Quiz.created_at.desc()).all()
    for q in quizzes:
        linked.append({
            "id": q.id,
            "content_id": q.id,
            "type": "quiz",
            "topic": q.title,
            "created_at": q.created_at.isoformat() if q.created_at else None,
        })
    return linked


@router.get("", response_model=list[SessionOut])
def list_sessions(request: Request, db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Session)
    if user.role == "instructor":
        query = query.filter(Session.instructor_id == user.id)
    sessions = query.order_by(Session.date, Session.start_time).all()
    out = []
    for item in sessions:
        refresh_status(item, db)
        out_item = SessionOut.model_validate(item)
        out_item.effective_status = effective_status(item)
        inst = db.query(User).filter(User.id == item.instructor_id).first()
        if inst:
            out_item.instructor_name = inst.name
        out_item.linked_content = _get_session_linked_content(item.id, db)
        out.append(out_item)
    db.commit()

    # Audit: user listing sessions
    log_audit_event(db, action="list_sessions", user=user, resource_type="session", request=request)

    return out


@router.get("/browse")
def browse_sessions(request: Request, db: DbSession = Depends(get_db), user: User = Depends(require_role("student"))):
    sessions = db.query(Session).order_by(Session.date, Session.start_time).all()
    for item in sessions:
        refresh_status(item, db)
    db.commit()
    # Effective status decides visibility — a stale 'pending' row whose start
    # passed days ago must not appear in the browse catalog.
    eff_map = {item.id: effective_status(item) for item in sessions}
    statuses = Counter(eff_map.values())
    registrations = db.query(SessionRegistration).all()
    catalog = [
        serialize_browse_session(item, user, registrations, db)
        for item in sessions
        if eff_map[item.id] in {"upcoming", "live"}
    ]

    # Audit: student browsing available sessions
    log_audit_event(db, action="browse_sessions", user=user, resource_type="session", request=request)

    return {
        "sessions": catalog,
        "summary": {
            "available": len(catalog),
            "registered": sum(1 for item in catalog if item["is_registered"]),
            "live_now": statuses.get("live", 0),
        },
    }


@router.post("", response_model=SessionOut)
def create_session(payload: SessionIn, request: Request, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    # Idempotent create: identical session (same instructor/title/date/start)
    # already exists -> return it instead of inserting a duplicate.
    existing = db.query(Session).filter(
        Session.instructor_id == user.id,
        Session.title == payload.title,
        Session.date == payload.date,
        Session.start_time == payload.start_time,
    ).first()
    if existing:
        refresh_status(existing, db)
        db.commit()
        res = SessionOut.model_validate(existing)
        res.instructor_name = user.name
        res.linked_content = _get_session_linked_content(existing.id, db)
        return res

    item = Session(**payload.model_dump(), instructor_id=user.id)
    refresh_status(item, db)
    db.add(item)
    db.commit()
    db.refresh(item)
    res = SessionOut.model_validate(item)
    res.instructor_name = user.name
    res.linked_content = _get_session_linked_content(item.id, db)

    # Audit: instructor creating session
    log_session_access(db, user, item.id, action="create_session", request=request)

    return res


@router.put("/{session_id}", response_model=SessionOut)
def update_session(session_id: int, payload: SessionIn, request: Request, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    query = db.query(Session).filter(Session.id == session_id)
    if user.role != "admin":
        query = query.filter(Session.instructor_id == user.id)
    item = query.first()
    if not item:
        raise HTTPException(404, "Session not found")
    eff = effective_status(item)
    if eff in ("ended", "missed") or item.status in ("ended", "completed", "finished", "missed"):
        raise HTTPException(status_code=403, detail="Cannot edit a session that has already ended or expired.")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    refresh_status(item, db)
    db.commit()
    db.refresh(item)
    res = SessionOut.model_validate(item)
    inst = db.query(User).filter(User.id == item.instructor_id).first()
    if inst:
        res.instructor_name = inst.name
    res.linked_content = _get_session_linked_content(item.id, db)

    # Audit: instructor updating session
    log_session_access(db, user, session_id, action="update_session", request=request)

    return res


def _delete_session_dependencies(db: DbSession, session_id: int) -> None:
    """Remove rows that reference this session so the session row can be deleted."""
    db.query(EmotionLog).filter_by(session_id=session_id).delete()
    db.query(SessionRegistration).filter_by(session_id=session_id).delete()
    db.query(SessionNote).filter_by(session_id=session_id).delete()
    for resource in db.query(SessionResource).filter_by(session_id=session_id).all():
        try:
            Path(resource.file_path).unlink(missing_ok=True)
        except Exception:
            pass
    db.query(SessionResource).filter_by(session_id=session_id).delete()
    db.query(Report).filter_by(session_id=session_id).delete()
    db.query(Quiz).filter_by(session_id=session_id).delete()
    db.query(AIGeneration).filter_by(session_id=session_id).update({AIGeneration.session_id: None})
    share_frame = SHARE_DIR / f"session-{session_id}.jpg"
    share_frame.unlink(missing_ok=True)


@router.delete("/{session_id}")
def delete_session(session_id: int, request: Request, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    query = db.query(Session).filter(Session.id == session_id)
    if user.role != "admin":
        query = query.filter(Session.instructor_id == user.id)
    item = query.first()
    if not item:
        raise HTTPException(404, "Session not found")
    _delete_session_dependencies(db, session_id)
    db.delete(item)
    db.commit()

    # Audit: instructor deleting session
    log_session_access(db, user, session_id, action="delete_session", request=request)

    return {"message": "Session deleted"}


@router.post("/{session_id}/join")
def join_session(session_id: int, request: Request, background_tasks: BackgroundTasks, db: DbSession = Depends(get_db), user: User = Depends(require_role("student"))):
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    refresh_status(session, db)
    if session.status not in {"upcoming", "scheduled", "live", "ongoing", "pending", "preparing"}:
        raise HTTPException(400, "This session is no longer open for registration")
    reg = db.query(SessionRegistration).filter_by(session_id=session_id, student_id=user.id).first()
    if not reg:
        if session.max_students is not None:
            seats_taken = db.query(SessionRegistration).filter_by(session_id=session_id).count()
            if seats_taken >= session.max_students:
                raise HTTPException(400, "This session is already full")
        db.add(SessionRegistration(session_id=session_id, student_id=user.id))
        db.commit()
        # Notify the instructor by email when a student joins a pending/upcoming session
        if session.status in {"pending", "upcoming", "scheduled", "preparing"}:
            instructor = db.query(User).filter(User.id == session.instructor_id).first()
            if instructor and instructor.email:
                subject = f"New Student Enrolled: '{session.title}'"
                html_body = f"""
                <html><body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
                  <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
                    <h2 style="color: #0ea5e9;">EduSense AI Platform</h2>
                    <p>Hello <strong>{instructor.name}</strong>,</p>
                    <p>A new student has just enrolled in your session:</p>
                    <div style="background:#f8fafc; border-left:4px solid #0ea5e9; padding:12px 16px; border-radius:6px; margin:16px 0;">
                      <p style="margin:0;"><strong>Session:</strong> {session.title}</p>
                      <p style="margin:0;"><strong>Date:</strong> {session.date} at {session.start_time}</p>
                      <p style="margin:0;"><strong>Student:</strong> {user.name} ({user.email})</p>
                    </div>
                    <p>Log in to EduSense to view your session roster.</p>
                    <hr style="border:none;border-top:1px solid #eee;margin-top:30px;" />
                    <p style="font-size:0.8em;color:#999;text-align:center;">EduSense AI Platform &mdash; Automated Notification</p>
                  </div>
                </body></html>
                """
                background_tasks.add_task(_send_email_sync, instructor.email, subject, html_body)

    # Audit: student joining session
    log_session_access(db, user, session_id, action="join_session", request=request)

    return {"message": "Joined session"}


@router.delete("/{session_id}/join")
def leave_session(session_id: int, request: Request, db: DbSession = Depends(get_db), user: User = Depends(require_role("student"))):
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    reg = db.query(SessionRegistration).filter_by(session_id=session_id, student_id=user.id).first()
    if not reg:
        raise HTTPException(400, "You are not registered for this session")
    if session.status == "ongoing":
        raise HTTPException(400, "Cannot leave a session that is currently ongoing")
    db.delete(reg)
    db.commit()

    # Audit: student leaving session
    log_session_access(db, user, session_id, action="leave_session", request=request)

    return {"message": "Registration cancelled"}


@router.post("/{session_id}/join-live")
def mark_attendance(session_id: int, request: Request, db: DbSession = Depends(get_db), user: User = Depends(require_role("student"))):
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    reg = db.query(SessionRegistration).filter_by(session_id=session_id, student_id=user.id).first()
    if not reg:
        raise HTTPException(403, "You are not enrolled in this session")
    if session.status != "ongoing":
        raise HTTPException(400, "This session hasn't started yet. You can only join once the instructor starts it.")
    now_ts = datetime.now(timezone.utc)
    reg.attended = True
    if not getattr(reg, "joined_at", None):
        reg.joined_at = now_ts
    reg.left_at = now_ts
    db.commit()

    # Audit: student marking attendance
    log_session_access(db, user, session_id, action="mark_attendance", request=request)

    return {"message": "Attendance marked"}


@router.post("/{session_id}/leave-live")
def leave_live(session_id: int, request: Request, db: DbSession = Depends(get_db), user: User = Depends(require_role("student"))):
    reg = db.query(SessionRegistration).filter_by(session_id=session_id, student_id=user.id).first()
    if reg:
        reg.left_at = datetime.now(timezone.utc)
        db.commit()
    log_session_access(db, user, session_id, action="leave_live", request=request)
    return {"message": "Left live session"}


@router.post("/{session_id}/start")
def start_session(session_id: int, request: Request, background_tasks: BackgroundTasks, force_go_live: bool = False, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    query = db.query(Session).filter(Session.id == session_id)
    if user.role != "admin":
        query = query.filter(Session.instructor_id == user.id)
    item = query.first()
    if not item:
        raise HTTPException(404, "Session not found")
    eff = effective_status(item)
    if eff in ("ended", "missed") or item.status in ("ended", "completed", "finished", "missed"):
        raise HTTPException(status_code=403, detail="Cannot start a session that has already ended or expired.")

    action = "start_session_live" if (force_go_live or item.status == "preparing") else "start_session_preparing"

    if force_go_live or item.status == "preparing":
        item.status = "ongoing"
        db.commit()

        # Section 1.6: Send direct join link email to all enrolled students
        regs = db.query(SessionRegistration).filter_by(session_id=session_id).all()
        student_ids = [r.student_id for r in regs]
        students = db.query(User).filter(User.id.in_(student_ids)).all() if student_ids else []
        settings = get_settings()
        join_link = f"{settings.frontend_url}/student/sessions/{item.id}/live"
        for st in students:
            if st.email:
                background_tasks.add_task(send_session_live_email, st.email, st.name, item.title, user.name, join_link)
    else:
        # Start 15-minute prep mode automatically if started before time
        item.status = "preparing"
        item.prep_start_time = datetime.now(timezone.utc)
        db.commit()

        # Send notifications to registered students
        regs = db.query(SessionRegistration).filter_by(session_id=session_id).all()
        student_ids = [r.student_id for r in regs]
        students = db.query(User).filter(User.id.in_(student_ids)).all() if student_ids else []

        for st in students:
            if st.email:
                subject = f"Preparation Started: '{item.title}' is starting in 15 minutes!"
                html_body = f"""
                <html><body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
                  <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
                    <h2 style="color: #0ea5e9;">EduSense Session Notification</h2>
                    <p>Hello <strong>{st.name}</strong>,</p>
                    <p>The instructor <strong>{user.name}</strong> has started the 15-minute preparation window for your enrolled session:</p>
                    <div style="background:#f0fdf4; border-left:4px solid #10b981; padding:12px 16px; border-radius:6px; margin:16px 0;">
                      <p style="margin:0; font-size:1.1em;"><strong>Session:</strong> {item.title}</p>
                      <p style="margin:4px 0 0 0; color:#047857;"><strong>Status:</strong> Instructor preparing (Starts in 15 minutes)</p>
                    </div>
                    <p>You can join the room now to view meeting details and watch the 15-minute countdown clock!</p>
                    <hr style="border:none;border-top:1px solid #eee;margin-top:30px;" />
                    <p style="font-size:0.8em;color:#999;text-align:center;">EduSense AI Platform &mdash; Automated Notification</p>
                  </div>
                </body></html>
                """
                background_tasks.add_task(_send_email_sync, st.email, subject, html_body)

    # Audit: instructor starting session
    log_session_access(db, user, session_id, action=action, request=request)

    if force_go_live or item.status == "ongoing":
        return {"message": "Session is now live!", "status": "ongoing", "live_url": f"/instructor/sessions/{session_id}/live"}
    return {"message": "15-minute preparation timer started", "status": "preparing", "prep_start_time": item.prep_start_time.isoformat(), "live_url": f"/instructor/sessions/{session_id}/live"}


@router.get("/{session_id}/live")
def get_live_session(session_id: int, db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    item = db.query(Session).filter_by(id=session_id).first()
    if not item:
        raise HTTPException(404, "Session not found")
    if user.role == "instructor" and item.instructor_id != user.id:
        raise HTTPException(403, "Not your session")
    if user.role == "student":
        reg = db.query(SessionRegistration).filter_by(session_id=session_id, student_id=user.id).first()
        if not reg:
            raise HTTPException(403, "You are not enrolled in this session. Please enroll first from Browse.")
    refresh_status(item, db)
    db.commit()
    res = SessionOut.model_validate(item)
    inst = db.query(User).filter(User.id == item.instructor_id).first()
    if inst:
        res.instructor_name = inst.name
    return res


@router.post("/{session_id}/share-frame")
def upload_share_frame(session_id: int, payload: ShareFrameIn, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    query = db.query(Session).filter(Session.id == session_id)
    if user.role != "admin":
        query = query.filter(Session.instructor_id == user.id)
    item = query.first()
    if not item:
        raise HTTPException(404, "Session not found")
    SHARE_DIR.mkdir(parents=True, exist_ok=True)
    data = payload.image.split(",", 1)[1] if "," in payload.image else payload.image
    path = SHARE_DIR / f"session-{session_id}.jpg"
    path.write_bytes(base64.b64decode(data))
    return {"message": "Frame uploaded", "url": f"/static/live/session-{session_id}.jpg?t={path.stat().st_mtime}"}


@router.get("/{session_id}/share-frame")
def get_share_frame(session_id: int, _: User = Depends(get_current_user)):
    path = SHARE_DIR / f"session-{session_id}.jpg"
    if not path.exists():
        raise HTTPException(404, "No shared screen yet")
    return FileResponse(path, media_type="image/jpeg")


@router.post("/{session_id}/end")
def end_session(session_id: int, request: Request, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    query = db.query(Session).filter(Session.id == session_id)
    if user.role != "admin":
        query = query.filter(Session.instructor_id == user.id)
    item = query.first()
    if not item:
        raise HTTPException(404, "Session not found")
    item.status = "ended"
    db.commit()

    # Audit: instructor ending session
    log_session_access(db, user, session_id, action="end_session", request=request)

    return {"message": "Session ended"}


@router.post("/notes")
def create_session_note(note_data: NoteCreate, db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    note = SessionNote(
        session_id=note_data.session_id,
        student_id=user.id,
        note=note_data.note
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.get("/notes/{session_id}")
def get_session_notes(session_id: int, db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    notes = (
        db.query(SessionNote)
        .filter(SessionNote.session_id == session_id, SessionNote.student_id == user.id)
        .order_by(SessionNote.created_at.desc())
        .all()
    )
    return notes


@router.get("/{session_id}/attendees")
def get_session_attendees(session_id: int, request: Request, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    registrations = db.query(SessionRegistration).filter_by(session_id=session_id).all()
    student_ids = [reg.student_id for reg in registrations]
    students = db.query(User).filter(User.id.in_(student_ids)).all() if student_ids else []

    # Audit: instructor viewing session attendees (student data)
    log_session_access(db, user, session_id, action="view_attendees", request=request)

    return [{"id": s.id, "name": s.name, "email": s.email} for s in students]


# ─── Session Resource Upload ────────────────────────────────────────────────

@router.post("/{session_id}/resources")
async def upload_session_resource(
    session_id: int,
    file: UploadFile = File(...),
    subject: Optional[str] = Form(None),
    grade_level: Optional[str] = Form(None),
    db: DbSession = Depends(get_db),
    user: User = Depends(require_role("instructor"))
):
    """Upload a presentation/slide/PDF resource for a session.

    Optional form fields:
    - subject: Academic subject (e.g., "Physics", "Biology") for RAG filtering
    - grade_level: Grade level (e.g., "10", "11") for RAG filtering
    """
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    if session.instructor_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your session")

    # Save the file
    RESOURCE_DIR.mkdir(parents=True, exist_ok=True)
    original_name = file.filename or "resource"
    safe_filename = Path(original_name.replace("\\", "/")).name.replace(" ", "_")
    safe_name = f"session-{session_id}-{uuid.uuid4().hex}-{safe_filename}"
    dest = RESOURCE_DIR / safe_name
    content = await file.read()
    dest.write_bytes(content)

    resource = SessionResource(
        session_id=session_id,
        instructor_id=user.id,
        name=original_name,
        file_path=str(dest),
        file_type=file.content_type or "application/octet-stream",
        file_size=len(content),
    )
    db.add(resource)
    try:
        db.commit()
        db.refresh(resource)
    except Exception as exc:
        db.rollback()
        dest.unlink(missing_ok=True)
        logger.exception("Failed to save uploaded resource record")
        raise HTTPException(500, "Could not save uploaded resource") from exc

    # Ingest document into vector store
    from app.services.ingestion import ingest_file
    from app.services.vector_store import delete_by_source, init_collection
    source_id = f"resource_{resource.id}"
    try:
        chunks = ingest_file(
            file_path=resource.file_path,
            metadata={
                "source_id": source_id,
                "source_file": resource.name,
                "session_id": session.id,
                "instructor_id": user.id,
                "topic": session.title,
                "subject": subject,
                "grade_level": grade_level,
            },
        )
    except Exception as exc:
        logger.error(
            f"Failed to ingest resource {resource.id} into vector store: {exc}",
            exc_info=True
        )
        try:
            delete_by_source(source_id)
            remaining = init_collection().get(where={"source_id": source_id}, limit=1)
            if remaining.get("ids", []):
                logger.error(
                    f"Partial vector store cleanup incomplete for resource {resource.id} "
                    f"({source_id}): {len(remaining.get('ids', []))} chunk(s) still present after delete attempt.",
                )
        except Exception as cleanup_exc:
            logger.error(
                f"Vector store cleanup/verification failed for resource {resource.id} "
                f"({source_id}): {cleanup_exc}",
                exc_info=True,
            )
        raise HTTPException(
            status_code=500,
            detail=f"Resource uploaded, but vector store ingestion failed: {exc}"
        ) from exc

    return {
        "id": resource.id,
        "name": resource.name,
        "file_type": resource.file_type,
        "file_size": resource.file_size,
        "uploaded_at": resource.uploaded_at.isoformat(),
        "url": f"/static/resources/{safe_name}",
        "available": True,
        "chunks_indexed": len(chunks),
    }


@router.get("/resources/library")
def list_library_resources(db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    """List all uploaded resources in the instructor's library across all sessions."""
    resources = db.query(SessionResource).filter_by(instructor_id=user.id).order_by(SessionResource.uploaded_at.desc()).all()
    session_ids = {r.session_id for r in resources if r.session_id}
    sessions_map = {}
    if session_ids:
        sess_rows = db.query(Session.id, Session.title).filter(Session.id.in_(session_ids)).all()
        sessions_map = {s.id: s.title for s in sess_rows}

    result = []
    for resource in resources:
        stored_path = Path(resource.file_path) if resource.file_path else None
        filename = stored_path.name if stored_path else ""
        path = stored_path if stored_path and stored_path.is_file() else RESOURCE_DIR / filename
        available = bool(filename and path.is_file())
        result.append({
            "id": resource.id,
            "session_id": resource.session_id,
            "session_title": sessions_map.get(resource.session_id, "General Library"),
            "name": resource.name,
            "file_type": resource.file_type,
            "file_size": resource.file_size,
            "uploaded_at": resource.uploaded_at.isoformat(),
            "url": f"/static/resources/{filename}" if available else None,
            "available": available,
        })
    return result


@router.post("/resources/library")
async def upload_library_resource(
    file: UploadFile = File(...),
    session_ids: Optional[str] = Form(None),
    db: DbSession = Depends(get_db),
    user: User = Depends(require_role("instructor"))
):
    """Upload a file to the instructor library with optional many-to-many session tags."""
    parsed_sids = []
    if session_ids:
        for s in session_ids.split(","):
            s = s.strip()
            if s.isdigit():
                parsed_sids.append(int(s))

    if not parsed_sids:
        first_sess = db.query(Session).filter_by(instructor_id=user.id).first()
        if first_sess:
            parsed_sids = [first_sess.id]
        else:
            any_sess = db.query(Session).first()
            parsed_sids = [any_sess.id] if any_sess else [1]

    RESOURCE_DIR.mkdir(parents=True, exist_ok=True)
    original_name = file.filename or "resource"
    safe_filename = Path(original_name.replace("\\", "/")).name.replace(" ", "_")
    safe_name = f"library-{user.id}-{uuid.uuid4().hex}-{safe_filename}"
    dest = RESOURCE_DIR / safe_name
    content = await file.read()
    dest.write_bytes(content)

    created_ids = []
    for sid in parsed_sids:
        res = SessionResource(
            session_id=sid,
            instructor_id=user.id,
            name=original_name,
            file_path=str(dest),
            file_type=file.content_type or "application/octet-stream",
            file_size=len(content),
        )
        db.add(res)
        db.flush()
        created_ids.append(res.id)
    db.commit()

    return {
        "id": created_ids[0] if created_ids else None,
        "ids": created_ids,
        "name": original_name,
        "file_size": len(content),
        "url": f"/static/resources/{safe_name}",
        "session_ids": parsed_sids,
    }


@router.get("/{session_id}/resources")
def list_session_resources(session_id: int, db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    """List all uploaded resources for a session (instructor + enrolled students)."""
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    if user.role == "student":
        reg = db.query(SessionRegistration).filter_by(session_id=session_id, student_id=user.id).first()
        if not reg:
            raise HTTPException(403, "You are not enrolled in this session")
    resources = db.query(SessionResource).filter_by(session_id=session_id).order_by(SessionResource.uploaded_at.desc()).all()
    result = []
    for resource in resources:
        stored_path = Path(resource.file_path) if resource.file_path else None
        filename = stored_path.name if stored_path else ""
        path = stored_path if stored_path and stored_path.is_file() else RESOURCE_DIR / filename
        available = bool(filename and path.is_file())
        result.append({
            "id": resource.id,
            "name": resource.name,
            "file_type": resource.file_type,
            "file_size": resource.file_size,
            "uploaded_at": resource.uploaded_at.isoformat(),
            "url": f"/static/resources/{filename}" if available else None,
            "available": available,
        })
    return result


@router.delete("/resources/{resource_id}")
def delete_session_resource(resource_id: int, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    resource = db.query(SessionResource).filter_by(id=resource_id).first()
    if not resource:
        raise HTTPException(404, "Resource not found")
    if resource.instructor_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your resource")
    try:
        Path(resource.file_path).unlink(missing_ok=True)
    except Exception:
        pass
    db.delete(resource)
    db.commit()

    # Remove indexed chunks from the vector store after SQL commit.
    # delete_by_source() suppresses internal exceptions and returns None on both
    # success and failure, so we verify by checking for remaining chunks directly.
    from app.services.vector_store import delete_by_source, init_collection
    source_id = f"resource_{resource_id}"
    vs_cleanup_ok = True
    try:
        delete_by_source(source_id)
        collection = init_collection()
        remaining_by_id = collection.get(where={"source_id": source_id}, limit=1)
        remaining_by_file = collection.get(where={"source_file": source_id}, limit=1)
        if remaining_by_id.get("ids") or remaining_by_file.get("ids"):
            vs_cleanup_ok = False
    except Exception as verify_exc:
        logger.error(
            f"Vector store cleanup/verification failed for resource {resource_id} "
            f"({source_id}): {verify_exc}",
            exc_info=True,
        )
        vs_cleanup_ok = False

    if not vs_cleanup_ok:
        return {
            "message": "Resource deleted",
            "vector_store_cleanup": "failed — stale chunks may remain",
        }
    return {"message": "Resource deleted"}


# ─── Session AI Generations (link an AI gen to a session) ────────────────────

@router.post("/{session_id}/link-generation/{gen_id}")
def link_generation_to_session(
    session_id: int,
    gen_id: int,
    type: str | None = None,
    db: DbSession = Depends(get_db),
    user: User = Depends(require_role("instructor"))
):
    """Link an existing AI generation or Quiz to a specific session so students can access it."""
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    if session.instructor_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your session")

    # Try finding in AIGeneration first (unless type=='quiz')
    if type != "quiz":
        gen = db.query(AIGeneration).filter_by(id=gen_id, instructor_id=user.id).first()
        if gen:
            gen.session_id = session_id
            db.commit()
            return {"message": "Generation linked to session", "session_id": session_id, "generation_id": gen_id, "type": gen.type}

    # If not found or type is quiz, try Quiz table
    quiz = db.query(Quiz).filter_by(id=gen_id).first()
    if quiz:
        quiz.session_id = session_id
        db.commit()
        return {"message": "Quiz linked to session", "session_id": session_id, "generation_id": gen_id, "type": "quiz"}

    raise HTTPException(404, "AI Content not found")


@router.delete("/{session_id}/link-generation/{gen_id}")
@router.post("/{session_id}/unlink-generation/{gen_id}")
def unlink_generation_from_session(
    session_id: int,
    gen_id: int,
    type: str | None = None,
    db: DbSession = Depends(get_db),
    user: User = Depends(require_role("instructor"))
):
    """Unlink an AI generation or Quiz from a session."""
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    if session.instructor_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your session")

    unlinked = False
    if type != "quiz":
        gen = db.query(AIGeneration).filter_by(id=gen_id, session_id=session_id).first()
        if gen:
            gen.session_id = None
            unlinked = True

    if not unlinked:
        quiz = db.query(Quiz).filter_by(id=gen_id, session_id=session_id).first()
        if quiz:
            quiz.session_id = None
            unlinked = True

    if not unlinked:
        raise HTTPException(404, "Linked content not found for this session")

    db.commit()
    return {"message": "Content unlinked from session", "session_id": session_id, "generation_id": gen_id}


@router.get("/{session_id}/generations")
def list_session_generations(session_id: int, db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    """List all AI generations and quizzes linked to this session (for enrolled students and the instructor)."""
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    if user.role == "student":
        reg = db.query(SessionRegistration).filter_by(session_id=session_id, student_id=user.id).first()
        if not reg:
            raise HTTPException(403, "You are not enrolled in this session")
    gens = db.query(AIGeneration).filter_by(session_id=session_id).order_by(AIGeneration.created_at.desc()).all()
    result = []
    for g in gens:
        try:
            data = json.loads(g.data_json)
        except Exception:
            data = {}
        result.append({
            "id": g.id,
            "type": g.type,
            "topic": g.topic,
            "created_at": g.created_at.isoformat() if g.created_at else None,
            "data": data,
        })
    quizzes = db.query(Quiz).filter_by(session_id=session_id).order_by(Quiz.created_at.desc()).all()
    for q in quizzes:
        try:
            q_data = json.loads(q.questions_json)
        except Exception:
            q_data = []
        result.append({
            "id": q.id,
            "type": "quiz",
            "topic": q.title,
            "created_at": q.created_at.isoformat() if q.created_at else None,
            "data": {"title": q.title, "difficulty": q.difficulty, "questions": q_data},
        })
    return result


# ─── Student: My Attended Sessions + their resources ────────────────────────

@router.get("/student/my-sessions")
def student_my_sessions(request: Request, db: DbSession = Depends(get_db), user: User = Depends(require_role("student"))):
    """Return all sessions the student is enrolled in (past and upcoming)."""
    regs = db.query(SessionRegistration).filter_by(student_id=user.id).all()
    session_ids = [r.session_id for r in regs]
    sessions = db.query(Session).filter(Session.id.in_(session_ids)).order_by(Session.date.desc(), Session.start_time.desc()).all() if session_ids else []
    result = []
    for s in sessions:
        refresh_status(s, db)
        inst = db.query(User).filter(User.id == s.instructor_id).first()
        reg = next((r for r in regs if r.session_id == s.id), None)
        from app.services.attendance_service import calculate_student_attended_duration
        attended_dur = calculate_student_attended_duration(db, s.id, user.id)
        result.append({
            "id": s.id,
            "title": s.title,
            "description": s.description,
            "date": str(s.date),
            "start_time": str(s.start_time),
            "scheduled_duration": s.duration,
            "duration": attended_dur if (reg and reg.attended) else s.duration,
            "attended_duration": attended_dur,
            "status": s.status,
            "effective_status": effective_status(s),
            "instructor_name": inst.name if inst else None,
            "attended": reg.attended if reg else False,
        })
    db.commit()

    # Audit: student viewing their enrolled sessions
    log_audit_event(db, action="view_my_sessions", user=user, resource_type="session", request=request)

    return result
