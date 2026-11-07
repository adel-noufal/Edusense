#!/usr/bin/env python
"""
Task 4 Test: Verify RAG verification badges work correctly.

Tests:
1. Good RAG match -> sources populated, unverified=False
2. No RAG match -> sources empty, unverified=True
"""
import os
import sys
import tempfile
import shutil

# Ensure backend is in path
backend_dir = os.path.join(os.path.dirname(__file__), "backend")
sys.path.insert(0, backend_dir)

# Clear ChromaDB before test
chroma_dir = os.path.join(backend_dir, "data", "chroma")
if os.path.exists(chroma_dir):
    shutil.rmtree(chroma_dir)
os.makedirs(chroma_dir, exist_ok=True)

from app.agents.lesson_agent import LessonGenerationAgent
from app.agents.quiz_agent import QuizGenerationAgent
from app.agents.flashcard_agent import FlashcardGenerationAgent
from app.services.ingestion import process_and_ingest_document

# Mock request objects
class MockLessonRequest:
    def __init__(self, topic, prompt="", language="English", teaching_style="Interactive", duration=5, additional_notes="", session_id=None, source_session_id=None, subject=None, grade_level=None):
        self.topic = topic
        self.prompt = prompt
        self.language = language
        self.teaching_style = teaching_style
        self.duration = duration
        self.additional_notes = additional_notes
        self.session_id = session_id
        self.source_session_id = source_session_id
        self.subject = subject
        self.grade_level = grade_level


def test_rag_verified_lesson():
    """Test lesson generation with good RAG match returns sources and unverified=False"""
    # First ingest a document about "Neural Networks"
    test_content = b"Neural networks are computing systems inspired by biological neural networks. They consist of layers of interconnected nodes called neurons. Each connection has a weight that adjusts during learning. Backpropagation is the primary algorithm for training neural networks by computing gradients."

    ingest_result = process_and_ingest_document(
        file_bytes=test_content,
        filename="neural_networks.txt",
        subject="Computer Science",
        grade_level="University",
        topic="Neural Networks",
        source_id="test_nn_source"
    )
    print(f"Ingested: {ingest_result['chunk_count']} chunks")

    # Now generate a lesson on the same topic
    agent = LessonGenerationAgent()
    request = MockLessonRequest(
        topic="Neural Networks",
        subject="Computer Science",
        grade_level="University"
    )
    result = agent.generate(request)

    print(f"Lesson result keys: {result.data.keys()}")
    print(f"Sources: {result.data.get('sources', [])}")
    print(f"Unverified: {result.data.get('unverified', 'NOT_SET')}")

    # Verify RAG worked
    assert "sources" in result.data, "Sources key missing from result"
    assert "unverified" in result.data, "Unverified key missing from result"
    assert result.data["unverified"] == False, f"Expected unverified=False, got {result.data['unverified']}"
    assert len(result.data["sources"]) > 0, f"Expected sources to be populated, got {result.data['sources']}"
    assert "test_nn_source" in str(result.data["sources"]), f"Expected source_id in sources, got {result.data['sources']}"

    print("[PASS] PASS: Lesson with RAG match has sources populated and unverified=False")
    return True


def test_unverified_lesson():
    """Test lesson generation with no RAG match returns unverified=True"""
    agent = LessonGenerationAgent()
    request = MockLessonRequest(
        topic="Quantum Computing Basics",  # Topic not in vector store
        subject="Physics",
        grade_level="University"
    )
    result = agent.generate(request)

    print(f"Lesson result (no RAG): Sources: {result.data.get('sources', [])}, Unverified: {result.data.get('unverified', 'NOT_SET')}")

    # Verify unverified
    assert "sources" in result.data, "Sources key missing from result"
    assert "unverified" in result.data, "Unverified key missing from result"
    assert result.data["unverified"] == True, f"Expected unverified=True, got {result.data['unverified']}"
    assert len(result.data["sources"]) == 0, f"Expected empty sources, got {result.data['sources']}"

    print("[PASS] PASS: Lesson without RAG match has unverified=True and empty sources")
    return True


def test_rag_verified_quiz():
    """Test quiz generation with good RAG match returns sources and unverified=False"""
    agent = QuizGenerationAgent()
    result = agent.generate(
        topic="Neural Networks",
        difficulty="Medium",
        count=5,
        subject="Computer Science",
        grade_level="University"
    )

    print(f"Quiz result: Sources: {result.data.get('sources', [])}, Unverified: {result.data.get('unverified', 'NOT_SET')}")

    assert "sources" in result.data, "Sources key missing from result"
    assert "unverified" in result.data, "Unverified key missing from result"
    assert result.data["unverified"] == False, f"Expected unverified=False, got {result.data['unverified']}"
    assert len(result.data["sources"]) > 0, f"Expected sources to be populated, got {result.data['sources']}"
    assert "test_nn_source" in str(result.data["sources"]), f"Expected source_id in sources, got {result.data['sources']}"

    print("[PASS] PASS: Quiz with RAG match has sources populated and unverified=False")
    return True


def test_unverified_quiz():
    """Test quiz generation with no RAG match returns unverified=True"""
    agent = QuizGenerationAgent()
    result = agent.generate(
        topic="Quantum Computing Basics",
        difficulty="Medium",
        count=5,
        subject="Physics",
        grade_level="University"
    )

    print(f"Quiz result (no RAG): Sources: {result.data.get('sources', [])}, Unverified: {result.data.get('unverified', 'NOT_SET')}")

    assert "sources" in result.data, "Sources key missing from result"
    assert "unverified" in result.data, "Unverified key missing from result"
    assert result.data["unverified"] == True, f"Expected unverified=True, got {result.data['unverified']}"
    assert len(result.data["sources"]) == 0, f"Expected empty sources, got {result.data['sources']}"

    print("[PASS] PASS: Quiz without RAG match has unverified=True and empty sources")
    return True


def test_rag_verified_flashcard():
    """Test flashcard generation with good RAG match returns sources and unverified=False"""
    agent = FlashcardGenerationAgent()
    result = agent.generate(
        topic="Neural Networks",
        count=5,
        language="English",
        subject="Computer Science",
        grade_level="University"
    )

    print(f"Flashcard result: Sources: {result.data.get('sources', [])}, Unverified: {result.data.get('unverified', 'NOT_SET')}")

    assert "sources" in result.data, "Sources key missing from result"
    assert "unverified" in result.data, "Unverified key missing from result"
    assert result.data["unverified"] == False, f"Expected unverified=False, got {result.data['unverified']}"
    assert len(result.data["sources"]) > 0, f"Expected sources to be populated, got {result.data['sources']}"
    assert "test_nn_source" in str(result.data["sources"]), f"Expected source_id in sources, got {result.data['sources']}"

    print("[PASS] PASS: Flashcard with RAG match has sources populated and unverified=False")
    return True


def test_unverified_flashcard():
    """Test flashcard generation with no RAG match returns unverified=True"""
    agent = FlashcardGenerationAgent()
    result = agent.generate(
        topic="Quantum Computing Basics",
        count=5,
        language="English",
        subject="Physics",
        grade_level="University"
    )

    print(f"Flashcard result (no RAG): Sources: {result.data.get('sources', [])}, Unverified: {result.data.get('unverified', 'NOT_SET')}")

    assert "sources" in result.data, "Sources key missing from result"
    assert "unverified" in result.data, "Unverified key missing from result"
    assert result.data["unverified"] == True, f"Expected unverified=True, got {result.data['unverified']}"
    assert len(result.data["sources"]) == 0, f"Expected empty sources, got {result.data['sources']}"

    print("[PASS] PASS: Flashcard without RAG match has unverified=True and empty sources")
    return True


def test_simplify_from_recommendation():
    """Test that simplify_from_recommendation returns unverified=True (no RAG)"""
    agent = LessonGenerationAgent()
    result = agent.simplify_from_recommendation("Neural Networks", ["Use analogies", "Show diagrams"])

    print(f"Simplify result: Sources: {result.data.get('sources', [])}, Unverified: {result.data.get('unverified', 'NOT_SET')}")

    assert "unverified" in result.data, "Unverified key missing from simplify result"
    assert result.data["unverified"] == True, f"Expected unverified=True for simplify, got {result.data['unverified']}"
    assert result.data["sources"] == [], f"Expected empty sources for simplify, got {result.data['sources']}"

    print("[PASS] PASS: Simplify_from_recommendation returns unverified=True")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Running Task 4 Tests: RAG Verification Badges")
    print("=" * 60)

    tests = [
        test_rag_verified_lesson,
        test_unverified_lesson,
        test_rag_verified_quiz,
        test_unverified_quiz,
        test_rag_verified_flashcard,
        test_unverified_flashcard,
        test_simplify_from_recommendation,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] FAIL: {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[FAIL] ERROR: {test.__name__}: {e}")
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
    sys.exit(0)