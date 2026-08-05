import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.agents.engagement_agent import StudentEngagementAgent
from app.agents.flashcard_agent import FlashcardGenerationAgent
from app.agents.lesson_agent import LessonGenerationAgent
from app.agents.quiz_agent import QuizGenerationAgent
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.workflow import EduSenseAgentWorkflow
from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.models import AIGeneration, Quiz, Report, User, VideoProject
from app.schemas.schemas import FlashcardRequest, LessonRequest, QuizRequest, RecommendationDecision, VideoRequest
from app.services.export import build_json_bytes, build_video_zip, build_word_document_bytes, lesson_to_markdown, build_true_docx_bytes, build_pptx_bytes
from app.services.video import generate_educational_video

router = APIRouter(prefix="/ai", tags=["AI Agents"])
lessons = LessonGenerationAgent()
quizzes = QuizGenerationAgent()
flashcards = FlashcardGenerationAgent()
engagement = StudentEngagementAgent()
recommendations = RecommendationAgent()
workflow = EduSenseAgentWorkflow()


@router.post("/flashcards")
def generate_flashcards(payload: FlashcardRequest, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    result = flashcards.generate(payload.topic, payload.count, payload.language).data
    
    # Save to history
    generation = AIGeneration(
        instructor_id=user.id,
        type="flashcard",
        topic=payload.topic,
        prompt=f"Count: {payload.count}, Lang: {payload.language}",
        data_json=json.dumps(result)
    )
    db.add(generation)
    db.commit()
    result["id"] = generation.id
    return result


@router.post("/flashcards/export-word")
def export_flashcards_word(payload: FlashcardRequest, _: User = Depends(require_role("instructor"))):
    data = flashcards.generate(payload.topic, payload.count, payload.language).data
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
    result = lessons.generate(payload).data
    
    # Save to history
    generation = AIGeneration(
        instructor_id=user.id,
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
def generate_quiz(payload: QuizRequest, db: Session = Depends(get_db), _: User = Depends(require_role("instructor"))):
    result = quizzes.generate(payload.topic, payload.difficulty, payload.count).data
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
    project = VideoProject(instructor_id=user.id, title=payload.title, prompt=payload.prompt, language=payload.language, style=payload.style, duration=payload.duration, notes=payload.notes, status="processing")
    db.add(project)
    db.commit()
    db.refresh(project)
    lesson = lessons.generate(LessonRequest(topic=payload.title, prompt=payload.prompt, language=payload.language, teaching_style=payload.style, duration=payload.duration, additional_notes=payload.notes)).data
    video = generate_educational_video(project.id, project.title, lesson)
    project.video_path = video["video_url"]
    project.status = "completed"
    db.commit()
    return {
        "id": project.id,
        "status": project.status,
        "video_url": video["video_url"],
        "audio_url": video.get("audio_url"),
        "mp4_url": video.get("mp4_url"),
        "scenes": video.get("scenes"),
        "fallback": video.get("fallback"),
        "lesson": lesson,
    }


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
    project.title = payload.title
    project.prompt = payload.prompt
    project.language = payload.language
    project.style = payload.style
    project.duration = payload.duration
    project.notes = payload.notes
    project.status = "processing"
    db.commit()

    lesson = lessons.generate(
        LessonRequest(
            topic=payload.title,
            prompt=payload.prompt,
            language=payload.language,
            teaching_style=payload.style,
            duration=payload.duration,
            additional_notes=payload.notes,
        )
    ).data
    video = generate_educational_video(project.id, project.title, lesson)
    project.video_path = video["video_url"]
    project.status = "completed"
    db.commit()
    return {
        "id": project.id,
        "status": project.status,
        "video_url": video["video_url"],
        "audio_url": video.get("audio_url"),
        "mp4_url": video.get("mp4_url"),
        "scenes": video.get("scenes"),
        "fallback": video.get("fallback"),
        "lesson": lesson,
    }


@router.get("/videos")
def list_videos(db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    return db.query(VideoProject).filter_by(instructor_id=user.id).order_by(VideoProject.created_at.desc()).all()


@router.delete("/videos/{video_id}")
def delete_video(video_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("instructor"))):
    deleted = db.query(VideoProject).filter_by(id=video_id, instructor_id=user.id).delete()
    db.commit()
    if not deleted:
        raise HTTPException(404, "Video not found")
    return {"message": "Video deleted"}
