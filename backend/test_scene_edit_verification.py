"""
Verification test for BUG 3: Save Scene Edits & Re-render
Tests that editing a scene's narration actually updates the player.html content.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from app.services.video import rebuild_video_from_scenes

def test_player_html_updates():
    """Verify that rebuild_video_from_scenes actually updates player.html with new narration."""
    
    print("\n=== Scene Edit Verification Test ===\n")
    
    # Initial scenes
    initial_scenes = [
        {"title": "Intro", "narration": "Original text here", "bullets": ["Point A"], "duration_seconds": 10},
        {"title": "Concept", "narration": "Another original text", "bullets": ["Point B"], "duration_seconds": 10},
    ]
    
    # Rebuild with initial scenes
    result1 = rebuild_video_from_scenes(
        project_id=99999,
        title="Test Video",
        scenes=initial_scenes,
        language="English",
        re_tts=False,  # Skip TTS for this test
    )
    
    player_path = Path("app/static/videos/video-99999/player.html")
    if not player_path.exists():
        print("FAIL: player.html not created")
        return False
    
    initial_html = player_path.read_text(encoding="utf-8")
    
    # Verify initial narration is in HTML
    if "Original text here" not in initial_html:
        print("FAIL: Initial narration not found in player.html")
        return False
    print("PASS: Initial narration found in player.html")
    
    # Edit scenes with obviously different text
    edited_scenes = [
        {"title": "Intro", "narration": "EDITED TEXT - OBVIOUSLY DIFFERENT", "bullets": ["Point A"], "duration_seconds": 10},
        {"title": "Concept", "narration": "Another original text", "bullets": ["Point B"], "duration_seconds": 10},
    ]
    
    # Rebuild with edited scenes
    result2 = rebuild_video_from_scenes(
        project_id=99999,
        title="Test Video",
        scenes=edited_scenes,
        language="English",
        re_tts=False,
    )
    
    # Read updated HTML
    updated_html = player_path.read_text(encoding="utf-8")
    
    # Verify edited narration is in HTML
    if "EDITED TEXT - OBVIOUSLY DIFFERENT" not in updated_html:
        print("FAIL: Edited narration NOT found in player.html after rebuild")
        print(f"HTML preview: {updated_html[:500]}")
        return False
    print("PASS: Edited narration found in player.html after rebuild")
    
    # Verify old narration is gone
    if "Original text here" in updated_html:
        print("FAIL: Old narration still present in player.html")
        return False
    print("PASS: Old narration removed from player.html")
    
    # Verify scenes.json was also updated
    scenes_json_path = Path("app/static/videos/video-99999/scenes.json")
    if scenes_json_path.exists():
        scenes_data = json.loads(scenes_json_path.read_text(encoding="utf-8"))
        if scenes_data["scenes"][0]["narration"] == "EDITED TEXT - OBVIOUSLY DIFFERENT":
            print("PASS: scenes.json also updated with new narration")
        else:
            print("FAIL: scenes.json not updated correctly")
            return False
    
    print("\n=== All checks passed - scene edits DO update the video ===\n")
    return True

if __name__ == "__main__":
    test_player_html_updates()
