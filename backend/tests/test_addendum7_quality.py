from app.schemas.schemas import LessonRequest, QuizRequest, FlashcardRequest, VideoRequest
from app.services.content_pipeline import format_strict_text, validate_quality
from app.services.style_profiles import get_style_profile


def test_generation_duration_removed_from_non_video_schemas():
    """U14: only video requests carry a runtime.

    An older client that still posts `duration` to a lesson must not break, and
    the value must not appear in the lesson's own output.
    """
    lesson = LessonRequest(topic="Photosynthesis", prompt="", detail_level="Standard")
    legacy_lesson = LessonRequest(topic="Photosynthesis", prompt="", duration=9)
    quiz = QuizRequest(topic="Photosynthesis", count=5)
    flashcards = FlashcardRequest(topic="Photosynthesis", count=5)
    for request in (lesson, legacy_lesson):
        assert "duration" not in request.model_dump()
    assert "duration" not in quiz.model_dump()
    assert "duration" not in flashcards.model_dump()
    # The video word-count gate still reads a requested runtime.
    assert VideoRequest(title="V", prompt="p", duration=3).duration == 3


def test_style_profiles_have_distinct_section_and_layout_structures():
    interactive = get_style_profile("Interactive")
    formal = get_style_profile("Lecture/Formal")
    socratic = get_style_profile("Socratic")
    assert interactive["section_types"] != formal["section_types"]
    assert interactive["layout_mix"] != socratic["layout_mix"]
    assert formal["pacing"] != socratic["pacing"]


def test_strict_formatting_and_quality_validation():
    content = {
        "title": "Variables",
        "sections": [{"heading": "Basics", "content": "A variable stores a value."}],
        "cards": [{"front": "What is a variable?", "back": "A named value reference."}],
    }
    clean = format_strict_text(content)
    assert "**" not in str(clean)
    assert validate_quality({"sections": [{"content": "The same paragraph."}]}) == []
