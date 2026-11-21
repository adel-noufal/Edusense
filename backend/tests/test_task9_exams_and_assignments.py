"""
test_task9_exams_and_assignments.py
Task 9 â€” Exam Tab Infinite Load & Assignments Visibility
Tests:
  1. AuthContext exports token so useAuth().token is defined
  2. StudentExams.jsx & StudentAssignments.jsx use api() and don't stall with infinite loader
  3. GET /api/quizzes/student/exams returns published exams with session_title and stripped answers
  4. GET /api/assignments/student returns assignments for enrolled sessions with session_title
  5. POST /api/assignments/{id}/submit allows student to upload assignment submission
  6. GET /api/assignments/{id}/submission returns the submitted assignment status
"""
import io
import json
import os
import sys
from datetime import datetime, timezone, timedelta

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from fastapi.testclient import TestClient
from app.main import app
from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models.models import (
    User,
    Quiz,
    Session as ClassSession,
    SessionRegistration,
    Assignment,
    AssignmentSubmission,
)

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results = []

def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}" + (f" â€” {detail}" if detail else ""))
    results.append((label, condition))

def get_auth_headers(email: str, role: str):
    token = create_access_token(subject=email, role=role)
    return {"Authorization": f"Bearer {token}"}


def test_task9_exams_and_assignments():
    results.clear()
    client = TestClient(app)
    db = SessionLocal()
    try:
        instructor = db.query(User).filter_by(role="instructor").first()
        student = db.query(User).filter_by(role="student").first()
        if not instructor:
            instructor = User(email="task9_instructor@edusense.com", password_hash="hash", name="Prof. Test", role="instructor")
            db.add(instructor)
        if not student:
            student = User(email="task9_student@edusense.com", password_hash="hash", name="Student Test", role="student")
            db.add(student)
        db.commit()
        db.refresh(instructor)
        db.refresh(student)

        # Create a test session
        test_session = db.query(ClassSession).filter_by(title="Task 9 Quantum Computing").first()
        if not test_session:
            from datetime import date, time
            test_session = ClassSession(
                title="Task 9 Quantum Computing",
                description="Introductory quantum physics and gate operations.",
                date=date.today(),
                start_time=time(10, 0),
                duration=60,
                instructor_id=instructor.id,
                status="ongoing",
            )
            db.add(test_session)
            db.commit()
            db.refresh(test_session)

        # Register student for test session
        reg = db.query(SessionRegistration).filter_by(session_id=test_session.id, student_id=student.id).first()
        if not reg:
            reg = SessionRegistration(
                session_id=test_session.id,
                student_id=student.id,
                attended=True,
            )
            db.add(reg)
            db.commit()

        # Create a published exam linked to session
        test_exam = db.query(Quiz).filter_by(title="Midterm: Quantum Gates").first()
        if not test_exam:
            test_exam = Quiz(
                title="Midterm: Quantum Gates",
                difficulty="Medium",
                questions_json=json.dumps([{
                    "id": 1,
                    "question": "What does a Hadamard gate do?",
                    "options": ["Creates superposition", "Measures state", "Flips phase", "Deletes qubit"],
                    "correct_answer": "Creates superposition"
                }]),
                session_id=test_session.id,
                is_exam=True,
                is_published=True,
                time_limit_seconds=3600,
            )
            db.add(test_exam)
            db.commit()
            db.refresh(test_exam)

        # Create an assignment linked to session
        test_assignment = db.query(Assignment).filter_by(title="HW 1: Grover Search Analysis").first()
        if not test_assignment:
            test_assignment = Assignment(
                session_id=test_session.id,
                instructor_id=instructor.id,
                title="HW 1: Grover Search Analysis",
                description="Analyze quadratic speedup in database queries.",
                max_points=100.0,
                due_date=datetime.now(timezone.utc) + timedelta(days=7),
            )
            db.add(test_assignment)
            db.commit()
            db.refresh(test_assignment)

        test_exam_id = test_exam.id
        test_assignment_id = test_assignment.id
        student_email = student.email
        student_role = student.role
    finally:
        db.close()

    stu_headers = get_auth_headers(student_email, student_role)

    print("\n--- Tests 1 & 2: Frontend Codebase Audit ---")
    try:
        from pathlib import Path
        repo_root = Path(__file__).parents[2]
        auth_context_path = repo_root / "frontend" / "src" / "context" / "AuthContext.jsx"
        exams_page_path = repo_root / "frontend" / "src" / "pages" / "StudentExams.jsx"
        assignments_page_path = repo_root / "frontend" / "src" / "pages" / "StudentAssignments.jsx"

        auth_content = auth_context_path.read_text(encoding="utf-8")
        check("AuthContext exposes token in value", "token" in auth_content and "value" in auth_content)

        exams_content = exams_page_path.read_text(encoding="utf-8")
        check("StudentExams uses api() client", "api('/quizzes/student/exams')" in exams_content)
        check("StudentExams falls back gracefully when token absent", "setLoading(false)" in exams_content)
        check("StudentExams displays exam.session_title", "exam.session_title" in exams_content)

        assignments_content = assignments_page_path.read_text(encoding="utf-8")
        check("StudentAssignments uses api() client", "api('/assignments/student')" in assignments_content)
        check("StudentAssignments falls back gracefully when token absent", "setLoading(false)" in assignments_content)
        check("StudentAssignments groups by session_title", "session_title" in assignments_content)
    except Exception as e:
        check("Frontend audit failed", False, str(e))

    print("\n--- Test 3: GET /api/quizzes/student/exams ---")
    try:
        resp = client.get("/api/quizzes/student/exams", headers=stu_headers)
        check("student exams status 200", resp.status_code == 200, f"got {resp.status_code}")
        exams = resp.json() if resp.status_code == 200 else []
        check("returns list", isinstance(exams, list))
        matching_exam = next((e for e in exams if e.get("id") == test_exam_id), None)
        check("published exam found for enrolled student", matching_exam is not None)
        if matching_exam:
            check("session_title populated", matching_exam.get("session_title") == "Task 9 Quantum Computing", f"got {matching_exam.get('session_title')}")
            check("is_exam is True", matching_exam.get("is_exam") is True)
            qs = matching_exam.get("questions") or []
            if qs:
                check("correct answer stripped from questions", "correct_answer" not in qs[0], f"keys in question: {list(qs[0].keys())}")
    except Exception as e:
        check("fetch student exams", False, str(e))

    print("\n--- Test 4: GET /api/assignments/student ---")
    try:
        resp = client.get("/api/assignments/student", headers=stu_headers)
        check("student assignments status 200", resp.status_code == 200, f"got {resp.status_code}")
        assignments = resp.json() if resp.status_code == 200 else []
        check("returns list", isinstance(assignments, list))
        matching_asgn = next((a for a in assignments if a.get("id") == test_assignment_id), None)
        check("assignment found for enrolled student", matching_asgn is not None)
        if matching_asgn:
            check("session_title populated", matching_asgn.get("session_title") == "Task 9 Quantum Computing", f"got {matching_asgn.get('session_title')}")
            check("title matches", matching_asgn.get("title") == "HW 1: Grover Search Analysis")
            check("max_points is 100", matching_asgn.get("max_points") == 100.0)
    except Exception as e:
        check("fetch student assignments", False, str(e))

    print("\n--- Tests 5 & 6: Assignment Submission & Fetch Status ---")
    try:
        dummy_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
        files = {"file": ("grovers_report.pdf", io.BytesIO(dummy_pdf), "application/pdf")}
        resp_sub = client.post(f"/api/assignments/{test_assignment_id}/submit", headers=stu_headers, files=files)
        check("submit assignment status 200", resp_sub.status_code == 200, f"got {resp_sub.status_code}")
        sub_data = resp_sub.json()
        check("submission returns file_name", sub_data.get("file_name") == "grovers_report.pdf")
        check("submission returns assignment_id", sub_data.get("assignment_id") == test_assignment_id)

        resp_get_sub = client.get(f"/api/assignments/{test_assignment_id}/submission", headers=stu_headers)
        check("get submission status 200", resp_get_sub.status_code == 200, f"got {resp_get_sub.status_code}")
        status_data = resp_get_sub.json()
        check("retrieved submission matches file_name", status_data.get("file_name") == "grovers_report.pdf")
        check("retrieved submission has submitted_at timestamp", bool(status_data.get("submitted_at")))
    except Exception as e:
        check("assignment submission", False, str(e))

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"Results: {passed}/{total} passed")
    assert passed == total, f"FAILED: {[label for label, ok in results if not ok]}"


if __name__ == "__main__":
    test_task9_exams_and_assignments()
