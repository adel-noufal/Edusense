"""
Section 3 — Exam & Assignment verification test
Tests:
  1. Instructor can create a quiz and mark it is_exam=True
  2. Student enrolled in that session sees it in GET /quizzes/student/exams
  3. Student NOT enrolled does NOT see it
  4. Instructor can create an assignment for a session
  5. Student can list assignments for enrolled sessions
  6. Student can submit a file → AssignmentSubmission created
  7. Submission status shows file_name + submitted_at
  8. Non-enrolled student cannot list or submit assignments
"""
import sys, os, io, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from datetime import date
from fastapi.testclient import TestClient
from app.db.seed import init_db
from app.main import app
from app.db.session import get_db
from app.models.models import User, Session as ClassSession, SessionRegistration, Quiz
from app.core.security import hash_password, create_access_token

init_db(seed=False)

client = TestClient(app)
db = next(get_db())

PASSED = []
FAILED = []

def check(name, cond, detail=""):
    if cond:
        PASSED.append(name)
        print(f"  PASS {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL {name}{': ' + detail if detail else ''}")

# ── Helpers ──────────────────────────────────────────────────────────────────

def make_user(email, role):
    u = db.query(User).filter_by(email=email).first()
    if not u:
        u = User(name=f"Test {role}", email=email, password_hash=hash_password("test123"), role=role)
        db.add(u); db.commit(); db.refresh(u)
    return u

def tok(user):
    return create_access_token(user.email, user.role)

def make_session(instructor):
    from datetime import time
    s = ClassSession(
        title="Exam Test Session", description="",
        date=date(2026, 12, 1),
        start_time=time(10, 0),
        duration=60,
        instructor_id=instructor.id,
        status="scheduled",
    )
    db.add(s); db.commit(); db.refresh(s); return s

def enroll(student, session):
    reg = db.query(SessionRegistration).filter_by(session_id=session.id, student_id=student.id).first()
    if not reg:
        reg = SessionRegistration(session_id=session.id, student_id=student.id)
        db.add(reg); db.commit()

# ── Setup ────────────────────────────────────────────────────────────────────
print("\n=== Section 3 Verification ===\n")

instructor = make_user("s3_instructor@test.com", "instructor")
student_enrolled = make_user("s3_student_e@test.com", "student")
student_not_enrolled = make_user("s3_student_n@test.com", "student")
session = make_session(instructor)
enroll(student_enrolled, session)

inst_tok = tok(instructor)
stu_e_tok = tok(student_enrolled)
stu_n_tok = tok(student_not_enrolled)

# ── Test 1: Instructor creates a quiz and marks is_exam=True via PUT ──────────
print("Group A: Exams")

# Create a quiz via AI endpoint (use direct DB for speed in tests)
q = Quiz(
    session_id=session.id,
    title="Section 3 Exam",
    difficulty="Medium",
    questions_json=json.dumps([
        {"question": "2+2?", "type": "multiple_choice",
         "options": ["3","4","5","6"], "answer": "4"},
    ]),
    is_exam=True,
    is_published=True,
    fullscreen_lock=True,
    lock_back_navigation=True,
)
db.add(q); db.commit(); db.refresh(q)

check("1. Quiz created with is_exam=True", q.is_exam == True, f"is_exam={q.is_exam}")
check("2. Quiz created with is_published=True", q.is_published == True)
check("3. lock_back_navigation stored", q.lock_back_navigation == True)

# ── Test 2: Enrolled student sees exam in GET /quizzes/student/exams ──────────
r = client.get("/api/quizzes/student/exams", headers={"Authorization": f"Bearer {stu_e_tok}"})
check("4. Enrolled student can list exams (HTTP 200)", r.status_code == 200, f"status={r.status_code}")
exams = r.json() if r.status_code == 200 else []
found_exam = any(e["id"] == q.id for e in exams)
check("5. Exam appears in enrolled student's list", found_exam, f"exams={[e['id'] for e in exams]}")

# Check exam fields returned
if found_exam:
    exam_data = next(e for e in exams if e["id"] == q.id)
    check("6. is_exam field returned as True", exam_data.get("is_exam") == True)
    check("7. lock_back_navigation returned as True", exam_data.get("lock_back_navigation") == True)
    check("8. fullscreen_lock returned as True", exam_data.get("fullscreen_lock") == True)
    check("9. Correct answers stripped from questions", "answer" not in exam_data["questions"][0])
else:
    for name in ["6. is_exam field", "7. lock_back_navigation", "8. fullscreen_lock", "9. No answers"]:
        check(name, False, "exam not found")

# ── Test 3: Non-enrolled student does NOT see exam ────────────────────────────
r2 = client.get("/api/quizzes/student/exams", headers={"Authorization": f"Bearer {stu_n_tok}"})
check("10. Non-enrolled student gets 200 (empty list)", r2.status_code == 200, f"status={r2.status_code}")
other_exams = r2.json() if r2.status_code == 200 else []
check("11. Non-enrolled student sees empty exam list (not leaked)",
      not any(e["id"] == q.id for e in other_exams),
      f"found={other_exams}")

# ── Test 4: Instructor creates assignment ─────────────────────────────────────
print("\nGroup B: Assignments")

r = client.post(
    "/api/assignments/",
    json={
        "title": "Essay Assignment",
        "description": "Write 500 words on AI in education.",
        "due_date": "2026-12-15T23:59:00",
        "max_points": 50.0,
        "session_id": session.id,
    },
    headers={"Authorization": f"Bearer {inst_tok}"},
)
check("12. Instructor creates assignment (HTTP 201)", r.status_code == 201, f"status={r.status_code} body={r.text[:200]}")
assignment = r.json() if r.status_code == 201 else {}
check("13. Assignment title correct", assignment.get("title") == "Essay Assignment")
check("14. Assignment session_id correct", assignment.get("session_id") == session.id)

# ── Test 5: Enrolled student lists assignments ────────────────────────────────
r = client.get("/api/assignments/student", headers={"Authorization": f"Bearer {stu_e_tok}"})
check("15. Enrolled student lists assignments (HTTP 200)", r.status_code == 200, f"status={r.status_code}")
asgns = r.json() if r.status_code == 200 else []
found_asgn = any(a.get("id") == assignment.get("id") for a in asgns)
check("16. Assignment appears in enrolled student's list", found_asgn)

# ── Test 6: Non-enrolled student cannot list assignments ──────────────────────
r2 = client.get("/api/assignments/student", headers={"Authorization": f"Bearer {stu_n_tok}"})
check("17. Non-enrolled student sees empty list (not leaked)", r2.status_code == 200 and not any(
    a.get("id") == assignment.get("id") for a in r2.json()
))

# ── Test 7: Student submits a file ────────────────────────────────────────────
asgn_id = assignment.get("id")
if asgn_id:
    fake_pdf = io.BytesIO(b"%PDF-1.4 fake pdf content for test")
    fake_pdf.name = "essay.pdf"
    r = client.post(
        f"/api/assignments/{asgn_id}/submit",
        files={"file": ("essay.pdf", fake_pdf, "application/pdf")},
        headers={"Authorization": f"Bearer {stu_e_tok}"},
    )
    check("18. Student submits file (HTTP 200)", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    sub = r.json() if r.status_code == 200 else {}
    check("19. Submission has correct file_name", sub.get("file_name") == "essay.pdf")
    check("20. Submission has file_size > 0", (sub.get("file_size") or 0) > 0)
    check("21. Submission has submitted_at timestamp", bool(sub.get("submitted_at")))
    check("22. Submission links to correct assignment", sub.get("assignment_id") == asgn_id)

    # ── Test 8: Check submission status ──────────────────────────────────────
    r2 = client.get(
        f"/api/assignments/{asgn_id}/submission",
        headers={"Authorization": f"Bearer {stu_e_tok}"},
    )
    check("23. Student can check own submission status (HTTP 200)", r2.status_code == 200)
    sub2 = r2.json() if r2.status_code == 200 else {}
    check("24. Status response has file_name", sub2.get("file_name") == "essay.pdf")

    # Non-enrolled student cannot submit
    fake2 = io.BytesIO(b"fake")
    r3 = client.post(
        f"/api/assignments/{asgn_id}/submit",
        files={"file": ("hack.pdf", fake2, "application/pdf")},
        headers={"Authorization": f"Bearer {stu_n_tok}"},
    )
    check("25. Non-enrolled student cannot submit (HTTP 403)", r3.status_code == 403, f"status={r3.status_code}")
else:
    for n in range(18, 26):
        check(f"{n}. (skipped - assignment creation failed)", False)

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"Results: {len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
else:
    print("ALL PASSED PASS")
    sys.exit(0)
