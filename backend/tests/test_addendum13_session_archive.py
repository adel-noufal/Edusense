"""U11 regression test: leftover test rows are hidden reversibly, real ones stay.

The visible symptom was a Sessions list full of "Empty Test Session" and
"B5 Future" rows. This test builds those rows (plus a real session of the same
title that has a registration) in the test database, archives the leftovers, and
checks that every listing helper hides the archived rows while the real session
and the protected titles are untouched. Restoring brings the rows back.
"""
from datetime import date, time

from app.db.session import SessionLocal
from app.models.models import Session, SessionRegistration, User
from app.services.session_archive import (
    archive_rows,
    restore_rows,
    find_test_session_rows,
    visible_sessions,
)

MARKER = date(2099, 1, 2)


def _cleanup(db, ids):
    db.query(SessionRegistration).filter(SessionRegistration.session_id.in_(ids)).delete(synchronize_session=False)
    db.query(Session).filter(Session.id.in_(ids)).delete(synchronize_session=False)
    db.commit()


def test_leftover_test_rows_are_archived_and_restorable():
    db = SessionLocal()
    created: list[int] = []
    try:
        student = db.query(User).filter_by(role="student").first()
        assert student is not None

        empty_test = Session(instructor_id=student.id, title="Empty Test Session",
                             description="", date=MARKER, start_time=time(9, 0),
                             duration=30, status="completed")
        future = Session(instructor_id=student.id, title="B5 Future",
                         description="", date=MARKER, start_time=time(10, 0),
                         duration=30, status="missed")
        real_same_title = Session(instructor_id=student.id, title="Empty Test Session",
                                  description="has a student", date=MARKER, start_time=time(11, 0),
                                  duration=30, status="ended")
        protected = Session(instructor_id=student.id, title="Task 9 Quantum Computing",
                            description="", date=MARKER, start_time=time(12, 0),
                            duration=30, status="ended")
        db.add_all([empty_test, future, real_same_title, protected])
        db.commit()
        created = [empty_test.id, future.id, real_same_title.id, protected.id]
        db.add(SessionRegistration(session_id=real_same_title.id, student_id=student.id))
        db.commit()

        matched = [row.id for row in find_test_session_rows(db) if row.id in created]
        assert matched == [empty_test.id, future.id], "only empty test rows may match"

        assert archive_rows(db, [empty_test, future]) == 2
        db.expire_all()

        visible_ids = {row.id for row in visible_sessions(db).all()}
        assert empty_test.id not in visible_ids
        assert future.id not in visible_ids
        # A row with a real registration and a real session keep showing up.
        assert real_same_title.id in visible_ids
        assert protected.id in visible_ids

        # Restore puts them back exactly.
        assert restore_rows(db, [empty_test.id, future.id]) == 2
        visible_ids = {row.id for row in visible_sessions(db).all()}
        assert {empty_test.id, future.id} <= visible_ids
    finally:
        if created:
            _cleanup(db, created)
        db.close()
