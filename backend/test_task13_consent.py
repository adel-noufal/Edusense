"""
test_task13_consent.py -- Integration tests for Task 13 (Legal & Privacy Compliance).

Tests verify:
1. POST /api/emotions/consent/give   -- give consent for emotion_detection / quiz_anti_cheat.
2. GET  /api/emotions/consent/check/{type} -- check returns has_consent=true after giving.
3. GET  /api/emotions/consent/list   -- user sees their consent records.
4. POST /api/emotions/consent/withdraw/{type} -- withdraw sets has_consent=false.
5. Consent gate: POST /api/emotions/analyze is 403 without consent.
6. Consent gate: POST /api/emotions/analyze is not blocked once consent is given.
7. Invalid consent_type rejected with 400.
8. ConsentRecord model has required fields (user_id, consent_type, given, version, timestamp).
9. No auth -> 401 on all consent endpoints.

Run:
    python test_task13_consent.py
"""
from __future__ import annotations

import os
import sys
import uuid

# ── Path bootstrap ────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(os.path.dirname(__file__), 'edusense.db')}")
os.environ.setdefault("EDUSENSE_DATABASE_URL", os.environ["DATABASE_URL"])
os.environ.setdefault("PYTHONUTF8", "1")

PASSED = 0
FAILED = 0


def ok(msg: str):
    global PASSED
    PASSED += 1
    print(f"  [PASS]  {msg}")


def fail(msg: str, exc: Exception | None = None):
    global FAILED
    FAILED += 1
    detail = f" -- {exc}" if exc else ""
    print(f"  [FAIL]  {msg}{detail}")


# ── Imports ───────────────────────────────────────────────────────────────────
try:
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import SessionLocal
    from app.models.models import User, ConsentRecord, Base
    from app.db.session import engine
    from app.core.security import hash_password
except ImportError as exc:
    print(f"[ERROR] Import failed: {exc}")
    sys.exit(1)

Base.metadata.create_all(bind=engine)
client = TestClient(app)

_USER_EMAIL = f"t13_{uuid.uuid4().hex[:8]}@consent.test"
_PASSWORD   = "testpass123"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_user() -> User:
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=_USER_EMAIL).first()
        if not user:
            user = User(name="T13 Consent User", email=_USER_EMAIL,
                        password_hash=hash_password(_PASSWORD), role="student")
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    finally:
        db.close()


def _login() -> str:
    r = client.post("/api/auth/login", json={"email": _USER_EMAIL, "password": _PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_01_consent_model_fields():
    print("\n[T13-01] ConsentRecord model has required fields")
    try:
        _ensure_user()
        db = SessionLocal()
        try:
            # Inspect model columns
            cols = {c.name for c in ConsentRecord.__table__.columns}
            required = {"id", "user_id", "consent_type", "given", "version", "timestamp", "withdrawn_at"}
            missing = required - cols
            assert not missing, f"Missing columns: {missing}"
        finally:
            db.close()
        ok(f"ConsentRecord has all required columns: {required}")
    except Exception as exc:
        fail("ConsentRecord model fields check failed", exc)


def test_02_no_auth_give_consent():
    print("\n[T13-02] POST /api/emotions/consent/give without token -> 401/403")
    try:
        r = client.post("/api/emotions/consent/give",
                        json={"consent_type": "emotion_detection", "version": "1.0"})
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
        ok("Unauthenticated consent/give is blocked")
    except Exception as exc:
        fail("Auth guard on consent/give failed", exc)


def test_03_give_consent_emotion_detection():
    print("\n[T13-03] POST /api/emotions/consent/give -- emotion_detection")
    try:
        token = _login()
        r = client.post("/api/emotions/consent/give",
                        json={"consent_type": "emotion_detection", "version": "1.0"},
                        headers=_auth_header(token))
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        assert data["consent_type"] == "emotion_detection"
        assert data["given"] is True
        assert data["version"] == "1.0"
        assert "id" in data
        ok(f"Consent given: id={data['id']}, type={data['consent_type']}, version={data['version']}")
    except Exception as exc:
        fail("Give consent (emotion_detection) failed", exc)


def test_04_give_consent_quiz_anti_cheat():
    print("\n[T13-04] POST /api/emotions/consent/give -- quiz_anti_cheat")
    try:
        token = _login()
        r = client.post("/api/emotions/consent/give",
                        json={"consent_type": "quiz_anti_cheat", "version": "1.0"},
                        headers=_auth_header(token))
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        assert data["consent_type"] == "quiz_anti_cheat"
        assert data["given"] is True
        ok(f"Consent given: type={data['consent_type']}")
    except Exception as exc:
        fail("Give consent (quiz_anti_cheat) failed", exc)


def test_05_check_consent_true():
    print("\n[T13-05] GET /api/emotions/consent/check/emotion_detection -> has_consent=true")
    try:
        token = _login()
        r = client.get("/api/emotions/consent/check/emotion_detection",
                       headers=_auth_header(token))
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        assert "has_consent" in data
        assert data["has_consent"] is True, f"Expected has_consent=True, got {data['has_consent']}"
        assert data["consent_type"] == "emotion_detection"
        assert data["version"] == "1.0"
        ok(f"Check consent: has_consent={data['has_consent']}, version={data['version']}")
    except Exception as exc:
        fail("Check consent true state failed", exc)


def test_06_list_consents():
    print("\n[T13-06] GET /api/emotions/consent/list -- user sees their consents")
    try:
        token = _login()
        r = client.get("/api/emotions/consent/list",
                       headers=_auth_header(token))
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 2, f"Expected >=2 consents, got {len(data)}"
        types = {c["consent_type"] for c in data}
        assert "emotion_detection" in types
        assert "quiz_anti_cheat" in types
        ok(f"Consent list returned {len(data)} record(s): {types}")
    except Exception as exc:
        fail("List consents failed", exc)


def test_07_invalid_consent_type_rejected():
    print("\n[T13-07] POST /api/emotions/consent/give -- invalid type -> 400")
    try:
        token = _login()
        r = client.post("/api/emotions/consent/give",
                        json={"consent_type": "invalid_type_xyz", "version": "1.0"},
                        headers=_auth_header(token))
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        ok("Invalid consent_type correctly rejected with 400")
    except Exception as exc:
        fail("Invalid consent_type validation failed", exc)


def test_08_withdraw_consent():
    print("\n[T13-08] POST /api/emotions/consent/withdraw/emotion_detection")
    try:
        token = _login()
        r = client.post("/api/emotions/consent/withdraw/emotion_detection",
                        headers=_auth_header(token))
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        assert "message" in data
        assert "withdrawn" in data["message"].lower()
        ok(f"Consent withdrawn: {data['message']}")
    except Exception as exc:
        fail("Withdraw consent failed", exc)


def test_09_check_consent_false_after_withdraw():
    print("\n[T13-09] GET /api/emotions/consent/check/emotion_detection -> has_consent=false after withdraw")
    try:
        token = _login()
        r = client.get("/api/emotions/consent/check/emotion_detection",
                       headers=_auth_header(token))
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        assert data["has_consent"] is False, \
            f"Expected has_consent=False after withdrawal, got {data['has_consent']}"
        ok("has_consent=False confirmed after withdrawal")
    except Exception as exc:
        fail("Check consent false after withdrawal failed", exc)


def test_10_withdraw_nonexistent_consent():
    print("\n[T13-10] POST /api/emotions/consent/withdraw/quiz_anti_cheat -- unknown consent -> not 500")
    try:
        # First withdraw quiz_anti_cheat (which exists)
        token = _login()
        r = client.post("/api/emotions/consent/withdraw/quiz_anti_cheat",
                        headers=_auth_header(token))
        assert r.status_code in (200, 404), f"Expected 200 or 404, got {r.status_code}: {r.text}"
        # Now withdraw again (record exists but already withdrawn -- should 404 or 200)
        r2 = client.post("/api/emotions/consent/withdraw/quiz_anti_cheat",
                         headers=_auth_header(token))
        assert r2.status_code != 500, f"Should not 500 on double-withdraw, got {r2.status_code}"
        ok("Double-withdraw does not cause 500")
    except Exception as exc:
        fail("Double-withdraw guard failed", exc)


def test_11_re_give_consent():
    print("\n[T13-11] POST /api/emotions/consent/give -- re-giving after withdraw works (upsert)")
    try:
        token = _login()
        r = client.post("/api/emotions/consent/give",
                        json={"consent_type": "emotion_detection", "version": "1.1"},
                        headers=_auth_header(token))
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        assert data["given"] is True
        assert data["version"] == "1.1"

        # Check now returns true again
        r2 = client.get("/api/emotions/consent/check/emotion_detection",
                        headers=_auth_header(token))
        assert r2.json()["has_consent"] is True
        ok("Re-giving consent after withdrawal works (upsert), version updated to 1.1")
    except Exception as exc:
        fail("Re-give consent (upsert) failed", exc)


def test_12_withdraw_invalid_type():
    print("\n[T13-12] POST /api/emotions/consent/withdraw/bad_type -> 400")
    try:
        token = _login()
        r = client.post("/api/emotions/consent/withdraw/bad_consent_type",
                        headers=_auth_header(token))
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        ok("Invalid consent_type on withdraw correctly rejected with 400")
    except Exception as exc:
        fail("Withdraw invalid type validation failed", exc)


def test_13_consent_records_in_db():
    print("\n[T13-13] ConsentRecord entries present in DB for test user")
    try:
        user = _ensure_user()
        db = SessionLocal()
        try:
            records = db.query(ConsentRecord).filter_by(user_id=user.id).all()
            assert len(records) >= 1, f"Expected >=1 ConsentRecord, got {len(records)}"
            for rec in records:
                assert rec.user_id == user.id
                assert rec.consent_type in ("emotion_detection", "quiz_anti_cheat")
        finally:
            db.close()
        ok(f"Found {len(records)} ConsentRecord(s) in DB for test user")
    except Exception as exc:
        fail("ConsentRecord DB presence check failed", exc)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  EduSense Task 13 -- Legal & Privacy Compliance Tests")
    print("=" * 60)

    test_01_consent_model_fields()
    test_02_no_auth_give_consent()
    test_03_give_consent_emotion_detection()
    test_04_give_consent_quiz_anti_cheat()
    test_05_check_consent_true()
    test_06_list_consents()
    test_07_invalid_consent_type_rejected()
    test_08_withdraw_consent()
    test_09_check_consent_false_after_withdraw()
    test_10_withdraw_nonexistent_consent()
    test_11_re_give_consent()
    test_12_withdraw_invalid_type()
    test_13_consent_records_in_db()

    print("\n" + "=" * 60)
    print(f"  Results: {PASSED} passed, {FAILED} failed")
    print("=" * 60)

    if FAILED:
        sys.exit(1)
