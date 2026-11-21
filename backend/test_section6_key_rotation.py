"""
Section 6 Verification Test — Multi-API-Key + Model-Chain Rotation for Gemini
Tests:
1. Settings parses multiple keys from comma-delimited strings and numbered env variables.
2. Key deduping, empty-string removal, and whitespace trimming.
3. Key masking security check (only first 4 and last 4 characters revealed).
4. GeminiRotator pair iteration: keys round-robin within each model, models in order.
5. Cooldown: failed (key, model) pairs are skipped until backoff expires.
6. Error classification: rotatable vs non-rotatable.
7. generate_content() rotates key on 429 then succeeds; falls back across models.
8. generate_content() raises typed GeminiError when all pairs exhausted.
9. Non-rotatable 400 raises immediately without rotation.
10. /health endpoint reports gemini_configured, gemini_keys_count, gemini_keys_status.
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

from app.core.config import Settings
from app.services.gemini import (
    GeminiError,
    GeminiRotator,
    _is_rate_limit_error,
    _is_rotatable_error,
    generate_content,
    rotator,
)


def _mock_settings(keys, model="gemini-2.0-flash"):
    """Build a settings-like object with explicit string attrs (avoids MagicMock pitfalls)."""
    s = MagicMock()
    s.gemini_api_keys = keys
    s.gemini_model = model
    s.gemini_models = ""
    s.gemini_models_chat = ""
    s.gemini_models_script = ""
    return s


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

    print("\n=== Section 6 Verification: Multi-Key + Model-Chain Rotation ===\n")

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

    # ─────────────────────────────────────────────────────────────────────────────
    # Group 2: Key Masking Security Check
    # ─────────────────────────────────────────────────────────────────────────────
    print("\nGroup 2: Key Masking Security Check")

    test_rotator = GeminiRotator()
    masked_long = test_rotator.mask_key("AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6")
    check("2.1 Long key masked correctly (first 4 and last 4 chars only)",
          masked_long == "AIza...O5P6",
          f"Got: {masked_long}")

    masked_short = test_rotator.mask_key("short")
    check("2.2 Short string (<8 chars) returns '***' completely obscured", masked_short == "***", f"Got: {masked_short}")
    check("2.3 None/empty returns '***'", test_rotator.mask_key("") == "***")

    # ─────────────────────────────────────────────────────────────────────────────
    # Group 3: Model chains & pair iteration order
    # ─────────────────────────────────────────────────────────────────────────────
    print("\nGroup 3: Model Chains & (key x model) Pair Iteration")

    r = GeminiRotator()
    with patch("app.services.gemini.get_settings", return_value=_mock_settings(
            ["K1", "K2"], model="gemini-primary")):
        chain = r.model_chain("chat")
        check("3.1 Primary configured model leads the chain", chain[0] == "gemini-primary", f"Got: {chain}")
        check("3.2 Default fallback models appended", "gemini-2.5-flash" in chain and "gemini-flash-latest" in chain, f"Got: {chain}")
        check("3.3 Chain has no duplicates", len(chain) == len(set(chain)), f"Got: {chain}")

        pairs = list(r.iter_pairs(["m1", "m2"]))
        # Expect: all keys for m1 (round-robin), then all keys for m2
        order = [(p[2], p[1]) for p in pairs]
        check("3.4 Models iterated in order, keys inner", order == [("m1", "K1"), ("m1", "K2"), ("m2", "K1"), ("m2", "K2")],
              f"Got: {order}")

        # After success on key index 1, next iteration starts at key index 0
        r.mark_success(1, "m1")
        pairs2 = list(r.iter_pairs(["m1"]))
        check("3.5 Round-robin advances after success", pairs2[0][1] == "K1", f"Got: {pairs2}")

        # Cooldown: fail (0, m1) -> skipped
        r.reset()
        r.mark_failure(0, "m1", None, "429 test")
        pairs3 = list(r.iter_pairs(["m1"]))
        check("3.6 Cooled-down pair is skipped", all(p[0] != 0 for p in pairs3), f"Got: {pairs3}")

        # All pairs cooled -> empty
        r.mark_failure(1, "m1", None, "429 test")
        pairs4 = list(r.iter_pairs(["m1"]))
        check("3.7 All cooled pairs yield nothing", pairs4 == [], f"Got: {pairs4}")

    # ─────────────────────────────────────────────────────────────────────────────
    # Group 4: Error classification
    # ─────────────────────────────────────────────────────────────────────────────
    print("\nGroup 4: Error Classification")

    check("4.1 429 rotatable", _is_rotatable_error(429, "RESOURCE_EXHAUSTED") is True)
    check("4.2 503 rotatable", _is_rotatable_error(503, "overloaded") is True)
    check("4.3 404 model-not-found rotatable (falls to next model)", _is_rotatable_error(404, "model not found") is True)
    check("4.4 invalid API key rotatable", _is_rotatable_error(400, '{"error":{"message":"API_KEY_INVALID"}}') is True)
    check("4.5 permission denied rotatable", _is_rotatable_error(403, "PERMISSION_DENIED") is True)
    check("4.6 generic 400 NOT rotatable", _is_rotatable_error(400, "Invalid JSON payload") is False)
    check("4.7 safety block NOT rotatable", _is_rotatable_error(400, "blocked due to safety settings") is False)
    check("4.8 rate-limit alias", _is_rate_limit_error(429, "") is True)

    # ─────────────────────────────────────────────────────────────────────────────
    # Group 5: End-to-End Failover in generate_content()
    # ─────────────────────────────────────────────────────────────────────────────
    print("\nGroup 5: End-to-End Failover in generate_content()")

    rotator.reset()
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

    with patch("app.services.gemini.get_settings", return_value=_mock_settings(mock_keys_e2e)):
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            try:
                res_text = generate_content("Test prompt for rotation")
                check("5.1 generate_content rotates past 429 to succeed with Key 2",
                      res_text == "Hello from Gemini Key 2!",
                      f"Got: {res_text}")
                gen_calls = [u for u in call_log if "generateContent" in u]
                check("5.2 Both keys attempted in order",
                      len(gen_calls) == 2 and "FailKey_1111" in gen_calls[0] and "SuccessKey_2222" in gen_calls[1],
                      f"Call log: {gen_calls}")
            except Exception as exc:
                check("5.1 generate_content rotation failed", False, str(exc))

    # Model fallback: key1 fails on model A (404), same key succeeds on model B
    rotator.reset()
    call_log.clear()
    good_key = ["OnlyKey_9999"]

    def fake_urlopen_models(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        call_log.append(url)
        if "model-a" in url:
            fp = io.BytesIO(b'{"error": {"code": 404, "message": "model not found"}}')
            raise urllib.error.HTTPError(url, 404, "Not Found", hdrs={}, fp=fp)
        if "model-b" in url:
            return mock_success_response
        raise RuntimeError(f"Unexpected URL: {url}")

    s_models = _mock_settings(good_key, model="model-a")
    s_models.gemini_models = "model-a,model-b"
    with patch("app.services.gemini.get_settings", return_value=s_models):
        with patch("urllib.request.urlopen", side_effect=fake_urlopen_models):
            try:
                res_text = generate_content("model fallback test")
                check("5.3 Falls back to next model on 404", res_text == "Hello from Gemini Key 2!", f"Got: {res_text}")
                check("5.4 model-a tried before model-b", "model-a" in call_log[0] and "model-b" in call_log[-1],
                      f"Call log: {call_log}")
            except Exception as exc:
                check("5.3 model fallback failed", False, str(exc))

    # All pairs exhausted -> typed GeminiError
    rotator.reset()
    def fake_urlopen_all_fail(req, timeout=15):
        fp = io.BytesIO(b'{"error": {"code": 429, "message": "quota"}}')
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many", hdrs={}, fp=fp)

    s_one = _mock_settings(["K1"], model="m-x")
    s_one.gemini_models = "m-x"   # single model -> single pair
    with patch("app.services.gemini.get_settings", return_value=s_one):
        with patch("urllib.request.urlopen", side_effect=fake_urlopen_all_fail):
            try:
                generate_content("will fail")
                check("5.5 exhausted pairs raise", False, "no exception")
            except GeminiError as exc:
                check("5.5 typed GeminiError raised", exc.code == GeminiError.QUOTA_EXHAUSTED, f"code={exc.code}")
            except Exception as exc:
                check("5.5 typed GeminiError raised", False, f"wrong type: {type(exc)} {exc}")

    # Non-rotatable 400 -> immediate raise, no rotation
    rotator.reset()
    call_log.clear()

    def fake_urlopen_400(req, timeout=15):
        call_log.append(req.full_url)
        raise MockHTTP400()

    with patch("app.services.gemini.get_settings", return_value=_mock_settings(["K1", "K2"], model="m-y")):
        # force single-model chain to keep it fast
        s400 = _mock_settings(["K1", "K2"], model="m-y")
        s400.gemini_models = "m-y"
        with patch("app.services.gemini.get_settings", return_value=s400):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen_400):
                threw = False
                try:
                    generate_content("Bad syntax request")
                except GeminiError as exc:
                    threw = exc.code == GeminiError.INVALID_REQUEST and "400" in str(exc)
                except RuntimeError as exc:
                    threw = "400" in str(exc)
                check("5.6 Non-rotatable 400 raises immediately (1 attempt)", threw and len(call_log) == 1,
                      f"calls={len(call_log)}")

    # ─────────────────────────────────────────────────────────────────────────────
    # Group 6: /health Endpoint Key Pool Status
    # ─────────────────────────────────────────────────────────────────────────────
    print("\nGroup 6: Health Check Inspection")

    rotator.reset()
    from app.main import health

    health_report = health()
    check("6.1 /health response contains gemini_configured", "gemini_configured" in health_report)
    check("6.2 /health response contains gemini_keys_count", "gemini_keys_count" in health_report and isinstance(health_report["gemini_keys_count"], int))
    check("6.3 /health response contains gemini_keys_status dict",
          "gemini_keys_status" in health_report and "total_keys" in health_report["gemini_keys_status"])
    ks = health_report["gemini_keys_status"]
    check("6.4 status reports pairs matrix", "pairs" in ks and isinstance(ks["pairs"], list), f"Got keys: {list(ks.keys())}")
    if ks.get("pairs"):
        p = ks["pairs"][0]
        check("6.5 pair entries have masked key + model + cooldown state",
              all(k in p for k in ("key_index", "key_masked", "model", "cooling_down")),
              f"Got: {p}")
        check("6.6 no raw key material in status", all(len(str(p.get("key_masked", ""))) <= 12 for p in ks["pairs"]),
              "key_masked too long")

    print("\n" + "=" * 50)
    print(f"Total Checks: {len(PASSED) + len(FAILED)} | Passed: {len(PASSED)} | Failed: {len(FAILED)}")
    print("=" * 50)
    assert len(FAILED) == 0, f"Failed checks: {FAILED}"


if __name__ == "__main__":
    test_section6()
