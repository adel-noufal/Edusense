"""Flashcard deck honesty (demo-day F1 / U3).

The old version of this file asserted the *fabricated* fallback deck: when the
model failed, the agent invented "pedagogical dimension" cards (throughput,
invariants, web titles) and this test required all 10 of them. Those templates
are gone. What must hold now:

  * model failure with no course chunks -> ContentGenerationUnavailable, and
    the caller gets a clear retry message instead of invented cards;
  * model failure with course chunks -> cards built only from those chunks
    (real quoted text + page citation), never padded to the requested count
    with filler;
  * a short/duplicated model answer keeps only the real, de-duplicated cards.
"""
import unittest
from unittest.mock import patch

from app.agents.flashcard_agent import FlashcardGenerationAgent, _generate_distinct_fallback_cards
from app.core.errors import ContentGenerationUnavailable


class TestTask6FlashcardDistinctness(unittest.TestCase):
    def setUp(self):
        self.agent = FlashcardGenerationAgent()

    def test_model_failure_without_sources_raises_honest_error(self):
        with patch("app.agents.flashcard_agent.generate_json_any", side_effect=Exception("Offline mode")):
            with patch("app.agents.tools.RAG_Search_Tool", return_value=[]):
                with patch("app.agents.tools.Web_Search_Tool", return_value=[]):
                    with self.assertRaises(ContentGenerationUnavailable) as ctx:
                        self.agent.generate(topic="Distributed Consensus", count=10, language="English")
        self.assertIn("nothing was created", str(ctx.exception).lower())
        self.assertNotIn("architectural", str(ctx.exception).lower())

    def test_cards_past_the_4th_are_distinct_and_rich(self):
        cards = _generate_distinct_fallback_cards(topic="Operating Systems", count=15)
        self.assertEqual(len(cards), 15)
        fronts = [c["front"] for c in cards]
        self.assertEqual(len(fronts), len(set(fronts)), "Duplicate question fronts")

    def test_large_count_25_cards(self):
        cards = _generate_distinct_fallback_cards(topic="Quantum Computing", count=25)
        self.assertEqual(len(cards), 25)
        fronts = [c["front"] for c in cards]
        self.assertEqual(len(fronts), len(set(fronts)), "Duplicate question detected when generating 25 cards")

    def test_rag_chunks_give_real_quoted_cards_only(self):
        """3 course chunks -> 3 cited cards, not 8 padded with invented ones."""
        sample_chunks = [
            {"source_file": "CS101_Lecture.pdf", "page": "12",
             "text": "A binary search tree maintains the invariant that left children are strictly less than the root."},
            {"source_file": "CS101_Lecture.pdf", "page": "14",
             "text": "Red-Black trees ensure O(log n) worst-case time by enforcing color invariants and tree rotations."},
            {"source_file": "Algorithms.pdf", "page": "45",
             "text": "B-Trees are optimized for block storage systems by minimizing disk seek operations through wide fanout."},
        ]
        with patch("app.agents.flashcard_agent.generate_json_any", side_effect=Exception("Offline mode")):
            with patch("app.agents.tools.RAG_Search_Tool", return_value=sample_chunks):
                result = self.agent.generate(
                    topic="Balanced Trees", count=8, language="English",
                    subject="Computer Science", grade_level="College",
                ).data

        cards = result.get("cards", [])
        self.assertLessEqual(len(cards), len(sample_chunks))
        self.assertIn("CS101_Lecture.pdf p.12", cards[0]["back"])
        self.assertIn("CS101_Lecture.pdf p.14", cards[1]["back"])
        self.assertIn("Algorithms.pdf p.45", cards[2]["back"])
        for card in cards:
            self.assertNotIn("Web:", card["front"])

    def test_llm_partial_answer_keeps_only_real_cards(self):
        llm_response = {
            "title": "Machine Learning Deck",
            "cards": [
                {"front": "What is overfitting?", "back": "When a model memorizes training noise rather than true signal."},
                {"front": "What is overfitting?", "back": "Duplicate front question!"},
                {"front": "What is gradient descent?", "back": "An optimization algorithm to minimize loss along gradient vectors."},
            ],
        }
        with patch("app.agents.flashcard_agent.generate_json_any", return_value=llm_response):
            with patch("app.agents.tools.RAG_Search_Tool", return_value=[]):
                with patch("app.agents.tools.Web_Search_Tool", return_value=[]):
                    result = self.agent.generate(topic="Machine Learning", count=6, language="English").data

        cards = result.get("cards", [])
        fronts = [c["front"] for c in cards]
        self.assertEqual(len(fronts), len(set(fronts)), "Duplicates remained after de-duplication")
        self.assertIn("What is overfitting?", fronts)
        self.assertIn("What is gradient descent?", fronts)
        self.assertEqual(len(cards), 2, "Only the two real model cards survive; nothing is invented")


if __name__ == "__main__":
    unittest.main()
