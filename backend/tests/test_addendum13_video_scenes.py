"""F6 — video scene density and on-screen cleanliness.

Two reported defects in the last real video (video-14.mp4: 2 scenes x 30 s for
a 60-second video, citation markers reaching slide text):

  * one scene per ~8-12 s, so a 1-minute video has at least 5 scenes;
  * ``[Web 1: ...]`` / ``[Source: ...]`` / URLs never appear in narration,
    slide text or bullets.

Rendering itself (ffmpeg + TTS) is not exercised here — no network in the gate.
"""
from __future__ import annotations

import math

from app.services.video import _section_count, _sanitize_scene, strip_citations


def test_scene_count_matches_8_to_12_seconds_per_scene():
    """Demo-length videos (1-2 min) get one slide per ~10 s."""
    for minutes in (1, 2):
        scenes = _section_count(minutes)
        avg = (minutes * 60) / scenes
        assert scenes >= 5, f"{minutes}-minute video got only {scenes} scenes"
        assert 8 <= avg <= 12.5, f"{minutes}-minute video averages {avg:.1f}s per scene"


def test_scene_count_capped_for_long_videos():
    # A 20-minute video must not turn into 120 model calls.
    assert _section_count(20) <= 12


def test_citations_and_urls_are_stripped_from_scene_text():
    scene = {
        "title": "Evaporation [Web 2: Wikipedia]",
        "narration": "Water rises as vapour [Source: ECU-ITAI-3-04.pdf p.58]. See https://example.com/water",
        "content": "Sun heats the surface [1]",
        "bullets": ["Evaporation [Web 1: Some site]", "Visit www.example.org for more"],
        "diagram": "",
        "duration_seconds": 10,
    }
    cleaned = _sanitize_scene(scene)
    blob = " ".join([cleaned["title"], cleaned["narration"], cleaned["content"], *cleaned["bullets"]])
    assert "[Web" not in blob
    assert "[Source:" not in blob
    assert "http" not in blob
    assert "www." not in blob
    assert "[1]" not in blob
    # The real content survives.
    assert "Evaporation" in cleaned["title"]
    assert "vapour" in cleaned["narration"].lower()


def test_strip_citations_keeps_plain_text():
    assert strip_citations("Photosynthesis converts light into glucose.") == \
        "Photosynthesis converts light into glucose."
    assert math.isclose(1, 1)
