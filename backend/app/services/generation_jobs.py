"""Persistent generation job storage (survives server restarts)."""
import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session as DbSession
from app.models.models import GenerationJob


def utcnow():
    return datetime.now(timezone.utc)


def create_job(db: DbSession, job_id: str, instructor_id: int, job_type: str, label: str = "") -> GenerationJob:
    job = GenerationJob(
        id=job_id,
        instructor_id=instructor_id,
        job_type=job_type,
        label=label or job_type,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def set_job_status(db: DbSession, job_id: str, status: str, result=None, error: str | None = None) -> None:
    job = db.query(GenerationJob).filter_by(id=job_id).first()
    if not job:
        return
    job.status = status
    job.error = error
    job.result_json = json.dumps(result) if result is not None else job.result_json
    job.updated_at = utcnow()
    db.commit()


def get_job_payload(db: DbSession, job_id: str, instructor_id: int | None = None) -> dict | None:
    query = db.query(GenerationJob).filter_by(id=job_id)
    if instructor_id is not None:
        query = query.filter_by(instructor_id=instructor_id)
    job = query.first()
    if not job:
        return None
    result = None
    if job.result_json:
        try:
            result = json.loads(job.result_json)
        except Exception:
            result = job.result_json
    return {"status": job.status, "result": result, "error": job.error, "type": job.job_type, "label": job.label}


def list_pending_jobs(db: DbSession, instructor_id: int) -> list[dict]:
    jobs = (
        db.query(GenerationJob)
        .filter_by(instructor_id=instructor_id, status="pending")
        .order_by(GenerationJob.created_at.desc())
        .all()
    )
    return [{"job_id": j.id, "type": j.job_type, "label": j.label, "status": j.status, "startedAt": j.created_at.isoformat()} for j in jobs]
