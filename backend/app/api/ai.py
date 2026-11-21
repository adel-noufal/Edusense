import json
import urllib.error
import urllib.request
import uuid
import threading
import time
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.agents.engagement_agent import StudentEngagementAgent
from app.agents.flashcard_agent import FlashcardGenerationAgent
from app.agents.lesson_agent import LessonGenerationAgent
from app.agents.quiz_agent import QuizGenerationAgent, normalize_difficulty
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.workflow import EduSenseAgentWorkflow
from app.agents.orchestrator import AgentOrchestrator
from app.api.deps import get_current_user, require_role
from app.db.session import get_db, SessionLocal
from app.models.models import AIGeneration, ChatMessage as ChatMessageModel, Quiz, QuizAgentConfig, Report, Session as ClassSession, SessionResource, User, VideoProject, SessionRegistration
from app.schemas.schemas import FlashcardRequest, LessonRequest, QuizRequest, QuizAgentConfigCreate, QuizAgentConfigUpdate, QuizAgentConfigOut, RecommendationDecision, VideoRequest, VideoScenesUpdateRequest
from app.services.export import build_json_bytes, build_video_zip, build_word_document_bytes, lesson_to_markdown, build_true_docx_bytes, build_pptx_bytes
from app.services.generation_jobs import create_job, get_job_payload, list_pending_jobs, set_job_status
from app.services.source_extractor import build_session_source_context
from app.services.video import generate_educational_video, rebuild_video_from_scenes
from app.core.audit import log_audit_event

VIDEO_STATIC_DIR = Path(__file__).resolve().parents[1] / "static" / "videos"


# Rate limiter: 30 requests per minute per user (token bucket)
# TODO: This is in-memory only â€” correct for single-process deployment.
# For multi-worker deployments, replace with a shared store (e.g., Redis).
class _RateLimiter:
    def __init__(self, rate: int = 30, per: int = 60):
        self.rate = rate
        self.per = per
        self._buckets: dict[int, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, user_id: int) -> bool:
        now = time.time()
        with self._lock:
            bucket = self._buckets.get(user_id, [])
            # Remove expired tokens
            bucket = [t for t in bucket if now - t < self.per]
            if len(bucket) >= self.rate:
                return False
            bucket.append(now)
            self._buckets[user_id] = bucket
            return True


_rate_limiter = _RateLimiter(rate=30, per=60)


def _check_rate_limit(user: User) -> None:
    if not _rate_limiter.check(user.id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded: max 30 requests per minute")


router = APIRouter(prefix="/ai", tags=["AI Agents"])
lessons = LessonGenerationAgent()
quizzes = QuizGenerationAgent()
flashcards = FlashcardGenerationAgent()
engagement = StudentEngagementAgent()
recommendations = RecommendationAgent()
workflow = EduSenseAgentWorkflow()
orchestrator = AgentOrchestrator()

# In-memory cache for fast polling; DB is source of truth across restarts
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


class ChatMessageItem(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    conversation_history: List[ChatMessageItem] = []
    subject: Optional[str] = None
    grade_level: Optional[str] = None
    stream: bool = False
    # Uploaded file text to inject as context (from /api/chat/upload)
    file_context: Optional[str] = None
    source_id: Optional[str] = None


class EnhancePromptRequest(BaseModel):
    prompt: str
    context: dict = {}


_analytics_cache: dict[str, dict] = {}


def _cache_job(job_id: str, status: str, result=None, error: str | None = None, progress: int = 0, message: str = ""):
    with _jobs_lock:
        _jobs[job_id] = {
            "status": status,
            "result": result,
            "error": error,
            "progress": progress,
            "message": message,
        }


def _update_job_progress(job_id: str, progress: int, message: str):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["progress"] = progress
            _jobs[job_id]["message"] = message


def _persist_job(job_id: str, instructor_id: int, job_type: str, label: str):
    db = SessionLocal()
    try:
        create_job(db, job_id, instructor_id, job_type, label)
    finally:
        db.close()
    _cache_job(job_id, "pending")


def _finish_job(job_id: str, status: str, result=None, error: str | None = None):
    db = SessionLocal()
    try:
        set_job_status(db, job_id, status, result=result, error=error)
    finally:
        db.close()
    _cache_job(job_id, status, result=result, error=error)


def _get_source_context(
    db: Session,
    source_session_id: int | None,
    instructor_id: int,
    source_resource_ids: list[int] | None = None
) -> str:
    if source_resource_ids:
        resources = db.query(SessionResource).filter(
            SessionResource.id.in_(source_resource_ids),
            SessionResource.instructor_id == instructor_id
        ).all()
        return build_session_source_context(resources)
    if not source_session_id:
        return ""
    resources = db.query(SessionResource).filter_by(session_id=source_session_id, instructor_id=instructor_id).all()
    return build_session_source_context(resources)


def _append_source(notes: str | None, context: str) -> str:
    if not context.strip():
        return notes or ""
    block = f"\n\nUploaded preparation materials:\n{context.strip()}"
    return f"{notes or ''}{block}".strip()[:16000]


def _run_lesson_bg(job_id: str, payload: LessonRequest, instructor_id: int):
    """Runs in a daemon thread â€” survives tab close."""
    try:
        db = SessionLocal()
        try:
            source = _get_source_context(
            db,
            payload.source_session_id,
            instructor_id,
            getattr(payload, "source_resource_ids", None)
        )
            enriched = payload.model_copy(update={
                "additional_notes": _append_source(payload.additional_notes, source),
            })
            result = lessons.generate(enriched).data  # subject/grade_level are on enriched
            gen = AIGeneration(
                instructor_id=instructor_id,
                session_id=payload.session_id,
                type="lesson",
                topic=payload.topic,
                prompt=payload.prompt,
                data_json=json.dumps(result),
            )
            db.add(gen)
            db.commit()
            db.refresh(gen)
            result["id"] = gen.id
        finally:
            db.close()
        _finish_job(job_id, "done", result)
    except Exception as exc:
        _finish_job(job_id, "error", error=str(exc))


def _run_flashcard_bg(job_id: str, payload: FlashcardRequest, instructor_id: int):
    try:
        db = SessionLocal()
        try:
            source = _get_source_context(
            db,
            payload.source_session_id,
            instructor_id,
            getattr(payload, "source_resource_ids", None)
        )
            prompt = _append_source(payload.prompt, source)
            result = flashcards.generate(
                payload.topic, payload.count, payload.language, prompt,
                subject=payload.subject, grade_level=payload.grade_level,
                teaching_style=payload.teaching_style,
            ).data
            gen = AIGeneration(
                instructor_id=instructor_id,
                session_id=payload.session_id,
                type="flashcard",
                topic=payload.topic,
                prompt=payload.prompt or f"Count: {payload.count}, Lang: {payload.language}",
                data_json=json.dumps(result),
            )
            db.add(gen)
            db.commit()
            db.refresh(gen)
            result["id"] = gen.id
        finally:
            db.close()
        _finish_job(job_id, "done", result)
    except Exception as exc:
        _finish_job(job_id, "error", error=str(exc))


def _run_quiz_bg(job_id: str, payload: QuizRequest, instructor_id: int):
    try:
        db = SessionLocal()
        try:
            source = _get_source_context(
            db,
            payload.source_session_id,
            instructor_id,
            getattr(payload, "source_resource_ids", None)
        )
            prompt = _append_source(payload.prompt, source)
            result = quizzes.generate(
                payload.topic, payload.difficulty, payload.count, prompt,
                subject=payload.subject, grade_level=payload.grade_level,
                config_id=payload.config_id,
                teaching_style=payload.teaching_style,
            ).data

            # Apply config settings to quiz if config_id provided
            config_time_limit = None
            config_fullscreen_lock = False
            config_camera_monitoring = False
            if payload.config_id:
                config = db.query(QuizAgentConfig).filter_by(id=payload.config_id, instructor_id=instructor_id).first()
                if config:
                    config_time_limit = config.time_limit_seconds
                    config_fullscreen_lock = config.fullscreen_lock
                    config_camera_monitoring = config.camera_monitoring

            # Idempotent: reuse an identical quiz instead of duplicating it
            quiz = db.query(Quiz).filter_by(
                session_id=payload.session_id, title=result["title"]
            ).first()
            if quiz is None:
                quiz = Quiz(
                    session_id=payload.session_id,
                    title=result["title"],
                    difficulty=result["difficulty"],
                    questions_json=json.dumps(result["questions"]),
                    time_limit_seconds=config_time_limit,
                    fullscreen_lock=config_fullscreen_lock,
                    camera_monitoring=config_camera_monitoring,
                    instructor_id=instructor_id,
                )
                db.add(quiz)
                db.commit()
                db.refresh(quiz)
            result["id"] = quiz.id
            result["time_limit_seconds"] = config_time_limit
            result["fullscreen_lock"] = config_fullscreen_lock
            result["camera_monitoring"] = config_camera_monitoring
        finally:
            db.close()
        _finish_job(job_id, "done", result)
    except Exception as exc:
        _finish_job(job_id, "error", error=str(exc))


def _serialize_video_project(project: VideoProject) -> dict:
    project_dir = VIDEO_STATIC_DIR / f"video-{project.id}"
    scenes = []
    scenes_file = project_dir / "scenes.json"
    if scenes_file.exists():
        try:
            scenes_data = json.loads(scenes_file.read_text(encoding="utf-8"))
            scenes = scenes_data.get("scenes") or []
        except Exception:
            scenes = []
    mp4_path = VIDEO_STATIC_DIR / f"video-{project.id}.mp4"
    audio_path = project_dir / "narration.mp3"
    return {
        "id": project.id,
        "title": project.title,
        "prompt": project.prompt,
        "language": project.language,
        "style": project.style,
        "duration": project.duration,
        "notes": project.notes,
        "status": project.status,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "video_url": project.video_path or f"/static/videos/video-{project.id}/player.html",
        "audio_url": f"/static/videos/video-{project.id}/narration.mp3" if audio_path.exists() else None,
        "mp4_url": f"/static/videos/video-{project.id}.mp4" if mp4_path.exists() else None,
        "scenes": scenes,
        "fallback": not audio_path.exists() and not mp4_path.exists(),
    }


def _format_video_job_error(exc: Exception) -> str:
    """Structured error payload for video jobs: {code, stage, message} as JSON."""
    from app.services.video import VideoStageError
    from app.services.gemini import GeminiError
    if isinstance(exc, VideoStageError):
        return json.dumps(exc.to_dict())
    if isinstance(exc, GeminiError):
        return json.dumps({"code": exc.code, "stage": "script_generation", "message": exc.user_message})
    return json.dumps({"code": "INTERNAL", "stage": "assembly", "message": str(exc)[:500]})


def _raise_video_http(exc: Exception):
    """Convert pipeline exceptions into a 502 with structured detail."""
    from app.services.video import VideoStageError
    from app.services.gemini import GeminiError
    if isinstance(exc, VideoStageError):
        raise HTTPException(status_code=502, detail=exc.to_dict())
    if isinstance(exc, GeminiError):
        raise HTTPException(status_code=502, detail={"code": exc.code, "stage": "script_generation", "message": exc.user_message})
    raise


def _run_video_bg(job_id: str, payload: VideoRequest, instructor_id: int):
    db = SessionLocal()
    project = None
    try:
        source = _get_source_context(
            db,
            payload.source_session_id,
            instructor_id,
            getattr(payload, "source_resource_ids", None)
        )
        notes = _append_source(payload.notes, source)
        project = VideoProject(
            instructor_id=instructor_id,
            title=payload.title,
            prompt=payload.prompt,
            language=payload.language,
            style=payload.style,
            duration=payload.duration,
            notes=notes,
            status="processing",
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        _update_job_progress(job_id, progress=10, message="Generating lesson script...")
        lesson = lessons.generate(
            LessonRequest(
                topic=payload.title,
                prompt=payload.prompt,
                language=payload.language,
                teaching_style=payload.style,
                duration=payload.duration,
                additional_notes=notes,
                session_id=payload.session_id,
                source_session_id=payload.source_session_id,
            )
        ).data
        _update_job_progress(job_id, progress=40, message="Building scenes and narration...")
        video = generate_educational_video(project.id, project.title, lesson)
        _update_job_progress(job_id, progress=85, message="Finalizing video...")
        project.video_path = video["video_url"]
        project.status = "completed"
        if payload.session_id:
            gen = AIGeneration(
                instructor_id=instructor_id,
                session_id=payload.session_id,
                type="video",
                topic=payload.title,
                prompt=payload.prompt,
                data_json=json.dumps({"video_id": project.id, "video_url": video["video_url"]}),
            )
            db.add(gen)
        db.commit()
        db.refresh(project)
        result = _serialize_video_project(project)
        result["lesson"] = lesson
        if video.get("warnings"):
            result["warnings"] = video["warnings"]
        _finish_job(job_id, "done", result)
    except Exception as exc:
        db.rollback()
        if project is not None:
            try:
                project.status = "failed"
                db.commit()
            except Exception:
                db.rollback()
        _finish_job(job_id, "error", error=_format_video_job_error(exc))
    finally:
        db.close()


def _run_video_edit_bg(job_id: str, video_id: int, payload: VideoRequest, instructor_id: int):
    db = SessionLocal()
    try:
        project = db.query(VideoProject).filter_by(id=video_id, instructor_id=instructor_id).first()
        if not project:
            raise HTTPException(404, "Video not found")
        source = _get_source_context(
            db,
            payload.source_session_id,
            instructor_id,
            getattr(payload, "source_resource_ids", None)
        )
        notes = _append_source(payload.notes, source)
        project.title = payload.title
        project.prompt = payload.prompt
        project.language = payload.language
        project.style = payload.style
        project.duration = payload.duration
        project.notes = notes
        project.status = "processing"
        db.commit()
        _update_job_progress(job_id, progress=10, message="Generating lesson script...")
        lesson = lessons.generate(
            LessonRequest(
                topic=payload.title,
                prompt=payload.prompt,
                language=payload.language,
                teaching_style=payload.style,
                duration=payload.duration,
                additional_notes=notes,
                session_id=payload.session_id,
                source_session_id=payload.source_session_id,
            )
        ).data
        _update_job_progress(job_id, progress=40, message="Building scenes and narration...")
        video = generate_educational_video(project.id, project.title, lesson)
        _update_job_progress(job_id, progress=85, message="Finalizing video...")
        project.video_path = video["video_url"]
        project.status = "completed"
        db.commit()
        db.refresh(project)
        result = _serialize_video_project(project)
        result["lesson"] = lesson
        if video.get("warnings"):
            result["warnings"] = video["warnings"]
        _finish_job(job_id, "done", result)
    except Exception as exc:
        db.rollback()
        _finish_job(job_id, "error", error=_format_video_job_error(exc))
    finally:
        db.close()


@router.post("/flashcards")
def generate_flashcards(payload: FlashcardRequest, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    source = _get_source_context(
        db,
        payload.source_session_id,
        user.id,
        getattr(payload, "source_resource_ids", None)
    )
    prompt = _append_source(payload.prompt, source)
    result = flashcards.generate(
        payload.topic, payload.count, payload.language, prompt,
        subject=payload.subject, grade_level=payload.grade_level,
        teaching_style=payload.teaching_style,
    ).data

    # Save to history
    generation = AIGeneration(
        instructor_id=user.id,
        session_id=payload.session_id,
        type="flashcard",
        topic=payload.topic,
        prompt=payload.prompt or f"Count: {payload.count}, Lang: {payload.language}",
        data_json=json.dumps(result)
    )
    db.add(generation)
    db.commit()
    result["id"] = generation.id
    return result


@router.post("/flashcards/export-word")
def export_flashcards_word(payload: FlashcardRequest, _: User = Depends(require_role("instructor"))):
    data = flashcards.generate(payload.topic, payload.count, payload.language, payload.prompt,
                               teaching_style=payload.teaching_style).data
    sections = []
    for index, card in enumerate(data.get("cards") or [], start=1):
        sections.append((f"Flashcard {index}", [f"Front: {card.get('front', '')}", f"Back: {card.get('back', '')}"]))
    filename = f"{data.get('title', 'flashcards').replace(' ', '-')}.doc"
    return StreamingResponse(
        build_word_document_bytes(data.get("title", "Flashcards"), sections),
        media_type="application/msword",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/lessons/export")
def export_lesson(payload: LessonRequest, _: User = Depends(require_role("instructor"))):
    data = lessons.generate(payload).data
    markdown = lesson_to_markdown(data)
    return StreamingResponse(
        iter([markdown.encode("utf-8")]),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{data.get("topic", "lesson").replace(" ", "-")}.md"'},
    )


@router.post("/lessons/export-word")
def export_lesson_word(payload: LessonRequest, _: User = Depends(require_role("instructor"))):
    data = lessons.generate(payload).data
    filename = f"{data.get('topic', 'lesson').replace(' ', '-')}.docx"
    return StreamingResponse(
        build_true_docx_bytes(data.get("topic", "Lesson"), data, "lesson"),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/lessons/export-pptx")
def export_lesson_pptx(payload: LessonRequest, _: User = Depends(require_role("instructor"))):
    data = lessons.generate(payload).data
    filename = f"{data.get('topic', 'lesson').replace(' ', '-')}.pptx"
    return StreamingResponse(
        build_pptx_bytes(data.get("topic", "Lesson"), data),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# â”€â”€â”€ B8: export already-generated content (no regeneration) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ContentExportRequest(BaseModel):
    title: str = "Export"
    content: dict = {}
    include_answers: bool = True


def _safe_filename(title: str, ext: str) -> str:
    import re as _re
    return _re.sub(r"[^A-Za-z0-9_-]+", "-", title or "export").strip("-")[:60] + ext


@router.post("/export/pptx")
def export_content_pptx(payload: ContentExportRequest, _: User = Depends(require_role("instructor"))):
    from app.services.export import build_pptx_bytes
    return StreamingResponse(
        build_pptx_bytes(payload.title, payload.content),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename(payload.title, ".pptx")}"'},
    )


@router.post("/export/pdf")
def export_content_pdf(payload: ContentExportRequest, _: User = Depends(require_role("instructor"))):
    from app.services.export import build_lesson_pdf_bytes, build_quiz_pdf_bytes, build_flashcards_pdf_bytes
    c = payload.content or {}
    if c.get("cards") is not None:
        buf = build_flashcards_pdf_bytes(c)
    elif c.get("questions") is not None:
        buf = build_quiz_pdf_bytes(c, payload.include_answers)
    else:
        buf = build_lesson_pdf_bytes(c)
    return StreamingResponse(
        buf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename(payload.title, ".pdf")}"'},
    )


@router.post("/export/docx")
def export_content_docx(payload: ContentExportRequest, _: User = Depends(require_role("instructor"))):
    from app.services.export import build_quiz_docx_bytes, build_true_docx_bytes
    c = payload.content or {}
    if c.get("questions") is not None:
        buf = build_quiz_docx_bytes(c, payload.include_answers)
    else:
        buf = build_true_docx_bytes(payload.title, c, "lesson")
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename(payload.title, ".docx")}"'},
    )


@router.post("/export/csv")
def export_content_csv(payload: ContentExportRequest, _: User = Depends(require_role("instructor"))):
    from app.services.export import build_flashcards_csv_bytes
    return StreamingResponse(
        build_flashcards_csv_bytes(payload.content or {}),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename(payload.title, ".csv")}"'},
    )


@router.get("/quizzes/{quiz_id}/download")
def download_quiz(quiz_id: int, db: Session = Depends(get_db), _: User = Depends(require_role("instructor"))):
    quiz = db.query(Quiz).filter_by(id=quiz_id).first()
    if not quiz:
        raise HTTPException(404, "Quiz not found")
    data = {"title": quiz.title, "difficulty": quiz.difficulty, "questions": json.loads(quiz.questions_json)}
    return StreamingResponse(
        build_json_bytes(data),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="quiz-{quiz_id}.json"'},
    )


@router.get("/quizzes/{quiz_id}/download-word")
def download_quiz_word(quiz_id: int, db: Session = Depends(get_db), _: User = Depends(require_role("instructor"))):
    quiz = db.query(Quiz).filter_by(id=quiz_id).first()
    if not quiz:
        raise HTTPException(404, "Quiz not found")
    questions = json.loads(quiz.questions_json)
    sections = []
    for index, question in enumerate(questions, start=1):
        content = [question.get("question", "")]
        for option in question.get("options") or []:
            content.append(option)
        content.append(f"Answer: {question.get('answer', '')}")
        if question.get("explanation"):
            content.append(f"Explanation: {question['explanation']}")
        sections.append((f"Question {index}", content))
    filename = f"quiz-{quiz_id}.doc"
    return StreamingResponse(
        build_word_document_bytes(quiz.title, sections),
        media_type="application/msword",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/videos/{video_id}/download")
def download_video(video_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    project = db.query(VideoProject).filter_by(id=video_id, instructor_id=user.id).first()
    if not project:
        raise HTTPException(404, "Video not found")
    archive = build_video_zip(video_id)
    if not archive:
        raise HTTPException(404, "Video files not found")
    safe_title = project.title.replace(" ", "-")[:40]
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}-video-{video_id}.zip"'},
    )


@router.get("/videos/{video_id}/script-docx")
def download_video_script_docx(video_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    from io import BytesIO
    from docx import Document
    project = db.query(VideoProject).filter_by(id=video_id, instructor_id=user.id).first()
    if not project:
        raise HTTPException(404, "Video not found")
    project_dir = VIDEO_STATIC_DIR / f"video-{project.id}"
    scenes_file = project_dir / "scenes.json"
    scenes = []
    if scenes_file.exists():
        try:
            scenes = json.loads(scenes_file.read_text(encoding="utf-8")).get("scenes", [])
        except Exception:
            pass
    doc = Document()
    doc.add_heading(f"{project.title} â€” Video Script", level=0)
    p_meta = doc.add_paragraph()
    p_meta.add_run(f"Duration: {project.duration} mins | Style: {project.style} | Language: {project.language}").italic = True
    doc.add_heading("Script Narration by Scene", level=1)
    if scenes:
        for idx, sc in enumerate(scenes, 1):
            doc.add_heading(f"Scene {idx}: {sc.get('title', f'Scene {idx}')}", level=2)
            doc.add_paragraph(sc.get("narration") or sc.get("content") or "")
            if sc.get("bullets"):
                for b in sc.get("bullets"):
                    doc.add_paragraph(b, style="List Bullet")
    else:
        doc.add_paragraph(project.prompt)
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    safe_title = _safe_filename(project.title + "-script", ".docx")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}"'},
    )


@router.get("/videos/{video_id}/script-pdf")
def download_video_script_pdf(video_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    from app.services.export import _pdf_doc
    project = db.query(VideoProject).filter_by(id=video_id, instructor_id=user.id).first()
    if not project:
        raise HTTPException(404, "Video not found")
    project_dir = VIDEO_STATIC_DIR / f"video-{project.id}"
    scenes_file = project_dir / "scenes.json"
    scenes = []
    if scenes_file.exists():
        try:
            scenes = json.loads(scenes_file.read_text(encoding="utf-8")).get("scenes", [])
        except Exception:
            pass
    blocks = [
        ("Metadata", [
            f"Duration: {project.duration} minutes",
            f"Language: {project.language}",
            f"Style: {project.style}",
        ])
    ]
    if scenes:
        for idx, sc in enumerate(scenes, 1):
            lines = [sc.get("narration") or sc.get("content") or ""]
            if sc.get("bullets"):
                lines += [f"â€¢ {b}" for b in sc.get("bullets")]
            blocks.append((f"Scene {idx}: {sc.get('title', '')}", lines))
    else:
        blocks.append(("Script", [project.prompt]))
    buf = _pdf_doc(f"{project.title} â€” Script", blocks)
    safe_title = _safe_filename(project.title + "-script", ".pdf")
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}"'},
    )


@router.get("/videos/{video_id}/subtitles-srt")
def download_video_subtitles_srt(video_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    import io
    project = db.query(VideoProject).filter_by(id=video_id, instructor_id=user.id).first()
    if not project:
        raise HTTPException(404, "Video not found")
    project_dir = VIDEO_STATIC_DIR / f"video-{project.id}"
    srt_file = project_dir / "subtitles.srt"
    if srt_file.exists():
        srt_content = srt_file.read_text(encoding="utf-8")
    else:
        scenes_file = project_dir / "scenes.json"
        scenes = []
        if scenes_file.exists():
            try:
                scenes = json.loads(scenes_file.read_text(encoding="utf-8")).get("scenes", [])
            except Exception:
                pass
        lines = []
        current_s = 0.0
        for idx, sc in enumerate(scenes, 1):
            dur = float(sc.get("duration_seconds") or 8.0)
            start_s = current_s
            end_s = current_s + dur
            current_s = end_s

            def _fmt(s):
                hrs = int(s // 3600)
                mins = int((s % 3600) // 60)
                secs = int(s % 60)
                millis = int((s - int(s)) * 1000)
                return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

            text = (sc.get("narration") or sc.get("content") or "").strip()
            lines.append(f"{idx}\n{_fmt(start_s)} --> {_fmt(end_s)}\n{text}\n")
        srt_content = "\n".join(lines) if lines else f"1\n00:00:00,000 --> 00:00:05,000\n{project.title}\n"

    buf = io.BytesIO(srt_content.encode("utf-8"))
    safe_title = _safe_filename(project.title + "-subtitles", ".srt")
    return StreamingResponse(
        buf,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}"'},
    )


@router.post("/lessons")
def generate_lesson(payload: LessonRequest, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    source = _get_source_context(
        db,
        payload.source_session_id,
        user.id,
        getattr(payload, "source_resource_ids", None)
    )
    enriched = payload.model_copy(update={
        "additional_notes": _append_source(payload.additional_notes, source),
    })
    result = lessons.generate(enriched).data  # subject/grade_level are on enriched

    # Save to history
    generation = AIGeneration(
        instructor_id=user.id,
        session_id=payload.session_id,
        type="lesson",
        topic=payload.topic,
        prompt=payload.prompt,
        data_json=json.dumps(result)
    )
    db.add(generation)
    db.commit()
    result["id"] = generation.id
    return result


@router.post("/quizzes")
def generate_quiz(payload: QuizRequest, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    source = _get_source_context(
        db,
        payload.source_session_id,
        user.id,
        getattr(payload, "source_resource_ids", None)
    )
    prompt = _append_source(payload.prompt, source)
    result = quizzes.generate(
        payload.topic, payload.difficulty, payload.count, prompt,
        subject=payload.subject, grade_level=payload.grade_level,
        config_id=payload.config_id,
    ).data

    # Apply config settings to quiz if config_id provided
    config_time_limit = None
    config_fullscreen_lock = False
    config_camera_monitoring = False
    if payload.config_id:
        config = db.query(QuizAgentConfig).filter_by(id=payload.config_id, instructor_id=user.id).first()
        if config:
            config_time_limit = config.time_limit_seconds
            config_fullscreen_lock = config.fullscreen_lock
            config_camera_monitoring = config.camera_monitoring

    quiz = db.query(Quiz).filter_by(
        session_id=payload.session_id, title=result["title"]
    ).first()
    if quiz is None:
        quiz = Quiz(
            session_id=payload.session_id,
            title=result["title"],
            difficulty=result["difficulty"],
            questions_json=json.dumps(result["questions"]),
            time_limit_seconds=config_time_limit,
            fullscreen_lock=config_fullscreen_lock,
            camera_monitoring=config_camera_monitoring,
            instructor_id=user.id,
        )
        db.add(quiz)
        db.commit()
    result["id"] = quiz.id
    result["time_limit_seconds"] = config_time_limit
    result["fullscreen_lock"] = config_fullscreen_lock
    result["camera_monitoring"] = config_camera_monitoring
    return result


@router.get("/quizzes")
def list_quizzes(db: Session = Depends(get_db), _: User = Depends(require_role("instructor"))):
    quizzes_list = db.query(Quiz).order_by(Quiz.created_at.desc()).all()
    result = []
    for q in quizzes_list:
        session_name = None
        enrolled_count = None
        if q.session_id:
            sess = db.query(ClassSession).filter_by(id=q.session_id).first()
            if sess:
                session_name = sess.title
                enrolled_count = db.query(SessionRegistration).filter_by(session_id=q.session_id).count()
        result.append({
            "id": q.id,
            "session_id": q.session_id,
            "session_title": session_name,
            "title": q.title,
            "difficulty": normalize_difficulty(q.difficulty),
            "created_at": q.created_at,
            "questions": json.loads(q.questions_json),
            "is_published": getattr(q, "is_published", True),
            "is_exam": getattr(q, "is_exam", False),
            "lock_back_navigation": getattr(q, "lock_back_navigation", False),
            "fullscreen_lock": getattr(q, "fullscreen_lock", False),
            "camera_monitoring": getattr(q, "camera_monitoring", False),
            "time_limit_seconds": q.time_limit_seconds,
            "time_limit_per_question_seconds": q.time_limit_per_question_seconds,
            "due_date": q.due_date,
            "available_from": q.available_from,
            # B4.3: publish visibility
            "enrolled_student_count": enrolled_count,
        })
    return result


@router.delete("/quizzes/{quiz_id}")
def delete_quiz(quiz_id: int, db: Session = Depends(get_db), _: User = Depends(require_role("instructor"))):
    deleted = db.query(Quiz).filter_by(id=quiz_id).delete()
    db.commit()
    if not deleted:
        raise HTTPException(404, "Quiz not found")
    return {"message": "Quiz deleted"}


# â”€â”€â”€ Quiz Agent Config Endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/quiz-configs", response_model=QuizAgentConfigOut)
def create_quiz_config(
    payload: QuizAgentConfigCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor"))
):
    """
    Create a reusable quiz generation configuration.
    Stores difficulty mix, question types, topic weights, time limits, and anti-cheat settings.
    """
    config = QuizAgentConfig(
        instructor_id=user.id,
        session_id=payload.session_id,
        name=payload.name,
        subject=payload.subject,
        grade_level=payload.grade_level,
        difficulty_mix=json.dumps(payload.difficulty_mix) if payload.difficulty_mix else None,
        question_types=json.dumps(payload.question_types) if payload.question_types else None,
        topic_weights=json.dumps(payload.topic_weights) if payload.topic_weights else None,
        time_limit_seconds=payload.time_limit_seconds,
        fullscreen_lock=payload.fullscreen_lock,
        camera_monitoring=payload.camera_monitoring,
        custom_prompt=payload.custom_prompt,
    )
    db.add(config)
    db.commit()
    db.refresh(config)

    # Audit
    log_audit_event(db, action="create_quiz_config", user=user, resource_type="quiz_config", resource_id=str(config.id), request=request, details={"name": config.name})

    return QuizAgentConfigOut.model_validate(config)


@router.get("/quiz-configs", response_model=list[QuizAgentConfigOut])
def list_quiz_configs(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor"))
):
    """List all quiz generation configurations for the instructor."""
    configs = db.query(QuizAgentConfig).filter_by(instructor_id=user.id).order_by(QuizAgentConfig.updated_at.desc()).all()
    return [QuizAgentConfigOut.model_validate(c) for c in configs]


@router.get("/quiz-configs/{config_id}", response_model=QuizAgentConfigOut)
def get_quiz_config(
    config_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor"))
):
    """Get a specific quiz generation configuration."""
    config = db.query(QuizAgentConfig).filter_by(id=config_id, instructor_id=user.id).first()
    if not config:
        raise HTTPException(404, "Quiz config not found")
    return QuizAgentConfigOut.model_validate(config)


@router.put("/quiz-configs/{config_id}", response_model=QuizAgentConfigOut)
def update_quiz_config(
    config_id: int,
    payload: QuizAgentConfigUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor"))
):
    """Update a quiz generation configuration."""
    config = db.query(QuizAgentConfig).filter_by(id=config_id, instructor_id=user.id).first()
    if not config:
        raise HTTPException(404, "Quiz config not found")

    config.name = payload.name
    config.session_id = payload.session_id
    config.subject = payload.subject
    config.grade_level = payload.grade_level
    config.difficulty_mix = json.dumps(payload.difficulty_mix) if payload.difficulty_mix else None
    config.question_types = json.dumps(payload.question_types) if payload.question_types else None
    config.topic_weights = json.dumps(payload.topic_weights) if payload.topic_weights else None
    config.time_limit_seconds = payload.time_limit_seconds
    config.fullscreen_lock = payload.fullscreen_lock
    config.camera_monitoring = payload.camera_monitoring
    config.custom_prompt = payload.custom_prompt

    db.commit()
    db.refresh(config)

    # Audit
    log_audit_event(db, action="update_quiz_config", user=user, resource_type="quiz_config", resource_id=str(config.id), request=request, details={"name": config.name})

    return QuizAgentConfigOut.model_validate(config)


@router.delete("/quiz-configs/{config_id}")
def delete_quiz_config(
    config_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor"))
):
    """Delete a quiz generation configuration."""
    config = db.query(QuizAgentConfig).filter_by(id=config_id, instructor_id=user.id).first()
    if not config:
        raise HTTPException(404, "Quiz config not found")

    config_name = config.name
    db.delete(config)
    db.commit()

    # Audit
    log_audit_event(db, action="delete_quiz_config", user=user, resource_type="quiz_config", resource_id=str(config_id), request=request, details={"name": config_name})

    return {"message": "Quiz config deleted"}


@router.get("/generations")
def list_generations(type: str | None = None, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    query = db.query(AIGeneration).filter_by(instructor_id=user.id)
    if type and type != "quiz":
        query = query.filter_by(type=type)
    # Quiz-type AIGeneration rows mirror Quiz records (appended below) â€”
    # listing both would show every quiz twice.
    query = query.filter(AIGeneration.type != "quiz")
    generations = query.order_by(AIGeneration.created_at.desc()).all()
    out = [
        {
            "id": g.id,
            "type": g.type,
            "topic": g.topic,
            "prompt": g.prompt,
            "session_id": g.session_id,
            "created_at": g.created_at,
            "data": json.loads(g.data_json) if g.data_json else {}
        }
        for g in generations
    ]
    if type is None or type == "quiz":
        quizzes = db.query(Quiz).order_by(Quiz.created_at.desc()).all()
        for q in quizzes:
            out.append({
                "id": q.id,
                "type": "quiz",
                "topic": q.title,
                "prompt": f"Quiz Â· {q.difficulty}",
                "session_id": q.session_id,
                "created_at": q.created_at,
                "data": {"title": q.title, "difficulty": q.difficulty}
            })
    return out


@router.get("/generations/{gen_id}")
def get_generation(gen_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    """Get the latest data for a single AI generation."""
    g = db.query(AIGeneration).filter_by(id=gen_id, instructor_id=user.id).first()
    if not g:
        raise HTTPException(404, "Generation not found")
    try:
        data = json.loads(g.data_json)
    except Exception:
        data = {}
    return {
        "id": g.id,
        "type": g.type,
        "topic": g.topic,
        "prompt": g.prompt,
        "session_id": g.session_id,
        "created_at": g.created_at,
        "data": data,
    }


@router.delete("/generations/{gen_id}")
def delete_generation(gen_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    deleted = db.query(AIGeneration).filter_by(id=gen_id, instructor_id=user.id).delete()
    db.commit()
    if not deleted:
        raise HTTPException(404, "Generation not found")
    return {"message": "Generation deleted"}


# â”€â”€ Background-safe queue endpoints (generation continues even if tab closes) â”€â”€â”€

@router.post("/lessons/queue")
def queue_lesson(payload: LessonRequest, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    """Starts lesson generation in a background thread. Returns job_id immediately."""
    job_id = str(uuid.uuid4())
    _persist_job(job_id, user.id, "lesson", payload.topic)
    t = threading.Thread(target=_run_lesson_bg, args=(job_id, payload, user.id), daemon=True)
    t.start()
    return {"job_id": job_id, "status": "pending"}


@router.post("/flashcards/queue")
def queue_flashcard(payload: FlashcardRequest, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    job_id = str(uuid.uuid4())
    _persist_job(job_id, user.id, "flashcard", payload.topic)
    t = threading.Thread(target=_run_flashcard_bg, args=(job_id, payload, user.id), daemon=True)
    t.start()
    return {"job_id": job_id, "status": "pending"}


@router.post("/quizzes/queue")
def queue_quiz(payload: QuizRequest, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    job_id = str(uuid.uuid4())
    _persist_job(job_id, user.id, "quiz", payload.topic)
    t = threading.Thread(target=_run_quiz_bg, args=(job_id, payload, user.id), daemon=True)
    t.start()
    return {"job_id": job_id, "status": "pending"}


@router.post("/videos/queue")
def queue_video(payload: VideoRequest, _: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    """Starts video generation in a background thread. Returns job_id immediately."""
    job_id = str(uuid.uuid4())
    _persist_job(job_id, user.id, "video", payload.title)
    t = threading.Thread(target=_run_video_bg, args=(job_id, payload, user.id), daemon=True)
    t.start()
    return {"job_id": job_id, "status": "pending"}


@router.post("/videos/{video_id}/edit/queue")
def queue_video_edit(video_id: int, payload: VideoRequest, _: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    job_id = str(uuid.uuid4())
    _persist_job(job_id, user.id, "video-edit", payload.title)
    t = threading.Thread(target=_run_video_edit_bg, args=(job_id, video_id, payload, user.id), daemon=True)
    t.start()
    return {"job_id": job_id, "status": "pending"}


@router.get("/jobs/pending")
def pending_jobs(db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    return list_pending_jobs(db, user.id)


@router.get("/job/{job_id}")
def poll_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    """Poll the status of a background generation job."""
    with _jobs_lock:
        cached = _jobs.get(job_id)
    if cached:
        return cached
    payload = get_job_payload(db, job_id, user.id)
    if payload:
        return payload
    raise HTTPException(404, "Job not found")


@router.get("/available-models")
def available_models(user: User = Depends(get_current_user)):
    """Healthy models across configured LLM providers for UI dropdowns.

    Returns "Auto" first, followed by:
      - Free-tier cloud models for providers with valid API keys (live-probed at startup)
      - Installed Ollama local models with "Offline" badge (if Ollama is reachable)
    Dead, cooling, or providers with no keys are excluded.
    """
    from app.services import llm
    from app.core.config import get_settings
    settings = get_settings()
    allow_paid = getattr(settings, "allow_paid_models", False)

    now = time.time()
    healthy = [
        {"provider": "auto", "model": "auto", "label": "Auto (best free model)"}
    ]
    seen: set[tuple[str, str]] = set()

    for provider, key_idx, _, model in llm.router.candidates("general"):
        if (provider, model) in seen:
            continue

        # Ollama local models get the "Offline" badge â€” always free
        if provider == "ollama":
            seen.add((provider, model))
            healthy.append({
                "provider": "ollama",
                "model": model,
                "label": f"ollama: {model}",
                "free_tier": True,
                "is_local": True,
                "badge": "Offline",
            })
            continue

        # C16: Filter by free tier if paid models not allowed
        if not allow_paid:
            profile = llm.router.get_model_profile(provider, model)
            is_free = profile.get("free_tier", profile.get("cost") == "free")
            if provider == "openrouter" and not model.endswith(":free"):
                is_free = False
            if provider == "deepinfra":
                is_free = False
            if not is_free:
                continue

        st = llm.router._states.get((provider, key_idx, model))
        gb = llm.router._group_blocked(provider, llm.router.key_group(provider, key_idx), model)
        disabled = bool(st and st.disabled)
        cooling = bool((st and st.cooldown_until > now) or gb > 0)
        if not disabled and not cooling:
            seen.add((provider, model))
            healthy.append({
                "provider": provider,
                "model": model,
                "label": f"{provider}: {model}",
                "free_tier": True,
            })
    return {"models": healthy}


@router.get("/engagement/{session_id}")
def get_engagement(session_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return engagement.calculate(db, session_id).data


class RecommendationsQueueRequest(BaseModel):
    session_id: str | int = "all"
    session_ids: list[int] | None = None
    selected_count: int | None = None  # number of sessions the user requested


def _resolve_recommendation_sessions(db: Session, instructor_id: int,
                                     session_id_arg: str | int,
                                     session_ids: list[int] | None) -> list:
    """Sessions owned by the instructor, reconciling stale statuses."""
    from app.api.sessions import reconcile_session_statuses
    reconcile_session_statuses(db)

    query = db.query(ClassSession).filter(
        ClassSession.instructor_id == instructor_id,
        ClassSession.status == "ended",
    )
    if session_ids:
        query = query.filter(ClassSession.id.in_([int(i) for i in session_ids]))
    elif str(session_id_arg) != "all":
        query = query.filter(ClassSession.id == int(session_id_arg))
    return query.all()


def _run_recommendations_bg(job_id: str, session_id_arg: str | int,
                            session_ids: list[int] | None, instructor_id: int | None = None,
                            selected_count: int | None = None):
    """Runs feedback loop analysis in background thread so it survives tab closes."""
    if instructor_id is None and isinstance(session_ids, int):
        instructor_id = session_ids
        session_ids = None
    db = SessionLocal()
    try:
        cache_key = f"{instructor_id}:{session_id_arg}:{sorted(session_ids or [])}"
        _update_job_progress(job_id, progress=15, message="Finding ended sessions...")

        ended = _resolve_recommendation_sessions(db, instructor_id, session_id_arg, session_ids)
        if not ended:
            _finish_job(job_id, "error", error="No ended sessions found to analyze.")
            return

        _update_job_progress(job_id, progress=35, message="Computing student emotion telemetry...")

        results = []
        for i, s in enumerate(ended):
            single_cache_key = f"{instructor_id}:{s.id}"
            if single_cache_key in _analytics_cache:
                results.append(_analytics_cache[single_cache_key])
                continue

            pct = 35 + int(((i + 1) / max(len(ended), 1)) * 40)
            _update_job_progress(job_id, progress=pct, message=f"Analyzing session: {s.title}...")

            emotion_report = workflow.emotions.distributions(db, s.id).data
            engagement_report = workflow.engagement.calculate(db, s.id).data
            from app.services.report_data import assess_session_data, insufficient_data_message, session_metrics
            _assessment = assess_session_data(db, s.id)
            _metrics = session_metrics(db, s.id, _assessment)
            _metrics["sufficient_data"] = _assessment["sufficient"]
            rec_report = workflow.recommendations.recommend(
                engagement_report, emotion_report, metrics=_metrics
            ).data

            res_item = {
                "session_id": s.id,
                "session_title": s.title,
                "emotion_report": emotion_report,
                "engagement_report": engagement_report,
                "recommendations": rec_report,
                "sufficiency": {
                    "sufficient": _assessment["sufficient"],
                    "missing": _assessment["missing"],
                    "checks": _assessment["checks"],
                    "message": None if _assessment["sufficient"] else insufficient_data_message(_assessment),
                },
            }
            _analytics_cache[single_cache_key] = res_item
            results.append(res_item)

        _update_job_progress(job_id, progress=85, message="Synthesizing pedagogical recommendations...")

        rec_list = list(dict.fromkeys(r for res in results for r in res.get("recommendations", {}).get("recommendations", [])))
        insufficient_sessions = [
            {"session_id": res["session_id"], "session_title": res["session_title"],
             "missing": res["sufficiency"]["missing"], "message": res["sufficiency"]["message"]}
            for res in results if not res["sufficiency"]["sufficient"]
        ]
        sufficient_count = len(results) - len(insufficient_sessions)
        insufficient = bool(insufficient_sessions)
        session_breakdown = [
            {
                "session_id": res["session_id"],
                "session_title": res["session_title"],
                "status": "analyzed" if res["sufficiency"]["sufficient"] else "insufficient",
                "missing": res["sufficiency"]["missing"],
                "message": res["sufficiency"]["message"] or "Analyzed successfully",
            }
            for res in results
        ]
        aggregate_dist = {}
        for res in results:
            dist = res.get("emotion_report", {}).get("distribution", {})
            for emo, val in dist.items():
                aggregate_dist[emo] = aggregate_dist.get(emo, 0) + val

        final_result = {
            "session_id": session_id_arg,
            "recommendations": {
                "recommendations": rec_list,
                "insufficient_data": insufficient,
                "sufficient_sessions": sufficient_count,
                "total_sessions": len(results),
                "selected_sessions": selected_count if selected_count is not None else len(results),
                "insufficient_sessions": insufficient_sessions,
                "session_breakdown": session_breakdown,
                "message": (f"{sufficient_count} of {len(results)} selected session(s) analyzed."
                            + (f" ({len(insufficient_sessions)} lack enough data)" if insufficient_sessions else "")),
            },
            "emotion_report": {"distribution": aggregate_dist},
            "engagement_report": results[0].get("engagement_report", {"attention_timeline": []}) if results else {"attention_timeline": []},
        }

        _analytics_cache[cache_key] = final_result
        _update_job_progress(job_id, progress=100, message="Analysis complete!")
        _finish_job(job_id, "done", final_result)
    except Exception as exc:
        _finish_job(job_id, "error", error=str(exc))
    finally:
        db.close()


@router.post("/recommendations/queue")
def queue_recommendations(
    payload: RecommendationsQueueRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor"))
):
    """Starts dashboard feedback loop analysis in background. Returns job_id immediately."""
    # Quick check if cached
    cache_key = f"{user.id}:{payload.session_id}:{sorted(payload.session_ids or [])}"
    if cache_key in _analytics_cache:
        job_id = str(uuid.uuid4())
        _persist_job(job_id, user.id, "analytics", "Dashboard Analysis")
        _finish_job(job_id, "done", _analytics_cache[cache_key])
        return {"job_id": job_id, "status": "done", "result": _analytics_cache[cache_key]}

    job_id = str(uuid.uuid4())
    _persist_job(job_id, user.id, "analytics", "Dashboard Analysis")
    t = threading.Thread(target=_run_recommendations_bg,
                         args=(job_id, payload.session_id, payload.session_ids, user.id, payload.selected_count), daemon=True)
    t.start()
    return {"job_id": job_id, "status": "pending"}


@router.get("/recommendations/{session_id}")
def get_recommendations(session_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    cache_key = f"{user.id}:{session_id}"
    if cache_key in _analytics_cache:
        return _analytics_cache[cache_key]

    loop = workflow.improvement_loop(db, session_id)
    report = Report(session_id=session_id, summary=loop["report"]["summary"], pdf_path=loop["report"]["pdf_path"])
    db.add(report)
    db.commit()
    _analytics_cache[cache_key] = loop
    return loop


@router.post("/recommendations/{session_id}/decision")
def decide_recommendation(session_id: int, payload: RecommendationDecision, _: User = Depends(require_role("instructor"))):
    return {"session_id": session_id, "accepted": payload.accepted, "action": payload.action or "noted"}


@router.post("/videos")
def create_video(payload: VideoRequest, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    source = _get_source_context(
        db,
        payload.source_session_id,
        user.id,
        getattr(payload, "source_resource_ids", None)
    )
    notes = _append_source(payload.notes, source)
    project = VideoProject(instructor_id=user.id, title=payload.title, prompt=payload.prompt, language=payload.language, style=payload.style, duration=payload.duration, notes=notes, status="processing")
    db.add(project)
    db.commit()
    db.refresh(project)
    try:
        lesson = lessons.generate(LessonRequest(topic=payload.title, prompt=payload.prompt, language=payload.language, teaching_style=payload.style, duration=payload.duration, additional_notes=notes, session_id=payload.session_id, source_session_id=payload.source_session_id)).data
        video = generate_educational_video(project.id, project.title, lesson)
    except Exception as exc:
        project.status = "failed"
        db.commit()
        _raise_video_http(exc)
    project.video_path = video["video_url"]
    project.status = "completed"
    db.commit()
    result = _serialize_video_project(project)
    result["lesson"] = lesson
    if video.get("warnings"):
        result["warnings"] = video["warnings"]
    return result


@router.post("/videos/{video_id}/edit")
def edit_video(
    video_id: int,
    payload: VideoRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor")),
):
    project = db.query(VideoProject).filter_by(id=video_id, instructor_id=user.id).first()
    if not project:
        raise HTTPException(404, "Video not found")
    source = _get_source_context(
        db,
        payload.source_session_id,
        user.id,
        getattr(payload, "source_resource_ids", None)
    )
    notes = _append_source(payload.notes, source)
    project.title = payload.title
    project.prompt = payload.prompt
    project.language = payload.language
    project.style = payload.style
    project.duration = payload.duration
    project.notes = notes
    project.status = "processing"
    db.commit()

    try:
        lesson = lessons.generate(
            LessonRequest(
                topic=payload.title,
                prompt=payload.prompt,
                language=payload.language,
                teaching_style=payload.style,
                duration=payload.duration,
                additional_notes=notes,
                session_id=payload.session_id,
                source_session_id=payload.source_session_id,
            )
        ).data
        video = generate_educational_video(project.id, project.title, lesson)
    except Exception as exc:
        project.status = "failed"
        db.commit()
        _raise_video_http(exc)
    project.video_path = video["video_url"]
    project.status = "completed"
    db.commit()
    response = _serialize_video_project(project)
    response["lesson"] = lesson
    if video.get("warnings"):
        response["warnings"] = video["warnings"]
    return response


@router.get("/videos/{video_id}")
def get_video(video_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    project = db.query(VideoProject).filter_by(id=video_id, instructor_id=user.id).first()
    if not project:
        raise HTTPException(404, "Video not found")
    return _serialize_video_project(project)


@router.put("/videos/{video_id}/scenes")
def update_video_scenes(
    video_id: int,
    payload: VideoScenesUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor")),
):
    """
    Update a video's scenes (titles, narration, duration_seconds) and re-render
    the player HTML + re-TTS each segment + re-stitch MP4 (when ffmpeg available).
    Does NOT re-generate the lesson â€” edits are applied directly to the scenes.
    """
    project = db.query(VideoProject).filter_by(id=video_id, instructor_id=user.id).first()
    if not project:
        raise HTTPException(404, "Video not found")

    title = payload.title or project.title
    language = payload.language or project.language or "English"
    scenes_data = [s.model_dump() for s in payload.scenes]

    result = rebuild_video_from_scenes(
        project_id=video_id,
        title=title,
        scenes=scenes_data,
        language=language,
        re_tts=True,
    )
    # Update DB record
    project.title = title
    project.language = language
    project.video_path = result["video_url"]
    project.status = "completed"
    db.commit()
    db.refresh(project)

    serialized = _serialize_video_project(project)
    serialized["scenes"] = result["scenes"]
    serialized["fallback"] = result["fallback"]
    serialized["duration_warning"] = result["duration_warning"]
    return serialized


@router.get("/videos")
def list_videos(db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    projects = db.query(VideoProject).filter_by(instructor_id=user.id).order_by(VideoProject.created_at.desc()).all()
    return [_serialize_video_project(project) for project in projects]


@router.delete("/videos/{video_id}")
def delete_video(video_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    deleted = db.query(VideoProject).filter_by(id=video_id, instructor_id=user.id).delete()
    db.commit()
    if not deleted:
        raise HTTPException(404, "Video not found")
    return {"message": "Video deleted"}


# â”€â”€â”€ Gemini Health Diagnostics â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/gemini-health")
def gemini_health(user: User = Depends(require_role("instructor"))):
    """
    Probe every configured (key, model) pair with a tiny prompt.
    Returns masked keys only â€” never key material.
    """
    from app.services.gemini import rotator
    import concurrent.futures

    keys = rotator.get_keys()
    models = rotator.model_chain("general")
    pairs = [(i, k, m) for i, k in enumerate(keys) for m in models]

    def probe(idx, key, model):
        t0 = time.time()
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={key}")
        body = json.dumps({"contents": [{"parts": [{"text": "Reply with the word: ok"}]}],
                           "generationConfig": {"maxOutputTokens": 8}}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                payload = json.loads(r.read().decode())
            text = "".join(p.get("text", "") for p in (payload.get("candidates") or [{}])[0].get("content", {}).get("parts") or [])
            return {"key_index": idx, "key_masked": rotator.mask_key(key), "model": model,
                    "healthy": bool(text.strip()), "latency_ms": round((time.time() - t0) * 1000),
                    "response": text.strip()[:40]}
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode()[:200]
            except Exception:
                pass
            return {"key_index": idx, "key_masked": rotator.mask_key(key), "model": model,
                    "healthy": False, "latency_ms": round((time.time() - t0) * 1000),
                    "error": f"HTTP {exc.code}: {detail[:120]}"}
        except Exception as exc:
            return {"key_index": idx, "key_masked": rotator.mask_key(key), "model": model,
                    "healthy": False, "latency_ms": round((time.time() - t0) * 1000),
                    "error": str(exc)[:120]}

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futures = [ex.submit(probe, i, k, m) for i, k, m in pairs]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())
    results.sort(key=lambda r: (r["key_index"], r["model"]))
    return {
        "total_keys": len(keys),
        "models_tested": models,
        "healthy_pairs": sum(1 for r in results if r["healthy"]),
        "total_pairs": len(results),
        "results": results,
        "rotator_state": rotator.status(),
    }


# â”€â”€â”€ Chat Endpoint â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _get_chatbot_settings():
    """Return (name, persona) from config, cached."""
    from app.core.config import get_settings
    s = get_settings()
    return s.chatbot_name, s.chatbot_persona


def _build_chat_query(message: str, file_context: str | None) -> str:
    """Prepend uploaded file context to the user message if present."""
    if file_context and file_context.strip():
        return f"[Uploaded file context]\n{file_context.strip()}\n\n[User question]\n{message}"
    return message


@router.post("/enhance-prompt")
def enhance_prompt(payload: EnhancePromptRequest, user: User = Depends(get_current_user)):
    """Rewrite a generation prompt into a clearer instruction.

    Preserves the user's language, intent, and all concrete constraints
    (topic, duration, counts, level). Uses the cheap 'prompt_enhance'
    provider chain; never trains on data (chat-completions only).
    """
    from app.services import llm

    prompt_text = (payload.prompt or "").strip()
    if not prompt_text:
        raise HTTPException(400, "Prompt is required")
    if len(prompt_text) > 8000:
        raise HTTPException(400, "Prompt is too long")

    ctx = {k: v for k, v in (payload.context or {}).items() if v not in (None, "", [], {})}
    context_line = "; ".join(f"{k}: {v}" for k, v in ctx.items()) or "none"

    instruction = (
        "You are a prompt engineer for an educational content generator. "
        "Rewrite the user's prompt into a clearer, more effective instruction. "
        "Improve clarity, audience, structure and constraints while preserving "
        "the user's intent AND their language (Arabic stays Arabic, mixed stays mixed). "
        "Never change concrete values such as duration, question counts, topics or languages. "
        "Return ONLY the improved prompt text â€” no preamble, no quotes, no explanation.\n\n"
        f"Form context: {context_line}\n\n"
        f"User prompt:\n{prompt_text}"
    )
    try:
        enhanced = llm.chat(instruction, task_type="prompt_enhance",
                            temperature=0.4, timeout=45)
    except Exception as exc:
        raise HTTPException(502, f"PROMPT_ENHANCE_FAILED: {exc}")

    enhanced = (enhanced or "").strip().strip('"').strip()
    if not enhanced:
        raise HTTPException(502, "INVALID_RESPONSE: enhancer returned empty text")
    return {"prompt": enhanced}


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    user: User = Depends(get_current_user),
):
    """
    Educational chat with RAG + Web Search + LLM orchestration.
    Returns answer with sources and mode metadata.
    Rate limited: 30 requests/minute per user.
    Persists conversation history by conversation_id.
    Supports chatbot identity (name/persona from config) and file context injection.
    """
    _check_rate_limit(user)

    bot_name, bot_persona = _get_chatbot_settings()

    # Generate or use existing conversation_id
    conversation_id = payload.conversation_id or str(uuid.uuid4())

    # Load history from DB if conversation_id provided and history not in request
    history = []
    if payload.conversation_id and not payload.conversation_history:
        db = SessionLocal()
        try:
            messages = db.query(ChatMessageModel).filter_by(
                conversation_id=payload.conversation_id,
                user_id=user.id
            ).order_by(ChatMessageModel.created_at, ChatMessageModel.id).all()
            history = [{"role": m.role, "content": m.content} for m in messages]
        finally:
            db.close()
    else:
        history = [{"role": msg.role, "content": msg.content} for msg in payload.conversation_history]

    effective_query = _build_chat_query(payload.message, payload.file_context)

    # Inject chatbot persona as a leading system context in the query
    persona_prefix = f"[System: Your name is {bot_name}. {bot_persona}]\n\n" if bot_persona else ""
    final_query = persona_prefix + effective_query

    result = await orchestrator._run_async(
        query=final_query,
        subject=payload.subject,
        grade_level=payload.grade_level,
        conversation_history=history,
        source_id=payload.source_id,
    )

    # Persist user message and assistant response
    db = SessionLocal()
    try:
        import json as _json
        user_msg = ChatMessageModel(
            conversation_id=conversation_id,
            user_id=user.id,
            role="user",
            content=payload.message,
        )
        assistant_msg = ChatMessageModel(
            conversation_id=conversation_id,
            user_id=user.id,
            role="assistant",
            content=result.answer,
            metadata_json=_json.dumps({
                "sources": result.sources,
                "web_sources": result.web_sources,
                "mode": result.mode,
                "rag_chunks_used": result.rag_chunks_used,
                "web_results_used": result.web_results_used,
                "fallback_reason": result.fallback_reason,
            })
        )
        db.add(user_msg)
        db.add(assistant_msg)
        db.commit()
    finally:
        db.close()

    return {
        "conversation_id": conversation_id,
        "answer": result.answer,
        "chatbot_name": bot_name,
        "sources": result.sources,
        "web_sources": result.web_sources,
        "mode": result.mode,
        "rag_chunks_used": result.rag_chunks_used,
        "web_results_used": result.web_results_used,
        "fallback_reason": result.fallback_reason,
    }


# â”€â”€â”€ Chat File Upload â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/chat/upload")
async def chat_upload(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """
    Upload a file and extract its text content for use as chat context.
    Supports: .txt, .md, .pdf (basic), .docx (basic).
    Returns extracted text (truncated to 8000 chars).
    """
    MAX_BYTES = 10 * 1024 * 1024  # 10 MB
    MAX_CHARS = 8000

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    filename = (file.filename or "").lower()
    text = ""

    try:
        if filename.endswith(".pdf"):
            try:
                import io
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(content))
                pages = [p.extract_text() or "" for p in reader.pages]
                text = "\n".join(pages)
            except ImportError:
                # Fallback: try raw text extraction
                text = content.decode("utf-8", errors="ignore")
        elif filename.endswith(".docx"):
            try:
                import io
                import docx
                doc = docx.Document(io.BytesIO(content))
                text = "\n".join(p.text for p in doc.paragraphs)
            except ImportError:
                text = content.decode("utf-8", errors="ignore")
        else:
            # txt, md, csv, etc.
            text = content.decode("utf-8", errors="ignore")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not extract text from file: {e}")

    text = text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="No text could be extracted from the file.")

    return {
        "filename": file.filename,
        "char_count": len(text),
        "text": text[:MAX_CHARS],
        "truncated": len(text) > MAX_CHARS,
    }


# â”€â”€â”€ Chat Conversation History Endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/chat/conversations")
async def list_conversations(
    user: User = Depends(get_current_user),
    limit: int = 50,
):
    """List all conversation IDs for the current user, ordered by most recent activity."""
    from sqlalchemy import func
    db = SessionLocal()
    try:
        conv_stats = db.query(
            ChatMessageModel.conversation_id,
            func.max(ChatMessageModel.created_at).label("last_at"),
            func.count(ChatMessageModel.id).label("message_count"),
        ).filter(
            ChatMessageModel.user_id == user.id
        ).group_by(
            ChatMessageModel.conversation_id
        ).order_by(
            func.max(ChatMessageModel.created_at).desc()
        ).limit(limit).all()

        results = []
        for conv_id, last_at, count in conv_stats:
            first_msg = db.query(ChatMessageModel.content).filter_by(
                conversation_id=conv_id,
                user_id=user.id,
                role="user"
            ).order_by(ChatMessageModel.created_at.asc()).first()
            results.append({
                "conversation_id": conv_id,
                "last_at": str(last_at),
                "message_count": count,
                "preview": (first_msg[0] if first_msg else "")[:80],
            })
        return results
    finally:
        db.close()


@router.get("/chat/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
):
    """Load full message history for a conversation."""
    db = SessionLocal()
    try:
        messages = db.query(ChatMessageModel).filter_by(
            conversation_id=conversation_id,
            user_id=user.id
        ).order_by(ChatMessageModel.created_at, ChatMessageModel.id).all()
        if not messages:
            raise HTTPException(status_code=404, detail="Conversation not found")
        import json as _json
        return {
            "conversation_id": conversation_id,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "created_at": str(m.created_at),
                    "metadata": _json.loads(m.metadata_json) if m.metadata_json else None,
                }
                for m in messages
            ]
        }
    finally:
        db.close()


@router.delete("/chat/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
):
    """Delete all messages in a conversation."""
    db = SessionLocal()
    try:
        deleted = db.query(ChatMessageModel).filter_by(
            conversation_id=conversation_id,
            user_id=user.id
        ).delete()
        db.commit()
        if deleted == 0:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"deleted": deleted, "conversation_id": conversation_id}
    finally:
        db.close()


@router.get("/chat/settings")
async def get_chatbot_settings(
    user: User = Depends(get_current_user),
):
    """Return chatbot identity settings (name, persona preview)."""
    bot_name, bot_persona = _get_chatbot_settings()
    return {
        "chatbot_name": bot_name,
        "persona_preview": bot_persona[:200],
    }


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    user: User = Depends(get_current_user),
):
    """
    Streaming educational chat with RAG + Web Search + LLM orchestration.
    Yields answer chunks followed by __METADATA__ JSON.
    Rate limited: 30 requests/minute per user.
    Persists conversation history by conversation_id.
    """
    _check_rate_limit(user)

    conversation_id = payload.conversation_id or str(uuid.uuid4())

    # Load history from DB if conversation_id provided and history not in request
    history = []
    if payload.conversation_id and not payload.conversation_history:
        db = SessionLocal()
        try:
            messages = db.query(ChatMessageModel).filter_by(
                conversation_id=payload.conversation_id,
                user_id=user.id
            ).order_by(ChatMessageModel.created_at, ChatMessageModel.id).all()
            history = [{"role": m.role, "content": m.content} for m in messages]
        finally:
            db.close()
    else:
        history = [{"role": msg.role, "content": msg.content} for msg in payload.conversation_history]

    # Save user message immediately
    db = SessionLocal()
    try:
        user_msg = ChatMessageModel(
            conversation_id=conversation_id,
            user_id=user.id,
            role="user",
            content=payload.message,
        )
        db.add(user_msg)
        db.commit()
    finally:
        db.close()

    full_answer = []
    metadata = {}

    async def generate():
        nonlocal full_answer, metadata
        async for chunk in orchestrator.run_stream(
            query=payload.message,
            subject=payload.subject,
            grade_level=payload.grade_level,
            conversation_history=history,
            source_id=payload.source_id,
        ):
            if chunk.startswith("\n\n__METADATA__"):
                import json as _json
                metadata = _json.loads(chunk[len("\n\n__METADATA__"):])
            else:
                full_answer.append(chunk)
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"

    response = StreamingResponse(generate(), media_type="text/event-stream")

    # Note: Assistant message persistence happens after streaming completes
    # In production, consider a background task or callback for this
    # For now, we'll persist in a background task
    import threading

    def _persist_after_stream():
        import time as _time
        # Wait for stream to complete (naive approach)
        _time.sleep(2)
        db = SessionLocal()
        try:
            import json as _json
            assistant_msg = ChatMessageModel(
                conversation_id=conversation_id,
                user_id=user.id,
                role="assistant",
                content="".join(full_answer),
                metadata_json=_json.dumps(metadata) if metadata else None,
            )
            db.add(assistant_msg)
            db.commit()
        finally:
            db.close()

    threading.Thread(target=_persist_after_stream, daemon=True).start()

    return response
