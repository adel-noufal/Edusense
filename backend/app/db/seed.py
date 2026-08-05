from datetime import date, time, timedelta
from sqlalchemy import text
from app.core.security import hash_password
from app.db.session import Base, SessionLocal, engine
from app.models.models import EmotionLog, Profile, Session, SessionRegistration, User


def _reset_pg_sequences(db):
    """Reset PostgreSQL sequences so new inserts don't collide with seeded IDs."""
    if "postgresql" not in str(engine.url):
        return
    tables = ["users", "profiles", "sessions", "session_registrations",
              "emotion_logs", "reports", "feedback", "video_projects",
              "quizzes", "session_notes"]
    for table in tables:
        try:
            db.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"
            ))
        except Exception:
            pass
    db.commit()


def init_db(seed: bool = True):
    Base.metadata.create_all(bind=engine)
    if not seed:
        return
    db = SessionLocal()
    try:
        if db.query(User).first():
            _reset_pg_sequences(db)
            return
        instructor = User(name="Dr. Adel Hassan", email="instructor@edusense.local", password_hash=hash_password("Password123"), role="instructor")
        student = User(name="Mona Student", email="student@edusense.local", password_hash=hash_password("Password123"), role="student")
        db.add_all([instructor, student])
        db.commit()
        db.refresh(instructor)
        db.refresh(student)
        db.add_all([Profile(user_id=instructor.id, university="EduSense University", department="AI Education"), Profile(user_id=student.id, university="EduSense University", department="Computer Science")])
        session = Session(instructor_id=instructor.id, title="Introduction to Machine Learning", description="Live adaptive lesson with emotion analytics.", date=date.today() + timedelta(days=1), start_time=time(10, 0), duration=60, max_students=40, status="pending")
        db.add(session)
        db.commit()
        db.refresh(session)
        db.add(SessionRegistration(session_id=session.id, student_id=student.id, attended=False))
        db.add_all([
            EmotionLog(session_id=session.id, student_id=student.id, emotion="neutral", confidence=0.82),
            EmotionLog(session_id=session.id, student_id=student.id, emotion="happy", confidence=0.74),
            EmotionLog(session_id=session.id, student_id=student.id, emotion="sad", confidence=0.48),
        ])
        db.commit()
        _reset_pg_sequences(db)
    finally:
        db.close()
