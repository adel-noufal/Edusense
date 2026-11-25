"""Addendum #11 regression tests: LLM load spread, 404 handling, KB/chat split."""
import time

import pytest

from app.services import llm
from app.services.rag_qa import _page_span


SHORT_FEATURES = ("kb_chat", "prompt_enhance", "flashcards", "quizzes", "general")


def test_gemini_is_last_cloud_option_for_short_features():
    for feature in SHORT_FEATURES:
        chain = llm.DEFAULT_FEATURE_CHAINS[feature]
        assert chain[-1] == "gemini", (feature, chain)
        assert chain[0] != "gemini", (feature, chain)
        # Ollama is appended by candidates(), never baked into the cloud chain.
        assert "ollama" not in chain, (feature, chain)


def test_gemini_stays_primary_for_long_video_scripts():
    assert llm.DEFAULT_FEATURE_CHAINS["video_script"][0] == "gemini"


def test_404_is_a_timed_disable_not_permanent():
    router = llm.router
    model = "addendum11-test-model"
    router._model_disabled.pop(("groq", model), None)
    router._states.pop(("groq", 0, model), None)

    router.mark_failure(
        "groq", 0, model, None, "HTTP 404: model does not exist", permanent=True
    )

    until = router._model_disabled[("groq", model)]
    assert until > time.time(), "404 must disable for a bounded time"
    assert router._model_gone("groq", model) is True

    # Simulate the cooldown expiring: the model is re-verified, not banned.
    router._model_disabled[("groq", model)] = time.time() - 1
    assert router._model_gone("groq", model) is False
    assert ("groq", model) not in router._model_disabled


def test_ollama_is_always_the_last_resort(monkeypatch):
    router = llm.router
    monkeypatch.setattr(router, "_ensure_ollama", lambda: None)
    monkeypatch.setattr(
        router, "provider_keys",
        lambda p: ["dummy"] if p in ("ollama", "groq") else [],
    )
    monkeypatch.setattr(
        router, "provider_models",
        lambda p, task="general": (
            ["llama3.2:latest"] if p == "ollama" else ["llama-3.3-70b-versatile"]
        ),
    )
    cands = router.candidates("kb_chat", prompt_tokens=10)
    assert cands, "candidates must never be empty while Ollama is up"
    assert cands[-1][0] == "ollama"


def test_circuit_breaker_caps_pairs_tried(monkeypatch):
    monkeypatch.setattr(llm, "_CACHE", {}, raising=False)
    calls = []

    def _fail(*args, **kwargs):
        calls.append(args[3])
        raise RuntimeError("boom")

    monkeypatch.setattr(llm, "_call_provider", _fail)
    pairs = [
        ("groq", 0, "k1", "m1"),
        ("nvidia", 0, "k2", "m2"),
        ("openrouter", 0, "k3", "m3"),
        ("gemini", 0, "k4", "m4"),
        ("deepinfra", 0, "k5", "m5"),
        ("cerebras", 0, "k6", "m6"),
        ("groq", 0, "k7", "m7"),
        ("nvidia", 0, "k8", "m8"),
    ]
    monkeypatch.setattr(llm.router, "candidates", lambda **kw: pairs)

    with pytest.raises(llm.GeminiError):
        llm.chat("hello", task_type="kb_chat")

    assert len(calls) == llm.MAX_ATTEMPTS_PER_REQUEST, calls


def test_chat_cache_avoids_a_second_provider_call(monkeypatch):
    calls = []

    def _ok(*args, **kwargs):
        calls.append(1)
        return "cached answer"

    monkeypatch.setattr(llm, "_call_provider", _ok)
    monkeypatch.setattr(
        llm.router, "candidates", lambda **kw: [("groq", 0, "k", "cache-model")]
    )
    llm._CACHE.clear()

    first = llm.chat("same prompt", task_type="prompt_enhance", cache_key="addendum11:a")
    second = llm.chat("same prompt", task_type="prompt_enhance", cache_key="addendum11:a")

    assert first == second == "cached answer"
    assert len(calls) == 1


def test_key_budget_stops_at_80_percent_of_free_rpd(monkeypatch):
    router = llm.router
    key = "budget-test-key"
    entry = llm.KeyEntry(provider="groq", key=key, label="budget", quota_group="g")
    entry.requests_today = 80
    monkeypatch.setattr(router, "_working", {"groq": ["allam-2-7b"]}, raising=False)
    monkeypatch.setattr(router, "_keys_by_provider", {"groq": [entry]}, raising=False)
    monkeypatch.setattr(router, "provider_keys", lambda p: [key] if p == "groq" else [])
    monkeypatch.setattr(
        router, "get_model_profile",
        lambda p, m: {"free_rpd": 100, "context_window": 128000,
                      "max_output_tokens": 4096, "free_tier": True},
    )
    assert router.candidates("prompt_enhance") == [], "80% of RPD must stop routing"


def test_retry_after_sets_cooldown():
    router = llm.router
    router.mark_failure("groq", 0, "retry-after-model", 12.0,
                        "HTTP 429: rate limited")
    state = router._states[("groq", 0, "retry-after-model")]
    assert state.cooldown_until - time.time() >= 8, "Retry-After must bound the cooldown"


def test_arabic_prompts_prefer_qwen2_locally(monkeypatch):
    router = llm.router
    monkeypatch.setattr(router, "_working", {}, raising=False)
    monkeypatch.setattr(router, "_ensure_ollama", lambda: None)
    monkeypatch.setattr(router, "provider_keys", lambda p: ["x"] if p == "ollama" else [])
    monkeypatch.setattr(
        router, "provider_models",
        lambda p, t="general": (
            ["llama3.2:latest", "qwen2.5:latest", "llama3.1:latest", "mistral:latest"]
            if p == "ollama" else []
        ),
    )
    cands = router.candidates("kb_chat", language="ar")
    assert cands and cands[0][3].startswith("qwen2.5"), cands


def test_kb_engine_private_never_uses_cloud(monkeypatch):
    from app.services import rag_qa

    seen = {}

    def _capture(*args, **kwargs):
        seen.update(kwargs)
        return "local answer"

    monkeypatch.setattr(llm, "chat", _capture)
    answer, model_used, _ = rag_qa._call_llm("question", engine="private")
    assert answer == "local answer"
    assert seen.get("only_provider") == "ollama"
    assert model_used == "ollama"


def test_page_reference_parsing():
    assert _page_span("explain normalization on page 40") == (40, 40)
    assert _page_span("summarize pages 40-45") == (40, 45)
    assert _page_span("pages 45 to 40") == (40, 45)
    assert _page_span("what is the main idea") is None


def test_chatbot_conversations_exclude_kb():
    from app.db.session import SessionLocal
    from app.models.models import ChatMessage, User
    from app.api.ai import WEB_PREFIX, migrate_conversation_kinds

    db = SessionLocal()
    try:
        user = db.query(User).first()
        assert user is not None
        legacy = "addendum11-legacy-conversation"
        db.query(ChatMessage).filter_by(conversation_id=legacy).delete()
        db.add(ChatMessage(conversation_id=legacy, user_id=user.id,
                           role="user", content="legacy question"))
        db.commit()

        moved = migrate_conversation_kinds(db)
        assert moved >= 1
        assert db.query(ChatMessage).filter_by(
            conversation_id=f"{WEB_PREFIX}{legacy}"
        ).first() is not None

        # Reversible: running the migration again changes nothing.
        assert migrate_conversation_kinds(db) == 0

        db.query(ChatMessage).filter_by(
            conversation_id=f"{WEB_PREFIX}{legacy}"
        ).delete()
        db.commit()
    finally:
        db.close()
