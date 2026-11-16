"""
Section 5 Verification Test — Quiz Publishing & Exam Deployment
Tests:
1. Instructor creates/generates a quiz.
2. Instructor publishes quiz as exam via POST /api/quizzes/{id}/publish-as-exam with all options:
   - session_id
   - overall timer (time_limit_seconds)
   - per-question timer (time_limit_per_question_seconds)
   - lock_back_navigation
   - fullscreen_lock
   - camera_monitoring
   - due_date
3. Session ownership security checks (403 for unauthorized instructor).
4. Enrolled student sees the published exam in GET /quizzes/student/exams with all security settings.
5. Questions are stripped of correct answers for students.
6. Non-enrolled student does not see the published exam.
7. Anti-cheat violation logging (fullscreen_exit, tab_switch) works on the published exam.
"""
import sys, os, io, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from datetime import date, time, datetime, timezone
from fastapi.testclient import TestClient
from app.db.seed import init_db
from app.main import app
from app.db.session import get_db
from app.models.models import User, Session as ClassSession, SessionRegistration, Quiz, QuizAttempt
from app.core.security import hash_password, create_access_token


def test_section5():
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

    print("\n=== Section 5 Verification ===\n")

    def get_or_create(email, role, name):
        u = db.query(User).filter_by(email=email).first()
        if not u:
            u = User(name=name, email=email, password_hash=hash_password("test123"), role=role)
            db.add(u); db.commit(); db.refresh(u)
        return u

    inst1 = get_or_create("s5_instructor1@test.com", "instructor", "Instructor One")
    inst2 = get_or_create("s5_instructor2@test.com", "instructor", "Instructor Two")
    student_enrolled = get_or_create("s5_student_enrolled@test.com", "student", "Enrolled Student")
    student_other = get_or_create("s5_student_other@test.com", "student", "Other Student")

    inst1_tok = create_access_token(inst1.email, inst1.role)
    inst2_tok = create_access_token(inst2.email, inst2.role)
    stu_tok = create_access_token(student_enrolled.email, student_enrolled.role)
    other_tok = create_access_token(student_other.email, student_other.role)

    session = db.query(ClassSession).filter_by(title="Section 5 Biology Lab").first()
    if not session:
        session = ClassSession(
            title="Section 5 Biology Lab",
            description="",
            date=date(2026, 11, 20),
            start_time=time(10, 0),
            duration=90,
            instructor_id=inst1.id,
            status="scheduled",
        )
        db.add(session); db.commit(); db.refresh(session)

    reg = db.query(SessionRegistration).filter_by(session_id=session.id, student_id=student_enrolled.id).first()
    if not reg:
        reg = SessionRegistration(session_id=session.id, student_id=student_enrolled.id, attended=False)
        db.add(reg); db.commit()

    db.query(SessionRegistration).filter_by(session_id=session.id, student_id=student_other.id).delete()
    db.commit()

    quiz_payload = {
        "title": "Cellular Biology Test",
        "topic": "Cell Biology",
        "subject": "Biology",
        "questions": [
            {
                "id": "q1",
                "question": "What is the powerhouse of the cell?",
                "options": ["Nucleus", "Mitochondria", "Ribosome", "Endoplasmic Reticulum"],
                "answer": "Mitochondria",
                "correct_answer": "Mitochondria",
                "explanation": "Mitochondria generate ATP."
            },
            {
                "id": "q2",
                "question": "Which organelle carries out photosynthesis?",
                "options": ["Chloroplast", "Golgi apparatus", "Vacuole", "Centrosome"],
                "answer": "Chloroplast",
                "correct_answer": "Chloroplast",
                "explanation": "Chloroplasts contain chlorophyll."
            }
        ]
    }
    r_create = client.post("/api/quizzes", json=quiz_payload, headers={"Authorization": f"Bearer {inst1_tok}"})
    check("1. Instructor 1 creates draft quiz (HTTP 201)", r_create.status_code == 201, f"status={r_create.status_code}")
    quiz_data = r_create.json()
    quiz_id = quiz_data["id"]

    due = "2026-11-25T18:00:00Z"
    publish_payload = {
        "session_id": session.id,
        "time_limit_seconds": 3600,
        "time_limit_per_question_seconds": 120,
        "lock_back_navigation": True,
        "fullscreen_lock": True,
        "camera_monitoring": True,
        "due_date": due,
    }

    r_unauth = client.post(f"/api/quizzes/{quiz_id}/publish-as-exam", json=publish_payload, headers={"Authorization": f"Bearer {inst2_tok}"})
    check("2. Unauthorized instructor cannot publish quiz as exam (HTTP 403)", r_unauth.status_code == 403, f"status={r_unauth.status_code}")

    r_pub = client.post(f"/api/quizzes/{quiz_id}/publish-as-exam", json=publish_payload, headers={"Authorization": f"Bearer {inst1_tok}"})
    check("3. Instructor publishes quiz as exam (HTTP 200)", r_pub.status_code == 200, f"status={r_pub.status_code} body={r_pub.text[:150]}")

    quiz = db.query(Quiz).filter_by(id=quiz_id).first()
    check("4. DB is_published is True", quiz.is_published == True)
    check("5. DB is_exam is True", quiz.is_exam == True)
    check("6. DB session_id links correctly", quiz.session_id == session.id)
    check("7. DB time_limit_seconds stored", quiz.time_limit_seconds == 3600)
    check("8. DB time_limit_per_question_seconds stored", quiz.time_limit_per_question_seconds == 120)
    check("9. DB lock_back_navigation stored", quiz.lock_back_navigation == True)
    check("10. DB fullscreen_lock stored", quiz.fullscreen_lock == True)
    check("11. DB camera_monitoring stored", quiz.camera_monitoring == True)

    r_exams = client.get("/api/quizzes/student/exams", headers={"Authorization": f"Bearer {stu_tok}"})
    check("12. Enrolled student lists exams (HTTP 200)", r_exams.status_code == 200, f"status={r_exams.status_code}")
    exams = r_exams.json() if r_exams.status_code == 200 else []
    exam_item = next((e for e in exams if e["id"] == quiz_id), None)
    check("13. Published exam appears in enrolled student's list", exam_item is not None)

    if exam_item:
        check("14. Exam item has time limits & anti-cheat flags",
              exam_item.get("time_limit_seconds") == 3600 and
              exam_item.get("lock_back_navigation") is True and
              exam_item.get("fullscreen_lock") is True)
        
        # Verify answers are stripped
        questions = exam_item.get("questions") or []
        has_answers = any("correct_answer" in q for q in questions)
        check("15. Exam questions are stripped of correct_answer", not has_answers)

    r_other = client.get("/api/quizzes/student/exams", headers={"Authorization": f"Bearer {other_tok}"})
    other_exams = r_other.json() if r_other.status_code == 200 else []
    check("16. Non-enrolled student does NOT see the exam", not any(e["id"] == quiz_id for e in other_exams))

    r_start = client.post(f"/api/quizzes/{quiz.id}/start", headers={"Authorization": f"Bearer {stu_tok}"})
    check("17. Enrolled student starts exam attempt (HTTP 200)", r_start.status_code == 200, f"status={r_start.status_code}")

    r_violation = client.post(
        f"/api/quizzes/{quiz.id}/violations?event_type=fullscreen_exit",
        headers={"Authorization": f"Bearer {stu_tok}"},
        json={"details": {"screen": "window_minimized"}},
    )
    check("18. Violation logged successfully (HTTP 200)", r_violation.status_code == 200, f"status={r_violation.status_code}")
    v_json = r_violation.json() if r_violation.status_code == 200 else {}
    check("19. Violation record has event_type=fullscreen_exit", v_json.get("event_type") == "fullscreen_exit")

    attempt_db = db.query(QuizAttempt).filter_by(quiz_id=quiz.id, student_id=student_enrolled.id).first()
    check("20. Student attempt auto-locked on critical violation", attempt_db.is_locked == True)

    print(f"\n{'='*50}")
    print(f"Results: {len(PASSED)} passed, {len(FAILED)} failed")
    assert len(FAILED) == 0, f"Failed tests: {FAILED}"


if __name__ == "__main__":
    test_section5()
