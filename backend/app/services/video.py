"""
video.py — Educational Video Generation Service

Improvements (Task 7):
- Per-scene TTS using gTTS (each scene narration → individual MP3 segment)
- Per-scene `duration_seconds` wired through ffmpeg: segment video matches actual audio length
- ffmpeg concat now muxes per-scene audio into each video segment (audio+video)
- Player slide durations driven by scene `duration_seconds` (ms), not a fixed 6500ms interval
- `rebuild_player_from_scenes()` — idempotent re-render of player + optionally re-TTS + ffmpeg stitch
  called by the new `PUT /api/videos/{id}/scenes` endpoint
"""
from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

STATIC_DIR = Path(__file__).resolve().parents[1] / "static" / "videos"

DEFAULT_SCENE_SECONDS = 8   # fallback when duration_seconds is 0 / missing
MIN_SCENE_SECONDS = 2
MAX_SCENE_SECONDS = 300


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _bullet_html(items: list[str]) -> str:
    if not items:
        return ""
    rows = "".join(f"<li>{html.escape(str(item))}</li>" for item in items if item)
    return f"<ul class='bullets'>{rows}</ul>"


def _split_bullets(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"[.\n•\-]+", text)
    return [part.strip() for part in parts if len(part.strip()) > 12][:4]


def _clamp_duration(secs: int | float | None) -> int:
    if not secs:
        return DEFAULT_SCENE_SECONDS
    return max(MIN_SCENE_SECONDS, min(MAX_SCENE_SECONDS, int(secs)))


def _lang_code(language: str) -> str:
    lang = (language or "English").lower()
    if "arab" in lang:
        return "ar"
    if "french" in lang or "français" in lang:
        return "fr"
    if "spanish" in lang or "español" in lang:
        return "es"
    if "german" in lang or "deutsch" in lang:
        return "de"
    if "portuguese" in lang:
        return "pt"
    if "italian" in lang:
        return "it"
    if "russian" in lang:
        return "ru"
    if "chinese" in lang:
        return "zh"
    if "japanese" in lang:
        return "ja"
    if "korean" in lang:
        return "ko"
    if "hindi" in lang:
        return "hi"
    if "turkish" in lang:
        return "tr"
    return "en"


# ---------------------------------------------------------------------------
# Per-scene TTS
# ---------------------------------------------------------------------------

def _gtts_scene(text: str, out_path: Path, lang: str = "en") -> bool:
    """Synthesise speech for a single scene narration. Returns True on success."""
    try:
        from gtts import gTTS
    except ImportError:
        return False
    try:
        gTTS(text=text[:3000], lang=lang).save(str(out_path))
        return out_path.exists() and out_path.stat().st_size > 100
    except Exception:
        return False


def _tts_all_scenes(
    project_dir: Path,
    scenes: list[dict],
    lang_code: str,
) -> tuple[bool, str | None]:
    """
    TTS each scene narration individually into segment-N-audio.mp3.
    Also stitches a combined narration.mp3 for the player (concatenated via ffmpeg when available,
    otherwise concatenated as a single gTTS call).
    Returns (any_audio_succeeded, combined_audio_name | None).
    """
    any_ok = False
    for idx, scene in enumerate(scenes):
        narration = (scene.get("narration") or scene.get("content") or "").strip()
        if not narration:
            continue
        out = project_dir / f"segment-{idx}-audio.mp3"
        ok = _gtts_scene(narration, out, lang_code)
        if ok:
            any_ok = True
            scene["_audio_file"] = str(out)   # store for ffmpeg use

    if not any_ok:
        return False, None

    # Build combined narration.mp3 by concatenating all scene audio files
    combined_path = project_dir / "narration.mp3"
    audio_files = [
        project_dir / f"segment-{idx}-audio.mp3"
        for idx in range(len(scenes))
        if (project_dir / f"segment-{idx}-audio.mp3").exists()
    ]
    if not audio_files:
        return False, None

    if shutil.which("ffmpeg") and len(audio_files) > 1:
        list_file = project_dir / "audio-list.txt"
        list_file.write_text(
            "".join(f"file '{f.as_posix()}'\n" for f in audio_files),
            encoding="utf-8",
        )
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                 "-acodec", "copy", str(combined_path)],
                check=True, capture_output=True,
            )
        except Exception:
            # Fallback: just copy first audio file as combined
            shutil.copy(str(audio_files[0]), str(combined_path))
    else:
        # Single segment or no ffmpeg — use the single file / first file
        shutil.copy(str(audio_files[0]), str(combined_path))

    return True, "narration.mp3"


# ---------------------------------------------------------------------------
# Player HTML writer (now uses per-scene duration_seconds for autoplay timing)
# ---------------------------------------------------------------------------

def _write_player(
    project_dir: Path,
    title: str,
    scenes: list[dict],
    audio_name: str | None,
) -> str:
    slides_html = []
    # Build JS array of per-slide durations in ms for timed autoplay
    slide_durations_ms = []
    for index, scene in enumerate(scenes):
        bullets = scene.get("bullets") or _split_bullets(
            scene.get("narration") or scene.get("content") or ""
        )
        highlight = scene.get("highlight") or (bullets[0] if bullets else "")
        body = html.escape(scene.get("narration") or scene.get("content") or "")
        dur_ms = _clamp_duration(scene.get("duration_seconds", DEFAULT_SCENE_SECONDS)) * 1000
        slide_durations_ms.append(dur_ms)
        slides_html.append(
            f"""
            <section class="slide{' active' if index == 0 else ''}" data-index="{index}" data-dur="{dur_ms}">
              <div class="slide-inner">
                <p class="slide-num">Slide {index + 1} / {len(scenes)}</p>
                <h2>{html.escape(scene.get('title') or f'Scene {index + 1}')}</h2>
                {f'<p class="highlight">{html.escape(highlight)}</p>' if highlight else ''}
                <p class="body">{body}</p>
                {_bullet_html(bullets[1:] if len(bullets) > 1 else bullets)}
              </div>
            </section>
            """
        )
    audio_block = f'<audio id="audio" controls src="{audio_name}"></audio>' if audio_name else ""
    durations_js = json.dumps(slide_durations_ms)
    player = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(title)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Inter, Arial, sans-serif; background: radial-gradient(circle at top, rgba(45,212,191,0.18), transparent 30%), linear-gradient(135deg, #071120, #10243f 55%, #0d1b2e); color: white; min-height: 100vh; overflow-x: hidden; }}
    body::before, body::after {{ content: ""; position: fixed; inset: auto; width: 28rem; height: 28rem; border-radius: 999px; filter: blur(80px); opacity: 0.4; animation: floatBlob 12s ease-in-out infinite; z-index: 0; }}
    body::before {{ top: -6rem; left: -4rem; background: rgba(45, 212, 191, 0.25); }}
    body::after {{ right: -6rem; bottom: -8rem; background: rgba(59, 130, 246, 0.2); animation-delay: -4s; }}
    .wrap {{ position: relative; z-index: 1; max-width: 1180px; margin: 0 auto; padding: 20px; }}
    h1 {{ font-size: clamp(1.4rem, 3vw, 2.3rem); margin-bottom: 16px; }}
    .slide {{ display: none; animation: fadeIn 0.5s ease; }}
    .slide.active {{ display: block; }}
    .slide-inner {{ background: rgba(7, 17, 32, 0.62); border: 1px solid rgba(94,234,212,0.24); border-radius: 24px; padding: clamp(20px, 4vw, 40px); min-height: 460px; box-shadow: 0 30px 80px rgba(0,0,0,0.3); backdrop-filter: blur(14px); }}
    .slide-num {{ color: #5eead4; font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; }}
    h2 {{ margin: 12px 0 16px; color: #5eead4; font-size: clamp(1.4rem, 3vw, 2rem); line-height: 1.3; }}
    .highlight {{ background: rgba(20,184,166,0.2); border-left: 4px solid #14b8a6; padding: 12px 16px; border-radius: 8px; font-weight: 600; margin-bottom: 16px; }}
    .body {{ line-height: 1.8; font-size: clamp(1rem, 2.2vw, 1.15rem); margin-bottom: 20px; white-space: pre-wrap; }}
    .bullets {{ margin: 0; padding-left: 1.25rem; line-height: 1.9; }}
    .bullets li {{ margin-bottom: 8px; }}
    .controls {{ display: flex; gap: 12px; margin-top: 20px; flex-wrap: wrap; }}
    button {{ background: linear-gradient(135deg, #14b8a6, #0d9488); color: white; border: 0; border-radius: 10px; padding: 12px 18px; font-weight: 700; cursor: pointer; }}
    audio {{ width: 100%; margin-top: 16px; }}
    .progress {{ height: 6px; background: rgba(255,255,255,0.15); border-radius: 999px; margin-bottom: 16px; overflow: hidden; }}
    .progress > span {{ display: block; height: 100%; background: linear-gradient(90deg, #5eead4, #2dd4bf, #60a5fa); width: 0%; transition: width 0.4s ease; }}
    .autoplay {{ display: inline-flex; align-items: center; gap: 8px; font-size: 14px; color: rgba(255,255,255,0.8); }}
    @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
    @keyframes floatBlob {{ 0%, 100% {{ transform: translate3d(0, 0, 0) scale(1); }} 50% {{ transform: translate3d(30px, -20px, 0) scale(1.08); }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>{html.escape(title)}</h1>
    <div class="progress"><span id="bar"></span></div>
    {''.join(slides_html)}
    <div class="controls">
      <button type="button" id="prev">Previous</button>
      <button type="button" id="next">Next</button>
      <button type="button" id="play">Play Narration</button>
      <label class="autoplay"><input type="checkbox" id="autoplay" checked /> Auto-advance slides</label>
    </div>
    {audio_block}
  </div>
  <script>
    const slides = Array.from(document.querySelectorAll('.slide'));
    const bar = document.getElementById('bar');
    const slideDurations = {durations_js};
    let current = 0;
    const audio = document.getElementById('audio');
    const autoplay = document.getElementById('autoplay');
    let autoplayTimer = null;

    function show(index) {{
      current = Math.max(0, Math.min(index, slides.length - 1));
      slides.forEach((slide, idx) => slide.classList.toggle('active', idx === current));
      if (bar) bar.style.width = (((current + 1) / slides.length) * 100) + '%';
      if (autoplay?.checked && !audio) scheduleNext();
    }}

    function scheduleNext() {{
      clearTimeout(autoplayTimer);
      const dur = slideDurations[current] || 8000;
      autoplayTimer = setTimeout(() => {{
        if (current >= slides.length - 1) show(0);
        else show(current + 1);
      }}, dur);
    }}

    document.getElementById('prev').addEventListener('click', () => {{ clearTimeout(autoplayTimer); show(current - 1); }});
    document.getElementById('next').addEventListener('click', () => {{ clearTimeout(autoplayTimer); show(current + 1); }});
    autoplay?.addEventListener('change', () => {{
      clearTimeout(autoplayTimer);
      if (autoplay.checked && !audio) scheduleNext();
    }});
    document.getElementById('play').addEventListener('click', () => {{
      const text = slides[current]?.querySelector('.body')?.innerText || '{html.escape(title)}';
      if (audio) {{ audio.play(); return; }}
      const utterance = new SpeechSynthesisUtterance(text);
      window.speechSynthesis.speak(utterance);
    }});
    if (audio) audio.addEventListener('timeupdate', () => {{
      const ratio = audio.duration ? audio.currentTime / audio.duration : 0;
      const newIdx = Math.min(slides.length - 1, Math.floor(ratio * slides.length));
      if (newIdx !== current) show(newIdx);
    }});
    // Kick off timed autoplay only when no audio track is available
    if (!audio && autoplay?.checked) scheduleNext();
  </script>
</body>
</html>"""
    player_path = project_dir / "player.html"
    player_path.write_text(player, encoding="utf-8")
    return str(player_path)


# ---------------------------------------------------------------------------
# ffmpeg: per-scene video segments with optional per-scene audio
# ---------------------------------------------------------------------------

def _try_ffmpeg(
    project_id: int,
    title: str,
    scenes: list[dict],
    total_minutes: int = 5,
) -> str | None:
    """
    Build MP4 by concatenating per-scene segments. Each segment:
    - Duration = scene['duration_seconds'] (or calculated from total_minutes / scene count)
    - If per-scene audio exists (segment-N-audio.mp3), mux it into the segment video
    - Otherwise produce a silent segment
    """
    if not shutil.which("ffmpeg"):
        return None
    output = STATIC_DIR / f"video-{project_id}.mp4"
    project_dir = STATIC_DIR / f"video-{project_id}"
    project_dir.mkdir(parents=True, exist_ok=True)
    if not scenes:
        return None
    try:
        fallback_secs = max(6, min(18, int((max(total_minutes, 1) * 60) / max(len(scenes), 1))))
        concat_lines = []
        for index, scene in enumerate(scenes):
            seg_dur = _clamp_duration(scene.get("duration_seconds", fallback_secs))
            title_file = project_dir / f"title-{index}.txt"
            body_file = project_dir / f"body-{index}.txt"
            title_file.write_text(
                (scene.get("title") or title).replace("'", ""), encoding="utf-8"
            )
            body_file.write_text(
                (scene.get("highlight") or scene.get("content") or "").replace("'", "")[:180],
                encoding="utf-8",
            )
            segment_path = project_dir / f"segment-{index}.mp4"
            audio_file = project_dir / f"segment-{index}-audio.mp3"
            has_audio = audio_file.exists() and audio_file.stat().st_size > 100

            if has_audio:
                # Build segment with per-scene audio: use audio duration to drive video length
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(audio_file),
                    "-f", "lavfi", "-i",
                    f"color=c=0x0f172a:s=1280x720:r=24",
                    "-vf", (
                        f"drawtext=textfile='{title_file.as_posix()}':fontcolor=0x5eead4:fontsize=42:x=80:y=100:line_spacing=10,"
                        f"drawtext=textfile='{body_file.as_posix()}':fontcolor=white:fontsize=28:x=80:y=200:line_spacing=8"
                    ),
                    "-shortest",    # end video when audio ends
                    "-pix_fmt", "yuv420p",
                    "-acodec", "aac", "-b:a", "128k",
                    str(segment_path),
                ]
            else:
                # Build silent visual-only segment with fixed duration
                cmd = [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i",
                    f"color=c=0x0f172a:s=1280x720:d={seg_dur}",
                    "-vf", (
                        f"drawtext=textfile='{title_file.as_posix()}':fontcolor=0x5eead4:fontsize=42:x=80:y=100:line_spacing=10,"
                        f"drawtext=textfile='{body_file.as_posix()}':fontcolor=white:fontsize=28:x=80:y=200:line_spacing=8"
                    ),
                    "-pix_fmt", "yuv420p",
                    str(segment_path),
                ]
            subprocess.run(cmd, check=True, capture_output=True)
            concat_lines.append(f"file '{segment_path.as_posix()}'\n")

        list_file = project_dir / "ffmpeg-list.txt"
        list_file.write_text("".join(concat_lines), encoding="utf-8")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
             "-c", "copy", str(output)],
            check=True, capture_output=True,
        )
        return str(output)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_educational_video(project_id: int, title: str, lesson: dict) -> dict:
    """
    Full video generation from a lesson dict (from LessonGenerationAgent).
    1. Convert lesson slides → scenes with duration_seconds wired
    2. Per-scene TTS → individual MP3 files
    3. Combined narration.mp3 for player fallback
    4. Write interactive HTML player (slide durations from duration_seconds)
    5. ffmpeg MP4 stitching (per-scene audio + timed visuals)
    """
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    project_dir = STATIC_DIR / f"video-{project_id}"
    project_dir.mkdir(parents=True, exist_ok=True)

    slides = lesson.get("slides") or []
    duration_min = int(lesson.get("duration") or 5)
    lang = lesson.get("language") or "English"
    lang_code = _lang_code(lang)

    # Build scenes with per-scene duration_seconds
    scenes: list[dict] = []
    for index, slide in enumerate(slides):
        content = slide.get("content") or ""
        scenes.append({
            "title": slide.get("title") or f"Slide {index + 1}",
            "narration": content,
            "content": content,
            "highlight": slide.get("diagram") or "",
            "bullets": _split_bullets(content),
            "duration_seconds": DEFAULT_SCENE_SECONDS,
        })

    if not scenes:
        script = lesson.get("script") or title
        for index, chunk in enumerate(script.split("\n\n")[:6]):
            scenes.append({
                "title": f"Part {index + 1}",
                "narration": chunk,
                "content": chunk,
                "bullets": _split_bullets(chunk),
                "duration_seconds": DEFAULT_SCENE_SECONDS,
            })

    # Pad to minimum scenes
    target_count = max(4, duration_min)
    if len(scenes) < target_count:
        script_parts = [
            part.strip()
            for part in re.split(r"(?<=[.!?])\s+", lesson.get("script") or "")
            if len(part.strip()) > 24
        ]
        while len(scenes) < target_count and script_parts:
            part = script_parts[len(scenes) % len(script_parts)]
            scenes.append({
                "title": f"Deep Dive {len(scenes) + 1}",
                "narration": part,
                "content": part,
                "highlight": "",
                "bullets": _split_bullets(part),
                "duration_seconds": DEFAULT_SCENE_SECONDS,
            })

    # Distribute total duration evenly (each scene gets equal share)
    secs_per_scene = max(DEFAULT_SCENE_SECONDS, int((duration_min * 60) / max(len(scenes), 1)))
    for scene in scenes:
        if not scene.get("duration_seconds") or scene["duration_seconds"] == DEFAULT_SCENE_SECONDS:
            scene["duration_seconds"] = secs_per_scene

    # Persist scenes.json
    (project_dir / "scenes.json").write_text(
        json.dumps({"title": title, "scenes": scenes}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Per-scene TTS
    any_audio, audio_name = _tts_all_scenes(project_dir, scenes, lang_code)

    # Write interactive HTML player (uses per-scene duration_seconds for timed autoplay)
    _write_player(project_dir, title, scenes, audio_name)

    # ffmpeg MP4 stitching (per-scene audio + timed visuals)
    mp4_path = _try_ffmpeg(project_id, title, scenes, duration_min)

    return {
        "video_path": str(project_dir / "player.html"),
        "video_url": f"/static/videos/video-{project_id}/player.html",
        "audio_url": f"/static/videos/video-{project_id}/narration.mp3" if any_audio else None,
        "mp4_url": f"/static/videos/video-{project_id}.mp4" if mp4_path else None,
        "scenes": scenes,
        "fallback": not any_audio and not mp4_path,
    }


def rebuild_video_from_scenes(
    project_id: int,
    title: str,
    scenes: list[dict],
    language: str = "English",
    re_tts: bool = True,
) -> dict:
    """
    Re-render an existing video project from an updated scenes list.
    Skips lesson generation — directly accepts the edited scenes array.
    Used by PUT /api/videos/{id}/scenes.
    """
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    project_dir = STATIC_DIR / f"video-{project_id}"
    project_dir.mkdir(parents=True, exist_ok=True)
    lang_code = _lang_code(language)

    # Ensure duration_seconds set on every scene
    for scene in scenes:
        if not scene.get("duration_seconds"):
            scene["duration_seconds"] = DEFAULT_SCENE_SECONDS
        scene.setdefault("bullets", _split_bullets(scene.get("narration") or scene.get("content") or ""))

    # Persist updated scenes.json
    (project_dir / "scenes.json").write_text(
        json.dumps({"title": title, "scenes": scenes}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    any_audio = False
    audio_name = None

    if re_tts:
        # Remove old per-scene audio so we don't reuse stale files
        for idx in range(len(scenes) + 5):
            old = project_dir / f"segment-{idx}-audio.mp3"
            if old.exists():
                old.unlink()
        any_audio, audio_name = _tts_all_scenes(project_dir, scenes, lang_code)
    else:
        # Check for existing per-scene audio
        for idx in range(len(scenes)):
            if (project_dir / f"segment-{idx}-audio.mp3").exists():
                any_audio = True
                audio_name = "narration.mp3"
                break

    _write_player(project_dir, title, scenes, audio_name)
    total_minutes = max(1, sum(s.get("duration_seconds", DEFAULT_SCENE_SECONDS) for s in scenes) // 60)
    mp4_path = _try_ffmpeg(project_id, title, scenes, total_minutes)

    return {
        "video_url": f"/static/videos/video-{project_id}/player.html",
        "audio_url": f"/static/videos/video-{project_id}/narration.mp3" if any_audio else None,
        "mp4_url": f"/static/videos/video-{project_id}.mp4" if mp4_path else None,
        "scenes": scenes,
        "fallback": not any_audio and not mp4_path,
    }
