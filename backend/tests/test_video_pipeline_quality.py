"""Video pipeline quality: planning, per-scene timing, de-duplication and rejection.

Covers the defects seen in a real generated MP4:
  * duration did not follow the requested length (too few scenes / too few words)
  * every slide sat on screen for a fixed time instead of its narration length
  * the same bullets were rendered twice (paragraph + list)
  * template placeholders and citation markers reached the slide
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import video as video_service
from app.services.video import (
    SCENE_PAUSE_SECONDS,
    VideoStageError,
    _section_count,
    _target_words,
    apply_measured_durations,
    build_slide_text,
    dedupe_bullets,
    is_placeholder,
    reject_placeholders,
    sanitize_bullets,
    strip_citations,
    write_srt,
)


def _settings(wpm: float = 140.0, tolerance: float = 0.10) -> SimpleNamespace:
    return SimpleNamespace(
        video_narration_wpm=wpm,
        video_script_tolerance=tolerance,
        video_tts_timeout=45.0,
    )


def _scene(title: str, narration: str, bullets=None, duration: int = 8) -> dict:
    return {"title": title, "narration": narration, "content": narration,
            "highlight": "", "bullets": bullets or [], "duration_seconds": duration}


# ---------------------------------------------------------------------------
# 1. Duration / word-count planning
# ---------------------------------------------------------------------------

def test_word_target_scales_with_duration():
    with patch("app.services.video.get_settings", return_value=_settings()):
        assert _target_words(1) == 140
        assert _target_words(3) == 420
        # 3 minutes at 140 wpm has to land near the 400-450 word expectation.
        assert 400 <= _target_words(3) <= 450


def test_scene_count_provides_enough_slides():
    # A 17-second video with 4 slides was the reported defect.
    assert _section_count(1) >= 5
    assert _section_count(3) >= 5


# ---------------------------------------------------------------------------
# 2. Per-scene timing comes from the narration audio
# ---------------------------------------------------------------------------

def test_scene_duration_is_measured_audio_plus_pause(tmp_path):
    scenes = [_scene("A", "First scene narration text here.", duration=45),
              _scene("B", "Second scene narration text here.", duration=45)]
    for index in range(2):
        (tmp_path / f"segment-{index}-audio.mp3").write_bytes(b"\xff\xfb" + b"\x00" * 300)

    with patch("app.services.video._probe_audio_duration", side_effect=[10.2, 3.1]):
        measured = apply_measured_durations(tmp_path, scenes)

    assert measured == 2
    assert scenes[0]["audio_seconds"] == 10.2
    # measured length + pause, never the 45 s that was hard-coded before
    assert scenes[0]["duration_seconds"] == int(-(-(10.2 + SCENE_PAUSE_SECONDS) // 1))
    assert scenes[1]["duration_seconds"] == int(-(-(3.1 + SCENE_PAUSE_SECONDS) // 1))
    assert scenes[0]["duration_seconds"] != 45


def test_scene_duration_falls_back_to_word_count_when_unprobeable(tmp_path):
    narration = " ".join(f"word{i}" for i in range(70))
    scenes = [_scene("A", narration)]
    with patch("app.services.video._probe_audio_duration", return_value=None), \
         patch("app.services.video.get_settings", return_value=_settings()):
        measured = apply_measured_durations(tmp_path, scenes)
    assert measured == 0
    # 70 words at 140 wpm = 30 s of narration
    assert 28 <= scenes[0]["duration_seconds"] <= 32


# ---------------------------------------------------------------------------
# 3. Bullet de-duplication and on-screen text
# ---------------------------------------------------------------------------

def test_bullets_are_deduplicated_case_and_punctuation_insensitive():
    out = dedupe_bullets(["Gradient descent", "gradient descent!", "Learning rate",
                          "Gradient  descent."])
    assert out == ["Gradient descent", "Learning rate"]


def test_bullets_are_capped_and_shortened():
    items = ["Real point number %d about the topic" % i for i in range(9)]
    out = sanitize_bullets(items)
    assert len(out) == 5
    assert all(len(item) <= 80 for item in out)


def test_slide_text_never_repeats_the_narration():
    narration = ("Backpropagation computes the gradient of the loss with respect to "
                 "every weight in the network. It reuses the chain rule.")
    scene = _scene("Backpropagation", narration, bullets=["Chain rule reuse", "Gradient of loss"])
    title, bullets = build_slide_text(scene)
    assert title == "Backpropagation"
    assert bullets == ["Chain rule reuse", "Gradient of loss"]
    assert narration not in " ".join([title, *bullets])


# ---------------------------------------------------------------------------
# 4. Citations and placeholders never reach the slide
# ---------------------------------------------------------------------------

def test_citations_and_urls_are_stripped():
    assert strip_citations("Evaporation [Web 1: Wikipedia]") == "Evaporation"
    assert strip_citations("See https://example.com/water for more") == "See for more"
    assert strip_citations("Water rises [Source: notes.pdf p.3]") == "Water rises"


def test_placeholder_and_filler_bullets_are_recognised():
    assert is_placeholder("[Input Context] -> [... Engine] -> [Optimized Outcome]")
    assert is_placeholder("Why top organizations leverage this concept")
    assert not is_placeholder("Gradient descent minimises the loss")


def test_sanitize_bullets_drops_placeholders():
    out = sanitize_bullets([
        "[Input Context] -> [... Engine] -> [Optimized Outcome]",
        "Why top organizations leverage this concept",
        "Gradient descent minimises the loss",
    ])
    assert out == ["Gradient descent minimises the loss"]


def test_reject_placeholders_raises_instead_of_rendering_template_text():
    scenes = [_scene("Training", "Real narration.",
                     bullets=["[Input Context] -> [... Engine] -> [Optimized Outcome]"])]
    with pytest.raises(VideoStageError) as excinfo:
        reject_placeholders(scenes)
    assert excinfo.value.code == "PLACEHOLDER_CONTENT"
    assert excinfo.value.stage == "script_generation"

    # A clean script passes.
    reject_placeholders([_scene("Training", "Real narration.", bullets=["Real key point"])])


# ---------------------------------------------------------------------------
# 5. Narration is delivered as subtitles, with sequential timing
# ---------------------------------------------------------------------------

def test_srt_timing_is_sequential_and_covers_every_scene(tmp_path):
    scenes = [_scene("A", "First sentence. Second sentence.", duration=10),
              _scene("B", "Another sentence entirely.", duration=6)]
    path = write_srt(tmp_path, scenes)
    assert path is not None
    content = path.read_text(encoding="utf-8")
    stamps = re.findall(r"(\d\d:\d\d:\d\d,\d\d\d) --> (\d\d:\d\d:\d\d,\d\d\d)", content)

    def seconds(value: str) -> float:
        hms, millis = value.split(",")
        h, m, s = (int(part) for part in hms.split(":"))
        return h * 3600 + m * 60 + s + int(millis) / 1000

    assert stamps, "no subtitle cues were written"
    previous_end = -1.0
    for start, end in stamps:
        assert seconds(start) >= previous_end - 0.001
        assert seconds(end) > seconds(start)
        previous_end = seconds(end)
    assert seconds(stamps[-1][1]) <= 16.5
    assert "First sentence." in content


# ---------------------------------------------------------------------------
# 6. Player markup: one title, key points once, narration only in transcript
# ---------------------------------------------------------------------------

def test_player_shows_each_bullet_once_and_no_narration_paragraph(tmp_path):
    narration = "This is the spoken narration that belongs in subtitles only."
    scenes = [_scene("Slide title", narration, bullets=["Point one", "Point two"])]
    video_service._write_player(tmp_path, "Deck", scenes, "narration.mp3")

    html_text = (tmp_path / "player.html").read_text(encoding="utf-8")
    slide_markup = html_text.split('<section class="slide', 1)[1].split("</section>", 1)[0]
    assert slide_markup.count("Point one") == 1
    assert slide_markup.count("Point two") == 1
    assert narration not in slide_markup
    # the narration still exists in the transcript panel
    assert narration in html_text


def test_player_is_rtl_for_arabic(tmp_path):
    scenes = [_scene("عنوان", "نص عربي.", bullets=["نقطة أولى"])]
    video_service._write_player(tmp_path, "درس", scenes, None, rtl=True)
    html_text = (tmp_path / "player.html").read_text(encoding="utf-8")
    assert 'dir="rtl"' in html_text
    assert 'lang="ar"' in html_text
    assert "Noto Sans Arabic" in html_text
