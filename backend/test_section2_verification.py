"""
EduSense Section 2 Verification Suite
Verifies:
1. Student name consistency: user.name is 'Student', not 'Mona'.
2. PUT /users/me updates name cleanly and persists.
3. Emotion capture rate limit: supports fine 1-second capture granularity without 429 errors.
4. Engagement calculation logic: no camera frames -> engagement_percentage is None / has_data is False (no fabricated 46 score).
5. GET /api/ai/engagement/{id} on sessions without frames returns None (no fake score).
6. Student session history exposes attendance boolean cleanly.
7. Enrolled student can fetch session resources for their history page.
"""

import os
import sys
import uuid

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ["DATABASE_URL"] = "sqlite:///./edusense.db"
os.environ["SECRET_KEY"] = "test-secret-key-section-2-verification"
os.environ["PYTHONUTF8"] = "1"

from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.models.models import User, Session, SessionRegistration, EmotionLog, SessionResource
from app.core.security import hash_password, create_access_token
from app.agents.engagement_agent import StudentEngagementAgent

client = TestClient(app)
db = SessionLocal()

print("=" * 60)
print("  EduSense Section 2 Verification Suite")
print("=" * 60)

passed = 0
failed = 0

def assert_test(cond, title, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {title}")
    else:
        failed += 1
        print(f"  [FAIL] {title} -> {detail}")

try:
    # 1. Verify student account name is 'Student', not hardcoded 'Mona'
    student = db.query(User).filter_by(email="student@edusense.local").first()
    assert_test(student is not None and student.name == "Student", "Student account name in DB is 'Student' (not Mona)", f"Got: {student.name if student else 'None'}")

    token = create_access_token(student.email, student.role)
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Verify GET /users/me returns 'Student'
    res = client.get("/api/users/me", headers=headers)
    assert_test(res.status_code == 200 and res.json().get("name") == "Student", "GET /api/users/me returns 'Student'", f"Got {res.status_code}: {res.text}")

    # 3. Test updating name via PUT /users/me
    res = client.put("/api/users/me", json={"name": "Student Profile Verified"}, headers=headers)
    assert_test(res.status_code == 200 and res.json().get("name") == "Student Profile Verified", "PUT /api/users/me successfully updates user name", f"Got: {res.text}")

    # Revert back to 'Student'
    client.put("/api/users/me", json={"name": "Student"}, headers=headers)

    # 4. Test Engagement calculation logic with NO camera frames captured
    # Create fresh clean test session with no frames
    from datetime import date, time as dt_time
    test_session = Session(
        instructor_id=1,
        title=f"Sec2 No Frames Test {uuid.uuid4().hex[:6]}",
        date=date(2026, 11, 20),
        start_time=dt_time(14, 0),
        duration=45,
        status="ended"
    )
    db.add(test_session)
    db.commit()
    db.refresh(test_session)

    agent_result = StudentEngagementAgent().calculate(db, test_session.id).data
    assert_test(agent_result.get("engagement_percentage") is None and agent_result.get("has_data") is False,
                "EngagementAgent returns engagement_percentage=None and has_data=False when no camera frames captured",
                f"Got: {agent_result}")

    # 5. Test GET /api/ai/engagement/{id} returns no fabricated score
    res = client.get(f"/api/ai/engagement/{test_session.id}", headers=headers)
    data = res.json()
    assert_test(res.status_code == 200 and data.get("engagement_percentage") is None,
                "GET /api/ai/engagement/{id} returns engagement_percentage=None (no fake 46 score)",
                f"Got: {data}")

    # 6. Test Emotion capture rate limit allows 1 frame per second (not blocked at 1.5s)
    # Grant emotion_detection consent first
    client.post("/api/emotions/consent/give", json={"consent_type": "emotion_detection", "version": "1.0"}, headers=headers)

    # Minimal 1x1 black pixel base64 jpeg
    sample_image = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="

    res1 = client.post("/api/emotions/analyze", json={"session_id": test_session.id, "image": sample_image}, headers=headers)
    assert_test(res1.status_code == 200, "First emotion frame analyzed successfully (200 OK)", f"Status: {res1.status_code}, error: {res1.text}")

    import time
    time.sleep(1.05)  # 1.05s later (would fail with 429 under old 1.5s limiter)
    res2 = client.post("/api/emotions/analyze", json={"session_id": test_session.id, "image": sample_image}, headers=headers)
    assert_test(res2.status_code == 200, "Second emotion frame 1s later accepted without 429 rate limit error", f"Status: {res2.status_code}, error: {res2.text}")

    # 7. Test Student session history & resources
    # Register student to test_session and mark attended
    reg = SessionRegistration(session_id=test_session.id, student_id=student.id, attended=True)
    db.add(reg)
    # Add a mock session resource
    res_model = SessionResource(
        session_id=test_session.id,
        instructor_id=1,
        name="lecture_notes_ch1.pdf",
        file_path="/tmp/lecture_notes_ch1.pdf",
        file_type="application/pdf",
        file_size=102400
    )
    db.add(res_model)
    db.commit()

    my_sessions = client.get("/api/sessions/student/my-sessions", headers=headers).json()
    matched = next((s for s in my_sessions if s["id"] == test_session.id), None)
    assert_test(matched is not None and matched["attended"] is True,
                "GET /api/sessions/student/my-sessions correctly exposes attended=True for attended session",
                f"Matched: {matched}")

    # 8. Student can fetch session resources
    resources_res = client.get(f"/api/sessions/{test_session.id}/resources", headers=headers)
    assert_test(resources_res.status_code == 200 and len(resources_res.json()) >= 1 and resources_res.json()[0]["name"] == "lecture_notes_ch1.pdf",
                "GET /api/sessions/{id}/resources returns attached resources for enrolled student in history",
                f"Got: {resources_res.text}")

finally:
    db.close()

print("=" * 60)
print(f"  Results: {passed} passed, {failed} failed")
print("=" * 60)

if failed > 0:
    sys.exit(1)
