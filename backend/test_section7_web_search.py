"""
Section 7 Verification: Web Search Grounding Beyond RAG

NOTE on patching: All agents use lazy imports inside helper functions:
    from app.agents.tools import RAG_Search_Tool
    from app.agents.tools import Web_Search_Tool
So the correct patch target is "app.agents.tools.RAG_Search_Tool" (the stub module's attributes).
"""
import sys
import os
import types
import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Put backend/ on sys.path  (must be FIRST, before any app.* import)
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

# ---------------------------------------------------------------------------
# Leaf stubs only — never overwrite real filesystem packages
# ---------------------------------------------------------------------------

def _leaf_stub(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod

# Fake gemini (no network calls)
def _fake_json(prompt, **kw):
    t = kw.get("task_type", "")
    if t == "quiz":
        return {"questions": [{"question": "Q?", "answer": "A",
                                "choices": ["A","B","C","D"], "correct_index": 0}]}
    if t == "flashcard":
        return {"title": "Deck", "cards": [{"front": "F?", "back": "B"}]}
    return {"lesson": "content", "objectives": [], "activities": []}

_leaf_stub("app.services.gemini",
           generate_text=lambda p, **k: "text",
           generate_json_any=_fake_json,
           generate_via_ollama=lambda *a, **k: "ollama",
           generate_content=lambda *a, **k: "content")

# DB stubs
_leaf_stub("app.db.session", SessionLocal=MagicMock(), get_db=MagicMock())
_leaf_stub("app.models.models", QuizAgentConfig=MagicMock())

# Tools stub — both tools return [] by default; tests patch them individually
tools_stub = _leaf_stub("app.agents.tools",
                         RAG_Search_Tool=lambda *a, **k: [],
                         Web_Search_Tool=lambda *a, **k: [])

# ---------------------------------------------------------------------------
# Import real app packages
# ---------------------------------------------------------------------------
importlib.import_module("app")
importlib.import_module("app.agents")

lesson_mod    = importlib.import_module("app.agents.lesson_agent")
quiz_mod      = importlib.import_module("app.agents.quiz_agent")
flashcard_mod = importlib.import_module("app.agents.flashcard_agent")

LessonGenerationAgent    = lesson_mod.LessonGenerationAgent
QuizGenerationAgent      = quiz_mod.QuizGenerationAgent
FlashcardGenerationAgent = flashcard_mod.FlashcardGenerationAgent

from app.agents.base import AgentResult

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------
RAG_CHUNKS = [
    {"text": "Photosynthesis converts light to energy", "source_file": "bio101.pdf", "page": "12"},
]
WEB_RESULTS = [
    {"title": "Photosynthesis Overview", "url": "https://example.com/photo",
     "content": "Light-dependent reactions occur in the thylakoid.", "score": 0.95},
    {"title": "Chlorophyll Role", "url": "https://example.com/chloro",
     "content": "Chlorophyll absorbs red and blue light.", "score": 0.88},
    {"title": "Calvin Cycle", "url": "https://example.com/calvin",
     "content": "Carbon fixation happens in the stroma.", "score": 0.82},
]
TOPIC   = "Photosynthesis"
SUBJECT = "Biology"
GRADE   = "10"

# ---------------------------------------------------------------------------
# Call helpers matching each agent's actual generate() signature
# ---------------------------------------------------------------------------

def _gen_lesson():
    req = SimpleNamespace(
        topic=TOPIC, subject=SUBJECT, grade_level=GRADE,
        count=3, language="English", prompt="", slide_count=5,
        diagram_count=1, image_count=1,
        teaching_style="Lecture", duration=45, additional_notes="",
    )
    return LessonGenerationAgent().generate(req)

def _gen_quiz():
    return QuizGenerationAgent().generate(
        topic=TOPIC, subject=SUBJECT, grade_level=GRADE,
        difficulty="Medium", count=3)

def _gen_flashcard():
    return FlashcardGenerationAgent().generate(
        topic=TOPIC, subject=SUBJECT, grade_level=GRADE, count=5)

# Patch helpers — target the stub module attributes since agents use lazy imports
_TOOLS = "app.agents.tools"
_RAG   = f"{_TOOLS}.RAG_Search_Tool"
_WEB   = f"{_TOOLS}.Web_Search_Tool"


# ===========================================================================
# GROUP 1: Lesson Agent Web Grounding
# ===========================================================================

class TestLessonAgentWebGrounding(unittest.TestCase):

    def test_rag_hit_no_web_call(self):
        """When RAG returns chunks, Web_Search_Tool must NOT be called."""
        with patch(_RAG, return_value=RAG_CHUNKS):
            with patch(_WEB, return_value=WEB_RESULTS) as web_m:
                _gen_lesson()
                web_m.assert_not_called()

    def test_rag_miss_web_called(self):
        """When RAG returns [], Web_Search_Tool IS called."""
        with patch(_RAG, return_value=[]):
            with patch(_WEB, return_value=WEB_RESULTS) as web_m:
                _gen_lesson()
                web_m.assert_called_once()

    def test_rag_miss_web_hit_unverified_false(self):
        """RAG=0, web=3 → unverified=False, sources have web labels, web_sources populated."""
        with patch(_RAG, return_value=[]):
            with patch(_WEB, return_value=WEB_RESULTS):
                res = _gen_lesson()
                self.assertFalse(res.data["unverified"],
                                 "unverified must be False when web sources available")
                sources = res.data.get("sources", [])
                self.assertTrue(any("Web" in s for s in sources),
                                f"Expected web source labels, got: {sources}")
                self.assertEqual(len(res.data.get("web_sources", [])), len(WEB_RESULTS))

    def test_rag_hit_unverified_false(self):
        """RAG=1, web not needed → unverified=False."""
        with patch(_RAG, return_value=RAG_CHUNKS):
            with patch(_WEB, return_value=[]):
                res = _gen_lesson()
                self.assertFalse(res.data["unverified"])

    def test_both_miss_unverified_true(self):
        """RAG=0, web=0 → unverified=True (graceful degradation, no crash)."""
        with patch(_RAG, return_value=[]):
            with patch(_WEB, return_value=[]):
                res = _gen_lesson()
                self.assertIsInstance(res, AgentResult)
                self.assertTrue(res.data["unverified"])

    def test_web_tool_exception_no_crash(self):
        """If Web_Search_Tool raises, agent still returns a result (no crash)."""
        with patch(_RAG, return_value=[]):
            with patch(_WEB, side_effect=Exception("Tavily down")):
                res = _gen_lesson()
                self.assertIsInstance(res, AgentResult)


# ===========================================================================
# GROUP 2: Quiz Agent Web Grounding
# ===========================================================================

class TestQuizAgentWebGrounding(unittest.TestCase):

    def test_rag_hit_no_web_call(self):
        """When RAG returns chunks, Web_Search_Tool must NOT be called."""
        with patch(_RAG, return_value=RAG_CHUNKS):
            with patch(_WEB, return_value=WEB_RESULTS) as web_m:
                _gen_quiz()
                web_m.assert_not_called()

    def test_rag_miss_web_called(self):
        """When RAG returns [], Web_Search_Tool IS called."""
        with patch(_RAG, return_value=[]):
            with patch(_WEB, return_value=WEB_RESULTS) as web_m:
                _gen_quiz()
                web_m.assert_called_once()

    def test_rag_miss_web_hit_unverified_false(self):
        """RAG=0, web=3 → unverified=False, sources have web labels, web_sources key present."""
        with patch(_RAG, return_value=[]):
            with patch(_WEB, return_value=WEB_RESULTS):
                res = _gen_quiz()
                self.assertFalse(res.data["unverified"])
                sources = res.data.get("sources", [])
                self.assertTrue(any("Web" in s for s in sources))
                self.assertIn("web_sources", res.data)

    def test_rag_hit_unverified_false(self):
        """RAG=1, web not needed → unverified=False."""
        with patch(_RAG, return_value=RAG_CHUNKS):
            with patch(_WEB, return_value=[]):
                res = _gen_quiz()
                self.assertFalse(res.data["unverified"])

    def test_both_miss_unverified_true(self):
        """RAG=0, web=0 → unverified=True (graceful degradation, no crash)."""
        with patch(_RAG, return_value=[]):
            with patch(_WEB, return_value=[]):
                res = _gen_quiz()
                self.assertIsInstance(res, AgentResult)
                self.assertTrue(res.data["unverified"])

    def test_web_tool_exception_no_crash(self):
        """If Web_Search_Tool raises, agent still returns a result."""
        with patch(_RAG, return_value=[]):
            with patch(_WEB, side_effect=Exception("Tavily error")):
                res = _gen_quiz()
                self.assertIsInstance(res, AgentResult)


# ===========================================================================
# GROUP 3: Flashcard Agent Web Grounding
# ===========================================================================

class TestFlashcardAgentWebGrounding(unittest.TestCase):

    def test_rag_hit_no_web_call(self):
        """When RAG returns chunks, Web_Search_Tool must NOT be called."""
        with patch(_RAG, return_value=RAG_CHUNKS):
            with patch(_WEB, return_value=WEB_RESULTS) as web_m:
                _gen_flashcard()
                web_m.assert_not_called()

    def test_rag_miss_web_called(self):
        """When RAG returns [], Web_Search_Tool IS called."""
        with patch(_RAG, return_value=[]):
            with patch(_WEB, return_value=WEB_RESULTS) as web_m:
                _gen_flashcard()
                web_m.assert_called_once()

    def test_rag_miss_web_hit_unverified_false(self):
        """RAG=0, web=3 → unverified=False, sources have web labels, web_sources populated."""
        with patch(_RAG, return_value=[]):
            with patch(_WEB, return_value=WEB_RESULTS):
                res = _gen_flashcard()
                self.assertFalse(res.data["unverified"])
                sources = res.data.get("sources", [])
                self.assertTrue(any("Web" in s for s in sources))
                self.assertEqual(len(res.data.get("web_sources", [])), len(WEB_RESULTS))

    def test_rag_hit_unverified_false(self):
        """RAG=1, web not needed → unverified=False."""
        with patch(_RAG, return_value=RAG_CHUNKS):
            with patch(_WEB, return_value=[]):
                res = _gen_flashcard()
                self.assertFalse(res.data["unverified"])

    def test_both_miss_unverified_true(self):
        """RAG=0, web=0 → unverified=True (graceful degradation, no crash)."""
        with patch(_RAG, return_value=[]):
            with patch(_WEB, return_value=[]):
                res = _gen_flashcard()
                self.assertIsInstance(res, AgentResult)
                self.assertTrue(res.data["unverified"])

    def test_web_tool_exception_no_crash(self):
        """If Web_Search_Tool raises, agent still returns a result."""
        with patch(_RAG, return_value=[]):
            with patch(_WEB, side_effect=Exception("Network down")):
                res = _gen_flashcard()
                self.assertIsInstance(res, AgentResult)


# ===========================================================================
# GROUP 4: _build_web_context helper existence and structure
# ===========================================================================

class TestWebContextHelperExists(unittest.TestCase):

    def test_lesson_has_helper(self):
        self.assertTrue(hasattr(lesson_mod, "_build_web_context"),
                        "lesson_agent must expose _build_web_context")

    def test_quiz_has_helper(self):
        self.assertTrue(hasattr(quiz_mod, "_build_web_context"),
                        "quiz_agent must expose _build_web_context")

    def test_flashcard_has_helper(self):
        self.assertTrue(hasattr(flashcard_mod, "_build_web_context"),
                        "flashcard_agent must expose _build_web_context")

    def test_helper_returns_triple_on_results(self):
        """_build_web_context must return (str, list, list) with correct content."""
        with patch(_WEB, return_value=WEB_RESULTS):
            context, raw, labels = lesson_mod._build_web_context(TOPIC)
        self.assertIsInstance(context, str)
        self.assertIsInstance(raw, list)
        self.assertIsInstance(labels, list)
        self.assertGreater(len(context), 0, "context block should be non-empty")
        self.assertEqual(len(raw), len(WEB_RESULTS))
        self.assertEqual(len(labels), len(WEB_RESULTS))

    def test_helper_empty_on_no_results(self):
        with patch(_WEB, return_value=[]):
            context, raw, labels = lesson_mod._build_web_context(TOPIC)
        self.assertEqual((context, raw, labels), ("", [], []))

    def test_helper_empty_on_exception(self):
        with patch(_WEB, side_effect=RuntimeError("fail")):
            context, raw, labels = lesson_mod._build_web_context(TOPIC)
        self.assertEqual((context, raw, labels), ("", [], []))


# ===========================================================================
# GROUP 5: Graceful Degradation (simulate no sources available)
# ===========================================================================

class TestGracefulDegradation(unittest.TestCase):

    def test_lesson_no_sources_returns_result(self):
        """Empty RAG + empty web → agent still returns result, unverified=True."""
        with patch(_RAG, return_value=[]):
            with patch(_WEB, return_value=[]):
                res = _gen_lesson()
                self.assertIsInstance(res, AgentResult)
                self.assertTrue(res.data["unverified"])

    def test_quiz_no_sources_returns_result(self):
        with patch(_RAG, return_value=[]):
            with patch(_WEB, return_value=[]):
                res = _gen_quiz()
                self.assertIsInstance(res, AgentResult)
                self.assertTrue(res.data["unverified"])

    def test_flashcard_no_sources_returns_result(self):
        with patch(_RAG, return_value=[]):
            with patch(_WEB, return_value=[]):
                res = _gen_flashcard()
                self.assertIsInstance(res, AgentResult)
                self.assertTrue(res.data["unverified"])


# ===========================================================================
# Run
# ===========================================================================

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [
        TestLessonAgentWebGrounding,
        TestQuizAgentWebGrounding,
        TestFlashcardAgentWebGrounding,
        TestWebContextHelperExists,
        TestGracefulDegradation,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
