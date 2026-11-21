from __future__ import annotations

import json
import re
from typing import Any

from app.services import llm
from app.services.style_profiles import get_style_profile

MARKDOWN_CHARS = re.compile(r"[*_]{1,3}|^#{1,6}\s", re.MULTILINE)


def strip_markdown(text: str) -> str:
    text = (text or "").replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-+]\s+", "", text, flags=re.MULTILINE)
    return text.strip()


def plan_content(topic: str, prompt: str, language: str, style: str,
                 detail_level: str = "Standard", source_context: str = "") -> dict:
    profile = get_style_profile(style)
    return {
        "topic": topic,
        "language": language,
        "style": style,
        "detail_level": detail_level,
        "learning_objectives": [],
        "audience": "general secondary or undergraduate learners",
        "outline": [
            {"heading": "Introduction", "goal": "Frame the topic", "type": profile["section_types"][0], "bloom": "Understand"},
            {"heading": "Core Concepts", "goal": "Teach the main concepts", "type": profile["section_types"][1], "bloom": "Apply"},
            {"heading": "Practice", "goal": "Give a worked or self-check activity", "type": profile["section_types"][-1], "bloom": "Analyze"},
            {"heading": "Summary", "goal": "Synthesize key ideas", "type": "summary", "bloom": "Evaluate"},
        ],
        "source_context": source_context,
        "style_rules": profile["prompt_rules"],
    }


def critique_output(content: dict, topic: str) -> dict:
    prompt = (
        "Verify this generated educational content. Return ONLY valid JSON:\n"
        '{"accuracy":0.0,"clarity":0.0,"structure":0.0,"level":0.0,"no_repetition":0.0,"formatting":0.0,"score":0.0,"weak_sections":[],"rewrite_instructions":[]}\n'
        "Score each field 0-1. Penalize unsupported claims, repeated paragraphs, and markdown symbols.\n"
        f"Topic: {topic}\nContent:\n{json.dumps(content, ensure_ascii=False)[:12000]}"
    )
    try:
        result = llm.chat_json(prompt, task_type="general")
        if isinstance(result, dict):
            score = float(result.get("score") or 0)
            return result if score > 0 else {"score": 0.75, "weak_sections": [], "rewrite_instructions": [], "fallback": True}
    except Exception:
        pass
    return {"score": 0.75, "weak_sections": [], "rewrite_instructions": [], "fallback": True}


def format_strict_text(value: Any) -> Any:
    if isinstance(value, str):
        return strip_markdown(value)
    if isinstance(value, list):
        return [format_strict_text(v) for v in value]
    if isinstance(value, dict):
        return {k: format_strict_text(v) for k, v in value.items()}
    return value


def validate_quality(content: dict, source_attached: bool = False) -> list[str]:
    raw = json.dumps(content, ensure_ascii=False)
    issues = []
    if MARKDOWN_CHARS.search(raw):
        issues.append("raw_markdown")
    if source_attached and not content.get("sources"):
        issues.append("missing_citations")
    sections = content.get("sections") or []
    norms = []
    for section in sections:
        text = re.sub(r"\s+", " ", str(section.get("content") or "").lower()).strip()
        if len(text) > 30:
            norms.append(text)
    if len(norms) != len(set(norms)):
        issues.append("repeated_paragraph")
    return issues
