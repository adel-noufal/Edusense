"""
Quiz Attempt & Anti-Cheat API Endpoints

Handles student quiz taking with server-side timer validation,
anti-cheat violation logging, and instructor violation review/re-entry.
"""
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.core.audit import log_audit_event, log_student_data_access
from app.db.session import get_db
from app.models.models import Quiz, QuizAttempt, QuizViolation, User, Session as ClassSession
from app.schemas.schemas import (
    QuizOut, PublishExamRequest, QuizAttemptOut, QuizSubmitRequest, QuizSubmitResponse,
    QuizViolationOut, QuizAgentConfigCreate, QuizAgentConfigOut, QuizAgentConfigUpdate
)
from app.models.models import SessionRegistration

router = APIRouter(prefix="/quizzes", tags=["Quiz Attempts"])


# ─── Student: Quiz Taking ────────────────────────────────────────────────────────

@router.get("/{quiz_id}", response_model=QuizOut)
def get_quiz_for_student(
    quiz_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("student"))
):
    """
    Get quiz metadata for student (questions WITHOUT correct answers).
    Checks enrollment if quiz is linked to a session.
    """
    quiz = db.query(Quiz).filter_by(id=quiz_id).first()
    if not quiz:
        raise HTTPException(404, "Quiz not found")

    # If quiz is linked to a session, verify student is enrolled
    if quiz.session_id:
        reg = db.query(ClassSession).join(ClassSession.registrations).filter(
            ClassSession.id == quiz.session_id,
            ClassSession.registrations.any(student_id=user.id)
        ).first()
        if not reg:
            raise HTTPException(403, "You are not enrolled in the session this quiz belongs to")

    # Strip correct answers from questions for student view
    questions = json.loads(quiz.questions_json)
    safe_questions = []
    for q in questions:
        safe_q = {k: v for k, v in q.items() if k != "answer"}
        safe_questions.append(safe_q)

    # Audit: student viewing quiz
    log_audit_event(db, action="view_quiz", user=user, resource_type="quiz", resource_id=str(quiz_id), request=request)

    return QuizOut(
        id=quiz.id,
        session_id=quiz.session_id,
        title=quiz.title,
        difficulty=quiz.difficulty,
        questions=safe_questions,
        created_at=quiz.created_at,
        time_limit_seconds=quiz.time_limit_seconds,
        time_limit_per_question_seconds=quiz.time_limit_per_question_seconds,
        fullscreen_lock=quiz.fullscreen_lock,
        camera_monitoring=quiz.camera_monitoring,
        is_published=quiz.is_published,
        is_exam=quiz.is_exam,
        lock_back_navigation=quiz.lock_back_navigation,
        due_date=quiz.due_date,
    )


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
            safe_q = {k: v for k, v in q.items() if k != "answer"}
            safe_questions.append(safe_q)

        result.append(QuizOut(
            id=quiz.id,
            session_id=quiz.session_id,
            title=quiz.title,
            difficulty=quiz.difficulty,
            questions=safe_questions,
            created_at=quiz.created_at,
            time_limit_seconds=quiz.time_limit_seconds,
            time_limit_per_question_seconds=quiz.time_limit_per_question_seconds,
            fullscreen_lock=quiz.fullscreen_lock,
            camera_monitoring=quiz.camera_monitoring,
            is_published=quiz.is_published,
            is_exam=quiz.is_exam,
            lock_back_navigation=quiz.lock_back_navigation,
            due_date=quiz.due_date,
        ))

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
    # Get all session IDs the student is enrolled in
    enrolled_session_ids = [
        r.session_id for r in
        db.query(SessionRegistration).filter_by(student_id=user.id).all()
    ]

    if not enrolled_session_ids:
        return []

    quizzes = (
        db.query(Quiz)
        .filter(
            Quiz.session_id.in_(enrolled_session_ids),
            Quiz.is_exam == True,
            Quiz.is_published == True,
        )
        .order_by(Quiz.created_at.desc())
        .all()
    )

    # Audit
    log_audit_event(db, action="list_student_exams", user=user,
                    resource_type="quiz", resource_id="all", request=request)

    result = []
    for quiz in quizzes:
        import json as _json
        questions = _json.loads(quiz.questions_json)
        safe_questions = [{k: v for k, v in q.items() if k != "answer"} for q in questions]
        result.append(QuizOut(
            id=quiz.id,
            session_id=quiz.session_id,
            title=quiz.title,
            difficulty=quiz.difficulty,
            questions=safe_questions,
            created_at=quiz.created_at,
            time_limit_seconds=quiz.time_limit_seconds,
            time_limit_per_question_seconds=quiz.time_limit_per_question_seconds,
            fullscreen_lock=quiz.fullscreen_lock,
            camera_monitoring=quiz.camera_monitoring,
            is_published=quiz.is_published,
            is_exam=quiz.is_exam,
            lock_back_navigation=quiz.lock_back_navigation,
            due_date=quiz.due_date,
        ))
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
    Publish a quiz as an Exam for a specific session.
    Sets is_exam=True, is_published=True, and configures anti-cheat + navigation locks.
    """
    quiz = db.query(Quiz).filter_by(id=quiz_id).first()
    if not quiz:
        raise HTTPException(404, "Quiz not found")

    session = db.query(ClassSession).filter_by(id=payload.session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    if session.instructor_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your session")

    quiz.is_exam = True
    quiz.is_published = True
    quiz.session_id = payload.session_id
    quiz.time_limit_seconds = payload.time_limit_seconds
    quiz.time_limit_per_question_seconds = payload.time_limit_per_question_seconds
    quiz.lock_back_navigation = payload.lock_back_navigation
    quiz.fullscreen_lock = payload.fullscreen_lock
    quiz.camera_monitoring = payload.camera_monitoring
    quiz.due_date = payload.due_date

    db.commit()
    db.refresh(quiz)

    log_audit_event(
        db, action="publish_quiz_as_exam", user=user,
        resource_type="quiz", resource_id=str(quiz.id), request=request,
        details={
            "session_id": payload.session_id,
            "time_limit_seconds": payload.time_limit_seconds,
            "time_limit_per_question_seconds": payload.time_limit_per_question_seconds,
            "lock_back_navigation": payload.lock_back_navigation,
            "fullscreen_lock": payload.fullscreen_lock,
            "camera_monitoring": payload.camera_monitoring,
        }
    )

    questions = json.loads(quiz.questions_json)
    return QuizOut(
        id=quiz.id,
        session_id=quiz.session_id,
        title=quiz.title,
        difficulty=quiz.difficulty,
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
    )


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

    # Check for existing active (unsubmitted, unlocked) attempt
    existing = db.query(QuizAttempt).filter_by(
        quiz_id=quiz_id,
        student_id=user.id,
        submitted_at=None
    ).first()
    if existing and not existing.is_locked:
        # Return existing attempt instead of creating new one
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

    # Score the quiz
    questions = json.loads(quiz.questions_json)
    score = 0.0
    max_score = float(len(questions))
    details = []

    for idx, q in enumerate(questions):
        correct_answer = q.get("answer", "").strip().upper()
        student_answer = payload.answers.get(idx, "").strip().upper()
        is_correct = student_answer == correct_answer
        if is_correct:
            score += 1.0

        details.append({
            "question_index": idx,
            "correct": is_correct,
            "student_answer": payload.answers.get(idx, ""),
            "correct_answer": q.get("answer", ""),
            "explanation": q.get("explanation", ""),
            "question_type": q.get("type", "multiple_choice"),
        })

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