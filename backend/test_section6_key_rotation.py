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
    "GEMINI_API_KEY_3": "numKey1",  # duplicate
}):
    s3 = Settings(gemini_api_key="baseKey")
    keys = s3.gemini_api_keys
    check("1.3 Numbered GEMINI_API_KEY_N env vars recognized", "numKey1" in keys and "numKey2" in keys, f"Got: {keys}")
    check("1.4 Numbered keys deduplicated with base key", len(keys) == 3, f"Got count: {len(keys)}")

# ─────────────────────────────────────────────────────────────────────────────
# Group 2: Key Masking & GeminiKeyRotator Logic
# ─────────────────────────────────────────────────────────────────────────────
print("\nGroup 2: GeminiKeyRotator State Machine & Cooldown")

test_rotator = GeminiKeyRotator(cooldown_seconds=0.3)
check("2.1 Mask empty or short keys safely", test_rotator.mask_key("short") == "***" and test_rotator.mask_key("") == "***")
check("2.2 Mask standard API key", test_rotator.mask_key("AIzaSyD123456789xyz") == "AIza...9xyz")

with patch.object(test_rotator, "get_keys", return_value=["k1", "k2", "k3"]):
    check("2.3 Starts at initial active key (k1)", test_rotator.get_active_key() == "k1")
    
    # Mark k1 exhausted
    next_k = test_rotator.mark_exhausted("k1", reason="HTTP 429")
    check("2.4 Rotating from k1 returns k2", next_k == "k2")
    check("2.5 Active key updated to k2", test_rotator.get_active_key() == "k2")

    # Mark k2 exhausted
    next_k = test_rotator.mark_exhausted("k2", reason="quota exceeded")
    check("2.6 Rotating from k2 returns k3", next_k == "k3")
    check("2.7 Active key updated to k3", test_rotator.get_active_key() == "k3")

    # Status check
    st = test_rotator.status()
    check("2.8 Status reports active and exhausted counts accurately",
          st["total_keys"] == 3 and st["active_keys"] == 1 and st["exhausted_keys"] == 2,
          f"Got: {st}")

    # Mark k3 exhausted -> all exhausted
    next_k = test_rotator.mark_exhausted("k3", reason="HTTP 429")
    check("2.9 Rotating when all keys exhausted returns None", next_k is None)

    # Cooldown recovery
    time.sleep(0.35)
    recovered_key = test_rotator.get_active_key()
    check("2.10 Exhausted key recovered after cooldown elapsed", recovered_key is not None, f"Got: {recovered_key}")
    check("2.11 Status reflects recovered active keys", test_rotator.status()["active_keys"] >= 1)

# ─────────────────────────────────────────────────────────────────────────────
# Group 3: Rate Limit Error Classifier
# ─────────────────────────────────────────────────────────────────────────────
print("\nGroup 3: Rate Limit & Quota Classifier")

check("3.1 HTTP 429 is classified as rate limit", _is_rate_limit_error(429, "Too Many Requests"))
check("3.2 RESOURCE_EXHAUSTED phrase classified as rate limit", _is_rate_limit_error(403, "RESOURCE_EXHAUSTED: quota exceeded"))
check("3.3 Quota exceeded phrase classified as rate limit", _is_rate_limit_error(503, "User has exceeded per-minute quota"))
check("3.4 Rate limit phrase classified as rate limit", _is_rate_limit_error(500, "rate limit exceeded for model"))
check("3.5 HTTP 400 Bad Request is NOT classified as rate limit", not _is_rate_limit_error(400, "INVALID_ARGUMENT: Bad JSON"))
check("3.6 HTTP 404 Not Found is NOT classified as rate limit", not _is_rate_limit_error(404, "Model not found"))

# ─────────────────────────────────────────────────────────────────────────────
# Group 4: generate_content() Key Failover & Exhaustion Flow
# ─────────────────────────────────────────────────────────────────────────────
print("\nGroup 4: generate_content() Runtime Failover")

mock_settings = MagicMock()
mock_settings.gemini_model = "gemini-2.0-flash"
mock_settings.gemini_api_keys = ["mock_key_A", "mock_key_B"]

success_response = {
    "candidates": [
        {
            "content": {
                "parts": [{"text": "Success from rotated Key B!"}]
            }
        }
    ]
}
success_body = json.dumps(success_response).encode("utf-8")

def failover_urlopen(request, timeout=15):
    url = request.full_url if hasattr(request, "full_url") else request.get_full_url()
    if "mock_key_A" in url:
        fp = io.BytesIO(b'{"error": {"code": 429, "message": "Resource exhausted: quota exceeded"}}')
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, fp)
    elif "mock_key_B" in url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = success_body
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        return mock_resp
    raise RuntimeError(f"Unexpected URL in test: {url}")

# Reset global rotator state for clean test
with rotator._lock:
    rotator._exhausted.clear()
    rotator._current_index = 0

with patch("app.services.gemini.get_settings", return_value=mock_settings):
    with patch("urllib.request.urlopen", side_effect=failover_urlopen):
        result = generate_content("Test failover prompt")
        check("4.1 generate_content rotates past 429 Key A to Key B and succeeds",
              result == "Success from rotated Key B!", f"Got: {result}")
        check("4.2 Rotator marked Key A as exhausted",
              "mock_key_A" in rotator._exhausted)

# Test all keys exhausted
def all_429_urlopen(request, timeout=15):
    url = request.full_url if hasattr(request, "full_url") else request.get_full_url()
    fp = io.BytesIO(b'{"error": "RESOURCE_EXHAUSTED"}')
    raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, fp)

with patch("app.services.gemini.get_settings", return_value=mock_settings):
    with patch("urllib.request.urlopen", side_effect=all_429_urlopen):
        threw = False
        try:
            generate_content("Exhaustion test")
        except RuntimeError as e:
            threw = True
            check("4.3 generate_content raises descriptive RuntimeError when all keys exhausted",
                  "All configured Gemini API keys" in str(e) and "exhausted" in str(e),
                  f"Error: {e}")
        if not threw:
            check("4.3 generate_content raises descriptive RuntimeError when all keys exhausted", False, "Did not raise")

# Test fast fail on HTTP 400 (do not exhaust all keys for bad request)
call_count = 0
def bad_req_urlopen(request, timeout=15):
    global call_count
    call_count += 1
    url = request.full_url if hasattr(request, "full_url") else request.get_full_url()
    fp = io.BytesIO(b'{"error": "INVALID_ARGUMENT: Prompt violates safety rules"}')
    raise urllib.error.HTTPError(url, 400, "Bad Request", {}, fp)

with rotator._lock:
    rotator._exhausted.clear()
    rotator._current_index = 0

with patch("app.services.gemini.get_settings", return_value=mock_settings):
    with patch("urllib.request.urlopen", side_effect=bad_req_urlopen):
        try:
            generate_content("Bad request")
        except RuntimeError as e:
            check("4.4 Non-rate-limit 400 error fails fast on first key without draining all keys",
                  call_count == 1 and "400" in str(e),
                  f"Call count: {call_count}, Error: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# Group 5: /health Endpoint Multi-Key Status Reporting
# ─────────────────────────────────────────────────────────────────────────────
print("\nGroup 5: /health Endpoint Multi-Key Reporting")

# Clean rotator for health check
with rotator._lock:
    rotator._exhausted.clear()
    rotator._current_index = 0

# Import health handler directly
from app.main import health

health_report = health()
check("5.1 /health response contains gemini_configured", "gemini_configured" in health_report)
check("5.2 /health response contains gemini_keys_count", "gemini_keys_count" in health_report and isinstance(health_report["gemini_keys_count"], int))
check("5.3 /health response contains gemini_keys_status dict",
      "gemini_keys_status" in health_report and "total_keys" in health_report["gemini_keys_status"])
check("5.4 gemini_keys_status details total, active, exhausted keys",
      all(k in health_report["gemini_keys_status"] for k in ("total_keys", "active_keys", "exhausted_keys", "current_index")))

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 50)
print(f"Total Checks: {len(PASSED) + len(FAILED)} | Passed: {len(PASSED)} | Failed: {len(FAILED)}")
print("=" * 50)

if FAILED:
    print(f"\nFAILED CHECKS ({len(FAILED)}):")
    for f in FAILED:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("\nALL SECTION 6 TESTS PASSED!")
    sys.exit(0)
