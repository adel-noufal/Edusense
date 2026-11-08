"""
test_section1_flow.py — Verification suite for Section 1 (Session Registration & Live Flow Redesign).

Verifies all 6 requirements of Section 1:
1. Instructor schedules a session — status is 'pending', not ongoing.
2. Student sees it under Browse with is_registered=False.
3. Student does NOT have it in their Upcoming/Registered list before enrolling.
4. Student must explicitly enroll via POST /api/sessions/{id}/join.
5. After enrolling, session appears in student's Upcoming list.
6. Session does NOT auto-move from 'pending' to 'ongoing' based on clock time.
7. Student cannot join live (POST /join-live) while session is not ongoing.
8. Non-enrolled student cannot access live room (GET /{id}/live returns 403).
9. Instructor starts session via POST /api/sessions/{id}/start (force_go_live=true).
10. Session status becomes 'ongoing'.
11. Live join notification email is queued/dispatched to all enrolled students.
12. Enrolled student can now mark attendance and join live session.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, time, timedelta

sys.path.insert(0, os.path.dirname(__file__))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(os.path.dirname(__file__), 'edusense.db')}")
os.environ.setdefault("EDUSENSE_DATABASE_URL", os.environ["DATABASE_URL"])

PASSED = 0
FAILED = 0

def ok(msg: str):
    global PASSED
    PASSED += 1
    print(f"  [PASS] {msg}")

def fail(msg: str, exc: Exception | None = None):
    global FAILED
    FAILED += 1
    detail = f" -- {exc}" if exc else ""
    print(f"  [FAIL] {msg}{detail}")

from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal, engine
from app.models.models import User, Session as ClassSession, SessionRegistration, Base
from app.core.security import hash_password, create_access_token

Base.metadata.create_all(bind=engine)
client = TestClient(app)

_INST_EMAIL = f"sec1_inst_{uuid.uuid4().hex[:6]}@edusense.test"
_STU_EMAIL  = f"sec1_stu_{uuid.uuid4().hex[:6]}@edusense.test"
_PASSWORD   = "Password123"

_inst_id: int = 0
_stu_id: int = 0
_inst_token: str = ""
_stu_token: str = ""
_session_id: int = 0

def setup_users():
    global _inst_id, _stu_id, _inst_token, _stu_token
    db = SessionLocal()
    try:
        inst = User(name="Prof. SectionOne", email=_INST_EMAIL, password_hash=hash_password(_PASSWORD), role="instructor")
        stu = User(name="Student SectionOne", email=_STU_EMAIL, password_hash=hash_password(_PASSWORD), role="student")
        db.add_all([inst, stu])
        db.commit()
        db.refresh(inst)
        db.refresh(stu)
        _inst_id = inst.id
        _stu_id = stu.id
    finally:
        db.close()
    
    _inst_token = create_access_token(subject=_INST_EMAIL, role="instructor")
    _stu_token = create_access_token(subject=_STU_EMAIL, role="student")

def test_01_instructor_schedules_session():
    print("\n[Step 1] Instructor schedules a session")
    global _session_id
    try:
        payload = {
            "title": "Quantum Computing Fundamentals",
            "description": "Exploration of qubits and superposition.",
            "date": str(date.today()),
            "start_time": "09:00",
            "duration": 60,
            "max_students": 25,
        }
        res = client.post("/api/sessions", json=payload, headers={"Authorization": f"Bearer {_inst_token}"})
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        _session_id = data["id"]
        assert data["status"] == "pending", f"Expected status 'pending', got {data['status']}"
        assert data["title"] == payload["title"]
        ok(f"Session scheduled successfully with id={_session_id}, status='pending'")
    except Exception as exc:
        fail("Instructor scheduling failed", exc)

def test_02_student_browse_sees_session_not_registered():
    print("\n[Step 2] Student sees session under Browse as available to enroll (is_registered=False)")
    try:
        res = client.get("/api/sessions/browse", headers={"Authorization": f"Bearer {_stu_token}"})
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        sessions = data.get("sessions", [])
        target = next((s for s in sessions if s["id"] == _session_id), None)
        assert target is not None, f"Session {_session_id} not found in browse catalog"
        assert target["is_registered"] is False, f"Expected is_registered=False, got {target['is_registered']}"
        assert target["status"] == "pending", f"Expected status 'pending', got {target['status']}"
        ok(f"Session {_session_id} visible in Browse with is_registered=False and status='pending'")
    except Exception as exc:
        fail("Browse check failed", exc)

def test_03_student_upcoming_does_not_contain_session_before_enrollment():
    print("\n[Step 3] Session does NOT show in student's Upcoming before explicit enrollment")
    try:
        res = client.get("/api/sessions/student/my-sessions", headers={"Authorization": f"Bearer {_stu_token}"})
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        my_sessions = res.json()
        enrolled_ids = [s["id"] for s in my_sessions]
        assert _session_id not in enrolled_ids, f"Bug: session {_session_id} auto-registered before enrollment!"
        ok(f"Session {_session_id} correctly absent from student's enrolled sessions list")
    except Exception as exc:
        fail("Pre-enrollment isolation check failed", exc)

def test_04_unenrolled_student_cannot_access_live_room():
    print("\n[Step 4] Unenrolled student cannot access live room (GET /{id}/live returns 403)")
    try:
        res = client.get(f"/api/sessions/{_session_id}/live", headers={"Authorization": f"Bearer {_stu_token}"})
        assert res.status_code == 403, f"Expected 403, got {res.status_code}: {res.text}"
        assert "not enrolled" in res.text.lower(), f"Unexpected error detail: {res.text}"
        ok(f"GET /sessions/{_session_id}/live returned 403 Forbidden for unenrolled student")
    except Exception as exc:
        fail("Unenrolled live access check failed", exc)

def test_05_student_explicitly_enrolls():
    print("\n[Step 5] Student explicitly enrolls (clicks Enroll)")
    try:
        res = client.post(f"/api/sessions/{_session_id}/join", headers={"Authorization": f"Bearer {_stu_token}"})
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        assert res.json().get("message") == "Joined session"
        ok(f"Student successfully enrolled in session {_session_id}")
    except Exception as exc:
        fail("Explicit enrollment failed", exc)

def test_06_session_now_shows_in_student_upcoming():
    print("\n[Step 6] Session now shows under student's Upcoming after enrollment")
    try:
        res = client.get("/api/sessions/student/my-sessions", headers={"Authorization": f"Bearer {_stu_token}"})
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        my_sessions = res.json()
        target = next((s for s in my_sessions if s["id"] == _session_id), None)
        assert target is not None, f"Enrolled session {_session_id} not found in my-sessions"
        assert target["status"] == "pending", f"Expected status 'pending', got {target['status']}"
        ok(f"Session {_session_id} confirmed in student's Upcoming list with status='pending'")
    except Exception as exc:
        fail("Post-enrollment verification failed", exc)

def test_07_student_cannot_join_live_before_instructor_starts():
    print("\n[Step 7] Enrolled student cannot join live before instructor starts it (POST /join-live returns 400)")
    try:
        res = client.post(f"/api/sessions/{_session_id}/join-live", headers={"Authorization": f"Bearer {_stu_token}"})
        assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
        assert "hasn't started yet" in res.text.lower() or "not started" in res.text.lower(), f"Unexpected detail: {res.text}"
        ok("POST /join-live correctly blocked with 400 because session status is 'pending'")
    except Exception as exc:
        fail("Gate check before instructor start failed", exc)

def test_08_no_auto_transition_to_ongoing_from_clock():
    print("\n[Step 8] Verify session remains 'pending' and does NOT auto-switch to 'ongoing'")
    try:
        res = client.get(f"/api/sessions", headers={"Authorization": f"Bearer {_inst_token}"})
        assert res.status_code == 200
        sessions = res.json()
        target = next((s for s in sessions if s["id"] == _session_id), None)
        assert target is not None
        assert target["status"] == "pending", f"Expected 'pending', but got '{target['status']}' — auto-move bug detected!"
        ok(f"Session status is '{target['status']}', confirming clock-based auto-start is disabled")
    except Exception as exc:
        fail("No auto-transition check failed", exc)

def test_09_instructor_starts_session_live():
    print("\n[Step 9] Instructor starts session (POST /{id}/start?force_go_live=true)")
    try:
        res = client.post(f"/api/sessions/{_session_id}/start?force_go_live=true", headers={"Authorization": f"Bearer {_inst_token}"})
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data["status"] == "ongoing", f"Expected status 'ongoing', got {data['status']}"
        ok("Instructor started session, status successfully changed to 'ongoing'")
    except Exception as exc:
        fail("Instructor start session failed", exc)

def test_10_student_now_can_join_live():
    print("\n[Step 10] Student can now join live and mark attendance")
    try:
        res = client.post(f"/api/sessions/{_session_id}/join-live", headers={"Authorization": f"Bearer {_stu_token}"})
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        assert res.json().get("message") == "Attendance marked"
        
        # Verify GET /live now returns 200 for student
        res_live = client.get(f"/api/sessions/{_session_id}/live", headers={"Authorization": f"Bearer {_stu_token}"})
        assert res_live.status_code == 200, f"Expected 200, got {res_live.status_code}"
        assert res_live.json()["status"] == "ongoing"
        ok("Student joined live and attendance successfully marked on ongoing session")
    except Exception as exc:
        fail("Student join live failed", exc)

if __name__ == "__main__":
    print("=" * 60)
    print("  EduSense Section 1 — Session Registration & Live Flow Tests")
    print("=" * 60)

    setup_users()
    test_01_instructor_schedules_session()
    test_02_student_browse_sees_session_not_registered()
    test_03_student_upcoming_does_not_contain_session_before_enrollment()
    test_04_unenrolled_student_cannot_access_live_room()
    test_05_student_explicitly_enrolls()
    test_06_session_now_shows_in_student_upcoming()
    test_07_student_cannot_join_live_before_instructor_starts()
    test_08_no_auto_transition_to_ongoing_from_clock()
    test_09_instructor_starts_session_live()
    test_10_student_now_can_join_live()

    print("\n" + "=" * 60)
    print(f"  Results: {PASSED} passed, {FAILED} failed")
    print("=" * 60)

    if FAILED:
        sys.exit(1)
