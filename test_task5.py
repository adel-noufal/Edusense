#!/usr/bin/env python
"""
Task 5 Test: Verify 4 failover states of the Agent Orchestrator.

Tests:
1. Online RAG+Web+LLM Success
2. Online RAG Only (Web fails)
3. Offline RAG+Template
4. Offline Template Only (RAG fails)
"""
import os
import sys
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# Ensure backend is in path
backend_dir = os.path.join(os.path.dirname(__file__), "backend")
sys.path.insert(0, backend_dir)

# Clear ChromaDB before test
chroma_dir = os.path.join(backend_dir, "data", "chroma")
if os.path.exists(chroma_dir):
    shutil.rmtree(chroma_dir)
os.makedirs(chroma_dir, exist_ok=True)

from app.agents.orchestrator import AgentOrchestrator, answer_question
from app.services.ingestion import process_and_ingest_document
from app.core.config import Settings, get_settings


def setup_test_data():
    """Ingest test document for RAG retrieval."""
    test_content = b"""
    Machine Learning Fundamentals

    Machine learning is a subset of artificial intelligence that enables systems to learn from data.
    Key concepts include supervised learning (classification, regression), unsupervised learning (clustering),
    and reinforcement learning. Popular algorithms include linear regression, decision trees, random forests,
    support vector machines, and neural networks.

    Deep learning uses multi-layer neural networks to model complex patterns. Convolutional Neural Networks (CNNs)
    excel at image processing, while Recurrent Neural Networks (RNNs) and Transformers handle sequential data.
    """

    result = process_and_ingest_document(
        file_bytes=test_content,
        filename="ml_fundamentals.txt",
        subject="Computer Science",
        grade_level="University",
        topic="Machine Learning",
        source_id="test_ml_source"
    )
    print(f"Setup: Ingested {result['chunk_count']} chunks")
    return result


def create_mock_settings(ai_provider="gemini", gemini_api_key="test-key", **kwargs):
    """Create a mock Settings instance with custom values."""
    defaults = {
        "ai_provider": ai_provider,
        "gemini_api_key": gemini_api_key,
        "gemini_model": "gemini-2.5-flash",
        "ollama_url": "http://localhost:11434/api/generate",
        "ollama_model": "llama3.2",
        "ollama_model_translation": "qwen2.5",
        "ollama_model_lesson": "mistral",
        "ollama_model_quiz": "llama3.1",
        "ollama_model_flashcard": "llama3.2",
        "rag_min_score": 0.6,
        "chroma_persist_dir": "data/chroma",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "tavily_api_key": "",
    }
    defaults.update(kwargs)
    return Settings(**defaults)


def test_state_1_online_rag_web_llm():
    """
    State 1: Online RAG+Web+LLM Success
    - RAG returns results
    - Web search returns results (mocked)
    - LLM generates response
    """
    print("\n=== Test State 1: Online RAG+Web+LLM ===")

    # Mock settings to simulate online mode
    mock_settings = create_mock_settings(ai_provider="gemini", gemini_api_key="test-key")

    # Mock Web_Search_Tool to return results
    from app.agents import orchestrator
    original_web_search = orchestrator.Web_Search_Tool

    def mock_web_search(query, max_results=5, **kwargs):
        return [
            {"title": "Latest ML Research 2024", "url": "https://example.com/ml2024", "content": "New transformer architectures achieve SOTA.", "score": 0.95},
            {"title": "ML Best Practices", "url": "https://example.com/best-practices", "content": "Regularization and dropout improve generalization.", "score": 0.88},
        ]

    orchestrator.Web_Search_Tool = mock_web_search

    # Mock LLM to return a response
    from app.agents.base import LocalLLM
    original_generate = LocalLLM.generate

    def mock_generate(self, prompt):
        return "Based on the knowledge base and web search, machine learning uses algorithms to learn from data. Recent research shows transformers achieving state-of-the-art results."

    LocalLLM.generate = mock_generate

    try:
        with patch('app.agents.orchestrator.get_settings', return_value=mock_settings):
            orchestrator = AgentOrchestrator()
            result = orchestrator.run(
                query="What is machine learning?",
                subject="Computer Science",
                grade_level="University"
            )

        print(f"Mode: {result.mode}")
        print(f"Answer: {result.answer[:100]}...")
        print(f"RAG chunks: {result.rag_chunks_used}")
        print(f"Web results: {result.web_results_used}")
        print(f"Sources: {result.sources}")
        print(f"Web sources: {[w['title'] for w in result.web_sources]}")

        assert result.mode == "online_rag_web_llm", f"Expected online_rag_web_llm, got {result.mode}"
        assert result.rag_chunks_used > 0, "Expected RAG chunks used"
        assert result.web_results_used > 0, "Expected web results used"
        assert len(result.sources) > 0, "Expected RAG sources"
        assert len(result.web_sources) > 0, "Expected web sources"
        assert "machine learning" in result.answer.lower(), "Answer should mention ML"

        print("[PASS] State 1 - Online RAG+Web+LLM")
        return True
    finally:
        orchestrator.Web_Search_Tool = original_web_search
        LocalLLM.generate = original_generate


def test_state_2_online_rag_only():
    """
    State 2: Online RAG Only (Web fails)
    - RAG returns results
    - Web search fails/returns empty
    - LLM generates response
    """
    print("\n=== Test State 2: Online RAG Only (Web Fails) ===")

    mock_settings = create_mock_settings(ai_provider="gemini", gemini_api_key="test-key")

    from app.agents import orchestrator
    original_web_search = orchestrator.Web_Search_Tool

    def mock_web_search_fail(query, max_results=5, **kwargs):
        return []  # Web search returns empty

    orchestrator.Web_Search_Tool = mock_web_search_fail

    from app.agents.base import LocalLLM
    original_generate = LocalLLM.generate

    def mock_generate(self, prompt):
        return "Based on the knowledge base, machine learning enables systems to learn from data without explicit programming."

    LocalLLM.generate = mock_generate

    try:
        with patch('app.agents.orchestrator.get_settings', return_value=mock_settings):
            orchestrator = AgentOrchestrator()
            result = orchestrator.run(
                query="What is machine learning?",
                subject="Computer Science",
                grade_level="University"
            )

        print(f"Mode: {result.mode}")
        print(f"Answer: {result.answer[:100]}...")
        print(f"RAG chunks: {result.rag_chunks_used}")
        print(f"Web results: {result.web_results_used}")
        print(f"Fallback reason: {result.fallback_reason}")

        assert result.mode == "online_rag_only", f"Expected online_rag_only, got {result.mode}"
        assert result.rag_chunks_used > 0, "Expected RAG chunks used"
        assert result.web_results_used == 0, "Expected no web results"
        assert "knowledge base" in result.answer.lower() or "machine learning" in result.answer.lower()

        print("[PASS] State 2 - Online RAG Only")
        return True
    finally:
        orchestrator.Web_Search_Tool = original_web_search
        LocalLLM.generate = original_generate


def test_state_3_offline_rag_template():
    """
    State 3: Offline RAG+Template
    - RAG returns results
    - LLM unavailable (offline mode)
    - Template fallback with RAG context
    """
    print("\n=== Test State 3: Offline RAG+Template ===")

    mock_settings = create_mock_settings(ai_provider="ollama", gemini_api_key="")

    from app.agents.base import LocalLLM
    original_generate = LocalLLM.generate

    def mock_generate_fail(self, prompt):
        raise Exception("LLM unavailable")

    LocalLLM.generate = mock_generate_fail

    try:
        with patch('app.agents.orchestrator.get_settings', return_value=mock_settings):
            orchestrator = AgentOrchestrator()
            result = orchestrator.run(
                query="What is machine learning?",
                subject="Computer Science",
                grade_level="University"
            )

        print(f"Mode: {result.mode}")
        print(f"Answer: {result.answer[:100]}...")
        print(f"RAG chunks: {result.rag_chunks_used}")
        print(f"Web results: {result.web_results_used}")
        print(f"Fallback reason: {result.fallback_reason}")

        assert result.mode == "offline_rag_template", f"Expected offline_rag_template, got {result.mode}"
        assert result.rag_chunks_used > 0, "Expected RAG chunks used"
        assert result.web_results_used == 0, "Expected no web results (offline)"
        assert "machine learning" in result.answer.lower() or "generated local" in result.answer.lower()

        print("[PASS] State 3 - Offline RAG+Template")
        return True
    finally:
        LocalLLM.generate = original_generate


def test_state_4_offline_template_only():
    """
    State 4: Offline Template Only (RAG fails)
    - RAG returns no results
    - LLM unavailable
    - Template fallback only
    """
    print("\n=== Test State 4: Offline Template Only (RAG Fails) ===")

    mock_settings = create_mock_settings(ai_provider="ollama", gemini_api_key="")

    from app.agents import orchestrator
    original_rag_search = orchestrator.RAG_Search_Tool

    def mock_rag_search_fail(query, **kwargs):
        return []  # RAG returns empty

    orchestrator.RAG_Search_Tool = mock_rag_search_fail

    from app.agents.base import LocalLLM
    original_generate = LocalLLM.generate

    def mock_generate_fail(self, prompt):
        raise Exception("LLM unavailable")

    LocalLLM.generate = mock_generate_fail

    try:
        with patch('app.agents.orchestrator.get_settings', return_value=mock_settings):
            orchestrator = AgentOrchestrator()
            result = orchestrator.run(
                query="What is quantum computing?",  # Topic not in KB
                subject="Physics",
                grade_level="University"
            )

        print(f"Mode: {result.mode}")
        print(f"Answer: {result.answer[:100]}...")
        print(f"RAG chunks: {result.rag_chunks_used}")
        print(f"Web results: {result.web_results_used}")
        print(f"Fallback reason: {result.fallback_reason}")

        assert result.mode == "offline_template_only", f"Expected offline_template_only, got {result.mode}"
        assert result.rag_chunks_used == 0, "Expected no RAG chunks"
        assert result.web_results_used == 0, "Expected no web results"
        assert "generated local" in result.answer.lower() or "quantum computing" in result.answer.lower()

        print("[PASS] State 4 - Offline Template Only")
        return True
    finally:
        orchestrator.RAG_Search_Tool = original_rag_search
        LocalLLM.generate = original_generate


def test_answer_question_convenience():
    """Test the convenience function answer_question."""
    print("\n=== Test Convenience Function ===")

    mock_settings = create_mock_settings(ai_provider="ollama", gemini_api_key="")

    from app.agents.base import LocalLLM
    original_generate = LocalLLM.generate

    def mock_generate_fail(self, prompt):
        raise Exception("LLM unavailable")

    LocalLLM.generate = mock_generate_fail

    try:
        with patch('app.agents.orchestrator.get_settings', return_value=mock_settings):
            result = answer_question(
                query="What is deep learning?",
                subject="Computer Science",
                grade_level="University"
            )

        print(f"Mode: {result.mode}")
        print(f"Answer: {result.answer[:100]}...")

        assert isinstance(result.mode, str), "Mode should be a string"
        assert result.answer, "Should have an answer"

        print("[PASS] Convenience function works")
        return True
    finally:
        LocalLLM.generate = original_generate


if __name__ == "__main__":
    print("=" * 60)
    print("Running Task 5 Tests: Agent Orchestrator Failover States")
    print("=" * 60)

    # Setup test data first
    setup_test_data()

    tests = [
        test_state_1_online_rag_web_llm,
        test_state_2_online_rag_only,
        test_state_3_offline_rag_template,
        test_state_4_offline_template_only,
        test_answer_question_convenience,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
    sys.exit(0)