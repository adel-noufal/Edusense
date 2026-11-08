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

# Setup users
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

# Setup session
session1 = ClassSession(
    title="S5 Advanced Algorithms",
    description="Exam readiness session",
    date=date(2026, 12, 20),
    start_time=time(9, 30),
    duration=90,
    instructor_id=inst1.id,
    status="scheduled",
)
db.add(session1); db.commit(); db.refresh(session1)

# Enroll student in session1
reg = db.query(SessionRegistration).filter_by(session_id=session1.id, student_id=student_enrolled.id).first()
if not reg:
    reg = SessionRegistration(session_id=session1.id, student_id=student_enrolled.id)
    db.add(reg); db.commit()

print("Group 1: Quiz Creation & Publish as Exam Flow")

# 1. Create a raw quiz (not published yet)
raw_questions = [
    {"question": "What is Dijkstra's algorithm used for?", "type": "multiple_choice", "options": ["Shortest path", "Sorting", "Hashing", "MST"], "answer": "Shortest path", "explanation": "Finds single-source shortest path."},
    {"question": "QuickSort has worst-case O(N^2) complexity.", "type": "true_false", "options": ["True", "False"], "answer": "True", "explanation": "When pivot choices are bad."},
]

quiz = Quiz(
    session_id=None,
    title="Algorithms Midterm Quiz",
    difficulty="Hard",
    questions_json=json.dumps(raw_questions),
    is_exam=False,
    is_published=False,
)
db.add(quiz); db.commit(); db.refresh(quiz)
check("1. Raw quiz created with is_exam=False", quiz.is_exam == False)

# 2. Unauthorized instructor cannot publish to someone else's session
r_unauth = client.post(
    f"/api/quizzes/{quiz.id}/publish-as-exam",
    headers={"Authorization": f"Bearer {inst2_tok}"},
    json={"session_id": session1.id}
)
check("2. Unauthorized instructor rejected with 403", r_unauth.status_code == 403, f"status={r_unauth.status_code}")

# 3. Publish quiz as Exam with complete anti-cheat & timer settings
publish_payload = {
    "session_id": session1.id,
    "time_limit_seconds": 3600,                    # 60 min overall timer
    "time_limit_per_question_seconds": 120,         # 2 min per question
    "lock_back_navigation": True,                   # Answers locked once moved past
    "fullscreen_lock": True,                        # Anti-cheat fullscreen
    "camera_monitoring": True,                      # Anti-cheat camera
    "due_date": "2026-12-25T23:59:00",
}

r_pub = client.post(
    f"/api/quizzes/{quiz.id}/publish-as-exam",
    headers={"Authorization": f"Bearer {inst1_tok}"},
    json=publish_payload,
)
check("3. Publish as exam succeeds with 200", r_pub.status_code == 200, f"status={r_pub.status_code} body={r_pub.text[:150]}")
pub_json = r_pub.json() if r_pub.status_code == 200 else {}
check("4. Response reflects is_exam=True", pub_json.get("is_exam") == True)
check("5. Response reflects is_published=True", pub_json.get("is_published") == True)
check("6. lock_back_navigation is True", pub_json.get("lock_back_navigation") == True)
check("7. fullscreen_lock is True", pub_json.get("fullscreen_lock") == True)
check("8. camera_monitoring is True", pub_json.get("camera_monitoring") == True)
check("9. time_limit_seconds is 3600", pub_json.get("time_limit_seconds") == 3600)
check("10. time_limit_per_question_seconds is 120", pub_json.get("time_limit_per_question_seconds") == 120)

print("\nGroup 2: Student Exams Tab Integration & Isolation")

# 4. Enrolled student sees the published exam in /student/exams
r_student_exams = client.get("/api/quizzes/student/exams", headers={"Authorization": f"Bearer {stu_tok}"})
check("11. Enrolled student GET /quizzes/student/exams returns 200", r_student_exams.status_code == 200)
stu_exams = r_student_exams.json() if r_student_exams.status_code == 200 else []
matching_exam = next((e for e in stu_exams if e["id"] == quiz.id), None)
check("12. Published exam appears in student's Exams tab", matching_exam is not None)

if matching_exam:
    check("13. Student exam has lock_back_navigation=True", matching_exam.get("lock_back_navigation") == True)
    check("14. Student exam has fullscreen_lock=True", matching_exam.get("fullscreen_lock") == True)
    check("15. Student exam questions have answers stripped", "answer" not in matching_exam["questions"][0])
else:
    for n in ["13. lock_back", "14. fullscreen", "15. no answers"]:
        check(n, False, "exam not found in list")

# 5. Non-enrolled student does NOT see the published exam
r_other_exams = client.get("/api/quizzes/student/exams", headers={"Authorization": f"Bearer {other_tok}"})
other_list = r_other_exams.json() if r_other_exams.status_code == 200 else []
check("16. Non-enrolled student cannot see the exam in Exams tab", not any(e["id"] == quiz.id for e in other_list))

print("\nGroup 3: Anti-Cheat Violation Logging on Published Exam")

# 6. Student starts the exam attempt
r_start = client.post(f"/api/quizzes/{quiz.id}/start", headers={"Authorization": f"Bearer {stu_tok}"})
check("17. Enrolled student starts exam attempt (HTTP 200)", r_start.status_code == 200, f"status={r_start.status_code}")

# 7. Student logs anti-cheat violation (e.g. fullscreen exit)
r_violation = client.post(
    f"/api/quizzes/{quiz.id}/violations?event_type=fullscreen_exit",
    headers={"Authorization": f"Bearer {stu_tok}"},
    json={"details": {"screen": "window_minimized"}},
)
check("18. Violation logged successfully (HTTP 200)", r_violation.status_code == 200, f"status={r_violation.status_code}")
v_json = r_violation.json() if r_violation.status_code == 200 else {}
check("19. Violation record has event_type=fullscreen_exit", v_json.get("event_type") == "fullscreen_exit")

# 8. Check that the attempt was automatically locked upon critical violation
attempt_db = db.query(QuizAttempt).filter_by(quiz_id=quiz.id, student_id=student_enrolled.id).first()
check("20. Student attempt auto-locked on critical violation", attempt_db.is_locked == True)

print(f"\n{'='*50}")
print(f"Results: {len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
else:
    print("ALL PASSED PASS")
    sys.exit(0)
