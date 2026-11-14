"""
test_task7_video_generation.py
Task 7 — Video Tab: Editing Controls & Generation Overhaul
Tests:
  1. generate_educational_video() returns correct keys
  2. Each scene has duration_seconds > 0
  3. rebuild_video_from_scenes() with 3 test scenes returns valid result dict
  4. Player HTML file is written to disk after generate_educational_video()
  5. VideoScenesUpdateRequest schema validates correctly
  6. PUT /api/videos/{id}/scenes returns 404 for unknown video_id (via TestClient)
  7. Import of rebuild_video_from_scenes from app.services.video works
"""
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results = []


def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    results.append((label, condition))


# ---------------------------------------------------------------------------
# TTS mock: prevent real HTTP calls during tests
# ---------------------------------------------------------------------------
def _mock_gtts_scene(text, out_path, lang="en"):
    """Write a tiny dummy MP3 header so the file passes size checks."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(b"\xff\xfb" + b"\x00" * 200)
    return True


# ---------------------------------------------------------------------------
# Test 7: Import
# ---------------------------------------------------------------------------
print("\n--- Test 7: Import ---")
try:
    from app.services.video import rebuild_video_from_scenes, generate_educational_video
    check("import rebuild_video_from_scenes", True)
    check("import generate_educational_video", True)
except Exception as e:
    check("import rebuild_video_from_scenes", False, str(e))
    check("import generate_educational_video", False, str(e))

# ---------------------------------------------------------------------------
# Test 5: VideoScenesUpdateRequest schema
# ---------------------------------------------------------------------------
print("\n--- Test 5: Schema ---")
try:
    from app.schemas.schemas import VideoScenesUpdateRequest, VideoSceneInput
    req = VideoScenesUpdateRequest(
        title="Test Video",
        language="English",
        scenes=[
            VideoSceneInput(title="Scene 1", narration="Hello world", duration_seconds=10),
            VideoSceneInput(title="Scene 2", narration="Second scene"),
        ]
    )
    check("VideoScenesUpdateRequest validates correctly", True)
    check("scenes count correct", len(req.scenes) == 2, f"got {len(req.scenes)}")
    check("default duration_seconds = 8", req.scenes[1].duration_seconds == 8)
    check("explicit duration_seconds = 10", req.scenes[0].duration_seconds == 10)
    # Boundary: too-small duration should raise ValidationError
    try:
        VideoSceneInput(title="bad", narration="x", duration_seconds=0)
        check("duration_seconds=0 raises validation error", False, "no error raised")
    except Exception:
        check("duration_seconds=0 raises validation error", True)
except Exception as e:
    check("schema import/validation", False, str(e))

# ---------------------------------------------------------------------------
# Tests 1, 2, 4: generate_educational_video() — mocking _gtts_scene
# generate_educational_video(project_id, title, lesson: dict) where lesson
# has keys: slides, duration, language, script
# ---------------------------------------------------------------------------
print("\n--- Tests 1, 2 & 4: generate_educational_video() ---")

FAKE_LESSON = {
    "duration": 1,
    "language": "English",
    "script": "Welcome to Python. Python is a language. It is easy to learn.",
    "slides": [
        {"title": "Introduction", "content": "Welcome to Python programming."},
        {"title": "Variables", "content": "Variables store data values in Python."},
        {"title": "Summary", "content": "Python is powerful and easy to learn."},
    ],
}

try:
    import app.services.video as _vid_mod

    with patch.object(_vid_mod, "_gtts_scene", side_effect=_mock_gtts_scene):
        result = generate_educational_video(
            project_id=99901,
            title="Python Basics",
            lesson=FAKE_LESSON,
        )

    check("returns dict", isinstance(result, dict))
    for key in ("video_url", "scenes", "fallback"):
        check(f"key '{key}' present", key in result, str(list(result.keys())))
    scenes = result.get("scenes", [])
    check("scenes is non-empty list", isinstance(scenes, list) and len(scenes) > 0, f"{len(scenes)} scenes")
    for i, s in enumerate(scenes):
        dur = s.get("duration_seconds", 0)
        check(f"scene[{i}].duration_seconds > 0", dur > 0, f"duration_seconds={dur}")

    # Test 4: Player HTML on disk
    from app.services.video import STATIC_DIR
    player_path = STATIC_DIR / "video-99901" / "player.html"
    check("player.html exists on disk", player_path.exists(), str(player_path))
    if player_path.exists():
        content = player_path.read_text(encoding="utf-8")
        check(
            "player.html contains slide elements",
            ".slide" in content or "data-dur" in content or "slideDurations" in content,
            f"first 300 chars: {content[:300]!r}"
        )
except Exception as e:
    import traceback
    check("generate_educational_video() ran without exception", False, str(e))
    traceback.print_exc()

# ---------------------------------------------------------------------------
# Test 3: rebuild_video_from_scenes()
# ---------------------------------------------------------------------------
print("\n--- Test 3: rebuild_video_from_scenes() ---")
TEST_SCENES = [
    {"title": "Introduction", "narration": "Welcome to this lesson.", "content": "Overview.",
     "highlight": "", "bullets": ["Point A", "Point B"], "duration_seconds": 6},
    {"title": "Main Concept", "narration": "Here is the main idea.", "content": "Main body.",
     "highlight": "Important!", "bullets": ["Key 1"], "duration_seconds": 8},
    {"title": "Summary", "narration": "That concludes our lesson.", "content": "Summary.",
     "highlight": "", "bullets": [], "duration_seconds": 5},
]
try:
    import app.services.video as _vid_mod2
    with patch.object(_vid_mod2, "_gtts_scene", side_effect=_mock_gtts_scene):
        rebuild_result = rebuild_video_from_scenes(
            project_id=99902,
            title="Rebuild Test Video",
            scenes=TEST_SCENES,
            language="English",
            re_tts=False,   # don't call TTS; just re-render player
        )
    check("rebuild_video_from_scenes() returns dict", isinstance(rebuild_result, dict))
    for key in ("video_url", "scenes", "fallback"):
        check(f"rebuild result has key '{key}'", key in rebuild_result, str(list(rebuild_result.keys())))
    r_scenes = rebuild_result.get("scenes", [])
    check("rebuild scenes count matches input", len(r_scenes) == 3, f"got {len(r_scenes)}")
except Exception as e:
    import traceback
    check("rebuild_video_from_scenes() ran without exception", False, str(e))
    traceback.print_exc()

# ---------------------------------------------------------------------------
# Test 6: PUT /api/videos/{id}/scenes → 404 for unknown id
# ---------------------------------------------------------------------------
print("\n--- Test 6: PUT /api/videos/unknown/scenes → 404 ---")
try:
    os.environ.setdefault("DATABASE_URL", "sqlite:///./test_task7.db")
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.put(
        "/api/videos/nonexistent-video-id-99/scenes",
        json={
            "title": "X",
            "language": "English",
            "scenes": [{"title": "S", "narration": "N", "duration_seconds": 5}],
        },
    )
    check("PUT /api/videos/unknown/scenes returns 404", resp.status_code == 404,
          f"got {resp.status_code}: {resp.text[:200]}")
except Exception as e:
    import traceback
    check("TestClient PUT /api/videos/unknown/scenes", False, str(e))
    traceback.print_exc()

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"Results: {passed}/{total} passed")
if passed == total:
    print("ALL TESTS PASSED")
else:
    failed = [label for label, ok in results if not ok]
    print("FAILED:\n  " + "\n  ".join(failed))
    sys.exit(1)
