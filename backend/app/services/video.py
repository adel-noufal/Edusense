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
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from app.core.config import get_settings

STATIC_DIR = Path(__file__).resolve().parents[1] / "static" / "videos"

DEFAULT_SCENE_SECONDS = 8   # fallback when duration_seconds is 0 / missing
MIN_SCENE_SECONDS = 2
MAX_SCENE_SECONDS = 300

# Scenes whose normalized narration is this similar are treated as duplicates
DUPLICATE_SIMILARITY_THRESHOLD = 0.82
# Max corrective LLM passes for script length / dedupe
MAX_SCRIPT_FIX_ATTEMPTS = 2


class VideoStageError(RuntimeError):
    """Structured video-pipeline failure: which stage + machine-readable code."""

    STAGES = ("script_generation", "tts", "render", "assembly")

    def __init__(self, stage: str, code: str, message: str):
        super().__init__(message)
        self.stage = stage if stage in self.STAGES else "assembly"
        self.code = code
        self.user_message = message

    def to_dict(self) -> dict:
        return {"code": self.code, "stage": self.stage, "message": self.user_message}


# ---------------------------------------------------------------------------
# Script length + anti-repetition helpers
# ---------------------------------------------------------------------------

def _count_words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or "", flags=re.UNICODE))


def _normalize_narration(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def find_duplicate_scene_pairs(scenes: list[dict]) -> list[tuple[int, int, float]]:
    """Return (i, j, similarity) pairs of scenes with near-identical narration."""
    norms = [_normalize_narration(s.get("narration") or s.get("content") or "") for s in scenes]
    pairs = []
    for i in range(len(norms)):
        for j in range(i + 1, len(norms)):
            a, b = norms[i], norms[j]
            if len(a) < 40 or len(b) < 40:
                continue
            sim = SequenceMatcher(None, a, b).ratio()
            if sim >= DUPLICATE_SIMILARITY_THRESHOLD:
                pairs.append((i, j, round(sim, 3)))
    return pairs


def _scenes_word_count(scenes: list[dict]) -> int:
    return sum(_count_words(s.get("narration") or s.get("content") or "") for s in scenes)


def _target_words(duration_min: int) -> int:
    settings = get_settings()
    return int(max(1, duration_min) * max(1.0, settings.video_narration_wpm))


def _within_tolerance(actual: int, target: int) -> bool:
    tol = get_settings().video_script_tolerance
    return abs(actual - target) <= target * tol


def _llm_adjust_scenes(scenes: list[dict], duration_min: int, title: str,
                       duplicates: list[tuple[int, int, float]] | None = None) -> list[dict] | None:
    """
    One corrective LLM pass: ask the model to rewrite scene narrations so the
    total word count hits the duration target AND repeated scenes become
    distinct. Returns adjusted scenes list or None on failure.
    """
    try:
        from app.services.gemini import generate_json_any
    except Exception:
        return None
    target = _target_words(duration_min)
    total = _scenes_word_count(scenes)
    scenes_json = json.dumps(
        [{"index": i, "title": s.get("title", ""), "narration": s.get("narration") or s.get("content") or ""}
         for i, s in enumerate(scenes)],
        ensure_ascii=False,
    )
    dup_note = ""
    if duplicates:
        dup_idx = sorted({idx for pair in duplicates for idx in pair[:2]})
        dup_note = (
            f"\nSCENES {dup_idx} contain repeated/near-duplicate narration. Rewrite each of them "
            "to cover a DIFFERENT aspect of the topic — do not restate earlier scenes.\n"
        )
    direction = "expand" if total < target else "condense"
    prompt = f"""You are editing the narration script for an educational video titled "{title}".
The video should run about {duration_min} minutes (~{target} words of narration at normal pace).
Current narration totals ~{total} words ({direction} needed).
{dup_note}
Rules:
- Keep the same number of scenes and their order.
- Each scene must cover a DISTINCT point; never repeat content from other scenes.
- Keep each scene's narration a single coherent paragraph of spoken-style text.
- Return ONLY valid JSON: {{"scenes": [{{"index": 0, "narration": "..."}}, ...]}} with one entry per input scene.

Input scenes:
{scenes_json}
"""
    try:
        data = generate_json_any(prompt, task_type="video")
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    adjusted = data.get("scenes")
    if not isinstance(adjusted, list) or len(adjusted) != len(scenes):
        return None
    out = [dict(s) for s in scenes]
    for item in adjusted:
        try:
            idx = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        if 0 <= idx < len(out):
            narration = str(item.get("narration") or "").strip()
            if narration:
                out[idx]["narration"] = narration
                out[idx]["content"] = narration
    return out


def enforce_script_quality(scenes: list[dict], duration_min: int, title: str) -> tuple[list[dict], list[str]]:
    """
    Verify narration word count is within ±tolerance of the duration target and
    that no two scenes are near-duplicates. Runs up to MAX_SCRIPT_FIX_ATTEMPTS
    corrective LLM passes; duplicate scenes that survive are dropped (later
    copy removed). Raises VideoStageError(stage=script_generation) if the word
    count cannot be brought into tolerance.
    Returns (scenes, warnings).
    """
    settings = get_settings()
    target = _target_words(duration_min)
    warnings: list[str] = []

    if not scenes:
        raise VideoStageError("script_generation", "EMPTY_SCRIPT",
                              "The generated lesson produced no scenes to narrate.")

    for attempt in range(MAX_SCRIPT_FIX_ATTEMPTS + 1):
        total = _scenes_word_count(scenes)
        dups = find_duplicate_scene_pairs(scenes)
        length_ok = _within_tolerance(total, target)
        if length_ok and not dups:
            return scenes, warnings
        if attempt >= MAX_SCRIPT_FIX_ATTEMPTS:
            break
        adjusted = _llm_adjust_scenes(scenes, duration_min, title, duplicates=dups or None)
        if adjusted is None:
            warnings.append("Script corrective pass unavailable; keeping generated script.")
            break
        scenes = adjusted

    # Final state
    total = _scenes_word_count(scenes)
    dups = find_duplicate_scene_pairs(scenes)
    # Drop later duplicates deterministically
    drop = {j for _, j, _ in dups}
    if drop:
        scenes = [s for i, s in enumerate(scenes) if i not in drop]
        warnings.append(f"Removed {len(drop)} repeated scene(s) from the script.")
        total = _scenes_word_count(scenes)

    if not _within_tolerance(total, target):
        raise VideoStageError(
            "script_generation", "LENGTH_OUT_OF_TOLERANCE",
            f"Generated script is ~{total} words but a {duration_min}-minute video needs "
            f"~{target} words (±{int(settings.video_script_tolerance * 100)}%). "
            "Please try again or choose a shorter duration.",
        )
    return scenes, warnings


# ---------------------------------------------------------------------------
# Sectioned narration script generation (outline -> per-section -> budgets)
# ---------------------------------------------------------------------------

def _section_count(duration_min: int) -> int:
    return max(2, min(8, int(round(max(1, duration_min)))))


def _llm_chat(prompt: str, task_type: str = "video", **kwargs) -> str:
    from app.services.gemini import generate_content
    return generate_content(prompt, task_type=task_type, **kwargs)


def _llm_chat_json(prompt: str, task_type: str = "video") -> dict | list | None:
    try:
        from app.services.gemini import generate_json_any
        return generate_json_any(prompt, task_type=task_type)
    except Exception:
        return None


def _section_outline(title: str, prompt: str, duration_min: int, language: str,
                     notes: str, n_sections: int, target: int) -> list[dict]:
    """Step 1: ask the LLM for an outline of distinct section goals + budgets."""
    budget_each = target // n_sections
    raw = _llm_chat_json(f"""Create an outline for an educational video.
Title: {title}
Topic/prompt: {prompt or title}
Language: {language}
Target runtime: ~{duration_min} minutes, ~{target} words of narration total.
Notes: {notes or 'none'}

Produce exactly {n_sections} sections. Each section MUST cover a DISTINCT aspect — no overlap, no repeated points.
Return ONLY valid JSON:
{{"sections": [{{"title": "...", "goal": "one sentence on what this section teaches", "budget_words": {budget_each}}}, ...]}}
Every budget_words must be between {int(budget_each*0.7)} and {int(budget_each*1.3)}.
""", task_type="video")
    sections = []
    if isinstance(raw, dict):
        sections = raw.get("sections") or []
    elif isinstance(raw, list):
        sections = raw
    out = []
    for i, s in enumerate(sections[:n_sections]):
        if not isinstance(s, dict):
            continue
        try:
            budget = int(s.get("budget_words") or budget_each)
        except (TypeError, ValueError):
            budget = budget_each
        budget = max(20, min(budget, int(budget_each * 1.5)))
        out.append({
            "title": str(s.get("title") or f"Section {i+1}")[:120],
            "goal": str(s.get("goal") or "")[:300],
            "budget_words": budget,
        })
    # Pad/truncate to exactly n_sections with sensible defaults
    while len(out) < n_sections:
        out.append({"title": f"Section {len(out)+1}", "goal": "", "budget_words": budget_each})
    return out[:n_sections]


def _gen_section_text(section: dict, outline: list[dict], index: int,
                      running_summary: str, title: str, language: str) -> str:
    """Step 2: generate one section's narration within its word budget.
    One corrective expand/condense retry if outside ±15%."""
    target = section["budget_words"]
    outline_txt = "\n".join(f"- {s['title']}: {s['goal']}" for s in outline)
    prev = f"Already covered (do NOT repeat):\n{running_summary}\n\n" if running_summary else ""
    base_prompt = f"""Write the narration script for ONE section of an educational video titled "{title}".
Language: {language}
Section {index+1}/{len(outline)}: "{section['title']}" — goal: {section['goal'] or 'teach the key concept'}
Full outline (context only — do NOT cover other sections' content):
{outline_txt}
{prev}Rules:
- Write spoken-style narration of approximately {target} words (acceptable range {int(target*0.85)}-{int(target*1.15)}).
- Plain text only, no headings, no markdown, no stage directions.
- Do not repeat or restate content from earlier sections.
Return ONLY the narration text."""
    text = (_llm_chat(base_prompt, task_type="video",
                      max_output_tokens=max(600, target * 3), timeout=180) or "").strip()
    words = _count_words(text)
    if not (int(target * 0.85) <= words <= int(target * 1.15)) and words > 0:
        direction = "expand" if words < target else "condense"
        fix_prompt = f"""Rewrite the narration below to be approximately {target} words ({direction} needed; acceptable {int(target*0.85)}-{int(target*1.15)} words). Keep the same topic and spoken style. Plain text only.

NARRATION:
{text}"""
        try:
            fixed = (_llm_chat(fix_prompt, task_type="video",
                               max_output_tokens=max(600, target * 3), timeout=180) or "").strip()
            if _count_words(fixed) > 0:
                text = fixed
        except Exception:
            pass
    return text


def generate_sectioned_scenes(title: str, prompt: str, duration_min: int,
                              language: str, notes: str = "",
                              slides: list[dict] | None = None) -> list[dict]:
    """
    Generate the video script in sections: outline -> per-section narration
    with word budgets and a running summary. Returns scene dicts compatible
    with the rest of the pipeline. Raises GeminiError (typed code) when all
    providers are exhausted; raises VideoStageError on unrecoverable length.
    """
    target = _target_words(duration_min)
    n = _section_count(duration_min)
    outline = _section_outline(title, prompt, duration_min, language, notes, n, target)

    scenes: list[dict] = []
    summary_parts: list[str] = []
    for i, section in enumerate(outline):
        text = _gen_section_text(section, outline, i,
                                 "\n".join(summary_parts[-3:]), title, language)
        if not text:
            raise VideoStageError("script_generation", "EMPTY_SECTION",
                                  f"Section '{section['title']}' produced no narration. Please try again.")
        slide = (slides[i] if slides and i < len(slides) else {}) or {}
        scenes.append({
            "title": section["title"],
            "narration": text,
            "content": slide.get("content") or text[:600],
            "highlight": slide.get("diagram") or slide.get("highlight") or "",
            "bullets": _split_bullets(slide.get("content") or text),
            "duration_seconds": DEFAULT_SCENE_SECONDS,
        })
        # running summary = first ~25 words of each finished section
        summary_parts.append(f"{section['title']}: {' '.join(text.split()[:25])}…")

    # Anti-repetition: drop near-duplicate sections deterministically
    dups = find_duplicate_scene_pairs(scenes)
    if dups:
        drop = {j for _, j, _ in dups}
        scenes = [s for i, s in enumerate(scenes) if i not in drop]

    # Final gate: total must be within ±tolerance of target
    total = _scenes_word_count(scenes)
    if not _within_tolerance(total, target):
        raise VideoStageError(
            "script_generation", "LENGTH_OUT_OF_TOLERANCE",
            f"Generated script is ~{total} words but a {duration_min}-minute video needs "
            f"~{target} words (±{int(get_settings().video_script_tolerance * 100)}%). "
            "Please try again or choose a shorter duration.",
        )
    return scenes


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


def _gtts_scene_timed(text: str, out_path: Path, lang: str, timeout: float) -> tuple[bool, str | None]:
    """Run gTTS with a hard timeout; returns (ok, error_message).
    shutdown(wait=False) so a hung worker thread cannot block the request."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        fut = pool.submit(_gtts_scene, text, out_path, lang)
        try:
            ok = fut.result(timeout=timeout)
            return ok, None if ok else "gTTS produced no audio file"
        except FuturesTimeout:
            return False, f"TTS timed out after {timeout:.0f}s"
        except Exception as exc:
            return False, str(exc)[:200]
    finally:
        pool.shutdown(wait=False)


def _tts_all_scenes(
    project_dir: Path,
    scenes: list[dict],
    lang_code: str,
) -> tuple[bool, str | None, list[str]]:
    """
    TTS each scene narration individually into segment-N-audio.mp3.
    Also stitches a combined narration.mp3 for the player (concatenated via ffmpeg when available,
    otherwise concatenated as a single gTTS call).
    Returns (any_audio_succeeded, combined_audio_name | None, per_scene_errors).
    """
    settings = get_settings()
    timeout = max(5.0, settings.video_tts_timeout)
    errors: list[str] = []
    failed = 0
    for idx, scene in enumerate(scenes):
        narration = (scene.get("narration") or scene.get("content") or "").strip()
        if not narration:
            continue
        out = project_dir / f"segment-{idx}-audio.mp3"
        ok, err = _gtts_scene_timed(narration, out, lang_code, timeout)
        if ok:
            continue
        failed += 1
        errors.append(f"scene {idx + 1}: {err or 'TTS failed'}")

    any_ok = failed < sum(1 for s in scenes if (s.get("narration") or s.get("content") or "").strip())

    if not any_ok:
        return False, None, errors or ["All narration segments failed text-to-speech"]

    # Build combined narration.mp3 by concatenating all scene audio files
    combined_path = project_dir / "narration.mp3"
    audio_files = [
        project_dir / f"segment-{idx}-audio.mp3"
        for idx in range(len(scenes))
        if (project_dir / f"segment-{idx}-audio.mp3").exists()
    ]
    if not audio_files:
        return False, None, errors or ["No narration audio was produced"]

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

    return True, "narration.mp3", errors


def _probe_audio_duration(audio_path: Path) -> float | None:
    """Return encoded audio duration in seconds when ffprobe is available."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    result = subprocess.run(
        [
            ffprobe, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        return None
    return duration if duration > 0 else None


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
      const elapsedMs = audio.currentTime * 1000;
      let totalMs = 0;
      let newIdx = 0;
      for (let index = 0; index < slideDurations.length; index++) {{
        totalMs += slideDurations[index];
        newIdx = index;
        if (elapsedMs < totalMs) break;
      }}
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

    # Preferred path: dedicated sectioned narration script (outline -> per-
    # section budgets -> running summary). Falls back to slide-derived scenes
    # only when the script service itself is unavailable.
    scenes: list[dict] | None = None
    script_warnings: list[str] = []
    try:
        scenes = generate_sectioned_scenes(
            title=title,
            prompt=lesson.get("prompt") or lesson.get("topic") or "",
            duration_min=duration_min,
            language=lang,
            notes=lesson.get("notes") or "",
            slides=slides,
        )
    except VideoStageError:
        raise
    except Exception as exc:
        from app.services.gemini import GeminiError
        if isinstance(exc, GeminiError):
            raise VideoStageError("script_generation", exc.code, exc.user_message) from exc
        scenes = None  # unexpected — fall back to slide-derived script

    if scenes is None:
        # Fallback path: derive scenes from lesson slides/script, then pad
        # ONLY with distinct, not-yet-used script parts — never cycle back
        # to earlier content (that produced repeated paragraphs).
        scenes = []
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

        target_count = max(4, duration_min)
        if len(scenes) < target_count:
            script_parts = [
                part.strip()
                for part in re.split(r"(?<=[.!?])\s+", lesson.get("script") or "")
                if len(part.strip()) > 24
            ]
            used = {_normalize_narration(s.get("narration") or s.get("content") or "") for s in scenes}
            for part in script_parts:
                if len(scenes) >= target_count:
                    break
                norm = _normalize_narration(part)
                if norm in used:
                    continue
                used.add(norm)
                scenes.append({
                    "title": f"Deep Dive {len(scenes) + 1}",
                    "narration": part,
                    "content": part,
                    "highlight": "",
                    "bullets": _split_bullets(part),
                    "duration_seconds": DEFAULT_SCENE_SECONDS,
                })

        # Script quality gate on the fallback path too.
        try:
            scenes, script_warnings = enforce_script_quality(scenes, duration_min, title)
        except VideoStageError:
            raise
        except Exception as exc:
            raise VideoStageError("script_generation", "SCRIPT_VALIDATION_FAILED",
                                  f"Could not validate the generated script: {exc}") from exc

    # Distribute total duration evenly (each scene gets equal share)
    secs_per_scene = max(DEFAULT_SCENE_SECONDS, int((duration_min * 60) / max(len(scenes), 1)))
    for scene in scenes:
        if not scene.get("duration_seconds") or scene["duration_seconds"] == DEFAULT_SCENE_SECONDS:
            scene["duration_seconds"] = secs_per_scene

    # Persist scenes.json
    (project_dir / "scenes.json").write_text(
        json.dumps({"title": title, "scenes": scenes, "warnings": script_warnings}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Per-scene TTS — per-scene timeout; partial failures are reported,
    # total failure raises a structured stage error.
    any_audio, audio_name, tts_errors = _tts_all_scenes(project_dir, scenes, lang_code)
    if not any_audio:
        detail = "; ".join(tts_errors[:3]) if tts_errors else "text-to-speech unavailable"
        raise VideoStageError("tts", "TTS_FAILED",
                              f"Narration audio could not be generated ({detail}). "
                              "Check network access to the TTS service and try again.")

    # Write interactive HTML player (uses per-scene duration_seconds for timed autoplay)
    _write_player(project_dir, title, scenes, audio_name)

    # ffmpeg MP4 stitching (per-scene audio + timed visuals) — optional;
    # the HTML player remains the playback path when ffmpeg is absent.
    mp4_path = _try_ffmpeg(project_id, title, scenes, duration_min)

    return {
        "video_path": str(project_dir / "player.html"),
        "video_url": f"/static/videos/video-{project_id}/player.html",
        "audio_url": f"/static/videos/video-{project_id}/narration.mp3" if any_audio else None,
        "mp4_url": f"/static/videos/video-{project_id}.mp4" if mp4_path else None,
        "scenes": scenes,
        "fallback": not mp4_path,
        "warnings": script_warnings + ([f"Partial TTS: {'; '.join(tts_errors[:3])}"] if tts_errors else []),
        "tts_errors": tts_errors,
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

    any_audio = False
    audio_name = None
    duration_warning = None

    if re_tts:
        # Remove old per-scene audio so we don't reuse stale files
        for idx in range(len(scenes) + 5):
            old = project_dir / f"segment-{idx}-audio.mp3"
            if old.exists():
                old.unlink()
        (project_dir / "narration.mp3").unlink(missing_ok=True)
        any_audio, audio_name, tts_errors = _tts_all_scenes(project_dir, scenes, lang_code)
        if any_audio:
            measured_durations = 0
            for idx, scene in enumerate(scenes):
                audio_path = project_dir / f"segment-{idx}-audio.mp3"
                if not audio_path.exists():
                    continue
                duration = _probe_audio_duration(audio_path)
                if duration is not None:
                    scene["duration_seconds"] = _clamp_duration(round(duration))
                    measured_durations += 1
            if not measured_durations:
                duration_warning = "Audio was regenerated, but ffprobe is unavailable; scene durations use the provided values."
            if tts_errors:
                duration_warning = (duration_warning + " " if duration_warning else "") + \
                    f"Some scenes had TTS issues: {'; '.join(tts_errors[:3])}"
        else:
            detail = "; ".join(tts_errors[:3]) if tts_errors else ""
            duration_warning = ("Text-to-speech could not generate audio"
                                + (f" ({detail})" if detail else "")
                                + "; the player will use browser speech synthesis.")
    else:
        # Check for existing per-scene audio
        for idx in range(len(scenes)):
            if (project_dir / f"segment-{idx}-audio.mp3").exists():
                any_audio = True
                audio_name = "narration.mp3"
                break

    (project_dir / "scenes.json").write_text(
        json.dumps({"title": title, "scenes": scenes}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_player(project_dir, title, scenes, audio_name)
    total_minutes = max(1, sum(s.get("duration_seconds", DEFAULT_SCENE_SECONDS) for s in scenes) // 60)
    (STATIC_DIR / f"video-{project_id}.mp4").unlink(missing_ok=True)
    mp4_path = _try_ffmpeg(project_id, title, scenes, total_minutes)

    return {
        "video_url": f"/static/videos/video-{project_id}/player.html",
        "audio_url": f"/static/videos/video-{project_id}/narration.mp3" if any_audio else None,
        "mp4_url": f"/static/videos/video-{project_id}.mp4" if mp4_path else None,
        "scenes": scenes,
        "fallback": not mp4_path,
        "duration_warning": duration_warning,
    }
