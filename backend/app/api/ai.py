import json
import uuid
import threading
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.agents.engagement_agent import StudentEngagementAgent
from app.agents.flashcard_agent import FlashcardGenerationAgent
from app.agents.lesson_agent import LessonGenerationAgent
from app.agents.quiz_agent import QuizGenerationAgent
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.workflow import EduSenseAgentWorkflow
from app.api.deps import get_current_user, require_role
from app.db.session import get_db, SessionLocal
from app.models.models import AIGeneration, Quiz, Report, SessionResource, User, VideoProject
from app.schemas.schemas import FlashcardRequest, LessonRequest, QuizRequest, RecommendationDecision, VideoRequest
from app.services.export import build_json_bytes, build_video_zip, build_word_document_bytes, lesson_to_markdown, build_true_docx_bytes, build_pptx_bytes
from app.services.generation_jobs import create_job, get_job_payload, list_pending_jobs, set_job_status
from app.services.source_extractor import build_session_source_context
from app.services.video import generate_educational_video

VIDEO_STATIC_DIR = Path(__file__).resolve().parents[1] / "static" / "videos"

router = APIRouter(prefix="/ai", tags=["AI Agents"])
lessons = LessonGenerationAgent()
quizzes = QuizGenerationAgent()
flashcards = FlashcardGenerationAgent()
engagement = StudentEngagementAgent()
recommendations = RecommendationAgent()
workflow = EduSenseAgentWorkflow()

# In-memory cache for fast polling; DB is source of truth across restarts
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


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
            result = lessons.generate(enriched).data
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
            result = flashcards.generate(payload.topic, payload.count, payload.language, prompt).data
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
            result = quizzes.generate(payload.topic, payload.difficulty, payload.count, prompt).data
            quiz = Quiz(session_id=payload.session_id, title=result["title"], difficulty=result["difficulty"], questions_json=json.dumps(result["questions"]))
            db.add(quiz)
            db.commit()
            db.refresh(quiz)
            result["id"] = quiz.id
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
    result = flashcards.generate(payload.topic, payload.count, payload.language, prompt).data

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
    result = lessons.generate(enriched).data

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
    result = quizzes.generate(payload.topic, payload.difficulty, payload.count, prompt).data
    quiz = Quiz(session_id=payload.session_id, title=result["title"], difficulty=result["difficulty"], questions_json=json.dumps(result["questions"]))
    db.add(quiz)
    db.commit()
    result["id"] = quiz.id
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
            "questions": json.loads(q.questions_json)
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
