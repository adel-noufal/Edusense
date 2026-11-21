"""
B4 tests — published exam visibility for students:
- exam linked to enrolled session -> visible
- exam linked to a session student is NOT enrolled in -> hidden
- session-less exam owned by an instructor the student has sessions with -> visible
- session-less exam owned by a different instructor -> hidden
- unpublished / non-exam quizzes never listed
- answers stripped from questions
"""
import json
import os
import sys
import uuid
from datetime import date, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(os.path.dirname(__file__), 'edusense.db')}")
os.environ.setdefault("EDUSENSE_DATABASE_URL", os.environ["DATABASE_URL"])

from app.db.session import SessionLocal
from app.models.models import Quiz, Session as ClassSession, SessionRegistration, User
from app.core.security import hash_password
from app.api.quizzes import list_student_exams

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))
    print(("PASS" if cond else "FAIL"), name, detail if not cond else "")


def _mk_user(db, role, tag):
    u = User(name=f"B4 {tag}", email=f"b4_{tag}_{uuid.uuid4().hex[:6]}@t.com",
             password_hash=hash_password("pw"), role=role)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _mk_session(db, instructor_id, title):
    s = ClassSession(instructor_id=instructor_id, title=title, description="t",
                     date=date.today(), start_time=time(10, 0), duration=30, status="ended")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _mk_quiz(db, **kw):
    kw.setdefault("is_exam", True)
    kw.setdefault("is_published", True)
    q = Quiz(title=kw.pop("title", "B4 Exam"),
             questions_json=json.dumps([{"question": "Q?", "answer": "A", "options": ["A", "B"]}]),
             **kw)
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


def _visible_ids(db, student):
    return {q.id for q in list_student_exams(request=None, db=db, user=student)}


def main():
    db = SessionLocal()
    inst = _mk_user(db, "instructor", "inst")
    other_inst = _mk_user(db, "instructor", "other")
    student = _mk_user(db, "student", "stu")
    outsider = _mk_user(db, "student", "out")

    enrolled = _mk_session(db, inst.id, "B4 Enrolled")
    foreign = _mk_session(db, other_inst.id, "B4 Foreign Session")
    db.add(SessionRegistration(session_id=enrolled.id, student_id=student.id))
    db.add(SessionRegistration(session_id=foreign.id, student_id=outsider.id))
    db.commit()

    q_enrolled = _mk_quiz(db, session_id=enrolled.id, instructor_id=inst.id, title="Enrolled Exam")
    q_foreign_sess = _mk_quiz(db, session_id=foreign.id, instructor_id=other_inst.id, title="Foreign Session Exam")
    q_all_students = _mk_quiz(db, session_id=None, instructor_id=inst.id, title="All Students Exam")
    q_other_owner = _mk_quiz(db, session_id=None, instructor_id=other_inst.id, title="Other Owner Exam")
    q_unpub = _mk_quiz(db, session_id=enrolled.id, instructor_id=inst.id, title="Unpub", is_published=False)
    q_not_exam = Quiz(title="Plain Quiz", questions_json="[]", session_id=enrolled.id,
                      is_exam=False, is_published=True, instructor_id=inst.id)
    db.add(q_not_exam)
    db.commit()

    vis = _visible_ids(db, student)
    check("enrolled-session exam visible", q_enrolled.id in vis, str(vis))
    check("foreign-session exam hidden", q_foreign_sess.id not in vis)
    check("session-less exam of own instructor visible", q_all_students.id in vis)
    check("session-less exam of other instructor hidden", q_other_owner.id not in vis)
    check("unpublished exam hidden", q_unpub.id not in vis)
    check("non-exam quiz hidden", q_not_exam.id not in vis)

    out_vis = _visible_ids(db, outsider)
    check("outsider sees foreign-session exam", q_foreign_sess.id in out_vis)
    check("outsider does NOT see own-instructor session-less exam", q_all_students.id not in out_vis)

    # answers stripped
    exams = list_student_exams(request=None, db=db, user=student)
    target = next(q for q in exams if q.id == q_enrolled.id)
    leaked = any("answer" in q or "correct_answer" in q for q in target.questions)
    check("correct answers stripped for students", not leaked, str(target.questions))

    db.close()
    failed = [c for c in CHECKS if not c[1]]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
