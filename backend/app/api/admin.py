from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException
from app.api.deps import require_role
from app.db.session import engine
from app.models.models import User

router = APIRouter(prefix="/admin", tags=["Admin"])

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
}


@router.get("/db/tables")
def list_tables(_: User = Depends(require_role("instructor"))):
    inspector = inspect(engine)
    tables = [name for name in inspector.get_table_names() if name in ALLOWED_TABLES]
    return {
        "engine": "postgresql" if "postgresql" in str(engine.url) else "sqlite",
        "database_file": str(engine.url).replace("postgresql+psycopg2://", "postgresql://"),
        "tables": sorted(tables),
    }


@router.get("/db/preview/{table_name}")
def preview_table(table_name: str, limit: int = 25, _: User = Depends(require_role("instructor"))):
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(404, "Table not available for preview")
    with engine.connect() as connection:
        rows = connection.execute(text(f"SELECT * FROM {table_name} LIMIT :limit"), {"limit": min(limit, 100)}).mappings().all()
        count = connection.execute(text(f"SELECT COUNT(*) AS total FROM {table_name}")).scalar_one()
    return {
        "table": table_name,
        "total_rows": count,
        "preview_rows": [dict(row) for row in rows],
    }
