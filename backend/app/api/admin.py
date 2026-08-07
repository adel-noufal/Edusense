from datetime import date, datetime
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException
from app.api.deps import require_role
from app.db.session import engine, get_db
from app.models.models import User, Session as AppSession, SessionRegistration, EmotionLog, Report, Feedback, VideoProject, Quiz, SessionNote, AIGeneration

router = APIRouter(prefix="/admin", tags=["admin"])

ALLOWED_TABLES = {
    "users",
    "profiles",
    "sessions",
    "session_registrations",
    "emotion_logs",
    "reports",
    "feedback",
    "video_projects",
    "quizzes",
    "session_notes",
    "ai_generations",
}


def serialize_cell(val):
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, bytes):
        return "<binary data>"
    return val


@router.get("/db/tables")
def list_tables(_: User = Depends(require_role("admin", "instructor"))):
    inspector = inspect(engine)
    tables = [name for name in inspector.get_table_names() if name in ALLOWED_TABLES]
    return {
        "engine": "postgresql" if "postgresql" in str(engine.url) else "sqlite",
        "database_file": str(engine.url).replace("postgresql+psycopg2://", "postgresql://"),
        "tables": sorted(tables),
    }


@router.get("/db/preview/{table_name}")
def preview_table(table_name: str, limit: int = 25, _: User = Depends(require_role("admin", "instructor"))):
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(404, "Table not available for preview")
    with engine.connect() as connection:
        rows = connection.execute(text(f"SELECT * FROM {table_name} LIMIT :limit"), {"limit": min(limit, 100)}).mappings().all()
        count = connection.execute(text(f"SELECT COUNT(*) AS total FROM {table_name}")).scalar_one()
    
    clean_rows = [{k: serialize_cell(v) for k, v in dict(row).items()} for row in rows]
    return {
        "table": table_name,
        "total_rows": count,
        "preview_rows": clean_rows,
    }


@router.post("/reset-data")
def reset_platform_data(db: Session = Depends(get_db)):
    """Deletes all sessions and generated data (emotions, quizzes, lessons, reports, notes) while keeping user and admin accounts intact."""
    db.query(EmotionLog).delete()
    db.query(Report).delete()
    db.query(Feedback).delete()
    db.query(VideoProject).delete()
    db.query(Quiz).delete()
    db.query(SessionNote).delete()
    db.query(AIGeneration).delete()
    db.query(SessionRegistration).delete()
    db.query(AppSession).delete()
    db.commit()
    return {"message": "All created sessions, logs, and generated content have been successfully cleared. Admin and user accounts remain active."}

