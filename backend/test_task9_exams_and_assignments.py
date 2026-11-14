"""
test_task9_exams_and_assignments.py
Task 9 — Exam Tab Infinite Load & Assignments Visibility
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

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
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
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    results.append((label, condition))

client = TestClient(app)

def get_auth_headers(email: str, role: str):
    token = create_access_token(subject=email, role=role)
    return {"Authorization": f"Bearer {token}"}

# ---------------------------------------------------------------------------
# Setup Database Fixtures
# ---------------------------------------------------------------------------
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
        test_session = ClassSession(
            title="Task 9 Quantum Computing",
            description="Quantum algorithms and Qubits",
            instructor_id=instructor.id,
            date=datetime.now(timezone.utc).date(),
            start_time=(datetime.now(timezone.utc) + timedelta(hours=1)).time(),
            duration=60,
        )
        db.add(test_session)
        db.commit()
        db.refresh(test_session)

    # Ensure student is enrolled in this session
    reg = db.query(SessionRegistration).filter_by(session_id=test_session.id, student_id=student.id).first()
    if not reg:
        reg = SessionRegistration(session_id=test_session.id, student_id=student.id)
        db.add(reg)
        db.commit()

    # Create a published exam for this session
    test_exam = db.query(Quiz).filter_by(session_id=test_session.id, is_exam=True).first()
    if not test_exam:
        test_exam = Quiz(
            session_id=test_session.id,
            title="Quantum Midterm Exam",
            difficulty="intermediate",
            is_exam=True,
            is_published=True,
            questions_json=json.dumps([
                {
                    "id": 1,
                    "question": "What is a qubit superposition?",
                    "options": ["A state of 0 and 1 simultaneously", "A classical bit", "A cooling unit"],
                    "answer": "A state of 0 and 1 simultaneously"
                }
            ]),
            time_limit_seconds=1800,
        )
        db.add(test_exam)
        db.commit()
        db.refresh(test_exam)

    # Create an assignment for this session
    test_assignment = db.query(Assignment).filter_by(session_id=test_session.id, title="Quantum Lab Report").first()
    if not test_assignment:
        test_assignment = Assignment(
            session_id=test_session.id,
            instructor_id=instructor.id,
            title="Quantum Lab Report",
            description="Submit code and PDF report for Grover's search algorithm.",
            due_date=datetime.now(timezone.utc) + timedelta(days=7),
            max_points=100.0,
        )
        db.add(test_assignment)
        db.commit()
        db.refresh(test_assignment)

    test_exam_id = test_exam.id
    test_assignment_id = test_assignment.id
    inst_headers = get_auth_headers(instructor.email, instructor.role)
    stu_headers = get_auth_headers(student.email, student.role)
finally:
    db.close()

# ---------------------------------------------------------------------------
# Test 1 & 2: Frontend Codebase Integrity Checks
# ---------------------------------------------------------------------------
print("\n--- Tests 1 & 2: Frontend Codebase Audit ---")
try:
    frontend_dir = os.path.join(BACKEND_DIR, "..", "frontend", "src")
    auth_ctx = open(os.path.join(frontend_dir, "context", "AuthContext.jsx"), encoding="utf-8").read()
    check("AuthContext exposes token in value", "token," in auth_ctx and "setToken" in auth_ctx)

    student_exams = open(os.path.join(frontend_dir, "pages", "StudentExams.jsx"), encoding="utf-8").read()
    check("StudentExams uses api() client", "api('/quizzes/student/exams')" in student_exams)
    check("StudentExams falls back gracefully when token absent", "setLoading(false)" in student_exams)
    check("StudentExams displays exam.session_title", "exam.session_title" in student_exams)

    student_assigns = open(os.path.join(frontend_dir, "pages", "StudentAssignments.jsx"), encoding="utf-8").read()
    check("StudentAssignments uses api() client", "api('/assignments/student')" in student_assigns)
    check("StudentAssignments falls back gracefully when token absent", "setLoading(false)" in student_assigns)
    check("StudentAssignments groups by session_title", "a.session_title" in student_assigns)
except Exception as e:
    check("Frontend Codebase Audit", False, str(e))

# ---------------------------------------------------------------------------
# Test 3: GET /api/quizzes/student/exams
# ---------------------------------------------------------------------------
print("\n--- Test 3: GET /api/quizzes/student/exams ---")
try:
    resp = client.get("/api/quizzes/student/exams", headers=stu_headers)
    check("student exams status 200", resp.status_code == 200, f"got {resp.status_code}")
    exams_data = resp.json()
    check("returns list", isinstance(exams_data, list))
    our_exam = next((e for e in exams_data if e["id"] == test_exam_id), None)
    check("published exam found for enrolled student", our_exam is not None)
    if our_exam:
        check("session_title populated", our_exam.get("session_title") == "Task 9 Quantum Computing", f"got {our_exam.get('session_title')}")
        check("is_exam is True", our_exam.get("is_exam") is True)
        # Verify student question does NOT have correct answer
        q0 = our_exam["questions"][0]
        check("correct answer stripped from questions", "answer" not in q0, f"keys in question: {list(q0.keys())}")
except Exception as e:
    check("student exams endpoint", False, str(e))

# ---------------------------------------------------------------------------
# Test 4: GET /api/assignments/student
# ---------------------------------------------------------------------------
print("\n--- Test 4: GET /api/assignments/student ---")
try:
    resp = client.get("/api/assignments/student", headers=stu_headers)
    check("student assignments status 200", resp.status_code == 200, f"got {resp.status_code}")
    assign_data = resp.json()
    check("returns list", isinstance(assign_data, list))
    our_assign = next((a for a in assign_data if a["id"] == test_assignment_id), None)
    check("assignment found for enrolled student", our_assign is not None)
    if our_assign:
        check("session_title populated", our_assign.get("session_title") == "Task 9 Quantum Computing", f"got {our_assign.get('session_title')}")
        check("title matches", our_assign.get("title") == "Quantum Lab Report")
        check("max_points is 100", our_assign.get("max_points") == 100.0)
except Exception as e:
    check("student assignments endpoint", False, str(e))

# ---------------------------------------------------------------------------
# Test 5 & 6: Assignment Submission Upload & Fetch Status
# ---------------------------------------------------------------------------
print("\n--- Tests 5 & 6: Assignment Submission & Fetch Status ---")
try:
    # 5. Upload assignment submission
    dummy_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    files = {"file": ("grovers_report.pdf", io.BytesIO(dummy_pdf), "application/pdf")}
    resp_sub = client.post(f"/api/assignments/{test_assignment_id}/submit", headers=stu_headers, files=files)
    check("submit assignment status 200", resp_sub.status_code == 200, f"got {resp_sub.status_code}")
    sub_data = resp_sub.json()
    check("submission returns file_name", sub_data.get("file_name") == "grovers_report.pdf")
    check("submission returns assignment_id", sub_data.get("assignment_id") == test_assignment_id)

    # 6. Fetch submission status
    resp_get_sub = client.get(f"/api/assignments/{test_assignment_id}/submission", headers=stu_headers)
    check("get submission status 200", resp_get_sub.status_code == 200, f"got {resp_get_sub.status_code}")
    status_data = resp_get_sub.json()
    check("retrieved submission matches file_name", status_data.get("file_name") == "grovers_report.pdf")
    check("retrieved submission has submitted_at timestamp", bool(status_data.get("submitted_at")))
except Exception as e:
    check("assignment submission", False, str(e))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"Results: {passed}/{total} passed")
if passed == total:
    print("ALL TESTS PASSED")
else:
    failed = [label for label, ok in results if not ok]
    print("FAILED:\n  " + "\n  ".join(failed))
    sys.exit(1)
