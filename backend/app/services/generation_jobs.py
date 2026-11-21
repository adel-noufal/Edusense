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
    # Run a quick reap before listing
    reap_stale_jobs(db, max_age_seconds=300)
    jobs = (
        db.query(GenerationJob)
        .filter_by(instructor_id=instructor_id, status="pending")
        .order_by(GenerationJob.created_at.desc())
        .all()
    )
    return [{"job_id": j.id, "type": j.job_type, "label": j.label, "status": j.status, "startedAt": j.created_at.isoformat()} for j in jobs]


def reap_stale_jobs(db: DbSession, max_age_seconds: int = 300) -> int:
    """Mark any pending/processing jobs older than max_age_seconds as failed."""
    from app.models.models import VideoProject
    now = utcnow()
    reaped = 0
    try:
        # 1. Generation jobs
        stale_jobs = db.query(GenerationJob).filter(GenerationJob.status.in_(["pending", "processing"])).all()
        for j in stale_jobs:
            ref_time = j.updated_at or j.created_at
            if ref_time and ref_time.tzinfo is None:
                ref_time = ref_time.replace(tzinfo=timezone.utc)
            if ref_time and (now - ref_time).total_seconds() > max_age_seconds:
                j.status = "failed"
                j.error = f"Job timed out (no progress for {max_age_seconds//60} minutes) - marked failed by reaper"
                j.updated_at = now
                reaped += 1

        # 2. Video projects stuck on processing
        stale_videos = db.query(VideoProject).filter_by(status="processing").all()
        for v in stale_videos:
            ref_time = v.created_at
            if ref_time and ref_time.tzinfo is None:
                ref_time = ref_time.replace(tzinfo=timezone.utc)
            if ref_time and (now - ref_time).total_seconds() > max_age_seconds:
                v.status = "failed"
                reaped += 1

        if reaped > 0:
            db.commit()
    except Exception:
        db.rollback()
    return reaped


def cleanup_stuck_jobs_on_startup(db: DbSession) -> int:
    """Clear all stuck pending/processing jobs and video projects on server boot."""
    from app.models.models import VideoProject
    now = utcnow()
    count = 0
    try:
        jobs = db.query(GenerationJob).filter(GenerationJob.status.in_(["pending", "processing"])).all()
        for j in jobs:
            j.status = "failed"
            j.error = "Server restarted while job was in progress"
            j.updated_at = now
            count += 1
        
        videos = db.query(VideoProject).filter_by(status="processing").all()
        for v in videos:
            v.status = "failed"
            count += 1

        if count > 0:
            db.commit()
    except Exception:
        db.rollback()
    return count
