import json
import uuid
import threading
import time
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.agents.engagement_agent import StudentEngagementAgent
from app.agents.flashcard_agent import FlashcardGenerationAgent
from app.agents.lesson_agent import LessonGenerationAgent
from app.agents.quiz_agent import QuizGenerationAgent
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.workflow import EduSenseAgentWorkflow
from app.agents.orchestrator import AgentOrchestrator
from app.api.deps import get_current_user, require_role
from app.db.session import get_db, SessionLocal
from app.models.models import AIGeneration, ChatMessage as ChatMessageModel, Quiz, QuizAgentConfig, Report, SessionResource, User, VideoProject
from app.schemas.schemas import FlashcardRequest, LessonRequest, QuizRequest, QuizAgentConfigCreate, QuizAgentConfigUpdate, QuizAgentConfigOut, RecommendationDecision, VideoRequest
from app.services.export import build_json_bytes, build_video_zip, build_word_document_bytes, lesson_to_markdown, build_true_docx_bytes, build_pptx_bytes
from app.services.generation_jobs import create_job, get_job_payload, list_pending_jobs, set_job_status
from app.services.source_extractor import build_session_source_context
from app.services.video import generate_educational_video
from app.core.audit import log_audit_event

VIDEO_STATIC_DIR = Path(__file__).resolve().parents[1] / "static" / "videos"


# Rate limiter: 30 requests per minute per user (token bucket)
# TODO: This is in-memory only — correct for single-process deployment.
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


def _cache_job(job_id: str, status: str, result=None, error: str | None = None):
    with _jobs_lock:
        _jobs[job_id] = {"status": status, "result": result, "error": error}


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


def _get_source_context(db: Session, source_session_id: int | None, instructor_id: int) -> str:
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
    """Runs in a daemon thread — survives tab close."""
    try:
        db = SessionLocal()
        try:
            source = _get_source_context(db, payload.source_session_id, instructor_id)
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
            source = _get_source_context(db, payload.source_session_id, instructor_id)
            prompt = _append_source(payload.prompt, source)
            result = flashcards.generate(
                payload.topic, payload.count, payload.language, prompt,
                subject=payload.subject, grade_level=payload.grade_level,
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
            source = _get_source_context(db, payload.source_session_id, instructor_id)
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
                config = db.query(QuizAgentConfig).filter_by(id=payload.config_id, instructor_id=instructor_id).first()
                if config:
                    config_time_limit = config.time_limit_seconds
                    config_fullscreen_lock = config.fullscreen_lock
                    config_camera_monitoring = config.camera_monitoring

            quiz = Quiz(
                session_id=payload.session_id,
                title=result["title"],
                difficulty=result["difficulty"],
                questions_json=json.dumps(result["questions"]),
                time_limit_seconds=config_time_limit,
                fullscreen_lock=config_fullscreen_lock,
                camera_monitoring=config_camera_monitoring,
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


def _run_video_bg(job_id: str, payload: VideoRequest, instructor_id: int):
    db = SessionLocal()
    try:
        source = _get_source_context(db, payload.source_session_id, instructor_id)
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
        _finish_job(job_id, "done", result)
    except Exception as exc:
        db.rollback()
        _finish_job(job_id, "error", error=str(exc))
    finally:
        db.close()


def _run_video_edit_bg(job_id: str, video_id: int, payload: VideoRequest, instructor_id: int):
    db = SessionLocal()
    try:
        project = db.query(VideoProject).filter_by(id=video_id, instructor_id=instructor_id).first()
        if not project:
            raise HTTPException(404, "Video not found")
        source = _get_source_context(db, payload.source_session_id, instructor_id)
        notes = _append_source(payload.notes, source)
        project.title = payload.title
        project.prompt = payload.prompt
        project.language = payload.language
        project.style = payload.style
        project.duration = payload.duration
        project.notes = notes
        project.status = "processing"
        db.commit()
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
        project.video_path = video["video_url"]
        project.status = "completed"
        db.commit()
        db.refresh(project)
        result = _serialize_video_project(project)
        result["lesson"] = lesson
        _finish_job(job_id, "done", result)
    except Exception as exc:
        db.rollback()
        _finish_job(job_id, "error", error=str(exc))
    finally:
        db.close()


@router.post("/flashcards")
def generate_flashcards(payload: FlashcardRequest, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    source = _get_source_context(db, payload.source_session_id, user.id)
    prompt = _append_source(payload.prompt, source)
    result = flashcards.generate(
        payload.topic, payload.count, payload.language, prompt,
        subject=payload.subject, grade_level=payload.grade_level,
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
    data = flashcards.generate(payload.topic, payload.count, payload.language, payload.prompt).data
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


@router.post("/lessons")
def generate_lesson(payload: LessonRequest, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    source = _get_source_context(db, payload.source_session_id, user.id)
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
    source = _get_source_context(db, payload.source_session_id, user.id)
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

    quiz = Quiz(
        session_id=payload.session_id,
        title=result["title"],
        difficulty=result["difficulty"],
        questions_json=json.dumps(result["questions"]),
        time_limit_seconds=config_time_limit,
        fullscreen_lock=config_fullscreen_lock,
        camera_monitoring=config_camera_monitoring,
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
    return [
        {
            "id": q.id,
            "session_id": q.session_id,
            "title": q.title,
            "difficulty": q.difficulty,
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
        }
        for q in quizzes_list
    ]


@router.delete("/quizzes/{quiz_id}")
def delete_quiz(quiz_id: int, db: Session = Depends(get_db), _: User = Depends(require_role("instructor"))):
    deleted = db.query(Quiz).filter_by(id=quiz_id).delete()
    db.commit()
    if not deleted:
        raise HTTPException(404, "Quiz not found")
    return {"message": "Quiz deleted"}


# ─── Quiz Agent Config Endpoints ───────────────────────────────────────────────────

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
    if type:
        query = query.filter_by(type=type)
    generations = query.order_by(AIGeneration.created_at.desc()).all()
    return [
        {
            "id": g.id,
            "type": g.type,
            "topic": g.topic,
            "prompt": g.prompt,
            "created_at": g.created_at,
            "data": json.loads(g.data_json)
        }
        for g in generations
    ]


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


# ── Background-safe queue endpoints (generation continues even if tab closes) ───

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
    payload = get_job_payload(db, job_id, user.id)
    if payload:
        return payload
    with _jobs_lock:
        cached = _jobs.get(job_id)
    if cached:
        return cached
    raise HTTPException(404, "Job not found")


@router.get("/engagement/{session_id}")
def get_engagement(session_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return engagement.calculate(db, session_id).data


@router.get("/recommendations/{session_id}")
def get_recommendations(session_id: int, db: Session = Depends(get_db), _: User = Depends(require_role("instructor"))):
    loop = workflow.improvement_loop(db, session_id)
    report = Report(session_id=session_id, summary=loop["report"]["summary"], pdf_path=loop["report"]["pdf_path"])
    db.add(report)
    db.commit()
    return loop


@router.post("/recommendations/{session_id}/decision")
def decide_recommendation(session_id: int, payload: RecommendationDecision, _: User = Depends(require_role("instructor"))):
    return {"session_id": session_id, "accepted": payload.accepted, "action": payload.action or "noted"}


@router.post("/videos")
def create_video(payload: VideoRequest, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    source = _get_source_context(db, payload.source_session_id, user.id)
    notes = _append_source(payload.notes, source)
    project = VideoProject(instructor_id=user.id, title=payload.title, prompt=payload.prompt, language=payload.language, style=payload.style, duration=payload.duration, notes=notes, status="processing")
    db.add(project)
    db.commit()
    db.refresh(project)
    lesson = lessons.generate(LessonRequest(topic=payload.title, prompt=payload.prompt, language=payload.language, teaching_style=payload.style, duration=payload.duration, additional_notes=notes, session_id=payload.session_id, source_session_id=payload.source_session_id)).data
    video = generate_educational_video(project.id, project.title, lesson)
    project.video_path = video["video_url"]
    project.status = "completed"
    db.commit()
    result = _serialize_video_project(project)
    result["lesson"] = lesson
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
    source = _get_source_context(db, payload.source_session_id, user.id)
    notes = _append_source(payload.notes, source)
    project.title = payload.title
    project.prompt = payload.prompt
    project.language = payload.language
    project.style = payload.style
    project.duration = payload.duration
    project.notes = notes
    project.status = "processing"
    db.commit()

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
    project.video_path = video["video_url"]
    project.status = "completed"
    db.commit()
    response = _serialize_video_project(project)
    response["lesson"] = lesson
    return response


@router.get("/videos/{video_id}")
def get_video(video_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    project = db.query(VideoProject).filter_by(id=video_id, instructor_id=user.id).first()
    if not project:
        raise HTTPException(404, "Video not found")
    return _serialize_video_project(project)


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


# ─── Chat Endpoint ────────────────────────────────────────────────────────────

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
    """
    _check_rate_limit(user)

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
            ).order_by(ChatMessageModel.created_at).all()
            history = [{"role": m.role, "content": m.content} for m in messages]
        finally:
            db.close()
    else:
        history = [{"role": msg.role, "content": msg.content} for msg in payload.conversation_history]

    result = await orchestrator._run_async(
        query=payload.message,
        subject=payload.subject,
        grade_level=payload.grade_level,
        conversation_history=history,
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
        "sources": result.sources,
        "web_sources": result.web_sources,
        "mode": result.mode,
        "rag_chunks_used": result.rag_chunks_used,
        "web_results_used": result.web_results_used,
        "fallback_reason": result.fallback_reason,
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
            ).order_by(ChatMessageModel.created_at).all()
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
