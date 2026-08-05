from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session as DbSession
from pydantic import BaseModel
import base64
from pathlib import Path
from collections import Counter
from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.models import Session, SessionRegistration, User, SessionNote
from app.schemas.schemas import SessionIn, SessionOut, NoteCreate
from app.services.status import session_status

router = APIRouter(prefix="/sessions", tags=["Sessions"])
SHARE_DIR = Path(__file__).resolve().parents[1] / "static" / "live"


class ShareFrameIn(BaseModel):
    image: str


def refresh_status(item: Session, db: DbSession):
    # Don't overwrite manually set statuses (ended, ongoing) or already-correct pending
    if item.status in ("ended", "ongoing"):
        return
    # Only auto-move from pending → ongoing when it's time, never auto-end
    computed = session_status(item.date, item.start_time, item.duration)
    if computed == "ongoing" and item.status == "pending":
        item.status = "ongoing"
        db.add(item)
    # If computed is "ended" (time passed), keep it as "pending" — instructor must manually end


def serialize_browse_session(item: Session, user: User, registrations: list[SessionRegistration]) -> dict:
    related = [registration for registration in registrations if registration.session_id == item.id]
    attendee_ids = {registration.student_id for registration in related}
    seats_left = max(item.max_students - len(attendee_ids), 0) if item.max_students is not None else None
    is_registered = user.id in attendee_ids
    return {
        "id": item.id,
        "instructor_id": item.instructor_id,
        "title": item.title,
        "description": item.description,
        "date": item.date,
        "start_time": item.start_time,
        "duration": item.duration,
        "max_students": item.max_students,
        "status": item.status,
        "registration_count": len(attendee_ids),
        "available_seats": seats_left,
        "is_registered": is_registered,
        "can_register": item.status in {"upcoming", "scheduled", "live", "ongoing", "pending"} and (is_registered or seats_left is None or seats_left > 0),
    }


@router.get("", response_model=list[SessionOut])
def list_sessions(db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Session)
    if user.role == "instructor":
        query = query.filter(Session.instructor_id == user.id)
    sessions = query.order_by(Session.date, Session.start_time).all()
    for item in sessions:
        refresh_status(item, db)
    db.commit()
    return sessions


@router.get("/browse")
def browse_sessions(db: DbSession = Depends(get_db), user: User = Depends(require_role("student"))):
    sessions = db.query(Session).order_by(Session.date, Session.start_time).all()
    for item in sessions:
        refresh_status(item, db)
    db.commit()
    statuses = Counter(item.status for item in sessions)
    registrations = db.query(SessionRegistration).all()
    catalog = [
        serialize_browse_session(item, user, registrations)
        for item in sessions
        if item.status in {"upcoming", "scheduled", "live", "ongoing", "pending"}
    ]
    return {
        "sessions": catalog,
        "summary": {
            "available": len(catalog),
            "registered": sum(1 for item in catalog if item["is_registered"]),
            "live_now": statuses.get("live", 0) + statuses.get("ongoing", 0),
        },
    }


@router.post("", response_model=SessionOut)
def create_session(payload: SessionIn, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    item = Session(**payload.model_dump(), instructor_id=user.id)
    refresh_status(item, db)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/{session_id}", response_model=SessionOut)
def update_session(session_id: int, payload: SessionIn, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    item = db.query(Session).filter(Session.id == session_id, Session.instructor_id == user.id).first()
    if not item:
        raise HTTPException(404, "Session not found")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    refresh_status(item, db)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{session_id}")
def delete_session(session_id: int, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    deleted = db.query(Session).filter(Session.id == session_id, Session.instructor_id == user.id).delete()
    db.commit()
    if not deleted:
        raise HTTPException(404, "Session not found")
    return {"message": "Session deleted"}


@router.post("/{session_id}/join")
def join_session(session_id: int, db: DbSession = Depends(get_db), user: User = Depends(require_role("student"))):
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    refresh_status(session, db)
    if session.status not in {"upcoming", "scheduled", "live", "ongoing", "pending"}:
        raise HTTPException(400, "This session is no longer open for registration")
    reg = db.query(SessionRegistration).filter_by(session_id=session_id, student_id=user.id).first()
    if not reg:
        if session.max_students is not None:
            seats_taken = db.query(SessionRegistration).filter_by(session_id=session_id).count()
            if seats_taken >= session.max_students:
                raise HTTPException(400, "This session is already full")
        db.add(SessionRegistration(session_id=session_id, student_id=user.id))
        db.commit()
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
def start_session(session_id: int, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    item = db.query(Session).filter_by(id=session_id, instructor_id=user.id).first()
    if not item:
        raise HTTPException(404, "Session not found")
    item.status = "ongoing"
    db.commit()
    return {"message": "Session started", "live_url": f"/instructor/sessions/{session_id}/live"}


@router.get("/{session_id}/live")
def get_live_session(session_id: int, db: DbSession = Depends(get_db), user: User = Depends(get_current_user)):
    item = db.query(Session).filter_by(id=session_id).first()
    if not item:
        raise HTTPException(404, "Session not found")
    if user.role == "instructor" and item.instructor_id != user.id:
        raise HTTPException(403, "Not your session")
    return SessionOut.model_validate(item)


@router.post("/{session_id}/share-frame")
def upload_share_frame(session_id: int, payload: ShareFrameIn, db: DbSession = Depends(get_db), user: User = Depends(require_role("instructor"))):
    item = db.query(Session).filter_by(id=session_id, instructor_id=user.id).first()
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
    item = db.query(Session).filter_by(id=session_id, instructor_id=user.id).first()
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
