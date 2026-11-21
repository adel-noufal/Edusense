"""
Video script quality gate tests:
- word-count target from duration x WPM, Â±tolerance enforcement
- corrective LLM pass invoked when out of tolerance
- duplicate-scene detection and removal
- VideoStageError raised (never silent wrong-length script)
- scene padding never reuses content (no repeated paragraphs)
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import video as video_service
from app.services.video import (
    VideoStageError,
    _count_words,
    _normalize_narration,
    _within_tolerance,
    enforce_script_quality,
    find_duplicate_scene_pairs,
    generate_educational_video,
)


def _scene(text, title="Scene"):
    return {"title": title, "narration": text, "content": text,
            "highlight": "", "bullets": [], "duration_seconds": 8}


def _words(n, prefix="word"):
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_word_count_and_tolerance():
    assert _count_words("Hello world, this is a test.") == 6
    # 5 min * 140 wpm = 700 target; tolerance 10% -> [630, 770]
    with patch("app.services.video.get_settings") as gs:
        s = gs.return_value
        s.video_narration_wpm = 140.0
        s.video_script_tolerance = 0.10
        s.video_tts_timeout = 45.0
        assert _within_tolerance(700, 700)
        assert _within_tolerance(630, 700)
        assert _within_tolerance(770, 700)
        assert not _within_tolerance(500, 700)
        assert not _within_tolerance(900, 700)


def test_duplicate_detection():
    a = "Photosynthesis is the process by which plants convert sunlight into chemical energy using chlorophyll."
    b = "Photosynthesis is the process by which plants convert sunlight into chemical energy using chlorophyll!"
    c = "Mitosis is the division of a eukaryotic cell nucleus into two genetically identical daughter nuclei."
    scenes = [_scene(a, "A"), _scene(b, "B"), _scene(c, "C")]
    dups = find_duplicate_scene_pairs(scenes)
    assert len(dups) == 1 and dups[0][0] == 0 and dups[0][1] == 1
    # distinct scenes -> no dups
    assert find_duplicate_scene_pairs([_scene(c, "C"), _scene(_words(30, "other"), "D")]) == []


def test_enforce_passes_when_on_target():
    scenes = [_scene(_words(350, "alpha"), "S1"), _scene(_words(350, "beta"), "S2")]
    with patch("app.services.video.get_settings") as gs:
        gs.return_value.video_narration_wpm = 140.0
        gs.return_value.video_script_tolerance = 0.10
        out, warnings = enforce_script_quality(scenes, duration_min=5, title="T")
    assert len(out) == 2 and warnings == []


def test_enforce_drops_duplicates_when_llm_unavailable():
    a = _words(60, "same")
    scenes = [_scene(a, "S1"), _scene(a, "S2"), _scene(_words(580, "uniq"), "S3")]
    with patch("app.services.video.get_settings") as gs, \
         patch("app.services.video._llm_adjust_scenes", return_value=None):
        gs.return_value.video_narration_wpm = 140.0
        gs.return_value.video_script_tolerance = 0.10
        out, warnings = enforce_script_quality(scenes, duration_min=5, title="T")
    # later duplicate removed; remaining total 640 words within [630,770]
    assert len(out) == 2
    assert any("repeated" in w for w in warnings)


def test_enforce_raises_when_length_unfixable():
    scenes = [_scene(_words(50, "tiny"), "S1")]
    with patch("app.services.video.get_settings") as gs, \
         patch("app.services.video._llm_adjust_scenes", return_value=None):
        gs.return_value.video_narration_wpm = 140.0
        gs.return_value.video_script_tolerance = 0.10
        try:
            enforce_script_quality(scenes, duration_min=5, title="T")
            assert False, "expected VideoStageError"
        except VideoStageError as exc:
            assert exc.stage == "script_generation"
            assert exc.code == "LENGTH_OUT_OF_TOLERANCE"
            assert "700" in exc.user_message


def test_llm_corrective_pass_applied():
    short = [_scene(_words(100, "s"), "S1")]
    fixed = [_scene(_words(700, "expanded"), "S1")]
    with patch("app.services.video.get_settings") as gs, \
         patch("app.services.video._llm_adjust_scenes", return_value=fixed) as adj:
        gs.return_value.video_narration_wpm = 140.0
        gs.return_value.video_script_tolerance = 0.10
        out, _ = enforce_script_quality(short, duration_min=5, title="T")
    assert adj.called
    assert _count_words(out[0]["narration"]) == 700


def test_padding_never_repeats_content():
    """generate_educational_video must not pad scenes with recycled text."""
    lesson = {
        "duration": 5,
        "language": "English",
        "slides": [],
        "script": "First unique sentence about alpha beta gamma delta.\n\n"
                  "Second unique sentence about epsilon zeta eta theta.\n\n"
                  "Third unique sentence about iota kappa lambda mu.",
    }
    captured = {}

    def fake_tts(project_dir, scenes, lang):
        captured["scenes"] = [dict(s) for s in scenes]
        return True, "narration.mp3", []

    with patch("app.services.video.get_settings") as gs, \
         patch("app.services.video.generate_sectioned_scenes", return_value=None), \
         patch("app.services.video._tts_all_scenes", side_effect=fake_tts), \
         patch("app.services.video._write_player"), \
         patch("app.services.video._try_ffmpeg", return_value=None):
        gs.return_value.video_narration_wpm = 5.0   # tiny target so script passes
        gs.return_value.video_script_tolerance = 10.0
        gs.return_value.video_tts_timeout = 45.0
        result = generate_educational_video(999001, "PadTest", lesson)

    narrations = [s["narration"] for s in captured["scenes"]]
    assert len(narrations) == len(set(narrations)), "duplicate narration produced by padding"
