import sys
import unittest
from unittest.mock import patch, MagicMock

from app.agents.flashcard_agent import (
    FlashcardGenerationAgent,
    _generate_distinct_fallback_cards,
    _build_rag_context,
    _build_rag_context_with_chunks,
    PEDAGOGICAL_DIMENSIONS,
)
from app.agents.base import AgentResult


class TestTask6FlashcardDistinctness(unittest.TestCase):
    def setUp(self):
        self.agent = FlashcardGenerationAgent()

    def test_default_count_10_all_distinct(self):
        """Verify generating 10 cards produces 10 completely unique questions and answers."""
        # Force fallback / template path
        with patch("app.agents.flashcard_agent.generate_json_any", side_effect=Exception("Offline mode")):
            with patch("app.agents.tools.RAG_Search_Tool", return_value=[]):
                with patch("app.agents.tools.Web_Search_Tool", return_value=[]):
                    result = self.agent.generate(
                        topic="Distributed Consensus",
                        count=10,
                        language="English",
                    ).data

        cards = result.get("cards", [])
        self.assertEqual(len(cards), 10, f"Expected exactly 10 cards, got {len(cards)}")

        fronts = [c["front"] for c in cards]
        backs = [c["back"] for c in cards]

        # Verify no duplicate front questions
        self.assertEqual(len(fronts), len(set(fronts)), "Duplicate question fronts detected in 10-card deck!")
        # Verify no duplicate back answers
        self.assertEqual(len(backs), len(set(backs)), "Duplicate answers detected in 10-card deck!")

        # Crucial check: verify cards 5 through 10 are NOT identical mechanism boilerplate
        for i, card in enumerate(cards[4:], start=5):
            self.assertNotIn("How does mechanism", card["front"], f"Card {i} still has generic 'mechanism' question")
            self.assertNotIn("Mechanism " + str(i) + " enforces strict contract boundaries", card["back"], f"Card {i} still has generic boilerplate answer")

    def test_cards_past_the_4th_are_distinct_and_rich(self):
        """Directly verify cards 5 through 15 are varied and cover different pedagogical domains."""
        cards = _generate_distinct_fallback_cards(
            topic="Operating Systems",
            count=15,
        )
        self.assertEqual(len(cards), 15)

        seen_fronts = set()
        seen_backs = set()
        for idx, card in enumerate(cards, start=1):
            front = card["front"]
            back = card["back"]
            self.assertNotIn(front, seen_fronts, f"Card #{idx} front was repeated: {front}")
            self.assertNotIn(back, seen_backs, f"Card #{idx} back was repeated: {back}")
            seen_fronts.add(front)
            seen_backs.add(back)

    def test_large_count_25_cards(self):
        """Verify generator scales cleanly past 20 items without duplicates."""
        cards = _generate_distinct_fallback_cards(
            topic="Quantum Computing",
            count=25,
        )
        self.assertEqual(len(cards), 25)
        fronts = [c["front"] for c in cards]
        self.assertEqual(len(fronts), len(set(fronts)), "Duplicate question detected when generating 25 cards!")

    def test_rag_chunk_grounding_distinctness(self):
        """Verify when RAG chunks are present, distinct cards are synthesized with proper source citations."""
        sample_chunks = [
            {"source_file": "CS101_Lecture.pdf", "page": "12", "text": "A binary search tree maintains the invariant that left children are strictly less than the root."},
            {"source_file": "CS101_Lecture.pdf", "page": "14", "text": "Red-Black trees ensure O(log n) worst-case time by enforcing color invariants and tree rotations."},
            {"source_file": "Algorithms.pdf", "page": "45", "text": "B-Trees are optimized for block storage systems by minimizing disk seek operations through wide fanout."},
        ]

        with patch("app.agents.flashcard_agent.generate_json_any", side_effect=Exception("Offline mode")):
            with patch("app.agents.tools.RAG_Search_Tool", return_value=sample_chunks):
                result = self.agent.generate(
                    topic="Balanced Trees",
                    count=8,
                    language="English",
                    subject="Computer Science",
                    grade_level="College",
                ).data

        cards = result.get("cards", [])
        self.assertEqual(len(cards), 8)

        # First 3 cards must reflect the 3 RAG chunks
        self.assertIn("CS101_Lecture.pdf p.12", cards[0]["back"])
        self.assertIn("CS101_Lecture.pdf p.14", cards[1]["back"])
        self.assertIn("Algorithms.pdf p.45", cards[2]["back"])

        # Remaining cards must be distinct pedagogical dimensions
        fronts = [c["front"] for c in cards]
        self.assertEqual(len(fronts), len(set(fronts)), "Duplicate cards found in RAG-grounded deck")

    def test_llm_partial_and_duplicate_cards_are_deduplicated_and_backfilled(self):
        """When LLM returns only 3 cards or returns duplicate cards, agent deduplicates and backfills to count."""
        llm_response = {
            "title": "Machine Learning Deck",
            "cards": [
                {"front": "What is overfitting?", "back": "When a model memorizes training noise rather than true signal."},
                {"front": "What is overfitting?", "back": "Duplicate front question!"},  # Duplicate
                {"front": "What is gradient descent?", "back": "An optimization algorithm to minimize loss along gradient vectors."},
            ]
        }

        with patch("app.agents.flashcard_agent.generate_json_any", return_value=llm_response):
            with patch("app.agents.tools.RAG_Search_Tool", return_value=[]):
                with patch("app.agents.tools.Web_Search_Tool", return_value=[]):
                    result = self.agent.generate(
                        topic="Machine Learning",
                        count=6,
                        language="English",
                    ).data

        cards = result.get("cards", [])
        self.assertEqual(len(cards), 6, f"Expected 6 backfilled cards, got {len(cards)}")

        fronts = [c["front"] for c in cards]
        self.assertEqual(len(fronts), len(set(fronts)), "Duplicates remained after backfilling")
        self.assertIn("What is overfitting?", fronts)
        self.assertIn("What is gradient descent?", fronts)


if __name__ == "__main__":
    unittest.main()
