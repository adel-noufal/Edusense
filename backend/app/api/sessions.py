from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session as DbSession
from pydantic import BaseModel
import asyncio
import base64
from pathlib import Path
from collections import Counter
from app.api.deps import get_current_user, require_role
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
from app.services.status import session_status
from app.services.email import _send_email_sync
import json

router = APIRouter(prefix="/sessions", tags=["Sessions"])
SHARE_DIR = Path(__file__).resolve().parents[1] / "static" / "live"
RESOURCE_DIR = Path(__file__).resolve().parents[1] / "static" / "resources"


class ShareFrameIn(BaseModel):
    image: str


from datetime import datetime, timezone, timedelta

def refresh_status(item: Session, db: DbSession):
    # Don't overwrite manually set statuses (ended, ongoing) or already-correct pending
    if item.status in ("ended", "ongoing"):
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
    # Only auto-move from pending → ongoing when it's time, never auto-end
    computed = session_status(item.date, item.start_time, item.duration)
    if computed == "ongoing" and item.status == "pending":
        item.status = "ongoing"
        db.add(item)


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
        "prep_start_time": item.prep_start_time.isoformat() if item.prep_start_time else None,
        "registration_count": len(attendee_ids),
        "available_seats": seats_left,
        "is_registered": is_registered,
        "can_register": item.status in {"upcoming", "scheduled", "live", "ongoing", "pending", "preparing"} and (is_registered or seats_left is None or seats_left > 0),
    }


@router.get("", response_model=list[SessionOut])
def list_sessions(db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Session)
    if user.role == "instructor":
        query = query.filter(Session.instructor_id == user.id)
    sessions = query.order_by(Session.date, Session.start_time).all()
    out = []
    for item in sessions:
        refresh_status(item, db)
        out_item = SessionOut.model_validate(item)
        inst = db.query(User).filter(User.id == item.instructor_id).first()
        if inst:
            out_item.instructor_name = inst.name
        out.append(out_item)
    db.commit()
    return out


@router.get("/browse")
def browse_sessions(db: DbSession = Depends(get_db), user: User = Depends(require_role("student"))):
    sessions = db.query(Session).order_by(Session.date, Session.start_time).all()
    for item in sessions:
        refresh_status(item, db)
    db.commit()
    statuses = Counter(item.status for item in sessions)
    registrations = db.query(SessionRegistration).all()
    catalog = [
        serialize_browse_session(item, user, registrations, db)
        for item in sessions
        if item.status in {"upcoming", "scheduled", "live", "ongoing", "pending", "preparing"}
    ]
    return {
        "sessions": catalog,
        "summary": {
            "available": len(catalog),
            "registered": sum(1 for item in catalog if item["is_registered"]),
            "live_now": statuses.get("live", 0) + statuses.get("ongoing", 0) + statuses.get("preparing", 0),
        },
    }


@router.post("", response_model=SessionOut)
def create_session(payload: SessionIn, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    item = Session(**payload.model_dump(), instructor_id=user.id)
    refresh_status(item, db)
    db.add(item)
    db.commit()
    db.refresh(item)
    res = SessionOut.model_validate(item)
    res.instructor_name = user.name
    return res


@router.put("/{session_id}", response_model=SessionOut)
def update_session(session_id: int, payload: SessionIn, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    query = db.query(Session).filter(Session.id == session_id)
    if user.role != "admin":
        query = query.filter(Session.instructor_id == user.id)
    item = query.first()
    if not item:
        raise HTTPException(404, "Session not found")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    refresh_status(item, db)
    db.commit()
    db.refresh(item)
    res = SessionOut.model_validate(item)
    inst = db.query(User).filter(User.id == item.instructor_id).first()
    if inst:
        res.instructor_name = inst.name
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
def delete_session(session_id: int, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    query = db.query(Session).filter(Session.id == session_id)
    if user.role != "admin":
        query = query.filter(Session.instructor_id == user.id)
    item = query.first()
    if not item:
        raise HTTPException(404, "Session not found")
    _delete_session_dependencies(db, session_id)
    db.delete(item)
    db.commit()
    return {"message": "Session deleted"}


@router.post("/{session_id}/join")
def join_session(session_id: int, background_tasks: BackgroundTasks, db: DbSession = Depends(get_db), user: User = Depends(require_role("student"))):
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
    return {"message": "Joined session"}


@router.delete("/{session_id}/join")
def leave_session(session_id: int, db: DbSession = Depends(get_db), user: User = Depends(require_role("student"))):
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
    return {"message": "Registration cancelled"}


@router.post("/{session_id}/join-live")
def mark_attendance(session_id: int, db: DbSession = Depends(get_db), user: User = Depends(require_role("student"))):
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    reg = db.query(SessionRegistration).filter_by(session_id=session_id, student_id=user.id).first()
    if not reg:
        raise HTTPException(400, "You are not registered for this session")
    reg.attended = True
    db.commit()
    return {"message": "Attendance marked"}


@router.post("/{session_id}/start")
def start_session(session_id: int, background_tasks: BackgroundTasks, force_go_live: bool = False, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    query = db.query(Session).filter(Session.id == session_id)
    if user.role != "admin":
        query = query.filter(Session.instructor_id == user.id)
    item = query.first()
    if not item:
        raise HTTPException(404, "Session not found")

    if force_go_live or item.status == "preparing":
        item.status = "ongoing"
        db.commit()
        return {"message": "Session is now live!", "status": "ongoing", "live_url": f"/instructor/sessions/{session_id}/live"}

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

    return {"message": "15-minute preparation timer started", "status": "preparing", "prep_start_time": item.prep_start_time.isoformat(), "live_url": f"/instructor/sessions/{session_id}/live"}


@router.get("/{session_id}/live")
def get_live_session(session_id: int, db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    item = db.query(Session).filter_by(id=session_id).first()
    if not item:
        raise HTTPException(404, "Session not found")
    if user.role == "instructor" and item.instructor_id != user.id:
        raise HTTPException(403, "Not your session")
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
def end_session(session_id: int, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    query = db.query(Session).filter(Session.id == session_id)
    if user.role != "admin":
        query = query.filter(Session.instructor_id == user.id)
    item = query.first()
    if not item:
        raise HTTPException(404, "Session not found")
    item.status = "ended"
    db.commit()
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
def get_session_attendees(session_id: int, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    registrations = db.query(SessionRegistration).filter_by(session_id=session_id).all()
    student_ids = [reg.student_id for reg in registrations]
    students = db.query(User).filter(User.id.in_(student_ids)).all() if student_ids else []
    return [{"id": s.id, "name": s.name, "email": s.email} for s in students]


# ─── Session Resource Upload ────────────────────────────────────────────────

@router.post("/{session_id}/resources")
async def upload_session_resource(
    session_id: int,
    file: UploadFile = File(...),
    db: DbSession = Depends(get_db),
    user: User = Depends(require_role("instructor"))
):
    """Upload a presentation/slide/PDF resource for a session."""
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    if session.instructor_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your session")

    # Save the file
    RESOURCE_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"session-{session_id}-{file.filename.replace(' ', '_')}"
    dest = RESOURCE_DIR / safe_name
    content = await file.read()
    dest.write_bytes(content)

    resource = SessionResource(
        session_id=session_id,
        instructor_id=user.id,
        name=file.filename,
        file_path=str(dest),
        file_type=file.content_type or "application/octet-stream",
        file_size=len(content),
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return {
        "id": resource.id,
        "name": resource.name,
        "file_type": resource.file_type,
        "file_size": resource.file_size,
        "uploaded_at": resource.uploaded_at.isoformat(),
        "url": f"/static/resources/{safe_name}",
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
    safe_name_fn = lambda r: Path(r.file_path).name if r.file_path else ""
    return [
        {
            "id": r.id,
            "name": r.name,
            "file_type": r.file_type,
            "file_size": r.file_size,
            "uploaded_at": r.uploaded_at.isoformat(),
            "url": f"/static/resources/{safe_name_fn(r)}",
        }
        for r in resources
    ]


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
    return {"message": "Resource deleted"}


# ─── Session AI Generations (link an AI gen to a session) ────────────────────

@router.post("/{session_id}/link-generation/{gen_id}")
def link_generation_to_session(
    session_id: int,
    gen_id: int,
    db: DbSession = Depends(get_db),
    user: User = Depends(require_role("instructor"))
):
    """Link an existing AI generation to a specific session so students can access it."""
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    if session.instructor_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your session")
    gen = db.query(AIGeneration).filter_by(id=gen_id, instructor_id=user.id).first()
    if not gen:
        raise HTTPException(404, "AI Generation not found")
    gen.session_id = session_id
    db.commit()
    return {"message": "Generation linked to session", "session_id": session_id, "generation_id": gen_id}


@router.get("/{session_id}/generations")
def list_session_generations(session_id: int, db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    """List all AI generations linked to this session (for enrolled students and the instructor)."""
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
            "created_at": g.created_at.isoformat(),
            "data": data,
        })
    return result


# ─── Student: My Attended Sessions + their resources ─────────────────────────

@router.get("/student/my-sessions")
def student_my_sessions(db: DbSession = Depends(get_db), user: User = Depends(require_role("student"))):
    """Return all sessions the student is enrolled in (past and upcoming)."""
    regs = db.query(SessionRegistration).filter_by(student_id=user.id).all()
    session_ids = [r.session_id for r in regs]
    sessions = db.query(Session).filter(Session.id.in_(session_ids)).order_by(Session.date.desc(), Session.start_time.desc()).all() if session_ids else []
    result = []
    for s in sessions:
        refresh_status(s, db)
        inst = db.query(User).filter(User.id == s.instructor_id).first()
        reg = next((r for r in regs if r.session_id == s.id), None)
        result.append({
            "id": s.id,
            "title": s.title,
            "description": s.description,
            "date": str(s.date),
            "start_time": str(s.start_time),
            "duration": s.duration,
            "status": s.status,
            "instructor_name": inst.name if inst else None,
            "attended": reg.attended if reg else False,
        })
    db.commit()
    return result
