"""
Assignment API Endpoints — Section 3

Instructor CRUD for assignments tied to sessions; student submission upload.
"""
import os
import shutil
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.core.audit import log_audit_event
from app.db.session import get_db
from app.models.models import (
    Assignment,
    AssignmentSubmission,
    SessionRegistration,
    Session as ClassSession,
    User,
)
from app.schemas.schemas import AssignmentIn, AssignmentOut, AssignmentSubmissionOut

router = APIRouter(prefix="/assignments", tags=["Assignments"])

# Directory where submission files are stored (created on first use)
SUBMISSIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "submissions")


def _ensure_submissions_dir():
    os.makedirs(SUBMISSIONS_DIR, exist_ok=True)


# ─── Instructor: Create / List assignments ────────────────────────────────────

@router.post("/", response_model=AssignmentOut, status_code=201)
def create_assignment(
    body: AssignmentIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor")),
):
    """Create a new assignment for a session (instructor only)."""
    # Verify the session belongs to this instructor
    session = db.query(ClassSession).filter_by(id=body.session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")
    if session.instructor_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your session")

    assignment = Assignment(
        session_id=body.session_id,
        instructor_id=user.id,
        title=body.title,
        description=body.description,
        due_date=body.due_date,
        max_points=body.max_points,
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    log_audit_event(
        db, action="create_assignment", user=user,
        resource_type="assignment", resource_id=str(assignment.id), request=request,
        details={"session_id": body.session_id, "title": body.title},
    )
    return AssignmentOut.model_validate(assignment)


@router.get("/session/{session_id}", response_model=list[AssignmentOut])
def list_assignments_for_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    List all assignments for a session.
    Instructors see all; students must be enrolled.
    """
    session = db.query(ClassSession).filter_by(id=session_id).first()
    if not session:
        raise HTTPException(404, "Session not found")

    if user.role == "student":
        enrolled = db.query(SessionRegistration).filter_by(
            session_id=session_id, student_id=user.id
        ).first()
        if not enrolled:
            raise HTTPException(403, "You are not enrolled in this session")
    elif user.role == "instructor" and session.instructor_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your session")

    assignments = (
        db.query(Assignment)
        .filter_by(session_id=session_id)
        .order_by(Assignment.created_at.asc())
        .all()
    )
    return [AssignmentOut.model_validate(a) for a in assignments]


# ─── Student: list all assignments across enrolled sessions ───────────────────

@router.get("/student", response_model=list[AssignmentOut])
def list_my_assignments(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("student")),
):
    """Return all assignments for the student's enrolled sessions."""
    enrolled_session_ids = [
        r.session_id
        for r in db.query(SessionRegistration).filter_by(student_id=user.id).all()
    ]
    if not enrolled_session_ids:
        return []

    assignments = (
        db.query(Assignment)
        .filter(Assignment.session_id.in_(enrolled_session_ids))
        .order_by(Assignment.due_date.asc(), Assignment.created_at.asc())
        .all()
    )

    log_audit_event(
        db, action="list_my_assignments", user=user,
        resource_type="assignment", resource_id="all", request=request,
    )
    return [AssignmentOut.model_validate(a) for a in assignments]


# ─── Student: submit assignment file ─────────────────────────────────────────

@router.post("/{assignment_id}/submit", response_model=AssignmentSubmissionOut)
def submit_assignment(
    assignment_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("student")),
):
    """
    Student uploads a submission file (PDF, Word, image, etc.).
    Only one submission per student per assignment — re-submitting replaces it.
    """
    assignment = db.query(Assignment).filter_by(id=assignment_id).first()
    if not assignment:
        raise HTTPException(404, "Assignment not found")

    # Verify enrollment
    enrolled = db.query(SessionRegistration).filter_by(
        session_id=assignment.session_id, student_id=user.id
    ).first()
    if not enrolled:
        raise HTTPException(403, "You are not enrolled in this session")

    # Validate file type (allow PDF, Word, images, zip, txt)
    ALLOWED_TYPES = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/jpeg", "image/png", "image/gif", "image/webp",
        "text/plain",
        "application/zip",
    }
    # Fallback: check by extension if content-type is generic
    if file.content_type not in ALLOWED_TYPES:
        ext = (file.filename or "").rsplit(".", 1)[-1].lower()
        ALLOWED_EXTS = {"pdf", "doc", "docx", "jpg", "jpeg", "png", "gif",
                        "webp", "txt", "zip"}
        if ext not in ALLOWED_EXTS:
            raise HTTPException(
                400, f"File type not allowed. Supported: PDF, Word, images, text, zip"
            )

    _ensure_submissions_dir()

    # Build safe filename
    safe_name = file.filename.replace("..", "").replace("/", "").replace("\\", "")
    dest_name = f"submission-{assignment_id}-{user.id}-{safe_name}"
    dest_path = os.path.join(SUBMISSIONS_DIR, dest_name)

    # Read file bytes to get size, then write
    file_bytes = file.file.read()
    file_size = len(file_bytes)

    if file_size == 0:
        raise HTTPException(400, "Uploaded file is empty")
    if file_size > 50 * 1024 * 1024:  # 50 MB limit
        raise HTTPException(413, "File too large (max 50 MB)")

    with open(dest_path, "wb") as f:
        f.write(file_bytes)

    # Remove old submission record if re-submitting
    existing = db.query(AssignmentSubmission).filter_by(
        assignment_id=assignment_id, student_id=user.id
    ).first()
    if existing:
        # Delete old file from disk if it exists
        if existing.file_path and os.path.exists(existing.file_path):
            try:
                os.remove(existing.file_path)
            except OSError:
                pass
        db.delete(existing)
        db.flush()

    submission = AssignmentSubmission(
        assignment_id=assignment_id,
        student_id=user.id,
        file_name=file.filename,
        file_path=dest_path,
        file_size=file_size,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    log_audit_event(
        db, action="submit_assignment", user=user,
        resource_type="assignment_submission", resource_id=str(submission.id),
        request=request,
        details={"assignment_id": assignment_id, "file_name": file.filename,
                 "file_size": file_size},
    )
    return AssignmentSubmissionOut.model_validate(submission)


@router.get("/{assignment_id}/submission", response_model=AssignmentSubmissionOut | None)
def get_my_submission(
    assignment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("student")),
):
    """Return the student's submission for an assignment, or null if not submitted."""
    assignment = db.query(Assignment).filter_by(id=assignment_id).first()
    if not assignment:
        raise HTTPException(404, "Assignment not found")

    # Verify enrollment
    enrolled = db.query(SessionRegistration).filter_by(
        session_id=assignment.session_id, student_id=user.id
    ).first()
    if not enrolled:
        raise HTTPException(403, "You are not enrolled in this session")

    submission = db.query(AssignmentSubmission).filter_by(
        assignment_id=assignment_id, student_id=user.id
    ).first()

    return AssignmentSubmissionOut.model_validate(submission) if submission else None


# ─── Instructor: list all submissions for an assignment ───────────────────────

@router.get("/{assignment_id}/submissions", response_model=list[AssignmentSubmissionOut])
def list_submissions(
    assignment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("instructor")),
):
    """List all student submissions for a given assignment (instructor only)."""
    assignment = db.query(Assignment).filter_by(id=assignment_id).first()
    if not assignment:
        raise HTTPException(404, "Assignment not found")

    # Verify ownership
    session = db.query(ClassSession).filter_by(id=assignment.session_id).first()
    if session and session.instructor_id != user.id and user.role != "admin":
        raise HTTPException(403, "Not your assignment")

    submissions = (
        db.query(AssignmentSubmission)
        .filter_by(assignment_id=assignment_id)
        .order_by(AssignmentSubmission.submitted_at.asc())
        .all()
    )

    log_audit_event(
        db, action="list_assignment_submissions", user=user,
        resource_type="assignment", resource_id=str(assignment_id), request=request,
    )
    return [AssignmentSubmissionOut.model_validate(s) for s in submissions]
