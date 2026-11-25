"""
B12 + B13 tests:
- B12: linked_content lists a quiz once (not gen-mirror + quiz row),
       idempotent manual quiz create, idempotent session create.
- B13: exam availability window — start blocked before available_from,
       allowed inside window, blocked after due_date.
"""
import json
import os
import sys
import uuid
from datetime import date, time, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(__file__)), 'edusense.db')}")
os.environ.setdefault("EDUSENSE_DATABASE_URL", os.environ["DATABASE_URL"])

from fastapi import HTTPException
from app.db.session import SessionLocal
from app.models.models import Quiz, AIGeneration, Session as ClassSession, SessionRegistration, User
from app.core.security import hash_password
from app.api.sessions import _get_session_linked_content, create_session
from app.api.quizzes import create_manual_quiz, start_quiz_attempt
from app.schemas.schemas import QuizCreateManual, QuizQuestionInput, SessionIn

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))
    print(("PASS" if cond else "FAIL"), name, detail if not cond else "")


def _mk_user(db, role, tag):
    u = User(name=f"B{tag}", email=f"b{tag}_{uuid.uuid4().hex[:6]}@t.com",
             password_hash=hash_password("pw"), role=role)
    db.add(u); db.commit(); db.refresh(u)
    return u


def _mk_session(db, instructor_id, title):
    s = ClassSession(instructor_id=instructor_id, title=title, description="t",
                     date=date.today(), start_time=time(10, 0), duration=30, status="scheduled")
    db.add(s); db.commit(); db.refresh(s)
    return s


def main():
    db = SessionLocal()
    inst = _mk_user(db, "instructor", "inst")
    student = _mk_user(db, "student", "stu")

    # ---------- B12 ----------
    sess = _mk_session(db, inst.id, "B12 Session")
    db.add(SessionRegistration(session_id=sess.id, student_id=student.id))

    q = Quiz(session_id=sess.id, instructor_id=inst.id, title="B12 Quiz",
             difficulty="Easy", questions_json=json.dumps([{"question": "Q?", "answer": "A"}]),
             is_exam=True, is_published=True)
    db.add(q)
    db.add(AIGeneration(instructor_id=inst.id, session_id=sess.id, type="quiz",
                        topic="B12 Quiz", prompt="mirror", data_json="{}"))
    db.commit(); db.refresh(q)

    linked = _get_session_linked_content(sess.id, db)
    quiz_entries = [l for l in linked if l["type"] == "quiz"]
    check("linked_content lists quiz exactly once", len(quiz_entries) == 1, str(linked))

    # idempotent manual quiz create
    payload = QuizCreateManual(
        title="B12 Manual", difficulty="Easy", session_id=sess.id,
        questions=[QuizQuestionInput(question="2+2?", answer="4", type="multiple_choice",
                                     options=["3", "4", "5"])],
        is_exam=True, is_published=True,
    )
    r1 = create_manual_quiz(payload, request=None, db=db, user=inst)
    r2 = create_manual_quiz(payload, request=None, db=db, user=inst)
    check("manual quiz create is idempotent", r1.id == r2.id, f"{r1.id} vs {r2.id}")

    # idempotent session create
    sp = SessionIn(title="B12 Dup Session", description="d", date=date.today(),
                   start_time=time(9, 0), duration=30)
    s1 = create_session(sp, request=None, db=db, user=inst)
    s2 = create_session(sp, request=None, db=db, user=inst)
    check("session create is idempotent", s1.id == s2.id, f"{s1.id} vs {s2.id}")

    # ---------- B13 ----------
    now = datetime.now(timezone.utc)
    q_future = Quiz(session_id=sess.id, instructor_id=inst.id, title="B13 Future",
                    difficulty="Easy", questions_json="[]",
                    is_exam=True, is_published=True,
                    available_from=now + timedelta(hours=2))
    q_open = Quiz(session_id=sess.id, instructor_id=inst.id, title="B13 Open",
                  difficulty="Easy", questions_json="[]",
                  is_exam=True, is_published=True,
                  available_from=now - timedelta(hours=1),
                  due_date=now + timedelta(hours=2))
    q_expired = Quiz(session_id=sess.id, instructor_id=inst.id, title="B13 Expired",
                     difficulty="Easy", questions_json="[]",
                     is_exam=True, is_published=True,
                     due_date=now - timedelta(hours=1))
    db.add_all([q_future, q_open, q_expired]); db.commit()
    db.refresh(q_future); db.refresh(q_open); db.refresh(q_expired)

    try:
        start_quiz_attempt(q_future.id, request=None, db=db, user=student)
        check("start blocked before available_from", False)
    except HTTPException as e:
        check("start blocked before available_from", e.status_code == 403, str(e.detail))

    att = start_quiz_attempt(q_open.id, request=None, db=db, user=student)
    check("start allowed inside window", att.id is not None)

    try:
        start_quiz_attempt(q_expired.id, request=None, db=db, user=student)
        check("start blocked after due_date", False)
    except HTTPException as e:
        check("start blocked after due_date", e.status_code == 403, str(e.detail))

    # QuizOut exposes the window
    from app.api.quizzes import _quiz_out
    out = _quiz_out(q_future, [])
    check("QuizOut exposes available_from", out.available_from is not None)

    db.close()
    failed = [c for c in CHECKS if not c[1]]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
