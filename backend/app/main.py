import asyncio
import logging
import os
import time
import uuid
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from app.api import admin, ai, assignments, auth, emotions, quizzes, rag, reports, sessions, users
from app.core.config import get_settings
from app.core.errors import ContentGenerationUnavailable
from app.core.logging_config import configure_logging
from app.db.seed import init_db
from app.core.scheduler import start_scheduler, shutdown_scheduler

configure_logging()
logger = logging.getLogger("edusense.api")

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
    in-browser facial emotion recognition (face-api.js, no image leaves the browser),
    and intelligent multi-tier AI model task routing across live, verified providers.

    👤 **Author:** Adel Mohamed Noufal
    🔗 **LinkedIn:** https://www.linkedin.com/in/adel-mohamed-noufal-3a9440348/
    📦 **GitHub:** https://github.com/adel-noufal/Edusense
    """,
    version="2.1.0",
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


@app.exception_handler(ContentGenerationUnavailable)
async def _content_generation_unavailable(request, exc: ContentGenerationUnavailable):
    """Honest failure path (F1): when no provider can answer, say so.

    Previously every agent swallowed the provider error and wrote a generic
    template, which the user saw as fabricated lesson/quiz/flashcard content.
    """
    return JSONResponse(status_code=503, content=exc.payload())


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    """Validation failures are JSON too, never Starlette's HTML page."""
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors()), "code": "validation_error"},
    )


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    """HTTP errors (404, 401, ...) always answer with a JSON body."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": "http_error"},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def _unhandled_error(request: Request, exc: Exception):
    """Last line of defence: an unhandled exception is logged and answered
    with JSON 500, so the browser never receives an HTML traceback page."""
    request_id = getattr(request.state, "request_id", "-")
    logger.exception("Unhandled %s on %s %s [%s]", type(exc).__name__, request.method, request.url.path, request_id)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error. The failure was logged; retry the request.",
            "code": "internal_error",
            "request_id": request_id,
        },
    )


class RequestGuardMiddleware(BaseHTTPMiddleware):
    """Request id, hang protection and slow-request logging.

    A stuck request (dead provider socket, saturated CPU) is cut off after
    ``request_timeout_seconds`` and answered with JSON 504 instead of hanging the
    browser tab forever. Static files and API docs are exempt.
    """

    EXEMPT_PREFIXES = ("/static", "/docs", "/redoc", "/openapi.json")

    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        started = time.perf_counter()
        exempt = request.url.path.startswith(self.EXEMPT_PREFIXES)
        timeout = float(getattr(settings, "request_timeout_seconds", 300) or 300)
        try:
            if exempt:
                response = await call_next(request)
            else:
                response = await asyncio.wait_for(call_next(request), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error("Request timed out after %.0fs: %s %s [%s]",
                         timeout, request.method, request.url.path, request_id)
            return JSONResponse(
                status_code=504,
                content={
                    "detail": f"The request took longer than {int(timeout)}s and was stopped. Retry, or use a faster model.",
                    "code": "request_timeout",
                    "request_id": request_id,
                },
            )
        except Exception as exc:  # pragma: no cover - defence in depth
            logger.exception("Unhandled %s on %s %s [%s]", type(exc).__name__, request.method, request.url.path, request_id)
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error.", "code": "internal_error", "request_id": request_id},
            )
        elapsed = (time.perf_counter() - started) * 1000
        if elapsed > 5000:
            logger.warning("Slow request %.1fs: %s %s [%s]", elapsed / 1000, request.method, request.url.path, request_id)
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(RequestGuardMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

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
    import threading
    try:
        import asyncio
        loop = asyncio.get_event_loop()

        def _edusense_exception_handler(loop, context):
            exc = context.get("exception")
            message = str(context.get("message") or "")
            if isinstance(exc, ConnectionResetError) or "10054" in message or "closed file" in message:
                return
            loop.default_exception_handler(context)

        loop.set_exception_handler(_edusense_exception_handler)
    except Exception:
        pass
    init_db(seed=True)
    # Reconcile stale session statuses (missed/ended) on boot
    try:
        from app.db.session import SessionLocal
        from app.api.sessions import reconcile_session_statuses
        from app.services.generation_jobs import cleanup_stuck_jobs_on_startup
        _db = SessionLocal()
        try:
            n = reconcile_session_statuses(_db)
            if n:
                print(f"Startup: reconciled {n} stale session statuses")
            cleared = cleanup_stuck_jobs_on_startup(_db)
            if cleared:
                print(f"Startup: cleared {cleared} stale pending/processing background jobs")
            # Reversible migration: tag legacy chatbot conversations as web:
            from app.api.ai import migrate_conversation_kinds, reconcile_video_records
            moved = migrate_conversation_kinds(_db)
            if moved:
                print(f"Startup: tagged {moved} legacy chatbot messages as web: conversations")
            video_fix = reconcile_video_records(_db)
            if video_fix["notes_cleaned"] or video_fix["videos_marked_failed"]:
                print(f"Startup: video records reconciled {video_fix}")
        finally:
            _db.close()
    except Exception as exc:
        print(f"Startup session/job reconcile skipped: {exc}")
    try:
        start_scheduler()
    except Exception as exc:
        logger.warning("Scheduler did not start: %s", exc)

    # C9 & P0-3: Warm up the live model catalog and vector store in background threads
    def _warmup_services():
        from app.services import warmup

        # Live catalog discovery (per provider and key) + 1-token probes, so
        # routing and the dropdown only offer models this account can use.
        warmup.set_status("model_discovery", "warming")
        try:
            from app.services import model_discovery
            cached = model_discovery.load_cache()
            age = model_discovery.cache_age_seconds(cached)
            if age > model_discovery.REFRESH_AFTER_SECONDS:
                model_discovery.discover()
                warmup.set_status("model_discovery", "ready", "probed live catalogs")
            else:
                print(f"LLM model discovery cache is fresh ({age/60:.0f} min old)")
                warmup.set_status("model_discovery", "ready", f"cache {age/60:.0f} min old")
        except Exception as e:
            print(f"LLM model discovery skipped: {e}")
            warmup.set_status("model_discovery", "failed", str(e)[:200])

        warmup.set_status("knowledge_base", "warming")
        try:
            from app.services.vector_store import init_collection
            init_collection()   # loads ChromaDB + embedding model once
            print("KB warm-up complete")
            warmup.set_status("knowledge_base", "ready")
        except Exception as e:
            print(f"KB warm-up skipped: {e}")
            warmup.set_status("knowledge_base", "failed", str(e)[:200])

    # Emotion recognition runs in the browser (face-api.js); there is no
    # server-side model to warm up any more. This bookkeeping must never be
    # able to stop the server from starting.
    try:
        from app.services import warmup

        warmup.set_status("emotion_detector", "ready", "in-browser (face-api.js)")
    except Exception as exc:
        logger.warning("Warm-up status could not be published: %s", exc)

    threading.Thread(target=_warmup_services, daemon=True, name="edusense-warmup").start()

@app.on_event("shutdown")
def shutdown():
    try:
        shutdown_scheduler()
    except Exception:
        pass


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

    # Check Ollama connectivity (short timeout: /health must always answer fast)
    ollama_reachable = False
    import urllib.request
    try:
        base = settings.ollama_url.replace("/api/generate", "")
        with urllib.request.urlopen(f"{base}/api/tags", timeout=1.5):
            ollama_reachable = True
    except Exception:
        ollama_reachable = False

    from app.services import warmup

    return {
        "status": "ok",
        "service": "EduSense",
        "warmup": warmup.snapshot(),
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


@app.get("/api/health")
def api_health_alias():
    return health()
