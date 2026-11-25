"""Reversible archiving of test/QA session rows (U11).

Tests and QA scripts wrote directly into the developer database, so the Sessions
page filled with "Empty Test Session" and "B5 Future" rows. Deleting them is not
the first move: this module exports them to JSON and hides them (archived_at),
which every session listing filters out. `restore` clears the flag, so the rows
and their ids come back exactly as they were.

A row is matched only when ALL of these hold:
- its title is exactly one of TEST_TITLES,
- it has no student registrations,
- it has no session resources,
- it has no reports.
Real teaching sessions are never matched, whatever their title.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session as OrmSession

from app.models.models import Report, Session, SessionRegistration, SessionResource
from app.services.timefmt import iso_z

TEST_TITLES = ("Empty Test Session", "B5 Future", "Test Session")


def visible_sessions(db: OrmSession, model=Session):
    """Every session listing starts here, so archived rows never reappear."""
    return db.query(model).filter(model.archived_at.is_(None))


def find_test_session_rows(db: OrmSession, titles: tuple[str, ...] = TEST_TITLES) -> list[Session]:
    """Rows matching a test title that carry no student data at all."""
    candidates = db.query(Session).filter(Session.title.in_(titles)).all()
    matched: list[Session] = []
    for row in candidates:
        has_registration = db.query(SessionRegistration).filter_by(session_id=row.id).first()
        has_resource = db.query(SessionResource).filter_by(session_id=row.id).first()
        has_report = db.query(Report).filter_by(session_id=row.id).first()
        if not (has_registration or has_resource or has_report):
            matched.append(row)
    return matched


def row_to_dict(db: OrmSession, row: Session) -> dict:
    return {
        "id": row.id,
        "instructor_id": row.instructor_id,
        "title": row.title,
        "description": row.description,
        "date": str(row.date) if row.date else None,
        "start_time": str(row.start_time) if row.start_time else None,
        "duration": row.duration,
        "max_students": row.max_students,
        "status": row.status,
        "prep_start_time": iso_z(row.prep_start_time),
        "reminder_sent": row.reminder_sent,
        "reminders_sent": row.reminders_sent,
        "registrations": [
            {"id": reg.id, "student_id": reg.student_id}
            for reg in db.query(SessionRegistration).filter_by(session_id=row.id).all()
        ],
        "resources": [
            {"id": res.id, "name": res.name}
            for res in db.query(SessionResource).filter_by(session_id=row.id).all()
        ],
        "reports": [
            {"id": rep.id}
            for rep in db.query(Report).filter_by(session_id=row.id).all()
        ],
    }


def archive_rows(db: OrmSession, rows: list[Session]) -> int:
    stamp = datetime.now(timezone.utc)
    for row in rows:
        row.archived_at = stamp
    db.commit()
    return len(rows)


def restore_rows(db: OrmSession, session_ids: list[int]) -> int:
    rows = db.query(Session).filter(Session.id.in_(session_ids)).all()
    for row in rows:
        row.archived_at = None
    db.commit()
    return len(rows)
