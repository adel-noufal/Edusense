"""
Verification Test for Task 5:
1. Manual Quiz Authoring via POST /api/quizzes
2. Publishing manual quiz as Exam
3. Updating Exam Settings via PATCH/PUT and publish-as-exam
4. Access control: Student view strips answers, Instructor view retains answers
"""
import os
import sys
import json
from datetime import datetime, timezone, timedelta

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models.models import User, Quiz, AIGeneration, Session as ClassSession, SessionRegistration

client = TestClient(app)

def get_auth_headers(email: str, role: str):
    token = create_access_token(subject=email, role=role)
    return {"Authorization": f"Bearer {token}"}

def test_task5_full_flow():
    db = SessionLocal()
    try:
        print("\n=== TASK 5 VERIFICATION: MANUAL QUIZ AUTHORING & EXAM SETTINGS ===")

        # 1. Setup instructor and student
        instructor = db.query(User).filter_by(role="instructor").first()
        student = db.query(User).filter_by(role="student").first()
        assert instructor, "Instructor user required"
        assert student, "Student user required"

        inst_headers = get_auth_headers(instructor.email, instructor.role)
        stu_headers = get_auth_headers(student.email, student.role)

        # Create a test session owned by this instructor
        test_session = ClassSession(
            title="Task 5 Linear Algebra Session",
            description="Testing manual quiz creation and settings",
            instructor_id=instructor.id,
            date=datetime.now(timezone.utc).date(),
            start_time=(datetime.now(timezone.utc) + timedelta(hours=1)).time(),
            duration=60,
            status="scheduled",
        )
        db.add(test_session)
        db.commit()
        db.refresh(test_session)

        # Enroll student in session
        reg = SessionRegistration(session_id=test_session.id, student_id=student.id)
        db.add(reg)
        db.commit()

        # 2. Test Manual Quiz Creation via POST /api/quizzes
        print("\n--- 1. Testing Manual Quiz Authoring (POST /api/quizzes) ---")
        manual_payload = {
            "title": "Manual Vector Spaces Quiz",
            "difficulty": "Hard",
            "session_id": test_session.id,
            "is_exam": False,
            "questions": [
                {
                    "question": "What is the rank of a 3x3 identity matrix?",
                    "type": "multiple_choice",
                    "options": ["1", "2", "3", "0"],
                    "answer": "3",
                    "explanation": "An identity matrix has full rank equal to its dimension."
                },
                {
                    "question": "Every orthogonal matrix is invertible.",
                    "type": "true_false",
                    "options": ["True", "False"],
                    "answer": "True",
                    "explanation": "Q^T * Q = I implies Q is always invertible."
                },
                {
                    "question": "Name the transformation that preserves vector length.",
                    "type": "short_answer",
                    "options": [],
                    "answer": "Isometry",
                    "explanation": "An isometry preserves Euclidean distance and length."
                }
            ]
        }

        resp = client.post("/api/quizzes", headers=inst_headers, json=manual_payload)
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        quiz_data = resp.json()
        quiz_id = quiz_data["id"]
        assert quiz_data["title"] == "Manual Vector Spaces Quiz"
        assert len(quiz_data["questions"]) == 3
        assert quiz_data["is_exam"] is False
        print(f"âœ“ Manual quiz created successfully with id={quiz_id}, questions count={len(quiz_data['questions'])}")

        print("\n--- 1a. Testing Direct Manual Exam Default Fullscreen Lock ---")
        direct_exam_title = "Manual Exam Default Fullscreen Test"
        direct_exam_resp = client.post(
            "/api/quizzes",
            headers=inst_headers,
            json={
                "title": direct_exam_title,
                "difficulty": "Medium",
                "session_id": test_session.id,
                "is_exam": True,
                "questions": [{
                    "question": "What is a vector?",
                    "type": "short_answer",
                    "options": [],
                    "answer": "A quantity with magnitude and direction",
                }],
            },
        )
        assert direct_exam_resp.status_code in (200, 201), (
            f"Expected successful exam creation, got {direct_exam_resp.status_code}: {direct_exam_resp.text}"
        )
        direct_exam_data = direct_exam_resp.json()
        direct_exam_id = direct_exam_data["id"]
        assert direct_exam_data["fullscreen_lock"] is True
        print(f"âœ“ Directly authored exam defaults fullscreen_lock=True (quiz id={direct_exam_id})")

        # 3. Test Instructor vs Student view of the quiz
        print("\n--- 2. Testing Answer Visibility: Instructor sees answers, Student view strips answers ---")
        inst_view = client.get(f"/api/quizzes/{quiz_id}", headers=inst_headers)
        assert inst_view.status_code == 200
        inst_quiz = inst_view.json()
        assert inst_quiz["questions"][0].get("answer") == "3", "Instructor must be able to view correct answers"
        print(f"âœ“ Instructor view retains answers: question 1 answer = '{inst_quiz['questions'][0]['answer']}'")

        stu_view = client.get(f"/api/quizzes/{quiz_id}", headers=stu_headers)
        assert stu_view.status_code == 200
        stu_quiz = stu_view.json()
        assert "answer" not in stu_quiz["questions"][0], "Student view must strip answers for exam integrity"
        print("âœ“ Student view successfully strips correct answers for examination integrity")

        # 4. Test Publishing Manual Quiz as Exam via POST /api/quizzes/{id}/publish-as-exam
        print("\n--- 3. Testing Publishing Manual Quiz as Exam ---")
        due_time = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        publish_payload = {
            "session_id": test_session.id,
            "time_limit_seconds": 2700, # 45 minutes
            "time_limit_per_question_seconds": 90,
            "lock_back_navigation": True,
            "camera_monitoring": True,
            "due_date": due_time,
        }
        pub_resp = client.post(f"/api/quizzes/{quiz_id}/publish-as-exam", headers=inst_headers, json=publish_payload)
        assert pub_resp.status_code == 200, f"Expected 200, got {pub_resp.status_code}: {pub_resp.text}"
        pub_data = pub_resp.json()
        assert pub_data["is_exam"] is True
        assert pub_data["time_limit_seconds"] == 2700
        assert pub_data["fullscreen_lock"] is True
        assert pub_data["lock_back_navigation"] is True
        assert pub_data["camera_monitoring"] is True
        print(f"âœ“ Quiz {quiz_id} successfully published as Exam with time_limit=2700s, fullscreen=True, lock_back=True")

        # 5. Test Updating Existing Exam Settings via PATCH /api/quizzes/{id}
        print("\n--- 4. Testing 'Update Exam Settings' (PATCH /api/quizzes/{quiz_id}) ---")
        new_due_time = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
        update_payload = {
            "time_limit_seconds": 3600, # Updated to 60 mins
            "time_limit_per_question_seconds": 120,
            "lock_back_navigation": False, # Changed navigation lockdown
            "due_date": new_due_time,
        }
        patch_resp = client.patch(f"/api/quizzes/{quiz_id}", headers=inst_headers, json=update_payload)
        assert patch_resp.status_code == 200, f"Expected 200, got {patch_resp.status_code}: {patch_resp.text}"
        patch_data = patch_resp.json()
        assert patch_data["time_limit_seconds"] == 3600
        assert patch_data["time_limit_per_question_seconds"] == 120
        assert patch_data["lock_back_navigation"] is False
        print(f"âœ“ Exam settings successfully updated: time_limit={patch_data['time_limit_seconds']}s, lock_back_navigation={patch_data['lock_back_navigation']}")

        # 6. Test Updating Exam Settings via POST /api/quizzes/{quiz_id}/publish-as-exam (UI reuse path)
        print("\n--- 5. Testing 'Update Exam Settings' via Publish-As-Exam endpoint ---")
        republish_payload = {
            "session_id": test_session.id,
            "time_limit_seconds": 1800, # Changed to 30 mins
            "lock_back_navigation": True,
            "fullscreen_lock": True,
            "camera_monitoring": False,
        }
        repub_resp = client.post(f"/api/quizzes/{quiz_id}/publish-as-exam", headers=inst_headers, json=republish_payload)
        assert repub_resp.status_code == 200, f"Expected 200, got {repub_resp.status_code}: {repub_resp.text}"
        repub_data = repub_resp.json()
        assert repub_data["time_limit_seconds"] == 1800
        assert repub_data["camera_monitoring"] is False
        assert repub_data["lock_back_navigation"] is True
        print(f"âœ“ Settings update via publish-as-exam confirmed: time_limit={repub_data['time_limit_seconds']}s, camera={repub_data['camera_monitoring']}")

        # 7. Check student sees updated exam in /quizzes/student/exams
        stu_exams_resp = client.get("/api/quizzes/student/exams", headers=stu_headers)
        assert stu_exams_resp.status_code == 200
        stu_exams = stu_exams_resp.json()
        matching = next((e for e in stu_exams if e["id"] == quiz_id), None)
        assert matching is not None, "Exam must be visible to enrolled student"
        assert matching["time_limit_seconds"] == 1800
        assert matching["camera_monitoring"] is False
        print(f"âœ“ Enrolled student immediately sees the updated exam settings in their Exams tab!")

        # Clean up test session and quiz
        db.delete(reg)
        db.query(AIGeneration).filter_by(instructor_id=instructor.id, topic=direct_exam_title).delete()
        db.query(Quiz).filter_by(id=direct_exam_id).delete()
        db.query(Quiz).filter_by(id=quiz_id).delete()
        db.delete(test_session)
        db.commit()
        print("\nALL TASK 5 CHECKS PASSED SUCCESSFULLY!")
    finally:
        db.close()

if __name__ == "__main__":
    test_task5_full_flow()
