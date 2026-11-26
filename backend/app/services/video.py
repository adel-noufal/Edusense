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
import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.services.binaries import find_ffmpeg, find_ffprobe

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parents[1] / "static" / "videos"

DEFAULT_SCENE_SECONDS = 8   # fallback when duration_seconds is 0 / missing
MIN_SCENE_SECONDS = 2
MAX_SCENE_SECONDS = 300

# Scenes whose normalized narration is this similar are treated as duplicates
DUPLICATE_SIMILARITY_THRESHOLD = 0.82
# Max corrective LLM passes for script length / dedupe
MAX_SCRIPT_FIX_ATTEMPTS = 2

# A slide stays on screen for its narration length plus this short pause.
SCENE_PAUSE_SECONDS = 0.7
# A slide shows at most this many key points (never the narration again).
MAX_BULLETS = 5
BULLET_MAX_CHARS = 80

SLIDE_WIDTH = 1920
SLIDE_HEIGHT = 1080


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


LATEX_SUBS = {
    r"\rightarrow": "→", r"\leftarrow": "←", r"\to": "→", r"\Rightarrow": "⇒",
    r"\times": "×", r"\le": "≤", r"\ge": "≥", r"\pm": "±", r"\dots": "…",
}


def strip_latex(text: str) -> str:
    """Remove inline LaTeX so learners never see \\rightarrow in a slide."""
    if not text:
        return text
    out = str(text)
    for src, dst in LATEX_SUBS.items():
        out = out.replace(src, dst)
    return out.replace("$", "").replace("\\", "")


_CITATION_PATTERNS = (
    re.compile(r"\[\s*Web\s*\d+\s*:[^\]]*\]", re.IGNORECASE),
    re.compile(r"\[\s*Source\s*:[^\]]*\]", re.IGNORECASE),
    re.compile(r"\[\s*\d+\s*\]"),
    re.compile(r"https?://\S+", re.IGNORECASE),
    re.compile(r"\bwww\.\S+", re.IGNORECASE),
)


def strip_citations(text: str) -> str:
    """Remove citation markers and URLs from anything the learner will read or
    hear (F6b). Sources belong in a credits scene, not mid-slide."""
    if not isinstance(text, str) or not text:
        return text
    out = text
    for pattern in _CITATION_PATTERNS:
        out = pattern.sub("", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\s+([,.;:])", r"\1", out)
    return out.strip()


# Template artefacts a model sometimes emits instead of real lesson content.
_PLACEHOLDER_PATTERNS = (
    re.compile(r"\[\s*(?:input|insert|your|add|topic|context|engine|outcome|placeholder|"
               r"content|time|duration|scene|slide|title|optimized)\b[^\]]*\]", re.IGNORECASE),
    re.compile(r"\[\s*\.\.\.\s*[^\]]*\]", re.IGNORECASE),
    re.compile(r"\[\s*\]"),
    re.compile(r"->"),
)

_FILLER_PHRASES = (
    "why top organizations",
    "fast-paced world",
    "fast paced world",
    "let's dive in",
    "let us dive in",
    "unlock the power",
    "game-changer",
    "game changer",
    "a testament to",
    "tapestry of",
)


def is_placeholder(text: str) -> bool:
    """True when text is a template artefact or generic filler, not content."""
    value = (text or "").strip()
    if not value:
        return True
    lowered = value.lower()
    if any(phrase in lowered for phrase in _FILLER_PHRASES):
        return True
    return any(pattern.search(value) for pattern in _PLACEHOLDER_PATTERNS)


def dedupe_bullets(items: list[str]) -> list[str]:
    """Drop repeats (case/punctuation insensitive) while keeping the first order."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = re.sub(r"[^0-9a-z\u0600-\u06ff]+", "", (item or "").lower())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def sanitize_bullets(items: list[str] | None) -> list[str]:
    """On-screen key points: no citations, no placeholders, no repeats, at most 5."""
    cleaned: list[str] = []
    for item in items or []:
        text = strip_citations(strip_latex(str(item))).strip(" .\u2022-\u2013\u2014\t")
        text = re.sub(r"\s{2,}", " ", text)
        if not text or is_placeholder(text):
            continue
        if len(text) > BULLET_MAX_CHARS:
            cut = text[:BULLET_MAX_CHARS]
            text = cut.rsplit(" ", 1)[0].rstrip(",;:") if " " in cut else cut
        cleaned.append(text)
    return dedupe_bullets(cleaned)[:MAX_BULLETS]


def reject_placeholders(scenes: list[dict]) -> None:
    """Never ship template text: fail loudly instead of rendering a placeholder."""
    offenders: list[str] = []
    for index, scene in enumerate(scenes, 1):
        for label in ("title", "highlight"):
            value = scene.get(label)
            if isinstance(value, str) and value.strip() and is_placeholder(value):
                offenders.append(f"scene {index} {label}: {value.strip()[:60]}")
        for bullet in scene.get("bullets") or []:
            if is_placeholder(bullet):
                offenders.append(f"scene {index} bullet: {str(bullet)[:60]}")
    if offenders:
        raise VideoStageError(
            "script_generation", "PLACEHOLDER_CONTENT",
            "The AI returned template text instead of lesson content ("
            + "; ".join(offenders[:3])
            + "). Try again or rephrase the topic.",
        )


def _sanitize_scene(scene: dict) -> dict:
    cleaned = dict(scene)
    for key in ("title", "narration", "content", "diagram", "highlight"):
        if isinstance(cleaned.get(key), str):
            cleaned[key] = strip_citations(strip_latex(cleaned[key]))
    if isinstance(cleaned.get("bullets"), list):
        cleaned["bullets"] = sanitize_bullets(cleaned["bullets"])
    return cleaned


def _scenes_word_count(scenes: list[dict]) -> int:
    return sum(_count_words(s.get("narration") or s.get("content") or "") for s in scenes)


def _target_words(duration_min: int) -> int:
    settings = get_settings()
    return int(max(1, duration_min) * max(1.0, settings.video_narration_wpm))


def _within_tolerance(actual: int, target: int, duration_min: int | None = None) -> bool:
    # Short videos cannot hit a ±10% band: one sentence is several percent of
    # 140 words, and slower TTS still fills the runtime from scene durations.
    tol = get_settings().video_script_tolerance
    if duration_min is not None and duration_min <= 2:
        tol = max(tol, 0.35)
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
        length_ok = _within_tolerance(total, target, duration_min)
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

    if not _within_tolerance(total, target, duration_min):
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
    """`ceil(duration_seconds / 10)` scenes: one slide per ~10 s (F6a).

    A 1-minute video used to get 2 scenes of 30 s each, which read as a odd
    two-slide slideshow. Cap stays modest so script generation does not turn
    into a dozen sequential model calls.
    """
    seconds = max(60, int(round(max(1, duration_min))) * 60)
    by_density = -(-seconds // 10)
    return max(5, min(12, by_density))


def _llm_chat(prompt: str, task_type: str = "video",
              pin: tuple[str, str] | None = None, **kwargs) -> str:
    """One provider/model for the whole script: `pin` is (provider, model)."""
    if pin:
        from app.services.llm import chat as _chat
        provider, model = pin
        return _chat(prompt, task_type=task_type, model=model,
                     only_provider=provider, strict_model=True, **kwargs)
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
For every section give 3 to 5 key_points: short noun phrases (at most 8 words) a student reads on the slide.
key_points must state real ideas about the topic: no brackets, no arrows, no "[Input Context]" style templates, no marketing filler.
Return ONLY valid JSON:
{{"sections": [{{"title": "...", "goal": "one sentence on what this section teaches", "budget_words": {budget_each}, "key_points": ["...", "..."]}}, ...]}}
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
            "key_points": sanitize_bullets(s.get("key_points") or s.get("bullets") or []),
        })
    # Pad/truncate to exactly n_sections with sensible defaults
    while len(out) < n_sections:
        out.append({"title": f"Section {len(out)+1}", "goal": "",
                    "budget_words": budget_each, "key_points": []})
    return out[:n_sections]


def _gen_section_text(section: dict, outline: list[dict], index: int,
                      running_summary: str, title: str, language: str,
                      pin: tuple[str, str] | None = None) -> str:
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
    text = (_llm_chat(base_prompt, task_type="video", pin=pin,
                      max_output_tokens=max(600, target * 3), timeout=180) or "").strip()
    words = _count_words(text)
    if not (int(target * 0.85) <= words <= int(target * 1.15)) and words > 0:
        direction = "expand" if words < target else "condense"
        fix_prompt = f"""Rewrite the narration below to be approximately {target} words ({direction} needed; acceptable {int(target*0.85)}-{int(target*1.15)} words). Keep the same topic and spoken style. Plain text only.

NARRATION:
{text}"""
        try:
            fixed = (_llm_chat(fix_prompt, task_type="video", pin=pin,
                               max_output_tokens=max(600, target * 3), timeout=180) or "").strip()
            if _count_words(fixed) > 0:
                text = fixed
        except Exception:
            pass
    words = _count_words(text)
    if not (int(target * 0.85) <= words <= int(target * 1.15)) and words > 0:
        try:
            from app.services.gemini import generate_via_ollama
            local_text = generate_via_ollama(
                f"""Rewrite this narration to be approximately {target} words
(acceptable range {int(target*0.85)}-{int(target*1.15)} words).
Keep the topic and spoken style, expand or condense as needed, and return plain text only.

NARRATION:
{text}"""
            ).strip()
            if _count_words(local_text) > 0:
                text = local_text
        except Exception:
            pass
    return text


def generate_sectioned_scenes(title: str, prompt: str, duration_min: int,
                              language: str, notes: str = "",
                              slides: list[dict] | None = None) -> list[dict]:
    """
    Generate the video script in sections: outline -> per-section narration
    with word budgets and a running summary. Returns (scenes, models_used).
    One model writes every section; if it fails mid-way the failed section is
    retried on the next model of the same tier. Raises GeminiError (typed code)
    when all providers are exhausted; raises VideoStageError on unrecoverable
    length or placeholder content.
    """
    target = _target_words(duration_min)
    n = _section_count(duration_min)
    outline_started = time.time()
    outline = _section_outline(title, prompt, duration_min, language, notes, n, target)
    logger.info("[video] outline ready in %.1fs (%d sections, %d target words)",
                time.time() - outline_started, len(outline), target)

    scenes: list[dict] = []
    summary_parts: list[str] = []
    models_used: list[str] = []
    pin: tuple[str, str] | None = None
    for i, section in enumerate(outline):
        section_started = time.time()
        try:
            text = _gen_section_text(section, outline, i,
                                     "\n".join(summary_parts[-3:]), title, language, pin=pin)
        except Exception:
            if pin is None:
                raise
            # The pinned model failed mid-script: retry this scene on the next
            # model of the same tier, then continue with whatever answered.
            logger.warning("[video] pinned model %s failed on section %d; retrying unpinned",
                           pin[1], i + 1)
            pin = None
            text = _gen_section_text(section, outline, i,
                                     "\n".join(summary_parts[-3:]), title, language)
        try:
            from app.services.llm import last_used as _last_used
            used = _last_used() or {}
        except Exception:
            used = {}
        if used.get("model"):
            pair = (used.get("provider") or "", used["model"])
            pin = pin or pair
            if used["model"] not in models_used:
                models_used.append(used["model"])
        if not text:
            raise VideoStageError("script_generation", "EMPTY_SECTION",
                                  f"Section '{section['title']}' produced no narration. Please try again.")
        logger.info("[video] section %d/%d written in %.1fs", i + 1, len(outline),
                    time.time() - section_started)
        scenes.append({
            "title": section["title"],
            "narration": text,
            "content": text[:600],
            "highlight": "",
            "bullets": sanitize_bullets(section.get("key_points") or []),
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
    if not _within_tolerance(total, target, duration_min):
        raise VideoStageError(
            "script_generation", "LENGTH_OUT_OF_TOLERANCE",
            f"Generated script is ~{total} words but a {duration_min}-minute video needs "
            f"~{target} words (±{int(get_settings().video_script_tolerance * 100)}%). "
            "Please try again or choose a shorter duration.",
        )
    logger.info("[video] script models used: %s", ", ".join(models_used) or "unknown")
    return scenes, models_used


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
    if os.environ.get("EDUSENSE_OFFLINE") == "1" or os.environ.get("HF_HUB_OFFLINE") == "1":
        return False, (
            "Narration needs internet (Google TTS). Connect once to generate the voice "
            "track, or remove the OFFLINE file for this run."
        )
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        fut = pool.submit(_gtts_scene, text, out_path, lang)
        try:
            ok = fut.result(timeout=timeout)
            return ok, None if ok else "gTTS produced no audio file"
        except FuturesTimeout:
            return False, f"TTS timed out after {timeout:.0f}s"
        except Exception as exc:
            message = str(exc)[:200]
            if any(word in message.lower() for word in ("getaddrinfo", "connection", "network", "timed out")):
                message = (
                    "Narration needs internet (Google TTS) and the connection failed. "
                    "Connect once, or generate the video without narration."
                )
            return False, message
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

    ffmpeg_bin = find_ffmpeg()
    if ffmpeg_bin and len(audio_files) > 1:
        list_file = project_dir / "audio-list.txt"
        list_file.write_text(
            "".join(f"file '{f.as_posix()}'\n" for f in audio_files),
            encoding="utf-8",
        )
        try:
            subprocess.run(
                [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
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
    ffprobe = find_ffprobe()
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, OSError):
        return None
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
    rtl: bool = False,
) -> str:
    slides_html = []
    chapters_html = []
    transcript_html = []
    # Build JS array of per-slide durations in ms for timed autoplay
    slide_durations_ms = []
    for index, scene in enumerate(scenes):
        bullets = sanitize_bullets(scene.get("bullets"))
        body = html.escape(scene.get("narration") or scene.get("content") or "")
        dur_ms = _clamp_duration(scene.get("duration_seconds", DEFAULT_SCENE_SECONDS)) * 1000
        slide_durations_ms.append(dur_ms)
        chapter_title = html.escape(scene.get("title") or f"Scene {index + 1}")
        chapters_html.append(f'<button type="button" class="chapter" data-index="{index}"><span>{index + 1}</span>{chapter_title}</button>')
        transcript_html.append(f'<button type="button" class="transcript-line" data-index="{index}"><strong>{chapter_title}</strong><span>{body}</span></button>')
        slides_html.append(
            f"""
            <section class="slide{' active' if index == 0 else ''}" data-index="{index}" data-dur="{dur_ms}">
              <div class="slide-inner">
                <p class="slide-num">Slide {index + 1} / {len(scenes)}</p>
                <h2>{html.escape(scene.get('title') or f'Scene {index + 1}')}</h2>
                {_bullet_html(bullets)}
              </div>
            </section>
            """
        )
    audio_block = f'<audio id="audio" controls src="{audio_name}"></audio>' if audio_name else ""
    lang_attr = "ar" if rtl else "en"
    dir_attr = "rtl" if rtl else "ltr"
    durations_js = json.dumps(slide_durations_ms)
    player = f"""<!DOCTYPE html>
<html lang="{lang_attr}" dir="{dir_attr}">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(title)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Inter, 'Noto Sans Arabic', Arial, sans-serif; background: radial-gradient(circle at top, rgba(45,212,191,0.18), transparent 30%), linear-gradient(135deg, #071120, #10243f 55%, #0d1b2e); color: white; min-height: 100vh; overflow-x: hidden; }}
    body::before, body::after {{ content: ""; position: fixed; inset: auto; width: 28rem; height: 28rem; border-radius: 999px; filter: blur(80px); opacity: 0.4; animation: floatBlob 12s ease-in-out infinite; z-index: 0; }}
    body::before {{ top: -6rem; left: -4rem; background: rgba(45, 212, 191, 0.25); }}
    body::after {{ right: -6rem; bottom: -8rem; background: rgba(59, 130, 246, 0.2); animation-delay: -4s; }}
    .wrap {{ position: relative; z-index: 1; max-width: 1180px; margin: 0 auto; padding: 20px; }}
    .stage-layout {{ display: grid; grid-template-columns: 220px minmax(0,1fr) 280px; gap: 16px; }}
    .panel {{ background: rgba(7,17,32,0.72); border: 1px solid rgba(148,163,184,0.22); border-radius: 16px; padding: 12px; max-height: 520px; overflow-y: auto; }}
    .chapters, .transcript {{ display: grid; gap: 8px; }}
    .chapter, .transcript-line {{ width: 100%; text-align: left; background: rgba(15,23,42,0.7); border: 1px solid rgba(94,234,212,0.16); border-radius: 10px; padding: 10px; color: white; }}
    .chapter span {{ display: inline-grid; width: 24px; height: 24px; margin-right: 8px; place-items: center; border-radius: 999px; background: #14b8a6; }}
    .transcript-line strong {{ display: block; color: #5eead4; margin-bottom: 4px; }}
    .transcript-line span {{ display: block; line-height: 1.45; font-size: 12px; color: #dbeafe; }}
    .speed {{ background: rgba(15,23,42,0.8); color: white; border: 1px solid rgba(148,163,184,0.3); border-radius: 8px; padding: 8px; }}
    .quiz {{ display: none; margin-top: 12px; padding: 12px; border-radius: 12px; background: rgba(245,158,11,0.14); border: 1px solid rgba(251,191,36,0.4); }}
    .quiz.active {{ display: block; }}
    @media (max-width: 980px) {{ .stage-layout {{ grid-template-columns: 1fr; }} .panel {{ max-height: 220px; }} }}
    h1 {{ font-size: clamp(1.4rem, 3vw, 2.3rem); margin-bottom: 16px; }}
    .slide {{ display: none; animation: fadeIn 0.5s ease; }}
    .slide.active {{ display: block; }}
    .slide-inner {{ background: rgba(7, 17, 32, 0.62); border: 1px solid rgba(94,234,212,0.24); border-radius: 24px; padding: clamp(20px, 4vw, 40px); min-height: 460px; box-shadow: 0 30px 80px rgba(0,0,0,0.3); backdrop-filter: blur(14px); }}
    .slide-num {{ color: #5eead4; font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; }}
    h2 {{ margin: 12px 0 16px; color: #5eead4; font-size: clamp(1.4rem, 3vw, 2rem); line-height: 1.3; }}
    .highlight {{ background: rgba(20,184,166,0.2); border-left: 4px solid #14b8a6; padding: 12px 16px; border-radius: 8px; font-weight: 600; margin-bottom: 16px; }}
    .body {{ line-height: 1.8; font-size: clamp(1rem, 2.2vw, 1.15rem); margin-bottom: 20px; white-space: pre-wrap; }}
    .bullets {{ margin: 0; padding-left: 1.25rem; line-height: 1.9; font-size: clamp(1.05rem, 2.4vw, 1.5rem); }}
    .bullets li {{ margin-bottom: 10px; }}
    html[dir="rtl"] .bullets {{ padding-left: 0; padding-right: 1.25rem; }}
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
    <div class="stage-layout">
      <aside class="panel"><strong>Chapters</strong><div class="chapters">{''.join(chapters_html)}</div></aside>
      <main>{''.join(slides_html)}
        <div id="quiz" class="quiz">
          <strong>Pause checkpoint</strong>
          <p>Which key idea should you remember from this scene?</p>
          <button type="button" class="quiz-answer" data-correct="true">The scene's highlighted concept</button>
          <button type="button" class="quiz-answer" data-correct="false">An unrelated detail</button>
          <p id="quiz-result"></p>
        </div>
      </main>
      <aside class="panel"><strong>Transcript</strong><div class="transcript">{''.join(transcript_html)}</div></aside>
    </div>
    <div class="controls">
      <button type="button" id="prev">Previous</button>
      <button type="button" id="next">Next</button>
      <button type="button" id="play">Play Narration</button>
      <button type="button" id="explain">Explain this scene again simpler</button>
      <select id="speed" class="speed" aria-label="Playback speed">
        <option value="0.75">0.75x</option>
        <option value="1" selected>1x</option>
        <option value="1.25">1.25x</option>
        <option value="1.5">1.5x</option>
      </select>
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
      document.getElementById('quiz').classList.toggle('active', current % 2 === 1);
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
    document.querySelectorAll('.chapter, .transcript-line').forEach((item) => item.addEventListener('click', () => {{
      clearTimeout(autoplayTimer);
      show(Number(item.dataset.index));
      if (audio) audio.currentTime = slideDurations.slice(0, Number(item.dataset.index)).reduce((sum, value) => sum + value, 0) / 1000;
    }}));
    document.getElementById('speed').addEventListener('change', (event) => {{
      if (audio) audio.playbackRate = Number(event.target.value);
    }});
    document.querySelectorAll('.quiz-answer').forEach((item) => item.addEventListener('click', () => {{
      document.getElementById('quiz-result').textContent = item.dataset.correct === 'true'
        ? 'Correct — the highlighted concept is the key takeaway.'
        : 'Try again — choose the scene highlight.';
    }}));
    document.getElementById('explain').addEventListener('click', async () => {{
      const sceneText = slides[current]?.innerText || '{html.escape(title)}';
      const token = localStorage.getItem('edusense_token');
      try {{
        const response = await fetch('/api/ai/chat', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json', ...(token ? {{ Authorization: 'Bearer ' + token }} : {{}}) }},
          body: JSON.stringify({{ message: 'Explain this educational scene again more simply, with one analogy and one quick example: ' + sceneText, stream: false }})
        }});
        const data = await response.json();
        alert(data.answer || data.response || data.detail || 'The simpler explanation is unavailable.');
      }} catch (_) {{
        alert('The simpler explanation is unavailable because the AI service could not be reached.');
      }}
    }});
    autoplay?.addEventListener('change', () => {{
      clearTimeout(autoplayTimer);
      if (autoplay.checked && !audio) scheduleNext();
    }});
    document.getElementById('play').addEventListener('click', () => {{
      const text = slides[current]?.innerText || '{html.escape(title)}';
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
# Slides: designed background + ASS text (libass shapes Arabic correctly)
# ---------------------------------------------------------------------------

SLIDE_TITLE_SIZE = 76
SLIDE_BULLET_SIZE = 44


def _asset_fonts_dir() -> Path:
    """Bundled fonts live with the frontend so nothing is fetched from a CDN."""
    return Path(__file__).resolve().parents[3] / "frontend" / "public" / "fonts"


def _resolve_slide_font(rtl: bool) -> tuple[Path | None, str]:
    candidates = (
        [("noto-arabic-700.ttf", "Noto Sans Arabic"),
         ("noto-arabic-600.ttf", "Noto Sans Arabic")]
        if rtl else
        [("inter-700.ttf", "Inter"), ("inter-600.ttf", "Inter")]
    )
    for name, family in candidates:
        path = _asset_fonts_dir() / name
        if path.exists():
            return path, family
    system_font = Path("C:/Windows/Fonts/tahoma.ttf") if rtl else Path("C:/Windows/Fonts/arial.ttf")
    if system_font.exists():
        return system_font, ("Tahoma" if rtl else "Arial")
    return None, ("Noto Sans Arabic" if rtl else "Inter")


def _prepare_slide_font(project_dir: Path, rtl: bool) -> str:
    """Copy the slide font beside the ASS files so fontsdir=fonts stays a plain name."""
    source, family = _resolve_slide_font(rtl)
    fonts_dir = project_dir / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)
    if source and source.exists():
        target = fonts_dir / source.name
        if not target.exists():
            shutil.copy(str(source), str(target))
    return family


def _render_slide_background(project_dir: Path) -> Path:
    """A designed 1080p backdrop (gradient, accent bar, soft shapes) without text."""
    from PIL import Image, ImageDraw

    width, height = SLIDE_WIDTH, SLIDE_HEIGHT
    image = Image.new("RGB", (width, height), (11, 18, 32))
    draw = ImageDraw.Draw(image)
    top, bottom = (8, 15, 28), (17, 38, 62)
    for y in range(height):
        ratio = y / max(1, height - 1)
        draw.line([(0, y), (width, y)],
                  fill=tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3)))
    draw.ellipse([width - 620, -280, width + 160, 460], fill=(20, 58, 86))
    draw.ellipse([-300, height - 420, 380, height + 200], fill=(14, 45, 68))
    draw.rectangle([0, 0, width, height], outline=(28, 46, 68), width=2)
    draw.rectangle([0, 0, 18, height], fill=(20, 184, 166))
    path = project_dir / "slide-bg.png"
    image.save(path)
    return path


def _ass_time(seconds: float) -> str:
    total = max(0.0, float(seconds))
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    return f"{hours}:{minutes:02d}:{total % 60:05.2f}"


def _ass_escape(text: str) -> str:
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\r", " ")
        .replace("\n", "\\N")
    )


def build_slide_text(scene: dict) -> tuple[str, list[str]]:
    """Exactly one title and up to five key points; the narration is not repeated."""
    title = strip_citations(str(scene.get("title") or "")).strip()
    return title, sanitize_bullets(scene.get("bullets"))


def _write_slide_ass(path: Path, scene: dict, duration: float, family: str) -> None:
    title, bullets = build_slide_text(scene)
    lines = [f"{{\\fs{SLIDE_TITLE_SIZE}\\b1}}{_ass_escape(title)}"]
    if bullets:
        lines.append("")
        for bullet in bullets:
            lines.append(f"{{\\fs{SLIDE_BULLET_SIZE}\\b0}}\u2022 {_ass_escape(bullet)}")
    text = "\\N".join(lines)
    content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {SLIDE_WIDTH}
PlayResY: {SLIDE_HEIGHT}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Slide,{family},{SLIDE_TITLE_SIZE},&H00FFFFFF,&H000000FF,&H00101820,&H64000000,0,0,0,0,100,100,0,0,1,2,1,5,190,190,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,{_ass_time(0)},{_ass_time(duration)},Slide,,0,0,0,,{{\\an5\\pos({SLIDE_WIDTH // 2},{SLIDE_HEIGHT // 2})}}{text}
"""
    path.write_text(content, encoding="utf-8")


def _srt_time(seconds: float) -> str:
    total = max(0.0, float(seconds))
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = int(total % 60)
    millis = int(round((total - int(total)) * 1000))
    if millis == 1000:
        secs += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if part.strip()]


def write_srt(project_dir: Path, scenes: list[dict]) -> Path | None:
    """Narration as subtitles: the only place the spoken text appears in full."""
    blocks: list[str] = []
    clock = 0.0
    index = 1
    for scene in scenes:
        duration = float(scene.get("duration_seconds") or DEFAULT_SCENE_SECONDS)
        narration = str(scene.get("narration") or scene.get("title") or "")
        sentences = _split_sentences(narration) or [narration]
        total_words = sum(_count_words(s) for s in sentences) or 1
        cursor = clock
        for sentence in sentences:
            span = max(0.8, duration * (_count_words(sentence) / total_words))
            start = cursor
            end = min(clock + duration, cursor + span)
            if end <= start:
                break
            blocks.append(f"{index}\n{_srt_time(start)} --> {_srt_time(end)}\n{sentence}\n")
            index += 1
            cursor = end
        clock += duration
    if not blocks:
        return None
    path = project_dir / "subtitles.srt"
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


def apply_measured_durations(project_dir: Path, scenes: list[dict],
                             target_seconds: float | None = None) -> int:
    """Scene length = measured narration length + a short pause, never a fixed number.

    Falls back to words / WPM only when the audio cannot be probed. Returns how
    many scenes were actually measured.
    """
    settings = get_settings()
    wpm = max(1.0, float(getattr(settings, "video_narration_wpm", 140.0) or 140.0))
    measured = 0
    raw_audio: list[float] = []
    for index, scene in enumerate(scenes):
        audio_path = project_dir / f"segment-{index}-audio.mp3"
        seconds = None
        if audio_path.exists() and audio_path.stat().st_size > 100:
            seconds = _probe_audio_duration(audio_path)
            if seconds is not None:
                measured += 1
        if seconds is None:
            words = _count_words(scene.get("narration") or scene.get("content") or "")
            seconds = max(1.5, (words / wpm) * 60.0) if words else float(DEFAULT_SCENE_SECONDS)
        raw_audio.append(float(seconds))

    # Fit the narration to the requested runtime: the TTS voice pace varies with
    # punctuation, so a 60 s script can read as 84 s. atempo keeps speech natural
    # while making the rendered MP4 match the duration the user asked for.
    speed = 1.0
    total_audio = sum(raw_audio)
    if target_seconds and total_audio > 0:
        usable = max(1.0, float(target_seconds) - len(scenes) * SCENE_PAUSE_SECONDS)
        speed = total_audio / usable
        speed = min(1.6, max(0.75, speed))
        if 0.95 <= speed <= 1.05:
            speed = 1.0

    for scene, seconds in zip(scenes, raw_audio):
        if speed != 1.0:
            scene["speed_factor"] = round(speed, 3)
        else:
            scene.pop("speed_factor", None)
        played = seconds / speed
        scene["audio_seconds"] = round(played, 2)
        scene["duration_seconds"] = max(MIN_SCENE_SECONDS, int(math.ceil(played + SCENE_PAUSE_SECONDS)))

    # If the narration is shorter than the request, let the closing slide hold
    # instead of slowing speech below a natural pace.
    if target_seconds and scenes:
        deficit = float(target_seconds) - sum(s["duration_seconds"] for s in scenes)
        if 0 < deficit <= 30:
            scenes[-1]["duration_seconds"] = int(scenes[-1]["duration_seconds"] + math.ceil(deficit))
    return measured


# ---------------------------------------------------------------------------
# ffmpeg: per-scene slide segments (background + burned slide text + narration)
# ---------------------------------------------------------------------------

def _try_ffmpeg(
    project_id: int,
    title: str,
    scenes: list[dict],
    total_minutes: int = 5,
    rtl: bool = False,
) -> tuple[str | None, str | None]:
    """Render one MP4. Returns (path, None) or (None, real reason it failed).

    Each scene becomes a segment of exactly its narration length (plus a short
    pause) showing one title and its key points burned in by libass, then the
    segments are stitched. Audio is padded so a lossy MP3 never cuts the slide.
    """
    output = STATIC_DIR / f"video-{project_id}.mp4"
    project_dir = STATIC_DIR / f"video-{project_id}"
    project_dir.mkdir(parents=True, exist_ok=True)
    if not scenes:
        return None, "There are no scenes to render."

    ffmpeg_bin = find_ffmpeg()
    if not ffmpeg_bin:
        return None, (
            "MP4 was not produced because ffmpeg was not found. Install it "
            "(winget install Gyan.FFmpeg) or set EDUSENSE_FFMPEG_PATH."
        )

    errors: list[str] = []
    try:
        _render_slide_background(project_dir)
        family = _prepare_slide_font(project_dir, rtl)
        concat_lines: list[str] = []
        for index, scene in enumerate(scenes):
            duration = max(1.0, float(scene.get("duration_seconds") or DEFAULT_SCENE_SECONDS))
            ass_name = f"slide-{index}.ass"
            _write_slide_ass(project_dir / ass_name, scene, duration, family)
            audio_name = f"segment-{index}-audio.mp3"
            audio_path = project_dir / audio_name
            has_audio = audio_path.exists() and audio_path.stat().st_size > 100
            segment = f"segment-{index}.mp4"

            # Relative names + cwd=project_dir keep Windows drive colons out of
            # the filter graph, which otherwise must be escaped twice.
            command = [ffmpeg_bin, "-y", "-loop", "1", "-framerate", "30",
                       "-i", "slide-bg.png"]
            if has_audio:
                command += ["-i", audio_name]
            command += ["-t", f"{duration:.2f}",
                        "-vf", f"subtitles=filename={ass_name}:fontsdir=fonts",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                        "-pix_fmt", "yuv420p", "-r", "30"]
            if has_audio:
                audio_filters = []
                speed = float(scene.get("speed_factor") or 1.0)
                if abs(speed - 1.0) > 0.01:
                    audio_filters.append(f"atempo={speed:.3f}")
                audio_filters.append("apad")
                command += ["-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
                            "-af", ",".join(audio_filters)]
            else:
                command += ["-an"]
            command.append(segment)

            result = subprocess.run(command, cwd=str(project_dir), capture_output=True)
            if result.returncode != 0:
                detail = (result.stderr or b"").decode("utf-8", "ignore").strip()[-600:]
                errors.append(f"segment {index + 1}: {detail or 'ffmpeg failed'}")
                (project_dir / "concat-error.txt").write_text(
                    "\n---\n".join(errors), encoding="utf-8")
                return None, (
                    f"The encoder could not render scene {index + 1}. "
                    f"ffmpeg said: {detail or 'unknown error'}"
                )
            concat_lines.append(f"file '{segment}'\n")

        (project_dir / "ffmpeg-list.txt").write_text("".join(concat_lines), encoding="utf-8")
        attempts = (
            ["-f", "concat", "-safe", "0", "-i", "ffmpeg-list.txt", "-c", "copy"],
            ["-f", "concat", "-safe", "0", "-i", "ffmpeg-list.txt",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2"],
        )
        for flags in attempts:
            result = subprocess.run([ffmpeg_bin, "-y", *flags, str(output)],
                                    cwd=str(project_dir), capture_output=True)
            if result.returncode == 0 and output.exists() and output.stat().st_size >= 1024:
                return str(output), None
            detail = (result.stderr or b"").decode("utf-8", "ignore").strip()[-600:]
            errors.append(detail or "ffmpeg exited 0 but produced no usable MP4")
        (project_dir / "concat-error.txt").write_text("\n---\n".join(errors), encoding="utf-8")
        return None, (
            "The encoder could not stitch the scenes into one MP4. "
            f"ffmpeg said: {errors[-1][:400]}"
        )
    except Exception as exc:  # noqa: BLE001
        (project_dir / "concat-error.txt").write_text(repr(exc), encoding="utf-8")
        return None, f"The video encoder failed: {exc}"


def validate_video_artifacts(project_id: int) -> tuple[bool, str]:
    """A video may only be reported completed when its files really exist.

    Verifies the stitched MP4 on disk and, when ffprobe is available, that it
    has a real positive duration. Returns (ok, readable_reason).
    """
    project_dir = STATIC_DIR / f"video-{project_id}"
    mp4_path = STATIC_DIR / f"video-{project_id}.mp4"
    if not mp4_path.exists() or mp4_path.stat().st_size < 1024:
        if not find_ffmpeg():
            return False, (
                "MP4 was not produced because ffmpeg was not found. Install it "
                "(winget install Gyan.FFmpeg) or set EDUSENSE_FFMPEG_PATH."
            )
        detail = ""
        try:
            detail = (project_dir / "concat-error.txt").read_text(encoding="utf-8")[-400:].strip()
        except Exception:  # noqa: BLE001
            detail = ""
        return False, (
            "The video encoder could not stitch the MP4."
            + (f" ffmpeg said: {detail}" if detail else " Check the backend log for the ffmpeg error.")
        )
    ffprobe = find_ffprobe()
    if ffprobe:
        try:
            result = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(mp4_path)],
                check=True, capture_output=True, text=True, timeout=30,
            )
            if not (result.stdout or "").strip() or float(result.stdout.strip()) <= 0:
                return False, "MP4 exists but ffprobe reports no duration; the file is not playable."
        except Exception as exc:  # noqa: BLE001
            return False, f"MP4 exists but ffprobe could not read it: {exc}"
    audio_path = project_dir / "narration.mp3"
    if not audio_path.exists() or audio_path.stat().st_size < 100:
        return False, "Narration audio (narration.mp3) is missing; the video has no voice track."
    return True, "ok"


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
    models_used: list[str] = []
    try:
        scenes, models_used = generate_sectioned_scenes(
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

    scenes = [_sanitize_scene(s) for s in scenes]

    # Per-scene TTS — per-scene timeout; partial failures are reported,
    # total failure raises a structured stage error.
    any_audio, audio_name, tts_errors = _tts_all_scenes(project_dir, scenes, lang_code)
    if not any_audio:
        detail = "; ".join(tts_errors[:3]) if tts_errors else "text-to-speech unavailable"
        raise VideoStageError("tts", "TTS_FAILED",
                              f"Narration audio could not be generated ({detail}). "
                              "Check network access to the TTS service and try again.")

    # Timing comes from the narration itself: measured length plus a short pause.
    measured = apply_measured_durations(project_dir, scenes,
                                       target_seconds=duration_min * 60)
    if not measured:
        script_warnings.append(
            "ffprobe is unavailable, so scene lengths were estimated from the word count."
        )
    reject_placeholders(scenes)

    (project_dir / "scenes.json").write_text(
        json.dumps({"title": title, "scenes": scenes, "warnings": script_warnings,
                    "generated_with": models_used}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_srt(project_dir, scenes)

    rtl = lang_code == "ar"
    # Write interactive HTML player (same per-scene durations the MP4 uses)
    _write_player(project_dir, title, scenes, audio_name, rtl=rtl)

    # MP4 rendering is the only optional stage: the script, SRT and player are
    # already on disk, so a codec failure is reported instead of losing them.
    rendered = _try_ffmpeg(project_id, title, scenes, duration_min, rtl=rtl)
    mp4_path, mp4_error = rendered if isinstance(rendered, tuple) else (rendered, None)

    warnings = list(script_warnings)
    if tts_errors:
        warnings.append(f"Partial TTS: {'; '.join(tts_errors[:3])}")
    if mp4_error:
        warnings.append(f"MP4: {mp4_error}")

    return {
        "video_path": str(project_dir / "player.html"),
        "video_url": f"/static/videos/video-{project_id}/player.html",
        "audio_url": f"/static/videos/video-{project_id}/narration.mp3" if any_audio else None,
        "mp4_url": f"/static/videos/video-{project_id}.mp4" if mp4_path else None,
        "srt_url": f"/static/videos/video-{project_id}/subtitles.srt",
        "scenes": scenes,
        "generated_with": ", ".join(models_used) or None,
        "mp4_error": mp4_error,
        "fallback": not mp4_path,
        "warnings": warnings,
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
            measured_durations = apply_measured_durations(project_dir, scenes)
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
    write_srt(project_dir, scenes)
    rtl = lang_code == "ar"
    _write_player(project_dir, title, scenes, audio_name, rtl=rtl)
    total_minutes = max(1, sum(s.get("duration_seconds", DEFAULT_SCENE_SECONDS) for s in scenes) // 60)
    (STATIC_DIR / f"video-{project_id}.mp4").unlink(missing_ok=True)
    rendered = _try_ffmpeg(project_id, title, scenes, total_minutes, rtl=rtl)
    mp4_path, mp4_error = rendered if isinstance(rendered, tuple) else (rendered, None)

    return {
        "video_url": f"/static/videos/video-{project_id}/player.html",
        "audio_url": f"/static/videos/video-{project_id}/narration.mp3" if any_audio else None,
        "mp4_url": f"/static/videos/video-{project_id}.mp4" if mp4_path else None,
        "scenes": scenes,
        "fallback": not mp4_path,
        "mp4_error": mp4_error,
        "duration_warning": duration_warning,
    }
