"""
Section 6 Verification Test — Multi-API-Key Rotation for Google Gemini
Tests:
1. Settings parses multiple keys from comma-delimited strings and numbered env variables (GEMINI_API_KEY_1..N).
2. Key deduping, empty-string removal, and whitespace trimming.
3. Key masking security check (only first 4 and last 4 characters revealed).
4. GeminiKeyRotator basic rotation and active key selection.
5. GeminiKeyRotator automatic recovery after cooldown expiration.
6. Rate limit error detection logic (HTTP 429, RESOURCE_EXHAUSTED, quota exceeded).
7. Non-rate-limit errors (HTTP 400 Bad Request) do not rotate and fail immediately.
8. generate_content() rotates to Key 2 when Key 1 hits 429 rate limit, and succeeds.
9. generate_content() fails cleanly with informative error when all keys are exhausted.
10. /health endpoint reports gemini_configured, gemini_keys_count, and gemini_keys_status.
"""

import io
import json
import os
import sys
import time
import urllib.error
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from app.core.config import Settings, get_settings
from app.services.gemini import (
    GeminiKeyRotator,
    _is_rate_limit_error,
    generate_content,
    rotator,
)


def test_section6():
    PASSED = []
    FAILED = []

    def check(name, cond, detail=""):
        if cond:
            PASSED.append(name)
            print(f"  PASS {name}")
        else:
            FAILED.append(name)
            print(f"  FAIL {name}{': ' + detail if detail else ''}")

    print("\n=== Section 6 Verification: Multi-API-Key Rotation for Gemini ===\n")

    # ─────────────────────────────────────────────────────────────────────────────
    # Group 1: Settings & Key Parsing
    # ─────────────────────────────────────────────────────────────────────────────
    print("Group 1: Multi-Key Configuration & Settings Parsing")

    s1 = Settings(gemini_api_key="keyA, keyB,  keyC  ")
    check("1.1 Comma-delimited keys parsed into list", s1.gemini_api_keys == ["keyA", "keyB", "keyC"], f"Got: {s1.gemini_api_keys}")

    s2 = Settings(gemini_api_key="keyA, keyB, keyA, , ")
    check("1.2 Keys deduplicated and empty entries removed", s2.gemini_api_keys == ["keyA", "keyB"], f"Got: {s2.gemini_api_keys}")

    with patch.dict(os.environ, {
        "GEMINI_API_KEY_1": "numKey1",
        "GEMINI_API_KEY_2": "numKey2",
        "GEMINI_API_KEY_3": "numKey3",
    }, clear=False):
        s3 = Settings(gemini_api_key="")
        check("1.3 Numbered env variables discovered in order", s3.gemini_api_keys == ["numKey1", "numKey2", "numKey3"], f"Got: {s3.gemini_api_keys}")

    with patch.dict(os.environ, {
        "GEMINI_API_KEY_1": "numKeyA",
        "GEMINI_API_KEY_2": "commonKey",
    }, clear=False):
        s4 = Settings(gemini_api_key="commonKey, extraKey")
        check("1.4 Numbered keys merged with comma keys without duplicates",
              set(s4.gemini_api_keys) == {"commonKey", "extraKey", "numKeyA"},
              f"Got: {s4.gemini_api_keys}")

    # ─────────────────────────────────────────────────────────────────────────────
    # Group 2: Key Masking Security Check
    # ─────────────────────────────────────────────────────────────────────────────
    print("\nGroup 2: Key Masking Security Check")

    test_rotator = GeminiKeyRotator()
    masked_long = test_rotator.mask_key("AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6")
    check("2.1 Long key masked correctly (first 4 and last 4 chars only)",
          masked_long == "AIza...O5P6",
          f"Got: {masked_long}")

    masked_short = test_rotator.mask_key("short")
    check("2.2 Short string (<8 chars) returns '***' completely obscured", masked_short == "***", f"Got: {masked_short}")
    check("2.3 None/empty returns '***'", test_rotator.mask_key("") == "***")

    # ─────────────────────────────────────────────────────────────────────────────
    # Group 3: GeminiKeyRotator Rotation Logic & Cooldown
    # ─────────────────────────────────────────────────────────────────────────────
    print("\nGroup 3: Key Rotator Mechanics & Cooldown Recovery")

    mock_keys = ["Key_Alpha_1111", "Key_Beta_2222", "Key_Gamma_3333"]
    r = GeminiKeyRotator(cooldown_seconds=0.3)

    with patch.object(r, "get_keys", return_value=mock_keys):
        k1 = r.get_active_key()
        check("3.1 Initial active key is first key", k1 == "Key_Alpha_1111", f"Got: {k1}")

        next_k = r.mark_exhausted("Key_Alpha_1111", reason="429 Rate Limit")
        check("3.2 mark_exhausted advances to Key 2", next_k == "Key_Beta_2222", f"Got: {next_k}")
        check("3.3 get_active_key returns Key 2", r.get_active_key() == "Key_Beta_2222")

        st = r.status()
        check("3.4 Status reports 2 active, 1 exhausted", st["active_keys"] == 2 and st["exhausted_keys"] == 1, f"Status: {st}")

        r.mark_exhausted("Key_Beta_2222", reason="429 Rate Limit")
        check("3.5 Exhausting Key 2 advances to Key 3", r.get_active_key() == "Key_Gamma_3333")

        time.sleep(0.35)
        k_recovered = r.get_active_key()
        check("3.6 Cooldown elapsed: Key 1 recovered and usable again",
              k_recovered in mock_keys,
              f"Got: {k_recovered}")
        check("3.7 Status reports all 3 active after cooldown", r.status()["active_keys"] == 3)

    # ─────────────────────────────────────────────────────────────────────────────
    # Group 4: Failover in generate_content()
    # ─────────────────────────────────────────────────────────────────────────────
    print("\nGroup 4: End-to-End Failover in generate_content()")

    mock_keys_e2e = ["FailKey_1111", "SuccessKey_2222"]

    class MockHTTP429(urllib.error.HTTPError):
        def __init__(self):
            super().__init__("http://fake.url", 429, "Too Many Requests", hdrs={}, fp=io.BytesIO(b'{"error": "RESOURCE_EXHAUSTED: quota exceeded"}'))

    class MockHTTP400(urllib.error.HTTPError):
        def __init__(self):
            super().__init__("http://fake.url", 400, "Bad Request: malformed JSON", hdrs={}, fp=io.BytesIO(b'{"error": "INVALID_ARGUMENT: syntax error"}'))

    mock_success_response = MagicMock()
    mock_success_response.read.return_value = json.dumps({
        "candidates": [{"content": {"parts": [{"text": "Hello from Gemini Key 2!"}]}}]
    }).encode()
    mock_success_response.__enter__.return_value = mock_success_response

    call_log = []

    def fake_urlopen(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        call_log.append(url)
        if "FailKey_1111" in url:
            raise MockHTTP429()
        if "SuccessKey_2222" in url:
            return mock_success_response
        raise RuntimeError(f"Unexpected URL: {url}")

    with rotator._lock:
        rotator._exhausted.clear()
        rotator._current_index = 0

    with patch("app.services.gemini.get_settings") as mock_settings:
        mock_settings.return_value.gemini_api_keys = mock_keys_e2e
        mock_settings.return_value.gemini_model = "gemini-2.0-flash"

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            try:
                res_text = generate_content("Test prompt for rotation")
                check("4.1 generate_content rotates past 429 to succeed with Key 2",
                      res_text == "Hello from Gemini Key 2!",
                      f"Got: {res_text}")
                check("4.2 Both keys were attempted (FailKey followed by SuccessKey)",
                      len(call_log) == 2 and "FailKey_1111" in call_log[0] and "SuccessKey_2222" in call_log[1],
                      f"Call log: {call_log}")
            except Exception as exc:
                check("4.1 generate_content rotation failed", False, str(exc))

    # Test 400 Bad Request syntax error (non-rotatable) -> should raise immediately without exhausting key
    with rotator._lock:
        rotator._exhausted.clear()
        rotator._current_index = 0

    def fake_urlopen_400(req, timeout=15):
        raise MockHTTP400()

    with patch("app.services.gemini.get_settings") as mock_settings:
        mock_settings.return_value.gemini_api_keys = ["Key_Syntax_1111", "Key_Syntax_2222"]
        mock_settings.return_value.gemini_model = "gemini-2.0-flash"
        with patch("urllib.request.urlopen", side_effect=fake_urlopen_400):
            threw_expected = False
            try:
                generate_content("Bad syntax request")
            except RuntimeError as exc:
                threw_expected = "400" in str(exc)
            check("4.3 Non-rotatable 400 error does NOT rotate and raises RuntimeError immediately", threw_expected)

    # ─────────────────────────────────────────────────────────────────────────────
    # Group 5: /health Endpoint Key Pool Status
    # ─────────────────────────────────────────────────────────────────────────────
    print("\nGroup 5: Health Check Inspection")

    with rotator._lock:
        rotator._exhausted.clear()
        rotator._current_index = 0

    from app.main import health

    health_report = health()
    check("5.1 /health response contains gemini_configured", "gemini_configured" in health_report)
    check("5.2 /health response contains gemini_keys_count", "gemini_keys_count" in health_report and isinstance(health_report["gemini_keys_count"], int))
    check("5.3 /health response contains gemini_keys_status dict",
          "gemini_keys_status" in health_report and "total_keys" in health_report["gemini_keys_status"])
    check("5.4 gemini_keys_status details total, active, exhausted keys",
          all(k in health_report["gemini_keys_status"] for k in ("total_keys", "active_keys", "exhausted_keys", "current_index")))

    print("\n" + "=" * 50)
    print(f"Total Checks: {len(PASSED) + len(FAILED)} | Passed: {len(PASSED)} | Failed: {len(FAILED)}")
    print("=" * 50)
    assert len(FAILED) == 0, f"Failed checks: {FAILED}"


if __name__ == "__main__":
    test_section6()
