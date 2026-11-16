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


def test_section2():
    client = TestClient(app)
    db = SessionLocal()

    print("=" * 60)
    print("  EduSense Section 2 Verification Suite")
    print("=" * 60)

    passed = 0
    failed = 0

    def assert_test(cond, title, detail=""):
        nonlocal passed, failed
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

        # 3. Verify PUT /users/me updates name cleanly and persists
        test_new_name = "Student Updated"
        put_res = client.put("/api/users/me", json={"name": test_new_name}, headers=headers)
        assert_test(put_res.status_code == 200 and put_res.json().get("name") == test_new_name, "PUT /api/users/me successfully updates user name", f"Got {put_res.status_code}: {put_res.text}")

        # Revert back to 'Student' for subsequent tests
        client.put("/api/users/me", json={"name": "Student"}, headers=headers)

        # 4. Verify emotion capture rate limit handles fine 1s frequency
        test_session = db.query(Session).first()
        if not test_session:
            inst = db.query(User).filter_by(role="instructor").first()
            from datetime import date, time
            test_session = Session(instructor_id=inst.id, title="Rate Limit Test Session", date=date.today(), start_time=time(10, 0), duration=60, status="ongoing")
            db.add(test_session)
            db.commit()
            db.refresh(test_session)

        rapid_calls_succeeded = True
        err_msg = ""
        for i in range(5):
            r = client.post("/api/emotions", json={"session_id": test_session.id, "emotion": "happy", "confidence": 0.95}, headers=headers)
            if r.status_code != 200:
                rapid_calls_succeeded = False
                err_msg = f"Call {i+1} failed with status {r.status_code}: {r.text}"
                break
        assert_test(rapid_calls_succeeded, "POST /api/emotions accepts rapid 1-second interval frames without 429", err_msg)

        # 5. Verify Engagement Calculation: empty frames -> has_data=False / score=None
        from datetime import date, time
        inst = db.query(User).filter_by(role="instructor").first()
        empty_session = Session(instructor_id=inst.id, title="Empty Test Session", date=date.today(), start_time=time(14, 0), duration=45, status="completed")
        db.add(empty_session)
        db.commit()
        db.refresh(empty_session)

        agent = StudentEngagementAgent()
        calc_result = agent.calculate(db=db, session_id=empty_session.id).data
        assert_test(calc_result.get("has_data") is False and calc_result.get("engagement_percentage") is None,
                    "Engagement calculation returns has_data=False and None score when session has 0 emotion frames",
                    f"Got: {calc_result}")

        # 6. Verify GET /api/ai/engagement/{session_id} returns engagement_score=None
        eng_res = client.get(f"/api/ai/engagement/{empty_session.id}", headers=headers)
        assert_test(eng_res.status_code == 200 and eng_res.json().get("engagement_score") is None,
                    "GET /api/ai/engagement/{id} returns None engagement_score for session with no emotion logs",
                    f"Got {eng_res.status_code}: {eng_res.text}")

        # 7. Student session history attended flag
        reg = db.query(SessionRegistration).filter_by(session_id=test_session.id, student_id=student.id).first()
        if not reg:
            reg = SessionRegistration(session_id=test_session.id, student_id=student.id, attended=True)
            db.add(reg)
        else:
            reg.attended = True
        
        # Attach sample resource to test_session
        existing_res = db.query(SessionResource).filter_by(session_id=test_session.id).first()
        if not existing_res:
            res_obj = SessionResource(session_id=test_session.id, instructor_id=test_session.instructor_id, name="lecture_notes_ch1.pdf", file_path="/fake/path", file_type="pdf", file_size=1024)
            db.add(res_obj)
        db.commit()

        my_sessions = client.get("/api/sessions/student/my-sessions", headers=headers).json()
        matched = next((s for s in my_sessions if s["id"] == test_session.id), None)
        assert_test(matched is not None and matched["attended"] is True,
                    "GET /api/sessions/student/my-sessions correctly exposes attended=True for attended session",
                    f"Matched: {matched}")

        # 8. Student can fetch session resources
        resources_res = client.get(f"/api/sessions/{test_session.id}/resources", headers=headers)
        resources = resources_res.json() if resources_res.status_code == 200 else []
        missing_resource = next((resource for resource in resources if resource["name"] == "lecture_notes_ch1.pdf"), {})
        assert_test(resources_res.status_code == 200 and bool(missing_resource) and missing_resource["available"] is False and missing_resource["url"] is None,
                    "GET /api/sessions/{id}/resources returns attached resources for enrolled student in history",
                    f"Got: {resources_res.text}")

    finally:
        db.close()

    print("=" * 60)
    print(f"  Results: {passed} passed, {failed} failed")
    print("=" * 60)
    assert failed == 0, f"{failed} test(s) failed in Section 2 verification"


if __name__ == "__main__":
    test_section2()
