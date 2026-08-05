from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api import admin, ai, auth, emotions, reports, sessions, users
from app.core.config import get_settings
from app.db.seed import init_db
from app.core.scheduler import start_scheduler, shutdown_scheduler

settings = get_settings()
app = FastAPI(title="EduSense AI Education Platform", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(emotions.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


@app.on_event("startup")
def startup():
    init_db(seed=True)
    start_scheduler()

@app.on_event("shutdown")
def shutdown():
    shutdown_scheduler()


@app.get("/health")
def health():
    settings = get_settings()
    gemini_ok = bool(settings.gemini_api_key)
    gemini_hint = None
    key = settings.gemini_api_key or ""
    valid_format = key.startswith("AIza") or key.startswith("AQ.")
    if key and not valid_format:
        gemini_hint = "Get a key from aistudio.google.com (starts with AIza or AQ.)"
    db_kind = "postgresql" if "postgresql" in settings.database_url else "sqlite"

    # Check Ollama connectivity (non-blocking)
    ollama_reachable = False
    if settings.ai_provider == "ollama":
        import urllib.request
        try:
            base = settings.ollama_url.replace("/api/generate", "")
            with urllib.request.urlopen(f"{base}/api/tags", timeout=2):
                ollama_reachable = True
        except Exception:
            ollama_reachable = False

    return {
        "status": "ok",
        "service": "EduSense",
        "database": db_kind,
        "ai_provider": settings.ai_provider,
        "gemini_configured": gemini_ok,
        "gemini_key_valid_format": valid_format if key else False,
        "ollama_reachable": ollama_reachable if settings.ai_provider == "ollama" else None,
        "ollama_model": settings.ollama_model if settings.ai_provider == "ollama" else None,
        "hint": gemini_hint,
    }
