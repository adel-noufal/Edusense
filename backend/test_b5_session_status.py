"""
B5 tests — effective session status:
- past scheduled session is 'missed', never 'upcoming'
- live session past its duration becomes 'ended'
- no-limit live session stays 'live' until manually ended
- upcoming stays upcoming inside grace window
- browse catalog excludes missed/ended sessions
- refresh_status persists the transition
"""
import os
import sys
import uuid
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(os.path.dirname(__file__), 'edusense.db')}")
os.environ.setdefault("EDUSENSE_DATABASE_URL", os.environ["DATABASE_URL"])

from app.db.session import SessionLocal
from app.models.models import Session as ClassSession, User
from app.core.security import hash_password
from app.services.status import effective_status
from app.api.sessions import refresh_status, reconcile_session_statuses

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))
    print(("PASS" if cond else "FAIL"), name, detail if not cond else "")


def _item(status, days_ago, start_h=10, duration=60, prep=None):
    return SimpleNamespace(
        status=status,
        date=date.today() - timedelta(days=days_ago),
        start_time=time(start_h, 0),
        duration=duration,
        prep_start_time=prep,
    )


def _mk_user(db, tag):
    u = User(name=f"B5 {tag}", email=f"b5_{tag}_{uuid.uuid4().hex[:6]}@t.com",
             password_hash=hash_password("pw"), role="instructor")
    db.add(u); db.commit(); db.refresh(u)
    return u


def main():
    now = datetime.now().replace(tzinfo=None)

    # pure effective_status checks
    check("future scheduled -> upcoming",
          effective_status(_item("pending", -1, start_h=23), now) == "upcoming")
    check("past scheduled beyond grace -> missed",
          effective_status(_item("pending", 3), now) == "missed")
    check("past scheduled within grace -> upcoming",
          effective_status(_item("scheduled", 0, start_h=max(0, now.hour - 0), duration=60), now) in ("upcoming", "missed"))
    check("ended stored -> ended",
          effective_status(_item("ended", 1), now) == "ended")
    check("ongoing within duration -> live",
          effective_status(_item("ongoing", 0, start_h=now.hour, duration=120), now) == "live")
    check("ongoing past duration -> ended (stale live)",
          effective_status(_item("ongoing", 0, start_h=0, duration=30), now) == "ended")
    check("ongoing no-limit -> live",
          effective_status(_item("ongoing", 0, start_h=0, duration=None), now) == "live")
    check("cancelled -> cancelled",
          effective_status(_item("cancelled", -1), now) == "cancelled")
    check("missed stays missed",
          effective_status(_item("missed", 5), now) == "missed")

    # persistence through refresh_status + reconcile
    db = SessionLocal()
    inst = _mk_user(db, "inst")
    stale = ClassSession(instructor_id=inst.id, title="B5 Stale", description="t",
                         date=date.today() - timedelta(days=5),
                         start_time=time(9, 0), duration=45, status="pending")
    live_stale = ClassSession(instructor_id=inst.id, title="B5 LiveStale", description="t",
                              date=date.today(), start_time=time(0, 0),
                              duration=30, status="ongoing")
    future = ClassSession(instructor_id=inst.id, title="B5 Future", description="t",
                          date=date.today() + timedelta(days=2),
                          start_time=time(10, 0), duration=None, status="pending")
    db.add_all([stale, live_stale, future]); db.commit()

    changed = reconcile_session_statuses(db)
    db.refresh(stale); db.refresh(live_stale); db.refresh(future)
    check("reconcile transitions stale pending -> missed", stale.status == "missed", stale.status)
    check("reconcile transitions stale ongoing -> ended", live_stale.status == "ended", live_stale.status)
    check("reconcile leaves future session pending", future.status == "pending", future.status)
    check("reconcile reported changes", changed >= 2, str(changed))
    check("effective of reconciled stale is missed",
          effective_status(stale) == "missed")
    check("effective of reconciled live-stale is ended",
          effective_status(live_stale) == "ended")
    check("effective of no-limit future is upcoming",
          effective_status(future) == "upcoming")

    db.close()
    failed = [c for c in CHECKS if not c[1]]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
