"""
Section 3 â€” Exam & Assignment verification test
Tests:
  1. Instructor can create a quiz and mark it is_exam=True
  2. Student enrolled in that session sees it in GET /quizzes/student/exams
  3. Student NOT enrolled does NOT see it
  4. Instructor can create an assignment for a session
  5. Student can list assignments for enrolled sessions
  6. Student can submit a file â†’ AssignmentSubmission created
  7. Submission status shows file_name + submitted_at
  8. Non-enrolled student cannot list or submit assignments
"""
import sys, os, io, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from fastapi.testclient import TestClient
from app.db.seed import init_db
from app.main import app
from app.db.session import get_db
from app.models.models import User, Session as ClassSession, SessionRegistration, Quiz
from app.core.security import hash_password, create_access_token


def test_section3():
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

    def make_user(email, role):
        u = db.query(User).filter_by(email=email).first()
        if not u:
            u = User(name=f"Test {role}", email=email, password_hash=hash_password("test123"), role=role)
            db.add(u); db.commit(); db.refresh(u)
        return u

    def tok(user):
        return create_access_token(user.email, user.role)

    print("\n=== Section 3 Verification ===\n")

    inst = make_user("s3_inst@test.com", "instructor")
    stu_e = make_user("s3_stu_enrolled@test.com", "student")
    stu_n = make_user("s3_stu_not_enrolled@test.com", "student")

    from datetime import time as dtime
    sess = db.query(ClassSession).filter_by(title="S3 Exam Test Session").first()
    if not sess:
        sess = ClassSession(
            instructor_id=inst.id,
            title="S3 Exam Test Session",
            description="Testing exams and assignments",
            date=date.today(),
            start_time=dtime(9, 0),
            duration=60,
            status="pending",
        )
        db.add(sess); db.commit(); db.refresh(sess)

    reg = db.query(SessionRegistration).filter_by(session_id=sess.id, student_id=stu_e.id).first()
    if not reg:
        reg = SessionRegistration(session_id=sess.id, student_id=stu_e.id, attended=False)
        db.add(reg); db.commit()

    db.query(SessionRegistration).filter_by(session_id=sess.id, student_id=stu_n.id).delete()
    db.commit()

    inst_tok  = tok(inst)
    stu_e_tok = tok(stu_e)
    stu_n_tok = tok(stu_n)

    print("Group A: Exams")
    exam_payload = {
        "title": "Quantum Physics Midterm",
        "topic": "Quantum Mechanics",
        "subject": "Physics",
        "session_id": sess.id,
        "is_exam": True,
        "is_published": True,
        "lock_back_navigation": True,
        "fullscreen_lock": True,
        "camera_monitoring": False,
        "questions": [
            {
                "id": "q1",
                "question": "What is a qubit?",
                "options": ["A bit in quantum superposition", "A classic bit", "A photon", "None"],
                "answer": "A bit in quantum superposition",
                "correct_answer": "A bit in quantum superposition",
                "explanation": "Qubits can exist in superposition."
            }
        ]
    }
    r = client.post("/api/quizzes", json=exam_payload, headers={"Authorization": f"Bearer {inst_tok}"})
    check("1. Quiz created with is_exam=True", r.status_code == 201, f"status={r.status_code}")
    exam_id = r.json().get("id") if r.status_code == 201 else None

    if exam_id:
        created_quiz = db.query(Quiz).filter_by(id=exam_id).first()
        check("2. Quiz created with is_published=True", getattr(created_quiz, "is_published", False) == True)
        check("3. lock_back_navigation stored", getattr(created_quiz, "lock_back_navigation", False) == True)

    r_e = client.get("/api/quizzes/student/exams", headers={"Authorization": f"Bearer {stu_e_tok}"})
    check("4. Enrolled student can list exams (HTTP 200)", r_e.status_code == 200, f"status={r_e.status_code}")
    if r_e.status_code == 200:
        exams = r_e.json()
        found = any(e["id"] == exam_id for e in exams)
        check("5. Exam appears in enrolled student's list", found, f"exams={exams}")
        if found:
            ex = next(e for e in exams if e["id"] == exam_id)
            check("6. is_exam field returned as True", ex.get("is_exam") is True)
            check("7. lock_back_navigation returned as True", ex.get("lock_back_navigation") is True)
            check("8. fullscreen_lock returned as True", ex.get("fullscreen_lock") is True)
            qs = ex.get("questions") or []
            leaks = [q for q in qs if "correct_answer" in q]
            check("9. Correct answers stripped from questions", len(leaks) == 0, f"leaks={leaks}")

    r_n = client.get("/api/quizzes/student/exams", headers={"Authorization": f"Bearer {stu_n_tok}"})
    check("10. Non-enrolled student gets 200 (empty list)", r_n.status_code == 200, f"status={r_n.status_code}")
    if r_n.status_code == 200:
        exams_n = r_n.json()
        found_n = any(e["id"] == exam_id for e in exams_n)
        check("11. Non-enrolled student sees empty exam list (not leaked)", not found_n)

    print("\nGroup B: Assignments")
    asgn_payload = {
        "title": "Quantum Homework 1",
        "description": "Solve problem set 3. Submit PDF.",
        "session_id": sess.id,
        "max_points": 100.0,
        "due_date": "2026-12-31T23:59:59Z"
    }
    r = client.post("/api/assignments", json=asgn_payload, headers={"Authorization": f"Bearer {inst_tok}"})
    check("12. Instructor creates assignment (HTTP 201)", r.status_code == 201, f"status={r.status_code} body={r.text[:80]}")
    asgn_id = r.json().get("id") if r.status_code == 201 else None

    if asgn_id:
        check("13. Assignment title correct", r.json().get("title") == "Quantum Homework 1")
        check("14. Assignment session_id correct", r.json().get("session_id") == sess.id)

        r_asgn_e = client.get("/api/assignments/student", headers={"Authorization": f"Bearer {stu_e_tok}"})
        check("15. Enrolled student lists assignments (HTTP 200)", r_asgn_e.status_code == 200, f"status={r_asgn_e.status_code}")
        found_a = any(a["id"] == asgn_id for a in r_asgn_e.json()) if r_asgn_e.status_code == 200 else False
        check("16. Assignment appears in enrolled student's list", found_a)

        r_asgn_n = client.get("/api/assignments/student", headers={"Authorization": f"Bearer {stu_n_tok}"})
        found_n = any(a["id"] == asgn_id for a in r_asgn_n.json()) if r_asgn_n.status_code == 200 else False
        check("17. Non-enrolled student sees empty list (not leaked)", not found_n)

        fake_pdf = io.BytesIO(b"%PDF-1.4 Fake PDF Content for assignment submission")
        r_sub = client.post(
            f"/api/assignments/{asgn_id}/submit",
            files={"file": ("solution.pdf", fake_pdf, "application/pdf")},
            headers={"Authorization": f"Bearer {stu_e_tok}"},
        )
        check("18. Student submits file (HTTP 200)", r_sub.status_code == 200, f"status={r_sub.status_code} body={r_sub.text[:80]}")
        sub_data = r_sub.json() if r_sub.status_code == 200 else {}
        check("19. Submission has correct file_name", sub_data.get("file_name") == "solution.pdf")
        check("20. Submission has file_size > 0", sub_data.get("file_size", 0) > 0)
        check("21. Submission has submitted_at timestamp", bool(sub_data.get("submitted_at")))
        check("22. Submission links to correct assignment", sub_data.get("assignment_id") == asgn_id)

        r_status = client.get(
            f"/api/assignments/{asgn_id}/submission",
            headers={"Authorization": f"Bearer {stu_e_tok}"},
        )
        check("23. Student can check own submission status (HTTP 200)", r_status.status_code == 200, f"status={r_status.status_code}")
        check("24. Status response has file_name", r_status.json().get("file_name") == "solution.pdf" if r_status.status_code == 200 else False)

        fake2 = io.BytesIO(b"%PDF-1.4 malicious submission")
        r3 = client.post(
            f"/api/assignments/{asgn_id}/submit",
            files={"file": ("hack.pdf", fake2, "application/pdf")},
            headers={"Authorization": f"Bearer {stu_n_tok}"},
        )
        check("25. Non-enrolled student cannot submit (HTTP 403)", r3.status_code == 403, f"status={r3.status_code}")

    print(f"\n{'='*50}")
    print(f"Results: {len(PASSED)} passed, {len(FAILED)} failed")
    assert len(FAILED) == 0, f"Failed tests: {FAILED}"


if __name__ == "__main__":
    test_section3()
