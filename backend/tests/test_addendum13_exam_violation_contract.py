"""F5 contract test — exam violation reports must be accepted as a JSON body.

Reported symptom (demo-day list): during a real student exam
``POST /api/quizzes/147/violations`` answered ``422 Unprocessable Content``
while start and submit answered 200. Cause: the endpoint declared
``event_type`` / ``details`` as *query* parameters, but ``frontend/src/pages/
Quiz.jsx::logViolation`` sends ``{event_type, details}`` as a JSON body, so
FastAPI never saw ``event_type`` and rejected every report. No violation was
recorded and the attempt was never locked.

This test sends the exact body the browser sends and asserts the server
records it (200 + matching event_type + attempt locked).
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.models import Quiz, QuizAttempt

client = TestClient(app)

STUDENT = ("student@edusense.local", "Password123")


def _login(email: str, password: str) -> str:
    r = client.post("/api/auth/login", data={"username": email, "password": password})
    if r.status_code != 200:
        r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def test_violation_json_body_is_accepted_and_locks_attempt():
    db = SessionLocal()
    try:
        quiz = Quiz(
            session_id=None,
            title="F5 violation contract quiz",
            difficulty="Easy",
            questions_json=json.dumps([
                {"question": "Q?", "options": ["A", "B", "C", "D"], "answer": "A", "type": "multiple_choice"}
            ]),
            time_limit_seconds=3600,
            fullscreen_lock=True,
            camera_monitoring=False,
        )
        db.add(quiz)
        db.commit()
        db.refresh(quiz)
        quiz_id = quiz.id
    finally:
        db.close()

    token = _login(*STUDENT)
    headers = {"Authorization": f"Bearer {token}"}

    start = client.post(f"/api/quizzes/{quiz_id}/start", headers=headers)
    assert start.status_code == 200, f"start failed: {start.status_code} {start.text}"
    attempt_id = start.json()["id"]

    # Exactly what Quiz.jsx sends.
    r = client.post(
        f"/api/quizzes/{quiz_id}/violations",
        json={"event_type": "tab_switch", "details": {"source": "visibilitychange"}},
        headers=headers,
    )
    assert r.status_code == 200, f"expected 200 (was 422 before F5), got {r.status_code}: {r.text}"
    body = r.json()
    assert body["event_type"] == "tab_switch"
    assert body["details"] == {"source": "visibilitychange"}

    db = SessionLocal()
    try:
        attempt = db.query(QuizAttempt).filter_by(id=attempt_id).first()
        assert attempt is not None and attempt.is_locked is True, "attempt must lock after a violation"
    finally:
        db.close()


def test_violation_query_param_still_supported():
    """Old callers (and the existing suite) use ?event_type=; keep them working."""
    token = _login(*STUDENT)
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/quizzes/999999999/violations",
                    params={"event_type": "fullscreen_exit"}, headers=headers)
    assert r.status_code == 404, f"query form must reach the handler (404 unknown quiz), got {r.status_code}: {r.text}"


def test_violation_without_event_type_is_rejected():
    token = _login(*STUDENT)
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/quizzes/999999999/violations", json={"details": {}}, headers=headers)
    assert r.status_code == 422
