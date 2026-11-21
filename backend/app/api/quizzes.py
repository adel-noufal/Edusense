"""
Quiz Attempt & Anti-Cheat API Endpoints

Handles student quiz taking with server-side timer validation,
anti-cheat violation logging, and instructor violation review/re-entry.
"""
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.core.audit import log_audit_event, log_student_data_access
from app.db.session import get_db
from app.models.models import Quiz, QuizAttempt, QuizViolation, User, Session as ClassSession, AIGeneration
from app.schemas.schemas import (
    QuizOut, PublishExamRequest, QuizAttemptOut, QuizSubmitRequest, QuizSubmitResponse,
    QuizViolationOut, QuizAgentConfigCreate, QuizAgentConfigOut, QuizAgentConfigUpdate,
    QuizCreateManual, QuizUpdateSettings
)
from app.models.models import SessionRegistration
from app.agents.quiz_agent import normalize_difficulty

router = APIRouter(prefix="/quizzes", tags=["Quiz Attempts"])


def _quiz_out(quiz: Quiz, questions: list[dict], session_title: str | None = None, enrolled_student_count: int | None = None) -> QuizOut:
    """Single constructor for QuizOut responses — keeps reveal_answers and
    normalized difficulty consistent across every endpoint."""
    return QuizOut(
        id=quiz.id,
        session_id=quiz.session_id,
        session_title=session_title,
        title=quiz.title,
        difficulty=normalize_difficulty(quiz.difficulty),
        questions=questions,
        created_at=quiz.created_at,
        time_limit_seconds=quiz.time_limit_seconds,
        time_limit_per_question_seconds=quiz.time_limit_per_question_seconds,
        fullscreen_lock=quiz.fullscreen_lock,
        camera_monitoring=quiz.camera_monitoring,
        is_published=quiz.is_published,
        is_exam=quiz.is_exam,
        lock_back_navigation=quiz.lock_back_navigation,
        due_date=quiz.due_date,
        available_from=quiz.available_from,
        reveal_answers=quiz.reveal_answers,
        enrolled_student_count=enrolled_student_count,
    )


# ─── Quiz Creation & Taking ───────────────────────────────────────────────────────

@router.post("", response_model=QuizOut, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=QuizOut, status_code=status.HTTP_201_CREATED)
def create_manual_quiz(
    payload: QuizCreateManual,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor"))
):
    """
    Allows an instructor to build a quiz MANUALLY (write their own questions/answers)
    as an alternative to AI generation — same quiz object/schema either way.
    """
    if payload.session_id:
        session = db.query(ClassSession).filter_by(id=payload.session_id).first()
        if not session:
            raise HTTPException(404, "Target session not found")
        if session.instructor_id and session.instructor_id != user.id and user.role != "admin":
            raise HTTPException(403, "Cannot attach quiz to a session owned by another instructor")

    # Idempotent create: an identical quiz (same session + title) already
    # exists -> return it instead of inserting a duplicate row.
    existing = db.query(Quiz).filter_by(
        session_id=payload.session_id, title=payload.title.strip()
    ).first()
    if existing:
        try:
            return _quiz_out(existing, json.loads(existing.questions_json))
        except Exception:
            return _quiz_out(existing, [])

    questions_data = []
    for q in payload.questions:
        q_dict = {
            "question": q.question.strip(),
            "type": q.type,
            "options": q.options if q.options else (["True", "False"] if q.type == "true_false" else ["A", "B", "C", "D"]),
            "answer": q.answer.strip(),
            "explanation": q.explanation.strip() if q.explanation else "",
        }
        questions_data.append(q_dict)

    quiz = Quiz(
        session_id=payload.session_id,
        title=payload.title.strip(),
        difficulty=normalize_difficulty(payload.difficulty),
        questions_json=json.dumps(questions_data),
        is_exam=payload.is_exam,
        is_published=payload.is_published,
        time_limit_seconds=payload.time_limit_seconds,
        time_limit_per_question_seconds=payload.time_limit_per_question_seconds,
        lock_back_navigation=payload.lock_back_navigation,
        fullscreen_lock=payload.fullscreen_lock if payload.fullscreen_lock is not None else payload.is_exam,
        camera_monitoring=payload.camera_monitoring,
        due_date=payload.due_date,
        available_from=payload.available_from,
        reveal_answers=payload.reveal_answers,
        instructor_id=user.id,
    )
    db.add(quiz)
    db.commit()
    db.refresh(quiz)

    # Add AIGeneration record so it shows uniformly across historical views
    generation = AIGeneration(
        instructor_id=user.id,
        session_id=payload.session_id,
        type="quiz",
        topic=quiz.title,
        prompt=f"Manual Quiz · {quiz.difficulty}",
        data_json=json.dumps({
            "id": quiz.id,
            "title": quiz.title,
            "difficulty": quiz.difficulty,
            "questions": questions_data,
            "is_exam": quiz.is_exam,
            "session_id": quiz.session_id,
        })
    )
    db.add(generation)
    db.commit()

    log_audit_event(
        db, action="create_manual_quiz", user=user,
        resource_type="quiz", resource_id=str(quiz.id), request=request,
        details={"title": quiz.title, "question_count": len(questions_data), "is_exam": quiz.is_exam}
    )

    return _quiz_out(quiz, questions_data)


@router.get("/{quiz_id}", response_model=QuizOut)
def get_quiz_for_student(
    quiz_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Get quiz metadata.
    - If user is student: strips correct answers and verifies enrollment if linked.
    - If user is instructor/admin: returns full questions with answers.
    """
    quiz = db.query(Quiz).filter_by(id=quiz_id).first()
    if not quiz:
        raise HTTPException(404, "Quiz not found")

    questions = json.loads(quiz.questions_json)

    if user.role == "student":
        # If quiz is linked to a session, verify student is enrolled
        if quiz.session_id:
            reg = db.query(ClassSession).join(ClassSession.registrations).filter(
                ClassSession.id == quiz.session_id,
                ClassSession.registrations.any(student_id=user.id)
            ).first()
            if not reg:
                raise HTTPException(403, "You are not enrolled in the session this quiz belongs to")

        # Strip correct answers from questions for student view
        safe_questions = []
        for q in questions:
            safe_q = {k: v for k, v in q.items() if k not in ("answer", "correct_answer")}
            safe_questions.append(safe_q)
        display_questions = safe_questions
    else:
        display_questions = questions

    # Audit
    log_audit_event(db, action="view_quiz", user=user, resource_type="quiz", resource_id=str(quiz_id), request=request)

    return _quiz_out(quiz, display_questions)


@router.get("/session/{session_id}", response_model=list[QuizOut])
def list_quizzes_for_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("student"))
):
    """
    List all quizzes for a session (student view - no answers).
    Student must be enrolled in the session.
    """
    # Verify enrollment
    reg = db.query(ClassSession).join(ClassSession.registrations).filter(
        ClassSession.id == session_id,
        ClassSession.registrations.any(student_id=user.id)
    ).first()
    if not reg:
        raise HTTPException(403, "You are not enrolled in this session")

    quizzes = db.query(Quiz).filter_by(session_id=session_id).all()

    # Audit
    log_audit_event(db, action="list_session_quizzes", user=user, resource_type="quiz", resource_id=str(session_id), request=request)

    result = []
    for quiz in quizzes:
        questions = json.loads(quiz.questions_json)
        safe_questions = []
        for q in questions:
            safe_q = {k: v for k, v in q.items() if k not in ("answer", "correct_answer")}
            safe_questions.append(safe_q)

        result.append(_quiz_out(quiz, safe_questions))

    return result


@router.get("/student/exams", response_model=list[QuizOut])
def list_student_exams(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("student"))
):
    """
    List all published exams (is_exam=True, is_published=True) for sessions
    the student is enrolled in.  Returns questions WITHOUT correct answers.
    """
    # Get all session IDs the student is enrolled in, plus the instructors
    # who own those sessions (used for session-less "all my students" exams).
    regs = db.query(SessionRegistration).filter_by(student_id=user.id).all()
    enrolled_session_ids = [r.session_id for r in regs]

    my_instructor_ids = set()
    if enrolled_session_ids:
        my_instructor_ids = {
            int(row[0]) for row in
            db.query(ClassSession.instructor_id)
            .filter(ClassSession.id.in_(enrolled_session_ids),
                    ClassSession.instructor_id.isnot(None))
            .all()
        }

    if not enrolled_session_ids and not my_instructor_ids:
        return []

    # Visibility rule (B4): published exam AND (
    #   linked to a session the student is enrolled in
    #   OR not linked to any session and owned by an instructor the student
    #      has sessions with ("all my students" scope)
    #   OR legacy rows with no session and no owner — treated as instructor-
    #      scoped only when we can resolve an owner; otherwise hidden.
    query = db.query(Quiz).filter(
        Quiz.is_exam == True,
        Quiz.is_published == True,
    )
    from sqlalchemy import or_, and_
    conditions = []
    if enrolled_session_ids:
        conditions.append(Quiz.session_id.in_(enrolled_session_ids))
    if my_instructor_ids:
        conditions.append(and_(
            Quiz.session_id.is_(None),
            Quiz.instructor_id.in_(list(my_instructor_ids)),
        ))
    if not conditions:
        return []
    quizzes = (
        query.filter(or_(*conditions))
        .order_by(Quiz.created_at.desc())
        .all()
    )

    # Audit
    log_audit_event(db, action="list_student_exams", user=user,
                    resource_type="quiz", resource_id="all", request=request)

    sessions_map = {
        s.id: s.title
        for s in db.query(ClassSession).filter(ClassSession.id.in_(enrolled_session_ids)).all()
    }

    result = []
    for quiz in quizzes:
        import json as _json
        questions = _json.loads(quiz.questions_json)
        safe_questions = [{k: v for k, v in q.items() if k not in ("answer", "correct_answer")} for q in questions]
        result.append(_quiz_out(quiz, safe_questions, session_title=sessions_map.get(quiz.session_id)))
    return result


@router.post("/{quiz_id}/publish-as-exam", response_model=QuizOut)
def publish_quiz_as_exam(
    quiz_id: int,
    payload: PublishExamRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor"))
):
    """
    Publish a quiz as an Exam for a specific session, or update existing exam settings.
    Sets is_exam=True, is_published=True, and configures anti-cheat + navigation locks.
    """
    quiz = db.query(Quiz).filter_by(id=quiz_id).first()
    if not quiz:
        raise HTTPException(404, "Quiz not found")

    target_session_id = payload.session_id if payload.session_id is not None else quiz.session_id
    if not target_session_id:
        raise HTTPException(400, "A target session_id is required to publish an exam.")

    session = db.query(ClassSession).filter_by(id=target_session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    if session.instructor_id is None:
        session.instructor_id = user.id
    elif session.instructor_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your session")

    quiz.is_exam = True
    quiz.is_published = payload.is_published if payload.is_published is not None else True
    quiz.session_id = target_session_id
    quiz.time_limit_seconds = payload.time_limit_seconds
    quiz.time_limit_per_question_seconds = payload.time_limit_per_question_seconds
    quiz.lock_back_navigation = payload.lock_back_navigation
    quiz.fullscreen_lock = payload.fullscreen_lock
    quiz.camera_monitoring = payload.camera_monitoring
    quiz.due_date = payload.due_date
    quiz.available_from = payload.available_from
    if payload.reveal_answers is not None:
        quiz.reveal_answers = payload.reveal_answers
    # Ownership for visibility scoping — prefer the session's instructor,
    # fall back to the publishing user (covers session-less "all my students" exams).
    quiz.instructor_id = session.instructor_id or user.id

    db.commit()
    db.refresh(quiz)

    log_audit_event(
        db, action="publish_quiz_as_exam", user=user,
        resource_type="quiz", resource_id=str(quiz.id), request=request,
        details={
            "session_id": target_session_id,
            "time_limit_seconds": payload.time_limit_seconds,
            "time_limit_per_question_seconds": payload.time_limit_per_question_seconds,
            "lock_back_navigation": payload.lock_back_navigation,
            "fullscreen_lock": payload.fullscreen_lock,
            "camera_monitoring": payload.camera_monitoring,
        }
    )

    questions = json.loads(quiz.questions_json)
    sess_obj = db.query(ClassSession).filter_by(id=quiz.session_id).first() if quiz.session_id else None
    enrolled_count = db.query(SessionRegistration).filter_by(session_id=quiz.session_id).count() if quiz.session_id else 0
    return _quiz_out(quiz, questions, session_title=sess_obj.name if sess_obj else None, enrolled_student_count=enrolled_count)


@router.patch("/{quiz_id}", response_model=QuizOut)
@router.put("/{quiz_id}", response_model=QuizOut)
def update_quiz_or_settings(
    quiz_id: int,
    payload: QuizUpdateSettings,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor"))
):
    """
    Update exam settings, questions, or metadata for an existing quiz or exam.
    Ensures seamless saving of exam settings changes.
    """
    quiz = db.query(Quiz).filter_by(id=quiz_id).first()
    if not quiz:
        raise HTTPException(404, "Quiz not found")

    if payload.session_id is not None:
        session = db.query(ClassSession).filter_by(id=payload.session_id).first()
        if not session:
            raise HTTPException(404, "Target session not found")
        if session.instructor_id and session.instructor_id != user.id and user.role != "admin":
            raise HTTPException(403, "Not your session")
        quiz.session_id = payload.session_id

    if payload.title is not None:
        quiz.title = payload.title.strip()
    if payload.difficulty is not None:
        quiz.difficulty = normalize_difficulty(payload.difficulty)
    if payload.questions is not None:
        questions_data = []
        for q in payload.questions:
            questions_data.append({
                "question": q.question.strip(),
                "type": q.type,
                "options": q.options if q.options else (["True", "False"] if q.type == "true_false" else ["A", "B", "C", "D"]),
                "answer": q.answer.strip(),
                "explanation": q.explanation.strip() if q.explanation else "",
            })
        quiz.questions_json = json.dumps(questions_data)
    if payload.is_exam is not None:
        quiz.is_exam = payload.is_exam
    if payload.is_published is not None:
        quiz.is_published = payload.is_published
    if payload.time_limit_seconds is not None:
        quiz.time_limit_seconds = payload.time_limit_seconds if payload.time_limit_seconds > 0 else None
    if payload.time_limit_per_question_seconds is not None:
        quiz.time_limit_per_question_seconds = payload.time_limit_per_question_seconds if payload.time_limit_per_question_seconds > 0 else None
    if payload.lock_back_navigation is not None:
        quiz.lock_back_navigation = payload.lock_back_navigation
    if payload.fullscreen_lock is not None:
        quiz.fullscreen_lock = payload.fullscreen_lock
    if payload.camera_monitoring is not None:
        quiz.camera_monitoring = payload.camera_monitoring
    if payload.due_date is not None:
        quiz.due_date = payload.due_date
    quiz.available_from = payload.available_from
    if payload.reveal_answers is not None:
        quiz.reveal_answers = payload.reveal_answers
    if quiz.instructor_id is None:
        quiz.instructor_id = user.id
    if payload.session_id is not None:
        sess = db.query(ClassSession).filter_by(id=payload.session_id).first()
        if sess and sess.instructor_id:
            quiz.instructor_id = sess.instructor_id

    db.commit()
    db.refresh(quiz)

    log_audit_event(
        db, action="update_quiz_settings", user=user,
        resource_type="quiz", resource_id=str(quiz.id), request=request,
        details={"title": quiz.title, "is_exam": quiz.is_exam}
    )

    questions = json.loads(quiz.questions_json)
    sess_obj = db.query(ClassSession).filter_by(id=quiz.session_id).first() if quiz.session_id else None
    enrolled_count = db.query(SessionRegistration).filter_by(session_id=quiz.session_id).count() if quiz.session_id else 0
    return _quiz_out(quiz, questions, session_title=sess_obj.name if sess_obj else None, enrolled_student_count=enrolled_count)


@router.post("/{quiz_id}/start", response_model=QuizAttemptOut)
def start_quiz_attempt(
    quiz_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("student"))
):
    """
    Start a quiz attempt. Records server-side start time.
    Returns attempt_id and quiz config (time limits, anti-cheat settings).
    """
    quiz = db.query(Quiz).filter_by(id=quiz_id).first()
    if not quiz:
        raise HTTPException(404, "Quiz not found")

    # Check enrollment if linked to session
    if quiz.session_id:
        reg = db.query(ClassSession).join(ClassSession.registrations).filter(
            ClassSession.id == quiz.session_id,
            ClassSession.registrations.any(student_id=user.id)
        ).first()
        if not reg:
            raise HTTPException(403, "You are not enrolled in the session this quiz belongs to")

    # Exams must be published and not past their due date
    if quiz.is_exam:
        if not quiz.is_published:
            raise HTTPException(403, "This exam is not published yet.")
        if quiz.due_date:
            due = quiz.due_date
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > due:
                raise HTTPException(403, "This exam is past its due date.")
        if quiz.available_from:
            avail = quiz.available_from
            if avail.tzinfo is None:
                avail = avail.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) < avail:
                raise HTTPException(403, "This exam is not available yet.")
        # Exams allow exactly one attempt — block API replay/re-entry
        already_submitted = db.query(QuizAttempt).filter_by(
            quiz_id=quiz_id,
            student_id=user.id,
        ).filter(QuizAttempt.submitted_at.isnot(None)).first()
        if already_submitted:
            raise HTTPException(409, "You have already submitted this exam. Only one attempt is allowed.")

    # Check for existing active (unsubmitted, unlocked) attempt
    existing = db.query(QuizAttempt).filter_by(
        quiz_id=quiz_id,
        student_id=user.id,
        submitted_at=None
    ).first()
    if existing and not existing.is_locked:
        # Return existing attempt instead of creating new one (resume after refresh)
        return QuizAttemptOut.model_validate(existing)

    attempt = QuizAttempt(
        quiz_id=quiz_id,
        student_id=user.id,
        session_id=quiz.session_id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    # Audit: student starting quiz
    log_audit_event(db, action="start_quiz", user=user, resource_type="quiz", resource_id=str(quiz_id), request=request, details={"attempt_id": attempt.id})

    return QuizAttemptOut.model_validate(attempt)


@router.post("/{quiz_id}/submit", response_model=QuizSubmitResponse)
def submit_quiz_attempt(
    quiz_id: int,
    payload: QuizSubmitRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("student"))
):
    """
    Submit quiz answers with server-side time validation.
    - Validates elapsed time against server-side started_at
    - Auto-fails if time limit exceeded
    - Scores answers and returns detailed breakdown
    """
    quiz = db.query(Quiz).filter_by(id=quiz_id).first()
    if not quiz:
        raise HTTPException(404, "Quiz not found")

    # Check enrollment if linked to session
    if quiz.session_id:
        reg = db.query(ClassSession).join(ClassSession.registrations).filter(
            ClassSession.id == quiz.session_id,
            ClassSession.registrations.any(student_id=user.id)
        ).first()
        if not reg:
            raise HTTPException(403, "You are not enrolled in the session this quiz belongs to")

    # Get active attempt
    attempt = db.query(QuizAttempt).filter_by(
        quiz_id=quiz_id,
        student_id=user.id,
        submitted_at=None
    ).first()
    if not attempt:
        # B13: Idempotent submit — if attempt was already submitted (e.g. auto-submit
        # race or network retry), return the recorded score safely.
        prior = db.query(QuizAttempt).filter_by(
            quiz_id=quiz_id, student_id=user.id
        ).filter(QuizAttempt.submitted_at.isnot(None)).order_by(QuizAttempt.submitted_at.desc()).first()
        if prior:
            details = json.loads(prior.details_json) if prior.details_json else []
            max_s = prior.max_score or 1.0
            pct = round(((prior.score or 0.0) / max_s) * 100, 1) if max_s > 0 else 0.0
            return QuizSubmitResponse(
                attempt_id=prior.id,
                score=prior.score or 0.0,
                max_score=max_s,
                percentage=pct,
                details=details,
                passed=(pct >= 60.0),
            )
        raise HTTPException(400, "No active quiz attempt found. Start the quiz first.")
    if attempt.is_locked:
        raise HTTPException(403, f"Quiz attempt is locked: {attempt.lock_reason}")

    # Server-side time validation
    now = datetime.now(timezone.utc)
    started_at = attempt.started_at
    if started_at.tzinfo is None:
        # Naive datetime - assume UTC
        started_at = started_at.replace(tzinfo=timezone.utc)
    server_elapsed = int((now - started_at).total_seconds())
    client_elapsed = payload.elapsed_seconds

    # Check per-quiz time limit
    time_limit = quiz.time_limit_seconds
    if time_limit and server_elapsed > time_limit:
        # Time exceeded - auto-submit with zero score
        attempt.submitted_at = datetime.now(timezone.utc)
        attempt.answers_json = json.dumps(payload.answers)
        attempt.score = 0.0
        attempt.max_score = float(len(json.loads(quiz.questions_json)))
        db.commit()

        # Log violation
        violation = QuizViolation(
            quiz_id=quiz_id,
            attempt_id=attempt.id,
            student_id=user.id,
            event_type="time_exceeded",
            details_json=json.dumps({
                "server_elapsed": server_elapsed,
                "client_elapsed": client_elapsed,
                "time_limit": time_limit,
            }),
        )
        db.add(violation)
        db.commit()

        # Audit
        log_audit_event(db, action="quiz_time_exceeded", user=user, resource_type="quiz", resource_id=str(quiz_id), request=request, details={"attempt_id": attempt.id, "elapsed": server_elapsed, "limit": time_limit})

        return QuizSubmitResponse(
            attempt_id=attempt.id,
            score=0.0,
            max_score=attempt.max_score,
            percentage=0.0,
            details=[],
            passed=False,
        )

    # Score the quiz. Question payloads in the DB use inconsistent schemas
    # ({answer|correct_answer} × {letter|option-text|missing type}), so resolve
    # both sides to option indexes / normalized text before comparing.
    def _resolve_option_index(value, options):
        """Map a letter (A-D), numeric index, or option text to an option index."""
        if value is None or not options:
            return None
        s = str(value).strip()
        if not s:
            return None
        up = s.upper()
        if len(up) == 1 and "A" <= up <= "D":
            idx = ord(up) - ord("A")
            if idx < len(options):
                return idx
        if s.isdigit() and int(s) < len(options):
            return int(s)
        for i, opt in enumerate(options):
            if str(opt).strip().lower() == s.lower():
                return i
        return None

    def _norm_tf(value) -> str:
        s = str(value or "").strip().upper()
        if s.startswith("T"):
            return "T"
        if s.startswith("F"):
            return "F"
        return ""

    questions = json.loads(quiz.questions_json)
    score = 0.0
    max_score = float(len(questions))
    details = []

    for idx, q in enumerate(questions):
        options = q.get("options") or []
        correct_raw = q.get("answer") or q.get("correct_answer") or ""
        student_raw = payload.answers.get(idx, "")
        q_type = q.get("type") or ("multiple_choice" if options else "short_answer")

        if options and q_type == "multiple_choice":
            c_idx = _resolve_option_index(correct_raw, options)
            s_idx = _resolve_option_index(student_raw, options)
            is_correct = c_idx is not None and c_idx == s_idx
            correct_display = options[c_idx] if c_idx is not None else str(correct_raw)
            student_display = options[s_idx] if s_idx is not None else str(student_raw)
        elif q_type == "true_false":
            is_correct = bool(student_raw) and _norm_tf(correct_raw) == _norm_tf(student_raw)
            correct_display = str(correct_raw)
            student_display = str(student_raw)
        else:
            is_correct = (
                bool(str(student_raw).strip())
                and str(student_raw).strip().lower() == str(correct_raw).strip().lower()
            )
            correct_display = str(correct_raw)
            student_display = str(student_raw)

        if is_correct:
            score += 1.0

        details.append({
            "question_index": idx,
            "correct": is_correct,
            "student_answer": student_display,
            "correct_answer": correct_display,
            "explanation": q.get("explanation", ""),
            "question_type": q_type,
        })

    # Instructor policy: hide correct answers/explanations when reveal_answers is off
    if not quiz.reveal_answers:
        for d in details:
            d.pop("correct_answer", None)
            d.pop("explanation", None)

    percentage = (score / max_score * 100) if max_score > 0 else 0.0
    passed = percentage >= 60.0  # 60% passing threshold

    attempt.submitted_at = datetime.now(timezone.utc)
    attempt.answers_json = json.dumps(payload.answers)
    attempt.score = score
    attempt.max_score = max_score
    attempt.details_json = json.dumps(details)
    db.commit()

    # Audit: student submitting quiz
    log_audit_event(db, action="submit_quiz", user=user, resource_type="quiz", resource_id=str(quiz_id), request=request, details={
        "attempt_id": attempt.id,
        "score": score,
        "max_score": max_score,
        "percentage": percentage,
        "elapsed_seconds": server_elapsed,
    })

    return QuizSubmitResponse(
        attempt_id=attempt.id,
        score=score,
        max_score=max_score,
        percentage=percentage,
        details=details,
        passed=passed,
    )


# ─── Instructor: Attempt Management ──────────────────────────────────────────────

@router.get("/{quiz_id}/attempts")
def list_quiz_attempts(
    quiz_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor"))
):
    """
    List all attempts for a quiz (instructor only).
    """
    quiz = db.query(Quiz).filter_by(id=quiz_id).first()
    if not quiz:
        raise HTTPException(404, "Quiz not found")

    # Verify instructor owns the quiz (or is admin)
    if quiz.session_id:
        session = db.query(ClassSession).filter_by(id=quiz.session_id).first()
        if session and session.instructor_id != user.id and user.role != "admin":
            raise HTTPException(403, "Not your quiz")

    attempts = db.query(QuizAttempt).filter_by(quiz_id=quiz_id).order_by(QuizAttempt.started_at.desc()).all()

    # Audit: instructor viewing attempts
    log_audit_event(db, action="list_quiz_attempts", user=user, resource_type="quiz", resource_id=str(quiz_id), request=request)

    return [
        {
            "id": a.id,
            "student_id": a.student_id,
            "student_name": db.query(User).filter_by(id=a.student_id).first().name if db.query(User).filter_by(id=a.student_id).first() else "Unknown",
            "started_at": a.started_at,
            "submitted_at": a.submitted_at,
            "is_locked": a.is_locked,
            "lock_reason": a.lock_reason,
            "score": a.score,
            "max_score": a.max_score,
            "percentage": round((a.score / a.max_score * 100), 1) if a.score and a.max_score else None,
        }
        for a in attempts
    ]


@router.get("/{quiz_id}/my-attempts", response_model=list[QuizAttemptOut])
def list_my_quiz_attempts(
    quiz_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("student")),
):
    """Return only the current student's attempts for a quiz."""
    quiz = db.query(Quiz).filter_by(id=quiz_id).first()
    if not quiz:
        raise HTTPException(404, "Quiz not found")
    if quiz.session_id:
        enrolled = db.query(SessionRegistration).filter_by(
            session_id=quiz.session_id,
            student_id=user.id,
        ).first()
        if not enrolled:
            raise HTTPException(403, "You are not enrolled in the session this quiz belongs to")
    return (
        db.query(QuizAttempt)
        .filter_by(quiz_id=quiz_id, student_id=user.id)
        .order_by(QuizAttempt.started_at.desc(), QuizAttempt.id.desc())
        .all()
    )


# ─── Anti-Cheat: Violation Logging & Review ──────────────────────────────────────

@router.post("/{quiz_id}/violations", response_model=QuizViolationOut)
def log_quiz_violation(
    quiz_id: int,
    event_type: str,
    details: Optional[dict] = None,
    request: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("student"))
):
    """
    Log an anti-cheat violation from the frontend.
    Called automatically when fullscreen exit, tab switch, or second device detected.
    Auto-locks the attempt and submits current answers.
    """
    quiz = db.query(Quiz).filter_by(id=quiz_id).first()
    if not quiz:
        raise HTTPException(404, "Quiz not found")

    # Get active attempt
    attempt = db.query(QuizAttempt).filter_by(
        quiz_id=quiz_id,
        student_id=user.id,
        submitted_at=None
    ).first()

    violation = QuizViolation(
        quiz_id=quiz_id,
        attempt_id=attempt.id if attempt else None,
        student_id=user.id,
        event_type=event_type,
        details_json=json.dumps(details) if details else None,
    )
    db.add(violation)

    # Lock the attempt if it exists and isn't already locked
    if attempt and not attempt.is_locked:
        attempt.is_locked = True
        attempt.lock_reason = f"Anti-cheat violation: {event_type}"
        # Auto-submit current answers (partial credit)
        # Note: actual answers would need to be sent from frontend; we just mark as locked

    db.commit()
    db.refresh(violation)

    # Audit
    log_audit_event(db, action="quiz_violation", user=user, resource_type="quiz", resource_id=str(quiz_id), request=request, details={
        "violation_id": violation.id,
        "event_type": event_type,
        "attempt_id": attempt.id if attempt else None,
    })

    return QuizViolationOut.model_validate(violation)


@router.get("/{quiz_id}/violations", response_model=list[QuizViolationOut])
def list_quiz_violations(
    quiz_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor"))
):
    """
    List all violations for a quiz (instructor only).
    """
    quiz = db.query(Quiz).filter_by(id=quiz_id).first()
    if not quiz:
        raise HTTPException(404, "Quiz not found")

    if quiz.session_id:
        session = db.query(ClassSession).filter_by(id=quiz.session_id).first()
        if session and session.instructor_id != user.id and user.role != "admin":
            raise HTTPException(403, "Not your quiz")

    violations = db.query(QuizViolation).filter_by(quiz_id=quiz_id).order_by(QuizViolation.timestamp.desc()).all()

    # Audit: instructor reviewing violations
    log_audit_event(db, action="list_quiz_violations", user=user, resource_type="quiz", resource_id=str(quiz_id), request=request)

    return [QuizViolationOut.model_validate(v) for v in violations]


@router.post("/{quiz_id}/attempts/{attempt_id}/re-enable")
def re_enable_quiz_attempt(
    quiz_id: int,
    attempt_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor"))
):
    """
    Instructor manually re-enables a locked quiz attempt.
    Requires explicit instructor action - no auto re-enable.
    """
    quiz = db.query(Quiz).filter_by(id=quiz_id).first()
    if not quiz:
        raise HTTPException(404, "Quiz not found")

    if quiz.session_id:
        session = db.query(ClassSession).filter_by(id=quiz.session_id).first()
        if session and session.instructor_id != user.id and user.role != "admin":
            raise HTTPException(403, "Not your quiz")

    attempt = db.query(QuizAttempt).filter_by(id=attempt_id, quiz_id=quiz_id).first()
    if not attempt:
        raise HTTPException(404, "Attempt not found")

    if not attempt.is_locked:
        raise HTTPException(400, "Attempt is not locked")

    # Unlock the attempt
    attempt.is_locked = False
    attempt.lock_reason = None

    # Update related violations as reviewed and re-entry approved
    violations = db.query(QuizViolation).filter_by(attempt_id=attempt_id).all()
    for v in violations:
        v.is_reviewed = True
        v.reviewed_by = user.id
        v.reviewed_at = datetime.now(timezone.utc)
        v.re_entry_approved = True

    db.commit()

    # Audit: instructor re-enabling attempt
    log_audit_event(db, action="re_enable_quiz_attempt", user=user, resource_type="quiz_attempt", resource_id=str(attempt_id), request=request, details={
        "quiz_id": quiz_id,
        "student_id": attempt.student_id,
    })

    return {"message": "Quiz attempt re-enabled. Student can now resume."}