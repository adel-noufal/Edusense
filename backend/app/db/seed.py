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


def _ensure_schema_updates(db):
    """Ensure newly added columns exist in PostgreSQL or SQLite tables."""
    try:
        if "postgresql" in str(engine.url):
            db.execute(text("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS prep_start_time TIMESTAMP WITH TIME ZONE;"))
            db.execute(text("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS reminders_sent VARCHAR(200);"))
            db.execute(text("ALTER TABLE ai_generations ADD COLUMN IF NOT EXISTS session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL;"))
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS session_resources (
                    id SERIAL PRIMARY KEY,
                    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    instructor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name VARCHAR(255) NOT NULL,
                    file_path VARCHAR(500) NOT NULL,
                    file_type VARCHAR(80) DEFAULT 'file',
                    file_size INTEGER,
                    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """))
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS generation_jobs (
                    id VARCHAR(36) PRIMARY KEY,
                    instructor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    job_type VARCHAR(40) NOT NULL,
                    label VARCHAR(180) DEFAULT '',
                    status VARCHAR(20) DEFAULT 'pending',
                    result_json TEXT,
                    error TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
            """))
        else:
            res = db.execute(text("PRAGMA table_info(sessions);")).fetchall()
            cols = [r[1] for r in res]
            if "prep_start_time" not in cols:
                db.execute(text("ALTER TABLE sessions ADD COLUMN prep_start_time DATETIME;"))
            if "reminders_sent" not in cols:
                db.execute(text("ALTER TABLE sessions ADD COLUMN reminders_sent VARCHAR(200);"))
            gen_cols = [r[1] for r in db.execute(text("PRAGMA table_info(ai_generations);")).fetchall()]
            if "session_id" not in gen_cols:
                db.execute(text("ALTER TABLE ai_generations ADD COLUMN session_id INTEGER;"))
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS session_resources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    instructor_id INTEGER NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    file_path VARCHAR(500) NOT NULL,
                    file_type VARCHAR(80) DEFAULT 'file',
                    file_size INTEGER,
                    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """))
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS generation_jobs (
                    id VARCHAR(36) PRIMARY KEY,
                    instructor_id INTEGER NOT NULL,
                    job_type VARCHAR(40) NOT NULL,
                    label VARCHAR(180) DEFAULT '',
                    status VARCHAR(20) DEFAULT 'pending',
                    result_json TEXT,
                    error TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """))
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"[Schema Check Note] {exc}")



def init_db(seed: bool = True):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _ensure_schema_updates(db)
        if not seed:
            return
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
