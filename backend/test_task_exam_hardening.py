"""
Item 6 tests — exam/quiz hardening:
- normalize_difficulty / normalize_questions (count honored, enum labels)
- exam one-attempt enforcement (409 on second start after submit)
- unpublished exam blocked (403)
- past-due exam blocked (403)
- reveal_answers=False strips correct_answer/explanation from submit details
- resubmit replay blocked (400)
"""
import json
import os
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(os.path.dirname(__file__), 'edusense.db')}")
os.environ.setdefault("EDUSENSE_DATABASE_URL", os.environ["DATABASE_URL"])

from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.models.models import Quiz, QuizAttempt, User, Session as ClassSession, SessionRegistration
from app.agents.quiz_agent import normalize_difficulty, normalize_questions
from app.core.security import hash_password

client = TestClient(app)
RESULTS = []
_PASSWORD = "testpass123"


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond), extra))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {extra}")


def login(email, password=_PASSWORD):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def main():
    db = SessionLocal()
    created = {"quizzes": [], "sessions": [], "regs": [], "attempts": []}
    try:
        # Dedicated users with known password (seeded users have unknown creds)
        suffix = uuid.uuid4().hex[:8]
        instructor = db.query(User).filter_by(email=f"exam-inst-{suffix}@test.local").first()
        if not instructor:
            instructor = User(name="Exam Inst", email=f"exam-inst-{suffix}@test.local",
                              password_hash=hash_password(_PASSWORD), role="instructor")
            db.add(instructor); db.commit(); db.refresh(instructor)
        student = db.query(User).filter_by(email=f"exam-stu-{suffix}@test.local").first()
        if not student:
            student = User(name="Exam Stu", email=f"exam-stu-{suffix}@test.local",
                           password_hash=hash_password(_PASSWORD), role="student")
            db.add(student); db.commit(); db.refresh(student)
        created["users"] = [instructor.id, student.id]
        inst_h = login(instructor.email)
        stu_h = login(student.email)

        # ── Unit: normalization ──────────────────────────────────────────
        check("difficulty intermediate->Medium", normalize_difficulty("intermediate") == "Medium")
        check("difficulty advanced->Hard", normalize_difficulty("Advanced") == "Hard")
        check("difficulty bogus->Medium", normalize_difficulty("xyz") == "Medium")
        qs = normalize_questions([{"question": "Q1?", "options": ["a", "b"], "answer": "a"}], 4, "Topic", "Medium")
        check("questions padded to count", len(qs) == 4)
        qs2 = normalize_questions([{"question": f"Q{i}?"} for i in range(10)], 3, "Topic", "Easy")
        check("questions truncated to count", len(qs2) == 3)

        # ── Fixture: session + enrollment + exam quiz ───────────────────
        sess = ClassSession(
            instructor_id=instructor.id, title="Exam Hardening Test",
            description="t", date=date.today(), start_time=time(9, 0),
            duration=None, status="ongoing",
        )
        db.add(sess); db.commit(); db.refresh(sess)
        created["sessions"].append(sess.id)
        reg = SessionRegistration(session_id=sess.id, student_id=student.id, attended=False)
        db.add(reg); db.commit(); db.refresh(reg)
        created["regs"].append(reg.id)

        questions = [
            {"type": "multiple_choice", "question": "2+2?",
             "options": ["3", "4", "5", "6"], "answer": "B", "explanation": "basic math"},
            {"type": "multiple_choice", "question": "Sky color?",
             "options": ["Green", "Blue", "Red", "Yellow"], "answer": "Blue", "explanation": "rayleigh"},
        ]
        quiz = Quiz(
            session_id=sess.id, title="Hardening Exam", difficulty="intermediate",
            questions_json=json.dumps(questions), is_exam=True, is_published=True,
            time_limit_seconds=3600, reveal_answers=False,
        )
        db.add(quiz); db.commit(); db.refresh(quiz)
        created["quizzes"].append(quiz.id)

        # ── API: exam flow ──────────────────────────────────────────────
        r = client.get(f"/api/quizzes/{quiz.id}", headers=stu_h)
        check("student GET quiz 200", r.status_code == 200)
        body = r.json()
        check("answers stripped for student", all("answer" not in q and "correct_answer" not in q for q in body["questions"]))
        check("difficulty normalized in API", body["difficulty"] == "Medium", body["difficulty"])
        check("reveal_answers surfaced", body.get("reveal_answers") is False)

        r = client.post(f"/api/quizzes/{quiz.id}/start", headers=stu_h)
        check("start attempt 200", r.status_code == 200, r.text[:150])
        attempt_id = r.json().get("id") if r.status_code == 200 else None
        created["attempts"].append(attempt_id)

        # resume: second start returns same attempt
        r2 = client.post(f"/api/quizzes/{quiz.id}/start", headers=stu_h)
        check("resume returns same attempt", r2.status_code == 200 and r2.json().get("id") == attempt_id)

        # submit with one correct (B->idx1) one wrong
        r3 = client.post(f"/api/quizzes/{quiz.id}/submit", headers=stu_h,
                         json={"answers": {0: "B", 1: "Red"}, "elapsed_seconds": 30})
        check("submit 200", r3.status_code == 200, r3.text[:200])
        if r3.status_code == 200:
            data = r3.json()
            check("score 1/2", data["score"] == 1.0 and data["max_score"] == 2.0, str(data.get("score")))
            check("reveal_answers=False hides correct_answer",
                  all("correct_answer" not in d and "explanation" not in d for d in data["details"]))
            check("passed False at 50%", data["passed"] is False)

        # replay submit -> 400 no active attempt
        r4 = client.post(f"/api/quizzes/{quiz.id}/submit", headers=stu_h,
                         json={"answers": {0: "B"}, "elapsed_seconds": 5})
        check("resubmit blocked 400", r4.status_code == 400, str(r4.status_code))

        # second attempt on exam -> 409
        r5 = client.post(f"/api/quizzes/{quiz.id}/start", headers=stu_h)
        check("exam one-attempt 409", r5.status_code == 409, f"{r5.status_code} {r5.text[:120]}")

        # ── unpublished exam blocked ────────────────────────────────────
        quiz2 = Quiz(
            session_id=sess.id, title="Unpublished Exam", difficulty="Easy",
            questions_json=json.dumps(questions), is_exam=True, is_published=False,
        )
        db.add(quiz2); db.commit(); db.refresh(quiz2)
        created["quizzes"].append(quiz2.id)
        r6 = client.post(f"/api/quizzes/{quiz2.id}/start", headers=stu_h)
        check("unpublished exam 403", r6.status_code == 403, str(r6.status_code))

        # ── past-due exam blocked ───────────────────────────────────────
        quiz3 = Quiz(
            session_id=sess.id, title="Expired Exam", difficulty="Easy",
            questions_json=json.dumps(questions), is_exam=True, is_published=True,
            due_date=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db.add(quiz3); db.commit(); db.refresh(quiz3)
        created["quizzes"].append(quiz3.id)
        r7 = client.post(f"/api/quizzes/{quiz3.id}/start", headers=stu_h)
        check("past-due exam 403", r7.status_code == 403, str(r7.status_code))

        # cleanup attempts for created quizzes
        for qid in created["quizzes"]:
            for a in db.query(QuizAttempt).filter_by(quiz_id=qid).all():
                db.delete(a)
        db.commit()
    finally:
        for qid in created["quizzes"]:
            db.query(Quiz).filter_by(id=qid).delete()
        for rid in created["regs"]:
            db.query(SessionRegistration).filter_by(id=rid).delete()
        for sid in created["sessions"]:
            db.query(ClassSession).filter_by(id=sid).delete()
        for uid in created.get("users", []):
            db.query(User).filter_by(id=uid).delete()
        db.commit()
        db.close()

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        for name, _, extra in failed:
            print(f"  FAILED: {name} {extra}")
        sys.exit(1)
    print("ALL EXAM HARDENING CHECKS PASSED")


if __name__ == "__main__":
    main()
