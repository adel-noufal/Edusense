from app.schemas.schemas import LessonRequest, QuizRequest, FlashcardRequest
from app.services.content_pipeline import format_strict_text, validate_quality
from app.services.style_profiles import get_style_profile


def test_generation_duration_removed_from_non_video_schemas():
    lesson = LessonRequest(topic="Photosynthesis", prompt="", detail_level="Standard")
    quiz = QuizRequest(topic="Photosynthesis", count=5)
    flashcards = FlashcardRequest(topic="Photosynthesis", count=5)
    assert "duration" not in lesson.model_dump()
    assert "duration" not in quiz.model_dump()
    assert "duration" not in flashcards.model_dump()


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
