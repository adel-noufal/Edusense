from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api import admin, ai, assignments, auth, emotions, quizzes, rag, reports, sessions, users
from app.core.config import get_settings
from app.db.seed import init_db
from app.core.scheduler import start_scheduler, shutdown_scheduler

settings = get_settings()

tags_metadata = [
    {"name": "auth", "description": "Authentication & JWT Token Management"},
    {"name": "users", "description": "User Profiles & Account Operations"},
    {"name": "sessions", "description": "Live Classroom Session Management"},
    {"name": "emotions", "description": "PyTorch v7 Webcam Emotion Analysis & Distribution Logs"},
    {"name": "ai", "description": "7-Agent Multi-Tier AI Generation (Lessons, Quizzes, Flashcards)"},
    {"name": "rag", "description": "Data Ingestion & Retrieval-Augmented Generation Knowledge Base"},
    {"name": "reports", "description": "ReportLab Executive PDF Generation & Analytics"},
    {"name": "admin", "description": "Administrative System Overview"},
]

app = FastAPI(
    title="EduSense AI Education Platform",
    description="""
    **EduSense** is a multi-agent AI Education Platform for adaptive learning, 
    real-time webcam facial emotion recognition (PyTorch v7 EfficientNet-B0 — 90.9% Accuracy), 
    and intelligent multi-tier AI model task routing (Gemini 2.0 Flash -> Specialized Local Ollama Models).

    👤 **Author:** Adel Mohamed Noufal  
    🔗 **LinkedIn:** https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/  
    📦 **GitHub:** https://github.com/adel-noufal/Edusense
    """,
    version="2.0.0",
    openapi_tags=tags_metadata,
    contact={
        "name": "Adel Mohamed Noufal",
        "url": "https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(emotions.router, prefix="/api")
app.include_router(quizzes.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(rag.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(assignments.router, prefix="/api")



@app.on_event("startup")
def startup():
    init_db(seed=True)
    start_scheduler()

@app.on_event("shutdown")
def shutdown():
    shutdown_scheduler()


@app.get("/health")
def health():
    from app.services.gemini import rotator

    settings = get_settings()
    keys = settings.gemini_api_keys
    gemini_ok = bool(keys)
    gemini_hint = None
    has_valid_format = any(k.startswith("AIza") or k.startswith("AQ.") for k in keys) if keys else False
    if keys and not has_valid_format:
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
        "gemini_keys_count": len(keys),
        "gemini_keys_status": rotator.status(),
        "gemini_key_valid_format": has_valid_format,
        "ollama_reachable": ollama_reachable if settings.ai_provider == "ollama" else None,
        "ollama_model": settings.ollama_model if settings.ai_provider == "ollama" else None,
        "hint": gemini_hint,
    }
