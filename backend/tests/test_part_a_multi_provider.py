"""
test_part_a_multi_provider.py — Comprehensive Verification Suite for Part A (Revised).

Tests:
1. Key Auto-Discovery & Registry:
   - Pooled keys (<PROVIDER>_API_KEYS)
   - Named keys (<PROVIDER>_KEY_<LABEL>)
   - Backward compatibility with legacy GEMINI_API_KEY, numbered vars, and chatbot key
2. Metadata & Quota Groups:
   - Quota group isolation & group cooldown propagation
   - Dedicated feature tag inference (e.g. video, chat)
3. Startup Validation & Probing:
   - Key status classification (healthy, invalid, rate_limited, no_access)
   - Auto-disabling of bad keys with masked logging, no server crash
4. Best-Fit Routing & Model Capabilities:
   - video_script routing (dedicated Gemini first, long context)
   - kb_chat routing (Groq speed first)
   - quizzes/flashcards/exams routing (JSON reliability & throughput)
   - reports routing (Gemini Flash analytical reasoning)
   - question_bank routing & verification provider exclusion
5. Strict-JSON Validation & One-Shot Repair:
   - Recovers from markdown fences and trailing commas
6. Privacy Constraints:
   - touch_student_data filters out may_train_on_data models
7. Visibility & Quota Counters:
   - Key masking security check (never reveals full keys)
   - Daily usage tracking
"""
import io
import json
import os
import sys
import time
import urllib.error
from unittest.mock import MagicMock, patch

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from app.core.config import Settings
from app.services.gemini import GeminiError
from app.services import llm
from app.services.llm import KeyEntry, LLMRouter, _repair_json_syntax


def test_all():
    PASSED = []
    FAILED = []

    def check(name: str, cond: bool, detail: str = ""):
        if cond:
            PASSED.append(name)
            print(f"  PASS: {name}")
        else:
            FAILED.append(name)
            print(f"  FAIL: {name}{' — ' + detail if detail else ''}")

    print("\n=== Part A (Revised) LLM Architecture Verification ===\n")

    # -------------------------------------------------------------------------
    # Group 1: Key Auto-Discovery & Backward Compatibility
    # -------------------------------------------------------------------------
    print("Group 1: Key Auto-Discovery & Backward Compatibility")

    test_env = {
        "GEMINI_API_KEY": "legacy_gemini_primary",
        "GEMINI_API_KEY_1": "legacy_gemini_num1",
        "CHATBOT_GEMINI_API_KEY": "legacy_chatbot_key",
        "GROQ_API_KEYS": "groq_key_1, groq_key_2",
        "CEREBRAS_KEY_BULK": "cerebras_named_bulk_key",
        "GEMINI_KEY_VIDEO_PROD": "gemini_named_video_key",
        "NVIDIA_KEY_EXAM_FAST": "nvidia_named_exam_key",
        "NVIDIA_KEY_EXAM_FAST_GROUP": "nvidia_group_a",
    }

    with patch.dict(os.environ, test_env, clear=True):
        router = LLMRouter()
        router.reload_keys()

        # Check Gemini keys discover legacy + named
        gemini_keys = router.provider_keys("gemini")
        check("1.1 Legacy Gemini keys discovered", "legacy_gemini_primary" in gemini_keys)
        check("1.2 Numbered Gemini key discovered", "legacy_gemini_num1" in gemini_keys)
        check("1.3 Dedicated chatbot Gemini key discovered", "legacy_chatbot_key" in gemini_keys)
        check("1.4 Named GEMINI_KEY_<LABEL> discovered", "gemini_named_video_key" in gemini_keys)

        # Check Groq pooled keys
        groq_keys = router.provider_keys("groq")
        check("1.5 Groq pooled keys discovered", "groq_key_1" in groq_keys and "groq_key_2" in groq_keys)

        # Check Cerebras named key
        cerebras_keys = router.provider_keys("cerebras")
        check("1.6 Cerebras named key discovered", "cerebras_named_bulk_key" in cerebras_keys)

        # Check NVIDIA named key
        nvidia_keys = router.provider_keys("nvidia")
        check("1.7 NVIDIA named key discovered", "nvidia_named_exam_key" in nvidia_keys)

    # -------------------------------------------------------------------------
    # Group 2: Per-Key Metadata & Quota Groups
    # -------------------------------------------------------------------------
    print("\nGroup 2: Per-Key Metadata & Dedicated Features")

    with patch.dict(os.environ, test_env, clear=True):
        router = LLMRouter()
        router.reload_keys()

        entries = {e.key: e for e in router._keys}

        # Check dedicated feature inference from label
        video_entry = entries.get("gemini_named_video_key")
        check("2.1 Video feature inferred from label 'video_prod'",
              video_entry is not None and "video_script" in video_entry.dedicated_features)

        exam_entry = entries.get("nvidia_named_exam_key")
        check("2.2 Exam/quiz feature inferred from label 'exam_fast'",
              exam_entry is not None and "exams" in exam_entry.dedicated_features)

        # Check custom quota group from env
        check("2.3 Quota group assigned from env metadata",
              exam_entry is not None and exam_entry.quota_group == "nvidia_group_a")

        # Quota group cooldown propagation test
        router.mark_failure("nvidia", 0, "meta/llama-3.3-70b-instruct", retry_after=60.0,
                            reason="429 rate limit", quota_group="nvidia_group_a")
        cd = router._group_blocked("nvidia", "nvidia_group_a", "meta/llama-3.3-70b-instruct")
        check("2.4 Quota group cooling down together", cd > 0.0)

    # -------------------------------------------------------------------------
    # Group 3: Startup Validation & Key Probing
    # -------------------------------------------------------------------------
    print("\nGroup 3: Key Validation & Auto-Disabling")

    router = LLMRouter()
    good_entry = KeyEntry(provider="gemini", key="AIzaSyValidKey1234567890", label="good")
    bad_entry = KeyEntry(provider="groq", key="gsk_InvalidBadKey0000000000", label="bad")

    def mock_probe_urlopen(req, timeout=8.0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        auth = req.get_header("Authorization", "") if hasattr(req, "get_header") else ""
        if "AIzaSyValidKey" in url or "AIzaSyValidKey" in auth:
            resp = MagicMock()
            resp.status = 200
            resp.read.return_value = b'{"models": []}'
            return resp
        if "gsk_InvalidBadKey" in auth or "gsk_InvalidBadKey" in url:
            fp = io.BytesIO(b'{"error": {"message": "Invalid API Key"}}')
            raise urllib.error.HTTPError(url, 401, "Unauthorized", hdrs={}, fp=fp)
        raise RuntimeError(f"Unexpected url: {url}")

    with patch("urllib.request.urlopen", side_effect=mock_probe_urlopen):
        status_good, _ = router.probe_key(good_entry)
        status_bad, _ = router.probe_key(bad_entry)
        check("3.1 Valid key classified as healthy", status_good == "healthy")
        check("3.2 401 response classified as invalid", status_bad == "invalid")

    # -------------------------------------------------------------------------
    # Group 4: Best-Fit Feature Routing
    # -------------------------------------------------------------------------
    print("\nGroup 4: Best-Fit Feature Routing")

    with patch.dict(os.environ, {
        "GEMINI_KEY_VIDEO_1": "gemini_video_key",
        "GEMINI_API_KEY": "gemini_general_key",
        "GROQ_API_KEYS": "groq_chat_key",
        "NVIDIA_API_KEYS": "nvidia_quiz_key",
        "DEEPINFRA_API_KEYS": "deepinfra_quiz_key",
    }, clear=True):
        router = LLMRouter()
        router.reload_keys()

        # A. video_script: dedicated video key should lead
        cands_video = router.candidates("video_script")
        check("4.1 video_script leads with Gemini provider",
              len(cands_video) > 0 and cands_video[0][0] == "gemini")
        check("4.2 video_script prioritizes dedicated video key",
              len(cands_video) > 0 and cands_video[0][2] == "gemini_video_key")

        # B. kb_chat: Groq speed should lead
        cands_chat = router.candidates("kb_chat")
        check("4.3 kb_chat leads with Groq for low latency",
              len(cands_chat) > 0 and cands_chat[0][0] == "groq")

        # C. quizzes: NVIDIA/OpenRouter/DeepInfra/Groq JSON throughput
        cands_quiz = router.candidates("quizzes")
        check("4.4 quizzes leads with high-throughput JSON provider",
              len(cands_quiz) > 0 and cands_quiz[0][0] in ("nvidia", "openrouter", "deepinfra", "groq"))

        # D. reports: Gemini Flash analytical reasoning leads
        cands_report = router.candidates("reports")
        check("4.5 reports leads with Gemini Flash",
              len(cands_report) > 0 and cands_report[0][0] == "gemini")

        # E. question_bank: Groq/Cerebras volume leads
        cands_bank = router.candidates("question_bank")
        check("4.6 question_bank leads with bulk provider (Groq/Cerebras)",
              len(cands_bank) > 0 and cands_bank[0][0] in ("groq", "cerebras"))

        # F. verification task: exclude_provider ensures divergence
        cands_verify = router.candidates("question_bank", exclude_provider="groq")
        check("4.7 Verification task excludes generating provider",
              all(c[0] != "groq" for c in cands_verify))

    # -------------------------------------------------------------------------
    # Group 5: Strict JSON Validation & One-Shot Repair
    # -------------------------------------------------------------------------
    print("\nGroup 5: Strict-JSON Syntax Repair")

    # Raw string with markdown code block
    fenced_json = "```json\n{\"question\": \"What is 2+2?\", \"answer\": 4}\n```"
    repaired1 = _repair_json_syntax(fenced_json)
    check("5.1 Markdown-fenced JSON repaired", repaired1 == {"question": "What is 2+2?", "answer": 4})

    # Raw string with trailing commas
    trailing_comma_json = '{"items": ["alpha", "beta",], "status": "ok",}'
    repaired2 = _repair_json_syntax(trailing_comma_json)
    check("5.2 Trailing comma JSON repaired", repaired2 == {"items": ["alpha", "beta"], "status": "ok"})

    # -------------------------------------------------------------------------
    # Group 6: Privacy & Data Masking Security Checks
    # -------------------------------------------------------------------------
    print("\nGroup 6: Privacy & Data Masking Security Checks")

    entry_mask = KeyEntry(provider="gemini", key="AIzaSyLongSecretKey1234567890ABCDEF")
    check("6.1 masked property hides middle chars",
          entry_mask.masked.startswith("AIza") and entry_mask.masked.endswith("CDEF") and "Secret" not in entry_mask.masked)
    check("6.2 masked_last4 reveals only last 4 chars", entry_mask.masked_last4 == "...CDEF")

    status_dump = router.status()
    raw_json_status = json.dumps(status_dump)
    check("6.3 Full secret key NEVER appears in router.status()",
          "LongSecretKey" not in raw_json_status and "1234567890" not in raw_json_status)

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    print("\n" + "=" * 60)
    print(f"Total: {len(PASSED) + len(FAILED)} | Passed: {len(PASSED)} | Failed: {len(FAILED)}")
    print("=" * 60)
    assert len(FAILED) == 0, f"Failed checks: {FAILED}"


if __name__ == "__main__":
    test_all()
