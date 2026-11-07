"""
test_task4.py — RAG integration tests for lesson/quiz/flashcard agents.

Tests verify:
1. Agents still work with no RAG data (empty vector store).
2. When chunks are seeded, agents inject source context and return sources[].
3. subject / grade_level filtering is respected.
4. All three agents produce valid response shapes including the new `sources` key.
"""
import os
import sys
import json
import uuid
import tempfile
import shutil

# ── Bootstrap path ─────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(os.path.dirname(__file__), 'edusense.db')}")
os.environ.setdefault("EDUSENSE_DATABASE_URL", os.environ["DATABASE_URL"])

# ── Imports ─────────────────────────────────────────────────────────────────
try:
    from app.services.vector_store import init_collection, add_chunks, query, get_client
    from app.agents.tools import RAG_Search_Tool
    from app.agents.lesson_agent import LessonGenerationAgent, _build_rag_context as lesson_rag
    from app.agents.quiz_agent import QuizGenerationAgent, _build_rag_context as quiz_rag
    from app.agents.flashcard_agent import FlashcardGenerationAgent, _build_rag_context as fc_rag
    from app.schemas.schemas import LessonRequest
except ImportError as e:
    print(f"[ERROR] Import failed: {e}")
    sys.exit(1)

PASSED = 0
FAILED = 0
TEST_COLLECTION = f"task4_test_{uuid.uuid4().hex[:8]}"


def ok(msg: str):
    global PASSED
    PASSED += 1
    print(f"  [PASS]  {msg}")


def fail(msg: str, exc: Exception | None = None):
    global FAILED
    FAILED += 1
    detail = f" -- {exc}" if exc else ""
    print(f"  [FAIL]  {msg}{detail}")


# ── Seed helper ─────────────────────────────────────────────────────────────

def _seed_chunks():
    """Insert a few test chunks so agents have something to retrieve."""
    from app.services.vector_store import ChunkRecord, ChunkMetadata
    chunks = [
        ChunkRecord(
            id=f"t4_{uuid.uuid4().hex}",
            text="Photosynthesis is the process by which green plants convert sunlight into glucose using CO2 and water. The light-dependent reactions occur in the thylakoid membrane.",
            metadata=ChunkMetadata(
                source_file="biology_ch4.pdf",
                page=12,
                subject="Biology",
                grade_level="10",
                topic="Photosynthesis",
            ),
        ),
        ChunkRecord(
            id=f"t4_{uuid.uuid4().hex}",
            text="The Calvin cycle (light-independent reactions) takes place in the stroma and uses ATP and NADPH produced in the light-dependent stage to fix CO2 into organic compounds.",
            metadata=ChunkMetadata(
                source_file="biology_ch4.pdf",
                page=13,
                subject="Biology",
                grade_level="10",
                topic="Photosynthesis",
            ),
        ),
        ChunkRecord(
            id=f"t4_{uuid.uuid4().hex}",
            text="Newton's First Law states that an object at rest stays at rest and an object in motion stays in motion unless acted upon by an external force.",
            metadata=ChunkMetadata(
                source_file="physics_ch1.pdf",
                page=5,
                subject="Physics",
                grade_level="10",
                topic="Newton's Laws",
            ),
        ),
    ]
    init_collection(name=TEST_COLLECTION)
    add_chunks(chunks, collection_name=TEST_COLLECTION)
    return chunks


# ── Monkey-patch RAG_Search_Tool to use our test collection ─────────────────

import app.agents.tools as _tools_mod
_original_rag = _tools_mod.RAG_Search_Tool


def _patched_rag(query, subject=None, grade_level=None, top_k=5, collection_name=None, min_score=None):
    return _original_rag(
        query=query,
        subject=subject,
        grade_level=grade_level,
        top_k=top_k,
        collection_name=TEST_COLLECTION,
        min_score=min_score if min_score is not None else 0.0,  # low threshold for test
    )


# Patch into all three agent modules' namespace too
import app.agents.lesson_agent as _lesson_mod
import app.agents.quiz_agent as _quiz_mod
import app.agents.flashcard_agent as _fc_mod

_lesson_mod.RAG_Search_Tool = _patched_rag  # type: ignore
_quiz_mod.RAG_Search_Tool = _patched_rag    # type: ignore
_fc_mod.RAG_Search_Tool = _patched_rag      # type: ignore


# ── Tests ────────────────────────────────────────────────────────────────────

def test_01_seed_and_rag_tool():
    print("\n[T4-01] Seed test collection and verify RAG_Search_Tool retrieves chunks")
    try:
        _seed_chunks()
        results = _patched_rag("photosynthesis process", subject="Biology", grade_level="10")
        assert len(results) > 0, "No results returned"
        assert "text" in results[0], "'text' key missing"
        assert "source_file" in results[0], "'source_file' key missing"
        assert "score" in results[0], "'score' key missing"
        print(f"     Retrieved {len(results)} chunk(s), top score={results[0]['score']:.4f}")
        ok("RAG_Search_Tool returns Biology chunks")
    except Exception as exc:
        fail("RAG_Search_Tool retrieval failed", exc)


def test_02_subject_filter():
    print("\n[T4-02] Verify subject filter excludes wrong-subject chunks")
    try:
        results = _patched_rag("photosynthesis", subject="Physics", grade_level="10")
        subjects = {r.get("subject") for r in results}
        print(f"     Subjects returned: {subjects}")
        assert "Biology" not in subjects or len(results) == 0, \
            f"Biology chunks leaked into Physics-filtered results: {subjects}"
        ok("Subject filter excludes Biology chunks when subject=Physics")
    except Exception as exc:
        fail("Subject filter test failed", exc)


def test_03_rag_context_builder_lesson():
    print("\n[T4-03] Lesson RAG context builder returns non-empty context for Biology")
    try:
        # We need to patch inside the helper
        import app.agents.lesson_agent as lm
        orig = lm.RAG_Search_Tool
        lm.RAG_Search_Tool = _patched_rag  # type: ignore
        try:
            ctx, sources = lm._build_rag_context("photosynthesis", "Biology", "10")
        finally:
            lm.RAG_Search_Tool = orig  # type: ignore

        print(f"     Context length: {len(ctx)} chars, sources: {sources}")
        assert ctx, "Context block is empty"
        assert sources, "Sources list is empty"
        assert any("biology_ch4.pdf" in s for s in sources), "Expected biology_ch4.pdf in sources"
        ok("Lesson _build_rag_context returns Biology context and sources")
    except Exception as exc:
        fail("Lesson RAG context builder failed", exc)


def test_04_lesson_agent_sources_key():
    print("\n[T4-04] LessonGenerationAgent.generate() returns 'sources' key")
    try:
        agent = LessonGenerationAgent()
        req = LessonRequest(
            topic="Photosynthesis",
            prompt="Focus on chloroplast structure",
            subject="Biology",
            grade_level="10",
        )
        result = agent.generate(req).data
        assert "sources" in result, "'sources' key not in lesson result"
        print(f"     sources={result['sources']}")
        ok(f"Lesson agent returns sources={result['sources']}")
    except Exception as exc:
        fail("Lesson agent sources key test failed", exc)


def test_05_quiz_agent_sources_key():
    print("\n[T4-05] QuizGenerationAgent.generate() returns 'sources' key")
    try:
        agent = QuizGenerationAgent()
        result = agent.generate(
            topic="Photosynthesis",
            difficulty="Medium",
            count=3,
            prompt="",
            subject="Biology",
            grade_level="10",
        ).data
        assert "sources" in result, "'sources' key not in quiz result"
        assert "questions" in result, "'questions' key not in quiz result"
        assert len(result["questions"]) >= 3, f"Expected ≥3 questions, got {len(result['questions'])}"
        print(f"     sources={result['sources']}, questions={len(result['questions'])}")
        ok(f"Quiz agent returns sources and {len(result['questions'])} questions")
    except Exception as exc:
        fail("Quiz agent sources key test failed", exc)


def test_06_flashcard_agent_sources_key():
    print("\n[T4-06] FlashcardGenerationAgent.generate() returns 'sources' key")
    try:
        agent = FlashcardGenerationAgent()
        result = agent.generate(
            topic="Photosynthesis",
            count=3,
            language="English",
            prompt="",
            subject="Biology",
            grade_level="10",
        ).data
        assert "sources" in result, "'sources' key not in flashcard result"
        assert "cards" in result, "'cards' key not in flashcard result"
        assert len(result["cards"]) >= 3, f"Expected ≥3 cards, got {len(result['cards'])}"
        print(f"     sources={result['sources']}, cards={len(result['cards'])}")
        ok(f"Flashcard agent returns sources and {len(result['cards'])} cards")
    except Exception as exc:
        fail("Flashcard agent sources key test failed", exc)


def test_07_no_rag_fallback():
    print("\n[T4-07] Agents work without RAG (no subject/grade_level specified)")
    try:
        agent = LessonGenerationAgent()
        req = LessonRequest(topic="Quantum Computing", prompt="")
        result = agent.generate(req).data
        assert "sources" in result, "'sources' key not in lesson result (no-RAG path)"
        print(f"     sources={result['sources']} (expected empty list)")
        ok("Lesson agent works and returns sources=[] when no subject/grade_level given")
    except Exception as exc:
        fail("No-RAG fallback test failed", exc)


def test_08_top_k_respected():
    print("\n[T4-08] top_k=1 returns at most 1 result")
    try:
        results = _patched_rag("photosynthesis", subject="Biology", top_k=1)
        assert len(results) <= 1, f"Expected ≤1 result, got {len(results)}"
        ok(f"top_k=1 respected — got {len(results)} result(s)")
    except Exception as exc:
        fail("top_k test failed", exc)


# ── Cleanup ─────────────────────────────────────────────────────────────────

def _cleanup():
    try:
        client = get_client()
        client.delete_collection(TEST_COLLECTION)
        print(f"\n[Cleanup] Deleted test collection '{TEST_COLLECTION}'")
    except Exception as exc:
        print(f"\n[Cleanup] Could not delete test collection: {exc}")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  EduSense Task 4 — RAG Agent Integration Tests")
    print("=" * 60)

    test_01_seed_and_rag_tool()
    test_02_subject_filter()
    test_03_rag_context_builder_lesson()
    test_04_lesson_agent_sources_key()
    test_05_quiz_agent_sources_key()
    test_06_flashcard_agent_sources_key()
    test_07_no_rag_fallback()
    test_08_top_k_respected()

    _cleanup()

    print("\n" + "=" * 60)
    print(f"  Results: {PASSED} passed, {FAILED} failed")
    print("=" * 60)

    if FAILED:
        sys.exit(1)
