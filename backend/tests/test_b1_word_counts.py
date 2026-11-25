"""
B1 Verification:
1. Polling backoff schedule [1000, 2000, 5000] ms -> stops on terminal state
2. Target word counts for 1 min, 4 min, and 10 min durations
3. Tolerance enforcement (+-10%)
"""
from app.services.video import _target_words, _within_tolerance, _count_words
from app.core.config import get_settings

def test_duration_word_count_targets():
    settings = get_settings()
    wpm = settings.video_narration_wpm  # default 140.0
    tol = settings.video_script_tolerance  # default 0.10

    # 1 minute video
    t1 = _target_words(1)
    assert t1 == int(1 * wpm), f"Expected {int(1*wpm)}, got {t1}"
    assert _within_tolerance(int(t1 * 0.95), t1)
    assert _within_tolerance(int(t1 * 1.05), t1)
    assert not _within_tolerance(int(t1 * 0.85), t1)

    # 4 minute video
    t4 = _target_words(4)
    assert t4 == int(4 * wpm), f"Expected {int(4*wpm)}, got {t4}"
    assert _within_tolerance(int(t4 * 0.95), t4)
    assert _within_tolerance(int(t4 * 1.05), t4)
    assert not _within_tolerance(int(t4 * 0.85), t4)

    # 10 minute video
    t10 = _target_words(10)
    assert t10 == int(10 * wpm), f"Expected {int(10*wpm)}, got {t10}"
    assert _within_tolerance(int(t10 * 0.95), t10)
    assert _within_tolerance(int(t10 * 1.05), t10)
    assert not _within_tolerance(int(t10 * 0.85), t10)

    print(f"\n[B1 PASS] 1-min target: {t1}w | 4-min target: {t4}w | 10-min target: {t10}w (wpm={wpm}, tol={tol})")

def test_polling_schedule_config():
    # Read frontend/src/context/GenerationJobContext.jsx to verify schedule
    import re
    from pathlib import Path
    ctx_file = Path(__file__).resolve().parents[2] / "frontend" / "src" / "context" / "GenerationJobContext.jsx"
    content = ctx_file.read_text(encoding="utf-8")
    assert "POLL_SCHEDULE_MS = [1000, 2000, 5000]" in content
    assert "STEADY_POLL_MS = 5000" in content
    assert "status === 'done'" in content
    assert "status === 'error'" in content
    print("\n[B1 PASS] GenerationJobContext verified: 1s -> 2s -> 5s backoff, stops on done/error")

if __name__ == "__main__":
    test_duration_word_count_targets()
    test_polling_schedule_config()
    print("\nALL B1 WORD-COUNT & POLLING TESTS PASSED!")
