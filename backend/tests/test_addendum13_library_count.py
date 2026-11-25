"""U7 baseline: the real Knowledge Base library must not silently lose documents.

The reporter saw "4 documents" become "3" and nothing failed. These chunk counts
were measured on the live collection on 2026-11-23 and are pinned here: adding
material is fine (>=), losing a document fails the gate.

The second half pins the isolation rule: test fixtures must never appear in the
live collection again (they belong to the tests' own collection).
"""
from collections import Counter
from pathlib import Path

import pytest

LIVE_COLLECTION = "edusense_knowledge"
LIVE_CHROMA_DIR = Path(__file__).resolve().parent.parent / "data" / "chroma"
BASELINE = {
    "ECU-ITAI-3-04.pdf": 129,
    "resource_9": 15,
}
TEST_FIXTURES = {"test_async_guide.pdf", "notes.txt", "test_notes.txt"}


_CACHE: list[dict] | None = None


def _live_metadata():
    """Read the live collection once: a second PersistentClient on the same path
    inside one process raises Chroma's "different settings" error."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    chromadb = pytest.importorskip("chromadb")
    if not (LIVE_CHROMA_DIR / "chroma.sqlite3").exists():
        pytest.skip("live Knowledge Base has not been built on this machine")
    client = chromadb.PersistentClient(path=str(LIVE_CHROMA_DIR))
    names = {c.name if hasattr(c, "name") else str(c) for c in client.list_collections()}
    if LIVE_COLLECTION not in names:
        pytest.skip("live Knowledge Base collection is absent")
    data = client.get_collection(LIVE_COLLECTION).get(include=["metadatas"])
    _CACHE = [m or {} for m in data["metadatas"]]
    return _CACHE


def test_real_documents_are_still_indexed():
    metadatas = _live_metadata()
    counts = Counter(m.get("source_id") for m in metadatas)
    for source, expected in BASELINE.items():
        assert counts.get(source, 0) >= expected, (
            f"{source} lost chunks: {counts.get(source, 0)} indexed, {expected} pinned. "
            f"Live counts: {dict(counts)}"
        )


def test_test_fixtures_are_not_in_the_live_collection():
    metadatas = _live_metadata()
    present = sorted({m.get("source_id") for m in metadatas} & TEST_FIXTURES)
    assert not present, (
        f"test fixtures were indexed into the live library: {present}. "
        "Tests must use the collection from conftest (EDUSENSE_RAG_COLLECTION)."
    )
