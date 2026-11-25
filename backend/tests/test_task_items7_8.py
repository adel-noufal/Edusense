"""
Items 7+8 tests:
- Item 7: session duration optional (None = no limit); SessionIn validation;
  session_status treats None as unbounded "ongoing".
- Item 8: KB chat history — persistence, list/search, rename, delete,
  user-scoped isolation (another instructor gets 404).
"""
import os
import sys
import uuid
from datetime import date, time, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(__file__)), 'edusense.db')}")
os.environ.setdefault("EDUSENSE_DATABASE_URL", os.environ["DATABASE_URL"])

from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.models.models import User, Session as ClassSession, ChatMessage
from app.schemas.schemas import SessionIn
from app.services.status import session_status
from app.core.security import hash_password
from pydantic import ValidationError

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


def _mk_instructor(db, suffix):
    email = f"kb-inst-{suffix}@test.local"
    u = db.query(User).filter_by(email=email).first()
    if not u:
        u = User(name="KB Inst", email=email, password_hash=hash_password(_PASSWORD), role="instructor")
        db.add(u); db.commit(); db.refresh(u)
    return u


def main():
    # ── Item 7: optional session duration ──────────────────────────────
    print("Item 7 — optional session duration")
    s = SessionIn(title="No Limit", date=date.today(), start_time=time(10, 0))
    check("SessionIn duration omitted -> None", s.duration is None)
    s2 = SessionIn(title="Limited", date=date.today(), start_time=time(10, 0), duration=90)
    check("SessionIn duration=90 ok", s2.duration == 90)
    for bad in (0, -5):
        try:
            SessionIn(title="Bad", date=date.today(), start_time=time(10, 0), duration=bad)
            check(f"SessionIn duration={bad} rejected", False)
        except ValidationError:
            check(f"SessionIn duration={bad} rejected", True)

    # status: None duration -> ongoing forever after start
    past = date.today() - timedelta(days=1)
    check("status None -> ongoing (started yesterday)", session_status(past, time(9, 0), None) == "ongoing")
    check("status 60min -> ended", session_status(past, time(9, 0), 60) == "ended")
    check("status future -> pending", session_status(date.today() + timedelta(days=1), time(9, 0), None) == "pending")

    db = SessionLocal()
    created_sessions = []
    try:
        suffix = uuid.uuid4().hex[:8]
        inst = _mk_instructor(db, suffix)
        inst_h = login(inst.email)

        # API: create session with no duration
        r = client.post("/api/sessions", json={
            "title": "Unlimited Session", "description": "t",
            "date": str(date.today()), "start_time": "10:00",
        }, headers=inst_h)
        check("POST /sessions no duration -> 200", r.status_code == 200, r.text[:120])
        if r.status_code == 200:
            sid = r.json().get("id")
            created_sessions.append(sid)
            check("stored duration is None", r.json().get("duration") is None, str(r.json().get("duration")))
            row = db.query(ClassSession).filter_by(id=sid).first()
            check("DB duration NULL", row is not None and row.duration is None)

        # API: absurdly large duration allowed (no arbitrary cap)
        r2 = client.post("/api/sessions", json={
            "title": "3-Day Session", "description": "t",
            "date": str(date.today()), "start_time": "10:00", "duration": 4320,
        }, headers=inst_h)
        check("POST /sessions duration=4320 accepted", r2.status_code == 200, r2.text[:120])
        if r2.status_code == 200:
            created_sessions.append(r2.json().get("id"))

        # ── Item 8: KB conversation persistence + isolation ────────────
        print("Item 8 — KB chat history")
        inst2 = _mk_instructor(db, suffix + "b")
        h1, h2 = inst_h, login(inst2.email)

        # Ask a question -> persists KB conversation
        r = client.post("/api/rag/ask", json={"question": "What is the capital of France?", "persist": True}, headers=h1)
        check("POST /rag/ask -> 200", r.status_code == 200, r.text[:120])
        conv_id = r.json().get("conversation_id", "") if r.status_code == 200 else ""
        check("conversation_id has kb: prefix", conv_id.startswith("kb:"), conv_id[:20])

        # Second turn reuses conversation
        r = client.post("/api/rag/ask", json={
            "question": "And what about Germany?",
            "conversation_id": conv_id,
        }, headers=h1)
        check("follow-up in same conversation -> 200", r.status_code == 200, r.text[:120])

        # List shows it with auto title
        r = client.get("/api/rag/chat/conversations", headers=h1)
        check("list conversations -> 200", r.status_code == 200)
        convs = r.json() if r.status_code == 200 else []
        mine = [c for c in convs if c["conversation_id"] == conv_id]
        check("conversation listed", len(mine) == 1, f"{len(convs)} total")
        check("auto title from first message", mine and "capital of France" in mine[0]["title"], mine[0]["title"][:60] if mine else "")

        # Get full history
        r = client.get(f"/api/rag/chat/conversations/{conv_id}", headers=h1)
        check("get conversation -> 200", r.status_code == 200)
        msgs = r.json().get("messages", []) if r.status_code == 200 else []
        roles = [m["role"] for m in msgs]
        check("history has user+assistant turns", roles.count("user") == 2 and roles.count("assistant") == 2, str(roles))

        # Search
        r = client.get("/api/rag/chat/conversations?q=capital", headers=h1)
        hits = [c for c in (r.json() if r.status_code == 200 else []) if c["conversation_id"] == conv_id]
        check("search q=capital finds chat", len(hits) == 1)

        # Rename
        r = client.patch(f"/api/rag/chat/conversations/{conv_id}", json={"title": "Geography chat"}, headers=h1)
        check("rename -> 200", r.status_code == 200, r.text[:100])
        r = client.get("/api/rag/chat/conversations", headers=h1)
        renamed = [c for c in (r.json() if r.status_code == 200 else []) if c["conversation_id"] == conv_id]
        check("renamed title listed", renamed and renamed[0]["title"] == "Geography chat" and renamed[0]["is_renamed"], renamed[0]["title"] if renamed else "")

        # Isolation: second instructor cannot see/get/delete it
        r = client.get("/api/rag/chat/conversations", headers=h2)
        other = [c for c in (r.json() if r.status_code == 200 else []) if c["conversation_id"] == conv_id]
        check("other instructor list excludes chat", len(other) == 0)
        r = client.get(f"/api/rag/chat/conversations/{conv_id}", headers=h2)
        check("other instructor get -> 404", r.status_code == 404, str(r.status_code))
        r = client.patch(f"/api/rag/chat/conversations/{conv_id}", json={"title": "hijack"}, headers=h2)
        check("other instructor rename -> 404", r.status_code == 404)
        r = client.delete(f"/api/rag/chat/conversations/{conv_id}", headers=h2)
        check("other instructor delete -> 404", r.status_code == 404)
        r = client.get(f"/api/rag/chat/conversations/{conv_id}", headers=h1)
        check("chat still exists after foreign delete attempt", r.status_code == 200)

        # Student role rejected
        stu_email = f"kb-stu-{suffix}@test.local"
        stu = db.query(User).filter_by(email=stu_email).first()
        if not stu:
            stu = User(name="KB Stu", email=stu_email, password_hash=hash_password(_PASSWORD), role="student")
            db.add(stu); db.commit()
        stu_h = login(stu_email)
        r = client.get("/api/rag/chat/conversations", headers=stu_h)
        check("student list -> 403", r.status_code == 403, str(r.status_code))

        # Delete own conversation
        r = client.delete(f"/api/rag/chat/conversations/{conv_id}", headers=h1)
        check("delete own -> 200", r.status_code == 200)
        r = client.get(f"/api/rag/chat/conversations/{conv_id}", headers=h1)
        check("deleted chat -> 404", r.status_code == 404)

    finally:
        for sid in created_sessions:
            db.query(ChatMessage).filter(ChatMessage.conversation_id.like("kb:%")).delete()
        for s in db.query(ClassSession).filter(ClassSession.id.in_(created_sessions)).all():
            db.delete(s)
        db.commit()
        db.close()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    if passed != len(RESULTS):
        sys.exit(1)
    print("ALL ITEM 7+8 CHECKS PASSED")


if __name__ == "__main__":
    main()
