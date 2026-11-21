"""
B2 tests — Run Feedback Loop silent failure:
- selected session_ids are honored (not silently widened to 'all')
- per-session data sufficiency is reported in the job result
- insufficient sessions produce an explicit message, never a blank panel
- sessions not owned by the instructor / not ended are excluded
"""
import os
import sys
import uuid
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(os.path.dirname(__file__), 'edusense.db')}")
os.environ.setdefault("EDUSENSE_DATABASE_URL", os.environ["DATABASE_URL"])

from app.db.session import SessionLocal
from app.models.models import Session as ClassSession, User
from app.core.security import hash_password
from app.api import ai as ai_api
from app.api.ai import _resolve_recommendation_sessions, _run_recommendations_bg, _jobs, _jobs_lock

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))
    print(("PASS" if cond else "FAIL"), name, detail if not cond else "")


def _mk_instructor(db, tag):
    u = User(name=f"B2 {tag}", email=f"b2_{tag}_{uuid.uuid4().hex[:6]}@t.com",
             password_hash=hash_password("pw"), role="instructor")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _mk_session(db, instructor_id, title, status="ended"):
    s = ClassSession(instructor_id=instructor_id, title=title, description="t",
                     date=date.today(), start_time=time(10, 0), duration=30, status=status)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _fake_agent(data):
    return SimpleNamespace(data=data)


def main():
    db = SessionLocal()
    inst = _mk_instructor(db, "inst")
    other = _mk_instructor(db, "other")
    s1 = _mk_session(db, inst.id, "B2 Session One")
    s2 = _mk_session(db, inst.id, "B2 Session Two")
    s_live = _mk_session(db, inst.id, "B2 Live", status="live")
    s_other = _mk_session(db, other.id, "B2 Foreign")

    # 1. resolve: ended + owned only
    all_ended = _resolve_recommendation_sessions(db, inst.id, "all", None)
    ids = {s.id for s in all_ended}
    check("resolve returns only instructor's ended sessions",
          ids == {s1.id, s2.id}, str(ids))

    # 2. resolve honors explicit session_ids
    picked = _resolve_recommendation_sessions(db, inst.id, "all", [s1.id, s_live.id, s_other.id])
    check("session_ids narrows selection and drops non-ended/foreign",
          [s.id for s in picked] == [s1.id], str([s.id for s in picked]))

    # 3. bg run: sufficiency payload + only selected sessions analyzed
    analyzed = []

    def fake_dist(db_, sid):
        analyzed.append(sid)
        return _fake_agent({"distribution": {"happy": 50.0, "neutral": 50.0}})

    fake_engagement = _fake_agent({"attention_timeline": []})
    fake_rec = _fake_agent({"recommendations": ["Keep sessions shorter."], "insufficient_data": False})

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {"status": "pending", "result": None, "error": None, "progress": 0, "message": ""}

    with patch.object(ai_api.workflow.emotions, "distributions", side_effect=fake_dist), \
         patch.object(ai_api.workflow.engagement, "calculate", return_value=fake_engagement), \
         patch.object(ai_api.workflow.recommendations, "recommend", return_value=fake_rec), \
         patch("app.services.report_data.assess_session_data",
               return_value={"sufficient": False, "missing": ["emotion_samples"],
                             "checks": {}, "emotion_samples": 0, "participants": 0,
                             "attended_minutes": 0, "raw_attended_minutes": 0,
                             "duration_capped": False, "cap_minutes": 720.0}):
        _run_recommendations_bg(job_id, "all", [s1.id, s2.id], inst.id)

    with _jobs_lock:
        job = dict(_jobs[job_id])

    check("job finished done", job["status"] == "done", str(job.get("error")))
    result = job.get("result") or {}
    recs = result.get("recommendations", {})
    check("only selected sessions analyzed", sorted(analyzed) == sorted([s1.id, s2.id]),
          str(analyzed))
    check("recommendations list populated", len(recs.get("recommendations", [])) >= 1)
    check("insufficient_data flagged", recs.get("insufficient_data") is True)
    check("per-session insufficiency detail present",
          len(recs.get("insufficient_sessions", [])) == 2
          and all("message" in s for s in recs["insufficient_sessions"]),
          str(recs.get("insufficient_sessions")))
    check("sufficient/total counts present",
          recs.get("sufficient_sessions") == 0 and recs.get("total_sessions") == 2)

    # 4. empty selection resolves to no sessions -> typed error, not silent
    job_id2 = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id2] = {"status": "pending", "result": None, "error": None, "progress": 0, "message": ""}
    with patch.object(ai_api.workflow.emotions, "distributions", return_value=fake_dist(db, 0)):
        _run_recommendations_bg(job_id2, "all", [999999], inst.id)
    with _jobs_lock:
        job2 = dict(_jobs[job_id2])
    check("no matching sessions -> error state", job2["status"] == "error"
          and "No ended sessions" in (job2.get("error") or ""), str(job2.get("error")))

    db.close()
    failed = [c for c in CHECKS if not c[1]]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
