import html
import json
import re
import shutil
import subprocess
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[1] / "static" / "videos"


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


def _write_player(project_dir: Path, title: str, scenes: list[dict], audio_name: str | None) -> str:
    slides_html = []
    for index, scene in enumerate(scenes):
        bullets = scene.get("bullets") or _split_bullets(scene.get("narration") or scene.get("content") or "")
        highlight = scene.get("highlight") or (bullets[0] if bullets else "")
        body = html.escape(scene.get("narration") or scene.get("content") or "")
        slides_html.append(
            f"""
            <section class="slide{' active' if index == 0 else ''}" data-index="{index}">
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
    progress = 100 / max(len(scenes), 1)
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
    .progress > span {{ display: block; height: 100%; background: linear-gradient(90deg, #5eead4, #2dd4bf, #60a5fa); width: {progress:.0f}%; transition: width 0.3s; }}
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
      <label class="autoplay"><input type="checkbox" id="autoplay" checked /> Auto-play slides</label>
    </div>
    {audio_block}
  </div>
  <script>
    const slides = Array.from(document.querySelectorAll('.slide'));
    const bar = document.getElementById('bar');
    let current = 0;
    const audio = document.getElementById('audio');
    const autoplay = document.getElementById('autoplay');
    let autoplayTimer = null;
    function show(index) {{
      current = Math.max(0, Math.min(index, slides.length - 1));
      slides.forEach((slide, idx) => slide.classList.toggle('active', idx === current));
      if (bar) bar.style.width = (((current + 1) / slides.length) * 100) + '%';
    }}
    function startAutoplay() {{
      if (!autoplay?.checked) return;
      clearInterval(autoplayTimer);
      autoplayTimer = setInterval(() => {{
        if (current >= slides.length - 1) {{
          show(0);
          return;
        }}
        show(current + 1);
      }}, 6500);
    }}
    document.getElementById('prev').addEventListener('click', () => show(current - 1));
    document.getElementById('next').addEventListener('click', () => show(current + 1));
    autoplay?.addEventListener('change', () => {{
      clearInterval(autoplayTimer);
      if (autoplay.checked) startAutoplay();
    }});
    document.getElementById('play').addEventListener('click', () => {{
      const text = slides[current]?.querySelector('.body')?.innerText || '{html.escape(title)}';
      if (audio) {{ audio.play(); return; }}
      const utterance = new SpeechSynthesisUtterance(text);
      window.speechSynthesis.speak(utterance);
    }});
    if (audio) audio.addEventListener('timeupdate', () => {{
      const ratio = audio.duration ? audio.currentTime / audio.duration : 0;
      show(Math.min(slides.length - 1, Math.floor(ratio * slides.length)));
    }});
    startAutoplay();
  </script>
</body>
</html>"""
    player_path = project_dir / "player.html"
    player_path.write_text(player, encoding="utf-8")
    return str(player_path)


def _try_ffmpeg(project_id: int, title: str, scenes: list[dict], total_minutes: int = 5) -> str | None:
    if not shutil.which("ffmpeg"):
        return None
    output = STATIC_DIR / f"video-{project_id}.mp4"
    project_dir = STATIC_DIR / f"video-{project_id}"
    project_dir.mkdir(parents=True, exist_ok=True)
    if not scenes:
        return None
    try:
        segment_duration = max(6, min(18, int((max(total_minutes, 1) * 60) / max(len(scenes), 1))))
        concat_lines = []
        for index, scene in enumerate(scenes):
            title_file = project_dir / f"title-{index}.txt"
            body_file = project_dir / f"body-{index}.txt"
            title_file.write_text((scene.get("title") or title).replace("'", ""), encoding="utf-8")
            body_file.write_text((scene.get("highlight") or scene.get("content") or "").replace("'", "")[:180], encoding="utf-8")
            segment_path = project_dir / f"segment-{index}.mp4"
            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=0x0f172a:s=1280x720:d={segment_duration}",
                "-vf",
                (
                    f"drawtext=textfile='{title_file.as_posix()}':fontcolor=0x5eead4:fontsize=42:x=80:y=100:"
                    "line_spacing=10,"
                    f"drawtext=textfile='{body_file.as_posix()}':fontcolor=white:fontsize=28:x=80:y=200:"
                    "line_spacing=8"
                ),
                "-pix_fmt",
                "yuv420p",
                str(segment_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            concat_lines.append(f"file '{segment_path.as_posix()}'\n")
        list_file = project_dir / "ffmpeg-list.txt"
        list_file.write_text("".join(concat_lines), encoding="utf-8")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(output)],
            check=True,
            capture_output=True,
        )
        return str(output)
    except Exception:
        return None


def _try_gtts(project_dir: Path, narration: str, lang: str = "en") -> str | None:
    try:
        from gtts import gTTS
    except ImportError:
        return None
    try:
        audio_path = project_dir / "narration.mp3"
        code = "ar" if lang.lower().startswith("arab") else "en"
        gTTS(text=narration[:5000], lang=code).save(str(audio_path))
        return "narration.mp3"
    except Exception:
        return None


def generate_educational_video(project_id: int, title: str, lesson: dict) -> dict:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    project_dir = STATIC_DIR / f"video-{project_id}"
    project_dir.mkdir(parents=True, exist_ok=True)

    slides = lesson.get("slides") or []
    scenes = []
    for index, slide in enumerate(slides):
        content = slide.get("content") or ""
        scenes.append({
            "title": slide.get("title") or f"Slide {index + 1}",
            "narration": content,
            "content": content,
            "highlight": slide.get("diagram") or "",
            "bullets": _split_bullets(content),
        })
    if not scenes:
        script = lesson.get("script") or title
        for index, chunk in enumerate(script.split("\n\n")[:6]):
            scenes.append({"title": f"Part {index + 1}", "narration": chunk, "content": chunk, "bullets": _split_bullets(chunk)})
    duration = int(lesson.get("duration") or 5)
    if len(scenes) < max(4, duration):
        script_parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", lesson.get("script") or "") if len(part.strip()) > 24]
        while len(scenes) < max(4, duration) and script_parts:
            part = script_parts[len(scenes) % len(script_parts)]
            scenes.append({
                "title": f"Deep Dive {len(scenes) + 1}",
                "narration": part,
                "content": part,
                "highlight": "",
                "bullets": _split_bullets(part),
            })

    narration = lesson.get("script") or "\n".join(scene["narration"] for scene in scenes)
    lang = lesson.get("language") or "English"
    (project_dir / "scenes.json").write_text(json.dumps({"title": title, "scenes": scenes}, ensure_ascii=False, indent=2), encoding="utf-8")

    audio_name = _try_gtts(project_dir, narration, lang)
    player_path = _write_player(project_dir, title, scenes, audio_name)
    mp4_path = _try_ffmpeg(project_id, title, scenes, duration)

    return {
        "video_path": player_path,
        "video_url": f"/static/videos/video-{project_id}/player.html",
        "audio_url": f"/static/videos/video-{project_id}/narration.mp3" if audio_name else None,
        "mp4_url": f"/static/videos/video-{project_id}.mp4" if mp4_path else None,
        "scenes": scenes,
        "fallback": not audio_name and not mp4_path,
    }
