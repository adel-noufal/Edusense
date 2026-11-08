"""
test_task10_11_quiz.py -- Integration tests for Task 10 (Quiz Timer) & Task 11 (Anti-Cheat).

Tests verify:
1. Quiz model exposes time_limit_seconds / time_limit_per_question_seconds / fullscreen_lock / camera_monitoring.
2. POST /api/quizzes/{quiz_id}/start  -- creates attempt, returns QuizAttemptOut.
3. POST /api/quizzes/{quiz_id}/submit -- scores correctly, enforces server-side elapsed check.
4. POST /api/quizzes/{quiz_id}/violations -- logs a violation and locks the attempt (anti-cheat).
5. GET  /api/quizzes/{quiz_id}/violations -- instructor can list violations.
6. POST /api/quizzes/{quiz_id}/attempts/{attempt_id}/re-enable -- instructor unlocks attempt.
7. Only students can start/submit; only instructors can list attempts / violations / re-enable.

Run:
    python test_task10_11_quiz.py
"""
from __future__ import annotations

import json
import os
import sys
import uuid

# ── Path bootstrap ────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(os.path.dirname(__file__), 'edusense.db')}")
os.environ.setdefault("EDUSENSE_DATABASE_URL", os.environ["DATABASE_URL"])
os.environ.setdefault("PYTHONUTF8", "1")

PASSED = 0
FAILED = 0


def ok(msg: str):
    global PASSED
    PASSED += 1
    print(f"  [PASS]  {msg}")


def fail(msg: str, exc: Exception | None = None):
    global FAILED
    FAILED += 1
    detail = f" -- {exc}" if exc else ""
    print(f"  [FAIL]  {msg}{detail}")


# ── Imports ───────────────────────────────────────────────────────────────────
try:
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import SessionLocal
    from app.models.models import Quiz, User, Base
    from app.db.session import engine, Session as ClassSession, SessionRegistration
    from app.core.security import hash_password, create_access_token
except ImportError as exc:
    print(f"[ERROR] Import failed: {exc}")
    sys.exit(1)

Base.metadata.create_all(bind=engine)
client = TestClient(app)

# ── Test identity emails ──────────────────────────────────────────────────────
_INST_EMAIL = f"t1011_inst_{uuid.uuid4().hex[:6]}@test.com"
_STU_EMAIL  = f"t1011_stu_{uuid.uuid4().hex[:6]}@test.com"
_PASSWORD   = "testpass123"

# ── Shared state between tests ────────────────────────────────────────────────
_quiz_id: int = 0
_attempt_id: int = 0
_violation_id: int = 0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_users() -> tuple[User, User]:
    db = SessionLocal()
    try:
        inst = db.query(User).filter_by(email=_INST_EMAIL).first()
        if not inst:
            inst = User(name="T1011 Instructor", email=_INST_EMAIL,
                        password_hash=hash_password(_PASSWORD), role="instructor")
            db.add(inst)
        stu = db.query(User).filter_by(email=_STU_EMAIL).first()
        if not stu:
            stu = User(name="T1011 Student", email=_STU_EMAIL,
                       password_hash=hash_password(_PASSWORD), role="student")
            db.add(stu)
        db.commit()
        db.refresh(inst)
        db.refresh(stu)
        return inst, stu
    finally:
        db.close()


def _create_quiz(instructor_id: int, student_id: int) -> int:
    """Insert a quiz directly into DB (bypasses AI generation) with time limit."""
    db = SessionLocal()
    try:
        questions = [
            {"question": "What is 2+2?", "options": ["2", "3", "4", "5"], "answer": "C", "type": "multiple_choice"},
            {"question": "Sky colour?",  "options": ["Red", "Blue", "Green", "Yellow"], "answer": "B", "type": "multiple_choice"},
        ]
        quiz = Quiz(
            session_id=None,
            title="Task 10/11 Test Quiz",
            difficulty="Easy",
            questions_json=json.dumps(questions),
            time_limit_seconds=3600,           # generous limit so tests don't auto-fail
            time_limit_per_question_seconds=60,
            fullscreen_lock=True,
            camera_monitoring=True,
        )
        db.add(quiz)
        db.commit()
        db.refresh(quiz)
        return quiz.id
    finally:
        db.close()


def _login(email: str) -> str:
    r = client.post("/api/auth/login", json={"email": email, "password": _PASSWORD})
    assert r.status_code == 200, f"Login failed for {email}: {r.text}"
    return r.json()["access_token"]


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_01_quiz_model_fields():
    print("\n[T10-01] Quiz model exposes timer & anti-cheat fields")
    global _quiz_id
    try:
        inst, stu = _ensure_users()
        _quiz_id = _create_quiz(inst.id, stu.id)
        db = SessionLocal()
        try:
            quiz = db.query(Quiz).filter_by(id=_quiz_id).first()
            assert quiz is not None, "Quiz not found after insert"
            assert quiz.time_limit_seconds == 3600
            assert quiz.time_limit_per_question_seconds == 60
            assert quiz.fullscreen_lock is True
            assert quiz.camera_monitoring is True
        finally:
            db.close()
        ok(f"Quiz id={_quiz_id} has correct timer/anti-cheat fields")
    except Exception as exc:
        fail("Quiz model fields check failed", exc)


def test_02_student_start_quiz():
    print("\n[T10-02] POST /api/quizzes/{quiz_id}/start -- student starts attempt")
    global _attempt_id
    try:
        token = _login(_STU_EMAIL)
        r = client.post(f"/api/quizzes/{_quiz_id}/start",
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        assert "id" in data, "'id' (attempt_id) missing from response"
        assert data["quiz_id"] == _quiz_id
        _attempt_id = data["id"]
        ok(f"Quiz attempt created: attempt_id={_attempt_id}")
    except Exception as exc:
        fail("Start quiz attempt failed", exc)


def test_03_start_returns_existing_attempt():
    print("\n[T10-03] POST /api/quizzes/{quiz_id}/start again -- returns existing active attempt")
    try:
        token = _login(_STU_EMAIL)
        r = client.post(f"/api/quizzes/{_quiz_id}/start",
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        assert data["id"] == _attempt_id, \
            f"Expected same attempt_id={_attempt_id}, got {data['id']}"
        ok("Second start call returns same attempt (idempotent)")
    except Exception as exc:
        fail("Idempotent start attempt test failed", exc)


def test_04_instructor_cannot_start():
    print("\n[T10-04] POST /api/quizzes/{quiz_id}/start -- instructor gets 403")
    try:
        token = _login(_INST_EMAIL)
        r = client.post(f"/api/quizzes/{_quiz_id}/start",
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"
        ok("Instructor blocked from starting quiz attempt (student-only)")
    except Exception as exc:
        fail("Instructor start quiz RBAC check failed", exc)


def test_05_student_submit_quiz():
    print("\n[T10-05] POST /api/quizzes/{quiz_id}/submit -- student submits quiz")
    try:
        token = _login(_STU_EMAIL)
        payload = {
            "attempt_id": _attempt_id,
            "answers": {"0": "C", "1": "B"},  # both correct
            "elapsed_seconds": 30,
        }
        r = client.post(f"/api/quizzes/{_quiz_id}/submit",
                        json=payload,
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        assert "score" in data
        assert "max_score" in data
        assert "percentage" in data
        assert "passed" in data
        assert data["score"] == 2.0, f"Expected score=2.0, got {data['score']}"
        assert data["percentage"] == 100.0, f"Expected 100%, got {data['percentage']}"
        assert data["passed"] is True
        ok(f"Quiz submitted: score={data['score']}/{data['max_score']}, "
           f"percentage={data['percentage']}%, passed={data['passed']}")
    except Exception as exc:
        fail("Submit quiz attempt failed", exc)


def test_06_cannot_resubmit():
    print("\n[T10-06] POST /api/quizzes/{quiz_id}/submit again -- 400 (no active attempt)")
    try:
        token = _login(_STU_EMAIL)
        payload = {"attempt_id": _attempt_id, "answers": {}, "elapsed_seconds": 5}
        r = client.post(f"/api/quizzes/{_quiz_id}/submit",
                        json=payload,
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        ok("Re-submission correctly blocked (400)")
    except Exception as exc:
        fail("Re-submission guard test failed", exc)


def test_07_instructor_list_attempts():
    print("\n[T10-07] GET /api/quizzes/{quiz_id}/attempts -- instructor lists attempts")
    try:
        token = _login(_INST_EMAIL)
        r = client.get(f"/api/quizzes/{_quiz_id}/attempts",
                       headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1, "Expected at least 1 attempt"
        ids = [a["id"] for a in data]
        assert _attempt_id in ids, f"attempt_id={_attempt_id} not in list"
        ok(f"Instructor sees {len(data)} attempt(s) for quiz")
    except Exception as exc:
        fail("Instructor list attempts failed", exc)


def test_08_student_cannot_list_attempts():
    print("\n[T10-08] GET /api/quizzes/{quiz_id}/attempts -- student gets 403")
    try:
        token = _login(_STU_EMAIL)
        r = client.get(f"/api/quizzes/{_quiz_id}/attempts",
                       headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"
        ok("Student blocked from listing attempts (instructor-only)")
    except Exception as exc:
        fail("Student list attempts RBAC check failed", exc)


def test_09_log_violation():
    print("\n[T11-09] POST /api/quizzes/{quiz_id}/violations -- log anti-cheat violation")
    global _violation_id, _attempt_id
    # Create a fresh attempt (previous one is submitted, so start a new quiz)
    try:
        # Create a second quiz for violation test
        inst, stu = _ensure_users()
        db = SessionLocal()
        try:
            q2 = Quiz(
                session_id=None,
                title="Anti-Cheat Violation Test Quiz",
                difficulty="Easy",
                questions_json=json.dumps([
                    {"question": "Q?", "options": ["A", "B", "C", "D"], "answer": "A", "type": "multiple_choice"}
                ]),
                time_limit_seconds=3600,
                fullscreen_lock=True,
                camera_monitoring=False,
            )
            db.add(q2)
            db.commit()
            db.refresh(q2)
            vquiz_id = q2.id
        finally:
            db.close()

        # Student starts the new quiz
        stu_token = _login(_STU_EMAIL)
        r = client.post(f"/api/quizzes/{vquiz_id}/start",
                        headers={"Authorization": f"Bearer {stu_token}"})
        assert r.status_code == 200, f"Start failed: {r.text}"
        v_attempt_id = r.json()["id"]

        # Log a violation
        r2 = client.post(
            f"/api/quizzes/{vquiz_id}/violations",
            params={"event_type": "tab_switch", "details": None},
            headers={"Authorization": f"Bearer {stu_token}"},
        )
        assert r2.status_code == 200, f"Status {r2.status_code}: {r2.text}"
        vdata = r2.json()
        assert "id" in vdata
        assert vdata["event_type"] == "tab_switch"
        _violation_id = vdata["id"]

        # Verify attempt is now locked
        db2 = SessionLocal()
        try:
            from app.models.models import QuizAttempt
            attempt = db2.query(QuizAttempt).filter_by(id=v_attempt_id).first()
            assert attempt is not None
            assert attempt.is_locked is True, "Attempt should be locked after violation"
        finally:
            db2.close()

        ok(f"Violation logged: id={_violation_id}, attempt locked correctly")

        # Store for re-enable test
        test_09_log_violation.vquiz_id = vquiz_id
        test_09_log_violation.v_attempt_id = v_attempt_id

    except Exception as exc:
        fail("Log violation test failed", exc)
        test_09_log_violation.vquiz_id = None
        test_09_log_violation.v_attempt_id = None


def test_10_instructor_list_violations():
    print("\n[T11-10] GET /api/quizzes/{quiz_id}/violations -- instructor lists violations")
    try:
        vquiz_id = getattr(test_09_log_violation, "vquiz_id", None)
        if not vquiz_id:
            fail("Skipped -- no vquiz_id from test_09")
            return
        token = _login(_INST_EMAIL)
        r = client.get(f"/api/quizzes/{vquiz_id}/violations",
                       headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(v["id"] == _violation_id for v in data), \
            f"violation_id={_violation_id} not in list"
        ok(f"Instructor sees {len(data)} violation(s)")
    except Exception as exc:
        fail("List violations failed", exc)


def test_11_student_cannot_list_violations():
    print("\n[T11-11] GET /api/quizzes/{quiz_id}/violations -- student gets 403")
    try:
        vquiz_id = getattr(test_09_log_violation, "vquiz_id", None)
        if not vquiz_id:
            fail("Skipped -- no vquiz_id from test_09")
            return
        token = _login(_STU_EMAIL)
        r = client.get(f"/api/quizzes/{vquiz_id}/violations",
                       headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"
        ok("Student blocked from listing violations (instructor-only)")
    except Exception as exc:
        fail("Student violations RBAC check failed", exc)


def test_12_re_enable_attempt():
    print("\n[T11-12] POST /api/quizzes/{quiz_id}/attempts/{attempt_id}/re-enable -- instructor unlocks")
    try:
        vquiz_id = getattr(test_09_log_violation, "vquiz_id", None)
        v_attempt_id = getattr(test_09_log_violation, "v_attempt_id", None)
        if not vquiz_id or not v_attempt_id:
            fail("Skipped -- missing data from test_09")
            return
        token = _login(_INST_EMAIL)
        r = client.post(f"/api/quizzes/{vquiz_id}/attempts/{v_attempt_id}/re-enable",
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        assert "message" in data
        assert "re-enabled" in data["message"].lower()

        # Verify attempt is now unlocked
        db = SessionLocal()
        try:
            from app.models.models import QuizAttempt
            attempt = db.query(QuizAttempt).filter_by(id=v_attempt_id).first()
            assert attempt is not None
            assert attempt.is_locked is False, "Attempt should be unlocked"
        finally:
            db.close()

        ok("Attempt re-enabled by instructor successfully")
    except Exception as exc:
        fail("Re-enable attempt test failed", exc)


def test_13_no_auth_blocked():
    print("\n[T11-13] Quiz endpoints require authentication (no token -> 401/403)")
    try:
        r = client.post(f"/api/quizzes/{_quiz_id}/start")
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
        ok("Unauthenticated request to /start is blocked")
    except Exception as exc:
        fail("Auth guard on quiz start failed", exc)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  EduSense Task 10 & 11 -- Quiz Timer & Anti-Cheat Tests")
    print("=" * 60)

    test_01_quiz_model_fields()
    test_02_student_start_quiz()
    test_03_start_returns_existing_attempt()
    test_04_instructor_cannot_start()
    test_05_student_submit_quiz()
    test_06_cannot_resubmit()
    test_07_instructor_list_attempts()
    test_08_student_cannot_list_attempts()
    test_09_log_violation()
    test_10_instructor_list_violations()
    test_11_student_cannot_list_violations()
    test_12_re_enable_attempt()
    test_13_no_auth_blocked()

    print("\n" + "=" * 60)
    print(f"  Results: {PASSED} passed, {FAILED} failed")
    print("=" * 60)

    if FAILED:
        sys.exit(1)
