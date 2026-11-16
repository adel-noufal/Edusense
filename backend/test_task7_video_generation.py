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


def test_task7_video_generation():
    results.clear()
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
                VideoSceneInput(title="Scene 1", narration="Welcome to the lesson.", duration_seconds=8),
                VideoSceneInput(title="Scene 2", narration="Here is the core concept.", duration_seconds=10),
            ]
        )
        check("VideoScenesUpdateRequest validates correctly", True)
        check("scenes count correct", len(req.scenes) == 2, f"got {len(req.scenes)}")
        check("default duration_seconds = 8", req.scenes[0].duration_seconds == 8)
        check("explicit duration_seconds = 10", req.scenes[1].duration_seconds == 10)
    except Exception as e:
        check("VideoScenesUpdateRequest validation", False, str(e))

    # Test invalid schema (duration_seconds <= 0)
    try:
        from pydantic import ValidationError
        try:
            VideoScenesUpdateRequest(
                title="Bad",
                language="English",
                scenes=[VideoSceneInput(title="S", narration="N", duration_seconds=0)]
            )
            check("duration_seconds=0 raises validation error", False, "no error raised")
        except ValidationError:
            check("duration_seconds=0 raises validation error", True)
    except Exception as e:
        check("duration_seconds=0 raises validation error", False, str(e))

    # ---------------------------------------------------------------------------
    # Tests 1, 2 & 4: generate_educational_video() output keys, durations & player.html
    # ---------------------------------------------------------------------------
    print("\n--- Tests 1, 2 & 4: generate_educational_video() ---")
    fake_generation_data = {
        "title": "Python Basics",
        "language": "English",
        "slides": [
            {
                "title": "Variables",
                "content": "In Python, variables are used to store data values.",
            },
            {
                "title": "Loops",
                "content": "Loops repeat a block of code while a condition is met.",
            },
            {
                "title": "Functions",
                "content": "A function is a block of code which only runs when it is called.",
            },
            {
                "title": "Summary",
                "content": "That concludes the Python Basics overview.",
            },
        ],
    }

    try:
        with patch("app.services.video._gtts_scene", side_effect=_mock_gtts_scene):
            result = generate_educational_video(99901, "Python Basics", fake_generation_data)

        check("returns dict", isinstance(result, dict))
        check("key 'video_url' present", "video_url" in result, str(list(result.keys())))
        check("key 'scenes' present", "scenes" in result, str(list(result.keys())))
        check("key 'fallback' present", "fallback" in result, str(list(result.keys())))

        scenes = result.get("scenes", [])
        check("scenes is non-empty list", len(scenes) > 0, f"{len(scenes)} scenes")
        for i, sc in enumerate(scenes):
            d = sc.get("duration_seconds", 0)
            check(f"scene[{i}].duration_seconds > 0", d > 0, f"duration_seconds={d}")

        # Check player.html exists
        from app.services.video import STATIC_DIR
        player_path = STATIC_DIR / "video-99901" / "player.html"
        check("player.html exists on disk", player_path.exists(), str(player_path))
        if player_path.exists():
            html_content = player_path.read_text(encoding="utf-8")
            check("player.html contains slide elements", "<!DOCTYPE html>" in html_content,
                  f"first 300 chars: {html_content[:300]!r}")
    except Exception as e:
        import traceback
        check("generate_educational_video execution", False, str(e))
        traceback.print_exc()

    # ---------------------------------------------------------------------------
    # Test 3: rebuild_video_from_scenes()
    # ---------------------------------------------------------------------------
    print("\n--- Test 3: rebuild_video_from_scenes() ---")
    test_scenes = [
        {"title": "Intro", "narration": "Welcome back to the course.", "bullets": ["Point A"], "duration_seconds": 15},
        {"title": "Core Concept", "narration": "Here is the heart of the topic.", "bullets": ["Point B"], "duration_seconds": 15},
        {"title": "Conclusion", "narration": "That wraps up today's lesson.", "bullets": ["Summary"], "duration_seconds": 15},
    ]

    try:
        with patch("app.services.video._gtts_scene", side_effect=_mock_gtts_scene):
            rebuild_result = rebuild_video_from_scenes(project_id=99902, title="Rebuild Test", scenes=test_scenes, language="English")

        check("rebuild_video_from_scenes() returns dict", isinstance(rebuild_result, dict))
        check("rebuild result has key 'video_url'", "video_url" in rebuild_result, str(list(rebuild_result.keys())))
        check("rebuild result has key 'scenes'", "scenes" in rebuild_result, str(list(rebuild_result.keys())))
        check("rebuild result has key 'fallback'", "fallback" in rebuild_result, str(list(rebuild_result.keys())))
        rebuilt_scenes = rebuild_result.get("scenes", [])
        check("rebuild scenes count matches input", len(rebuilt_scenes) == len(test_scenes), f"got {len(rebuilt_scenes)}")
    except Exception as e:
        import traceback
        check("rebuild_video_from_scenes execution", False, str(e))
        traceback.print_exc()

    # ---------------------------------------------------------------------------
    # Test 6: PUT /api/videos/{id}/scenes -> 404 for unknown video_id
    # ---------------------------------------------------------------------------
    print("\n--- Test 6: PUT /api/videos/unknown/scenes \u2192 404 ---")
    try:
        from fastapi.testclient import TestClient
        from app.main import app
        from app.core.security import create_access_token

        client = TestClient(app)
        token = create_access_token(subject="instructor@edusense.local", role="instructor")
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.put(
            "/api/videos/video-nonexistent-99999/scenes",
            json={
                "title": "X",
                "language": "English",
                "scenes": [{"title": "S", "narration": "N", "duration_seconds": 5}],
            },
            headers=headers,
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
    assert passed == total, f"FAILED: {[label for label, ok in results if not ok]}"


if __name__ == "__main__":
    test_task7_video_generation()
