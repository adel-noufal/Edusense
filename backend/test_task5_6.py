"""
test_task5_6.py  — Tests for Task 5 (RAG Q&A) and Task 6 (KB Suggestions).

Tests run against a FastAPI TestClient with an in-memory SQLite DB.
ChromaDB is seeded with small Biology and Physics chunks so we have
real embeddings without needing a real PDF file.

Run:
    python test_task5_6.py
"""
from __future__ import annotations

import os
import sys
import uuid

# ── path bootstrap ───────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DATABASE_URL",         f"sqlite:///{os.path.join(os.path.dirname(__file__), 'edusense.db')}")
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
    from app.models.models import User
    from app.core.security import hash_password
    from app.services.vector_store import ChunkRecord, ChunkMetadata, init_collection, add_chunks, get_client
    from app.services.rag_qa import answer_question, suggest_chunks
except ImportError as exc:
    print(f"[ERROR] Import failed: {exc}")
    sys.exit(1)

client = TestClient(app)

# ── Seed ChromaDB collection ─────────────────────────────────────────────────
TEST_COL = f"t56_{uuid.uuid4().hex[:8]}"

_BIO_CHUNKS = [
    ChunkRecord(
        id=f"t56_{uuid.uuid4().hex}",
        text="Photosynthesis converts light energy into chemical energy stored as glucose. "
             "Chlorophyll in the chloroplast absorbs sunlight during the light-dependent reactions.",
        metadata=ChunkMetadata(source_file="bio_ch4.pdf", page=12,
                               subject="Biology", grade_level="10", topic="Photosynthesis"),
    ),
    ChunkRecord(
        id=f"t56_{uuid.uuid4().hex}",
        text="The Calvin cycle fixes atmospheric CO2 into organic molecules using ATP and NADPH "
             "produced during the light reactions. It takes place in the stroma of the chloroplast.",
        metadata=ChunkMetadata(source_file="bio_ch4.pdf", page=13,
                               subject="Biology", grade_level="10", topic="Photosynthesis"),
    ),
    ChunkRecord(
        id=f"t56_{uuid.uuid4().hex}",
        text="Newton's Second Law: F = ma. The net force on an object equals its mass "
             "multiplied by its acceleration.",
        metadata=ChunkMetadata(source_file="phy_ch1.pdf", page=7,
                               subject="Physics", grade_level="10", topic="Newton Laws"),
    ),
]

def _seed():
    init_collection(name=TEST_COL)
    add_chunks(_BIO_CHUNKS, collection_name=TEST_COL)


# ── Monkey-patch RAG_Search_Tool to use TEST_COL with a low min_score ────────
import app.agents.tools as _tools_mod
import app.services.rag_qa as _qa_mod

_orig_rag = _tools_mod.RAG_Search_Tool

def _patched_rag(query, subject=None, grade_level=None, top_k=5,
                 collection_name=None, min_score=None):
    return _orig_rag(query=query, subject=subject, grade_level=grade_level,
                     top_k=top_k, collection_name=TEST_COL,
                     min_score=0.0)   # low threshold so test chunks always appear

_tools_mod.RAG_Search_Tool = _patched_rag   # type: ignore
_qa_mod.RAG_Search_Tool    = _patched_rag   # type: ignore


# ── Auth helper ───────────────────────────────────────────────────────────────
_TEST_EMAIL    = f"t56_{uuid.uuid4().hex[:6]}@test.com"
_TEST_EMAIL_S  = f"t56_s_{uuid.uuid4().hex[:6]}@test.com"
_TEST_PASSWORD = "testpass123"


def _ensure_users():
    """Create one instructor and one student for auth tests."""
    db = SessionLocal()
    try:
        for email, role in [(_TEST_EMAIL, "instructor"), (_TEST_EMAIL_S, "student")]:
            if not db.query(User).filter_by(email=email).first():
                db.add(User(name="T56 User", email=email,
                            password_hash=hash_password(_TEST_PASSWORD), role=role))
        db.commit()
    finally:
        db.close()


def _login(email: str) -> str:
    r = client.post("/api/auth/login",
                    json={"email": email, "password": _TEST_PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["access_token"]


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_01_service_answer_question_with_chunks():
    print("\n[T5-01] answer_question() returns answer + sources when chunks exist")
    try:
        result = answer_question("What is photosynthesis?", subject="Biology", grade_level="10")
        assert "answer"  in result, "'answer' key missing"
        assert "sources" in result, "'sources' key missing"
        assert result["chunks_used"] > 0, "No chunks used"
        print(f"     chunks_used={result['chunks_used']}, sources={[s['source_file'] for s in result['sources']]}")
        print(f"     answer (first 120 chars): {result['answer'][:120]}")
        ok("answer_question() returns answer and populated sources")
    except Exception as exc:
        fail("answer_question() with chunks failed", exc)


def test_02_service_answer_question_no_chunks():
    print("\n[T5-02] answer_question() returns polite message when no chunks found")
    try:
        # Very specific query that won't match anything in our tiny collection
        result = answer_question(
            "Explain the Krebs cycle step by step",
            subject="Chemistry",  # not indexed
            grade_level="12",
            min_score=0.99,       # impossibly high threshold
        )
        assert result["chunks_used"] == 0,  f"Expected 0 chunks, got {result['chunks_used']}"
        assert result["answer"],            "Answer string is empty"
        print(f"     answer (fallback): {result['answer'][:100]}")
        ok("answer_question() gives polite fallback when no chunks match")
    except Exception as exc:
        fail("answer_question() no-chunks fallback failed", exc)


def test_03_service_suggest_chunks():
    print("\n[T5-03] suggest_chunks() returns ranked chunks for topic")
    try:
        result = suggest_chunks("photosynthesis Calvin cycle", subject="Biology", grade_level="10", top_k=3)
        assert "chunks" in result, "'chunks' key missing"
        assert result["total"] > 0, "No chunks returned"
        assert all("score" in c for c in result["chunks"]), "score key missing from chunk"
        print(f"     total={result['total']}, top score={result['chunks'][0]['score']:.4f}")
        ok(f"suggest_chunks() returned {result['total']} chunk(s)")
    except Exception as exc:
        fail("suggest_chunks() failed", exc)


def test_04_api_ask_student_auth():
    print("\n[T5-04] POST /api/rag/ask returns 200 for authenticated student")
    try:
        token = _login(_TEST_EMAIL_S)
        r = client.post("/api/rag/ask",
                        json={"question": "What is photosynthesis?",
                              "subject": "Biology", "grade_level": "10"},
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"Status {r.status_code}: {r.text[:200]}"
        data = r.json()
        assert "answer"  in data, "'answer' key missing"
        assert "sources" in data, "'sources' key missing"
        print(f"     chunks_used={data.get('chunks_used')}, answer[:80]={data['answer'][:80]}")
        ok("POST /api/rag/ask returns answer for student")
    except Exception as exc:
        fail("POST /api/rag/ask student auth failed", exc)


def test_05_api_ask_no_auth():
    print("\n[T5-05] POST /api/rag/ask returns 401 when unauthenticated")
    try:
        r = client.post("/api/rag/ask",
                        json={"question": "What is the Calvin cycle?"})
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"
        ok("POST /api/rag/ask blocks unauthenticated requests")
    except Exception as exc:
        fail("POST /api/rag/ask auth check failed", exc)


def test_06_api_ask_empty_question():
    print("\n[T5-06] POST /api/rag/ask returns 422 for empty question")
    try:
        token = _login(_TEST_EMAIL_S)
        r = client.post("/api/rag/ask",
                        json={"question": "   "},
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        ok("POST /api/rag/ask returns 422 for empty question")
    except Exception as exc:
        fail("Empty question validation failed", exc)


def test_07_api_suggest_instructor():
    print("\n[T5-07] GET /api/rag/suggest returns chunks for instructor")
    try:
        token = _login(_TEST_EMAIL)
        r = client.get("/api/rag/suggest",
                       params={"topic": "photosynthesis", "subject": "Biology",
                               "grade_level": "10", "top_k": 5},
                       headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"Status {r.status_code}: {r.text[:200]}"
        data = r.json()
        assert "chunks" in data, "'chunks' key missing"
        assert "total"  in data, "'total' key missing"
        assert data["total"] > 0, "No chunks returned for Biology/photosynthesis"
        print(f"     total={data['total']}, top_score={data['chunks'][0]['score']:.4f}")
        ok(f"GET /api/rag/suggest returned {data['total']} chunk(s)")
    except Exception as exc:
        fail("GET /api/rag/suggest instructor failed", exc)


def test_08_api_suggest_student_forbidden():
    print("\n[T5-08] GET /api/rag/suggest returns 403 for student role")
    try:
        token = _login(_TEST_EMAIL_S)
        r = client.get("/api/rag/suggest",
                       params={"topic": "photosynthesis"},
                       headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"
        ok("GET /api/rag/suggest is blocked for students (instructor-only)")
    except Exception as exc:
        fail("GET /api/rag/suggest student access check failed", exc)


def test_09_suggest_subject_filter():
    print("\n[T5-09] GET /api/rag/suggest respects subject filter")
    try:
        token = _login(_TEST_EMAIL)
        r = client.get("/api/rag/suggest",
                       params={"topic": "Newton force", "subject": "Biology",
                               "grade_level": "10", "top_k": 5},
                       headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"Status {r.status_code}"
        data = r.json()
        # Physics chunks should NOT appear when subject=Biology
        subjects = {c.get("subject") for c in data["chunks"]}
        print(f"     subjects in results: {subjects}")
        assert "Physics" not in subjects or data["total"] == 0, \
            f"Physics chunks leaked through Biology filter: {subjects}"
        ok("Subject filter works on /api/rag/suggest")
    except Exception as exc:
        fail("Subject filter on /api/rag/suggest failed", exc)


def test_10_api_ask_top_k_respected():
    print("\n[T5-10] POST /api/rag/ask respects top_k=1")
    try:
        token = _login(_TEST_EMAIL_S)
        r = client.post("/api/rag/ask",
                        json={"question": "photosynthesis", "subject": "Biology",
                              "grade_level": "10", "top_k": 1},
                        headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, f"Status {r.status_code}: {r.text}"
        data = r.json()
        assert data["chunks_used"] <= 1, f"Expected <=1 chunk, got {data['chunks_used']}"
        ok(f"top_k=1 respected on /api/rag/ask, chunks_used={data['chunks_used']}")
    except Exception as exc:
        fail("/api/rag/ask top_k test failed", exc)


# ── Cleanup ───────────────────────────────────────────────────────────────────

def _cleanup():
    try:
        get_client().delete_collection(TEST_COL)
        print(f"\n[Cleanup] Deleted test collection '{TEST_COL}'")
    except Exception as exc:
        print(f"\n[Cleanup] Could not delete test collection: {exc}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  EduSense Task 5 & 6 -- RAG Q&A and KB Suggestions")
    print("=" * 60)

    _seed()
    _ensure_users()

    test_01_service_answer_question_with_chunks()
    test_02_service_answer_question_no_chunks()
    test_03_service_suggest_chunks()
    test_04_api_ask_student_auth()
    test_05_api_ask_no_auth()
    test_06_api_ask_empty_question()
    test_07_api_suggest_instructor()
    test_08_api_suggest_student_forbidden()
    test_09_suggest_subject_filter()
    test_10_api_ask_top_k_respected()

    _cleanup()

    print("\n" + "=" * 60)
    print(f"  Results: {PASSED} passed, {FAILED} failed")
    print("=" * 60)

    if FAILED:
        sys.exit(1)
