import importlib.util
import os
import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from app.models.models import Base
from app.db.seed import _ensure_schema_updates
from app.services.gemini import (
    GeminiKeyRotator,
    _is_rotatable_error,
    _is_rate_limit_error,
)


def test_schema_updates_sqlite_idempotency():
    """Verify _ensure_schema_updates runs cleanly on SQLite and is fully idempotent."""
    test_db_url = "sqlite:///:memory:"
    engine = create_engine(test_db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSession()

    try:
        # First execution: adds missing columns and tables
        _ensure_schema_updates(db)

        # Inspect columns on quizzes
        quiz_cols = [row[1] for row in db.execute(text("PRAGMA table_info(quizzes)")).fetchall()]
        assert "is_published" in quiz_cols
        assert "is_exam" in quiz_cols
        assert "lock_back_navigation" in quiz_cols
        assert "due_date" in quiz_cols

        # Inspect columns on session_registrations
        reg_cols = [row[1] for row in db.execute(text("PRAGMA table_info(session_registrations)")).fetchall()]
        assert "joined_at" in reg_cols
        assert "left_at" in reg_cols

        # Inspect new tables
        table_rows = db.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        tables = [r[0] for r in table_rows]
        assert "assignments" in tables
        assert "assignment_submissions" in tables
        assert "chat_messages" in tables

        # Second execution: must not crash with duplicate column errors
        _ensure_schema_updates(db)
    finally:
        db.close()


def test_alembic_migration_metadata():
    """Verify c59128f_harden_schema_task10 migration has valid metadata and callable upgrade/downgrade."""
    migration_path = Path(__file__).parent / "migrations" / "versions" / "c59128f_harden_schema_task10.py"
    assert migration_path.exists(), f"Migration file not found at {migration_path}"

    spec = importlib.util.spec_from_file_location("task10_migration", migration_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "c59128f01a23"
    assert module.down_revision == "ea27ee5275cf"
    assert callable(module.upgrade)
    assert callable(module.downgrade)


def test_rotatable_error_detection():
    """Verify _is_rotatable_error identifies rate limits, invalid keys, quota, and server capacity errors."""
    # HTTP 429 & 503
    assert _is_rotatable_error(429, "") is True
    assert _is_rotatable_error(503, "Service Unavailable") is True

    # Bad API key / permissions
    assert _is_rotatable_error(400, '{"error": {"message": "API_KEY_INVALID"}}') is True
    assert _is_rotatable_error(403, "API key not valid. Please pass a valid API key.") is True
    assert _is_rotatable_error(403, "PERMISSION_DENIED: billing_not_enabled for project") is True
    assert _is_rotatable_error(403, "The caller does not have permission / unregistered callers") is True
    assert _is_rotatable_error(400, "Your project has been suspended") is True

    # Quota / Resource exhausted
    assert _is_rotatable_error(400, "RESOURCE_EXHAUSTED: Rate limit per-minute quota exceeded") is True
    assert _is_rotatable_error(400, "too many requests") is True

    # Non-rotatable errors (client syntax errors, invalid JSON prompt, 404, 500 without capacity cues)
    assert _is_rotatable_error(400, "Invalid JSON payload received") is False
    assert _is_rotatable_error(404, "Model not found") is False
    assert _is_rotatable_error(500, "Internal server error") is False

    # Backwards compatibility alias
    assert _is_rate_limit_error(429, "") is True
    assert _is_rate_limit_error(403, "API_KEY_INVALID") is True


def test_rotator_failover_and_reset(monkeypatch):
    """Verify GeminiKeyRotator advances across keys on exhaustion and can be cleanly reset."""
    rotator = GeminiKeyRotator(cooldown_seconds=300.0)

    test_keys = ["AIzaSyKeyOne1111", "AIzaSyKeyTwo2222", "AIzaSyKeyThree3333"]
    monkeypatch.setattr(rotator, "get_keys", lambda: test_keys)

    # Initially at key 0
    assert rotator.get_active_key() == "AIzaSyKeyOne1111"
    status = rotator.status()
    assert status["total_keys"] == 3
    assert status["active_keys"] == 3
    assert status["exhausted_keys"] == 0

    # Exhaust key 1 -> should rotate to key 2
    next_key = rotator.mark_exhausted("AIzaSyKeyOne1111", reason="HTTP 400 API_KEY_INVALID")
    assert next_key == "AIzaSyKeyTwo2222"
    assert rotator.get_active_key() == "AIzaSyKeyTwo2222"

    status = rotator.status()
    assert status["active_keys"] == 2
    assert status["exhausted_keys"] == 1

    # Exhaust key 2 -> should rotate to key 3
    next_key = rotator.mark_exhausted("AIzaSyKeyTwo2222", reason="HTTP 429 Quota Exceeded")
    assert next_key == "AIzaSyKeyThree3333"
    assert rotator.get_active_key() == "AIzaSyKeyThree3333"

    # Exhaust key 3 -> all exhausted
    next_key = rotator.mark_exhausted("AIzaSyKeyThree3333", reason="HTTP 503")
    assert next_key is None

    # Reset rotator
    rotator.reset()
    assert rotator.get_active_key() == "AIzaSyKeyOne1111"
    status = rotator.status()
    assert status["active_keys"] == 3
    assert status["exhausted_keys"] == 0


def test_generate_content_rotates_on_invalid_key(monkeypatch):
    """Verify generate_content seamlessly fails over from an invalid key to a working key."""
    import io
    import json
    import urllib.error
    from app.services import gemini

    keys = ["BAD_KEY_1", "GOOD_KEY_2"]
    gemini.rotator.reset()
    monkeypatch.setattr(gemini.rotator, "get_keys", lambda: keys)

    class DummySettings:
        gemini_api_keys = keys
        gemini_model = "gemini-2.5-flash"

    monkeypatch.setattr(gemini, "get_settings", lambda: DummySettings())

    call_count = 0

    def mock_urlopen(request, timeout=15):
        nonlocal call_count
        call_count += 1
        url = request.full_url
        if "BAD_KEY_1" in url:
            fp = io.BytesIO(b'{"error": {"code": 400, "message": "API_KEY_INVALID"}}')
            raise urllib.error.HTTPError(url, 400, "Bad Request", hdrs={}, fp=fp)
        elif "GOOD_KEY_2" in url:
            payload = {
                "candidates": [{
                    "content": {
                        "parts": [{"text": "Success from key 2"}]
                    }
                }]
            }
            fp = io.BytesIO(json.dumps(payload).encode("utf-8"))
            return fp
        raise RuntimeError(f"Unexpected url: {url}")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    response = gemini.generate_content("hello")
    assert response == "Success from key 2"
    assert call_count == 2
    # Check rotator state: BAD_KEY_1 should be marked exhausted
    status = gemini.rotator.status()
    assert status["exhausted_keys"] == 1
    gemini.rotator.reset()


def test_frontend_quiz_timer_logic():
    """Verify Quiz.jsx has fixed closure for questionStartTime and attempt elapsed resumption."""
    quiz_path = Path(__file__).parents[1] / "frontend" / "src" / "pages" / "Quiz.jsx"
    assert quiz_path.exists(), f"Quiz.jsx not found at {quiz_path}"
    content = quiz_path.read_text(encoding="utf-8")

    # Resumption calculation
    assert "const elapsed = Math.max(0, Math.floor((Date.now() - serverStart) / 1000))" in content
    assert "const remaining = Math.max(0, quizData.time_limit_seconds - elapsed)" in content

    # Per-question closure
    assert "const qStart = Date.now()" in content
    assert "setQuestionStartTime(qStart)" in content
    assert "const elapsed = Math.floor((Date.now() - qStart) / 1000)" in content

    # Main timer auto-submit outside state reducer
    assert "setTimeout(() => handleTimeUp(), 0)" in content
