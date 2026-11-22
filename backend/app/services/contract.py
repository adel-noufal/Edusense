"""Output-contract checks for lessons, quizzes and flashcards.

Every rule is objective and runs on local models, so the suite costs no cloud
quota: exact counts, option/answer integrity, explanations, uniqueness,
Bloom tags, detail-level section ranges and language purity.
"""
from __future__ import annotations

import json
import re
import sys

LESSON_SECTION_RANGE = {"Brief": (3, 4), "Standard": (4, 6), "Detailed": (6, 8)}
LESSON_WORDS_PER_SECTION = {"Brief": (40, 120), "Standard": (90, 260), "Detailed": (180, 480)}
BLOOM_BY_DIFFICULTY = {
    "easy": ["Remember", "Understand", "Apply"],
    "medium": ["Understand", "Apply", "Analyze"],
    "hard": ["Analyze", "Evaluate", "Create"],
}
ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
LATIN_WORD_RE = re.compile(r"[A-Za-z]{3,}")


def _words(text: str) -> int:
    return len([w for w in re.split(r"\s+", str(text or "").strip()) if w])


def language_purity(text: str, language: str) -> tuple[bool, str]:
    """Arabic output must be mostly Arabic; English output mostly Latin."""
    text = str(text or "")
    arabic = len(ARABIC_RE.findall(text))
    latin = len(LATIN_WORD_RE.findall(text))
    total = arabic + latin
    if total < 20:
        return False, "too little text to judge"
    share = arabic / total
    if language.lower().startswith("ar"):
        ok = share >= 0.55
        return ok, f"arabic share {share:.0%} (needs >=55%)"
    ok = share <= 0.15
    return ok, f"arabic share {share:.0%} (needs <=15% for English)"


def enforce_lesson_detail(sections: list[dict], detail_level: str) -> list[dict]:
    low, high = LESSON_SECTION_RANGE.get(detail_level, (4, 6))
    return list(sections or [])[:high]


def check_lesson(result: dict, detail_level: str = "Standard", language: str = "English") -> list[str]:
    problems = []
    sections = result.get("sections") or []
    low, high = LESSON_SECTION_RANGE.get(detail_level, (4, 6))
    if not (low <= len(sections) <= high):
        problems.append(f"sections {len(sections)} outside {low}-{high} for {detail_level}")
    wlow, whigh = LESSON_WORDS_PER_SECTION.get(detail_level, (90, 260))
    for idx, section in enumerate(sections):
        n = _words(section.get("content", ""))
        if n < wlow // 2:
            problems.append(f"section {idx + 1} only {n} words")
        if n > whigh * 2:
            problems.append(f"section {idx + 1} has {n} words (too long)")
    ok, note = language_purity(json.dumps(sections, ensure_ascii=False), language)
    if not ok:
        problems.append(f"language purity: {note}")
    if not result.get("learning_objectives"):
        problems.append("no learning objectives")
    return problems


def stamp_quiz(result: dict, difficulty: str) -> dict:
    """Attach a Bloom tag to each question and a computed answer key."""
    bloom = BLOOM_BY_DIFFICULTY.get(str(difficulty).lower(), BLOOM_BY_DIFFICULTY["medium"])
    key = []
    for idx, q in enumerate(result.get("questions") or []):
        q.setdefault("bloom", bloom[idx % len(bloom)])
        key.append({"question": idx + 1, "answer": q.get("answer", "")})
    result["answer_key"] = key
    return result


def check_quiz(result: dict, expected_count: int, difficulty: str = "Medium") -> list[str]:
    problems = []
    questions = result.get("questions") or []
    if len(questions) != expected_count:
        problems.append(f"count {len(questions)} != {expected_count}")
    letters = set()
    for idx, q in enumerate(questions):
        options = q.get("options") or []
        if len(options) != 4:
            problems.append(f"q{idx + 1} has {len(options)} options")
        answer = str(q.get("answer", "")).strip().upper()
        if answer not in {"A", "B", "C", "D"}:
            problems.append(f"q{idx + 1} answer '{answer}' is not A-D")
        if len(str(q.get("explanation", ""))) < 40:
            problems.append(f"q{idx + 1} explanation too short")
        if not q.get("bloom"):
            problems.append(f"q{idx + 1} missing Bloom tag")
        letters.add(answer)
    expected = BLOOM_BY_DIFFICULTY.get(str(difficulty).lower())
    if expected and questions and not any(q.get("bloom") in expected for q in questions):
        problems.append("no Bloom tag matches the difficulty level")
    if result.get("answer_key") and len(result["answer_key"]) != len(questions):
        problems.append("answer key length mismatch")
    return problems


def check_flashcards(result: dict, expected_count: int, language: str = "English") -> list[str]:
    problems = []
    cards = result.get("cards") or []
    if len(cards) != expected_count:
        problems.append(f"count {len(cards)} != {expected_count}")
    fronts = [str(c.get("front", c.get("term", ""))).strip().lower() for c in cards]
    if len(set(fronts)) != len(fronts):
        problems.append("duplicate cards")
    for idx, card in enumerate(cards):
        if not str(card.get("front") or card.get("term") or "").strip():
            problems.append(f"card {idx + 1} missing front")
        if not str(card.get("back") or card.get("definition") or "").strip():
            problems.append(f"card {idx + 1} missing back")
    ok, note = language_purity(json.dumps(cards, ensure_ascii=False), language)
    if not ok:
        problems.append(f"language purity: {note}")
    return problems


def run_suite(local_only: bool = True) -> int:
    """Generate and print a PASS/FAIL table; local_only defaults to Ollama."""
    import os
    if local_only:
        os.environ["EDUSENSE_DISABLE_CLOUD"] = "1"
    else:
        os.environ.pop("EDUSENSE_DISABLE_CLOUD", None)
    from app.agents.quiz_agent import QuizGenerationAgent
    from app.agents.flashcard_agent import FlashcardGenerationAgent
    from app.agents.lesson_agent import LessonGenerationAgent
    from app.schemas.schemas import LessonRequest

    failures = 0

    def report(name: str, problems: list[str]) -> None:
        nonlocal failures
        print(f"{'PASS' if not problems else 'FAIL'}  {name}")
        for problem in problems[:6]:
            print(f"        - {problem}")
        if problems:
            failures += 1

    for level in ("Brief", "Standard", "Detailed"):
        try:
            lesson = LessonGenerationAgent().generate(
                LessonRequest(topic="The water cycle", prompt="", detail_level=level,
                              language="English", teaching_style="Interactive")
            ).data
            report(f"lesson/{level}", check_lesson(lesson, level, "English"))
        except Exception as exc:
            report(f"lesson/{level}", [f"generation failed: {exc}"])

    try:
        quiz = QuizGenerationAgent().generate("The water cycle", "Medium", 5, "", language="English").data
        quiz = stamp_quiz(quiz, "Medium")
        report("quiz/Medium x5", check_quiz(quiz, 5, "Medium"))
    except Exception as exc:
        report("quiz/Medium x5", [f"generation failed: {exc}"])

    try:
        cards = FlashcardGenerationAgent().generate("The water cycle", 5, "English", "").data
        report("flashcards/English x5", check_flashcards(cards, 5, "English"))
    except Exception as exc:
        report("flashcards/English x5", [f"generation failed: {exc}"])

    print("CONTRACT_FAILURES:", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run_suite(local_only="--cloud" not in sys.argv))
