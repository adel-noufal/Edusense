STYLE_PROFILES = {
    "Interactive": {
        "section_types": ["quick_check", "try_it", "worked_example", "reflection"],
        "layout_mix": ["quiz_discussion", "example_code", "bullets_visual", "process_flow"],
        "prompt_rules": "Place a quick check or try-it activity in every 2 sections. Prefer active participation.",
        "pacing": "alternating explanation and interaction",
    },
    "Lecture/Formal": {
        "section_types": ["definition", "theory", "evidence", "synthesis"],
        "layout_mix": ["definition_quote", "bullets_visual", "two_column", "summary"],
        "prompt_rules": "Use formal exposition, define terms before applications, and keep claims hierarchical.",
        "pacing": "steady conceptual exposition",
    },
    "Socratic": {
        "section_types": ["guiding_question", "hint", "answer", "transfer"],
        "layout_mix": ["quiz_discussion", "two_column", "definition_quote", "summary"],
        "prompt_rules": "Lead with questions and reveal hints before answers. Require learner reasoning.",
        "pacing": "question-pause-reveal",
    },
    "Storytelling/Real-world": {
        "section_types": ["scenario", "stakeholder_goal", "turning_point", "lesson"],
        "layout_mix": ["timeline", "two_column", "bullets_visual", "example_code"],
        "prompt_rules": "Open with a realistic scenario and use concrete stakes, consequences, and reflection.",
        "pacing": "narrative case-study pacing",
    },
    "Problem-based / Hands-on": {
        "section_types": ["problem", "worked_example", "constraint", "practice"],
        "layout_mix": ["example_code", "process_flow", "two_column", "quiz_discussion"],
        "prompt_rules": "Start from an observable problem, model the solution, then give a practice challenge.",
        "pacing": "problem-demonstration-practice",
    },
    "Visual": {
        "section_types": ["visual_concept", "diagram", "caption", "takeaway"],
        "layout_mix": ["diagram", "process_flow", "timeline", "big_number"],
        "prompt_rules": "Prefer short phrases, diagrams, arrows, timelines, and large visual anchors.",
        "pacing": "brief visual beats",
    },
}


def get_style_profile(style: str | None) -> dict:
    if not style:
        return STYLE_PROFILES["Interactive"]
    normalized = str(style).strip().lower()
    for name, profile in STYLE_PROFILES.items():
        if normalized in (name.lower(), name.lower().replace(" / ", "/").replace(" ", "")):
            return profile
    for alias in ("formal", "friendly", "professional"):
        if normalized == alias:
            return STYLE_PROFILES["Lecture/Formal"]
    return STYLE_PROFILES["Interactive"]
