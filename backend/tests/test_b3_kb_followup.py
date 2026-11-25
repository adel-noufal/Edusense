"""
B3 tests — KB follow-up rewrite + overview strategy + legacy source shapes:
- follow-up questions trigger a standalone-query rewrite via the LLM router
- retrieval uses the rewritten query, not the raw pronoun-laden question
- empty retrieval retries scoped to previously-used source files
- overview questions pull representative chunks from the dominant source
- "nothing found" only when both rewritten retrieval and scoped retry fail
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(__file__)), 'edusense.db')}")
os.environ.setdefault("EDUSENSE_DATABASE_URL", os.environ["DATABASE_URL"])

from app.services import rag_qa

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))
    print(("PASS" if cond else "FAIL"), name, detail if not cond else "")


def _chunk(text="chunk", source="book.pdf", page=1):
    return {"text": text, "source_file": source, "page": page,
            "subject": "", "grade_level": "", "topic": "", "score": 0.9}


def main():
    history = [
        {"role": "user", "content": "Summarize biology_book.pdf"},
        {"role": "assistant", "content": "The book covers cells...",
         "sources": ["biology_book.pdf"]},
    ]

    # 1. rewrite detection
    check("short follow-up needs rewrite",
          rag_qa._needs_rewrite("what else does it cover?", history) is True)
    check("long standalone question does not need rewrite",
          rag_qa._needs_rewrite(
              "Explain the process of photosynthesis in green plants in detail please",
              history) is False)
    check("no history -> no rewrite",
          rag_qa._needs_rewrite("what is mitosis?", None) is False)

    # 2. rewrite uses LLM and returns standalone query
    with patch("app.services.llm.chat", return_value="What topics does biology_book.pdf cover?") as m:
        q = rag_qa._rewrite_followup_query("what else are the covered topics?", history)
    check("rewrite returns standalone query", "biology_book" in q, q)
    check("rewrite called llm.chat once", m.call_count == 1)

    # 3. LLM failure -> original question (graceful)
    with patch("app.services.llm.chat", side_effect=RuntimeError("down")):
        q = rag_qa._rewrite_followup_query("what else does it cover?", history)
    check("rewrite failure falls back to raw question",
          q == "what else does it cover?", q)

    # 4. overview regex catches new phrasings
    for phrase in ["what topics does the book cover",
                   "what are the covered topics",
                   "table of contents",
                   "summarize this document",
                   "list the main chapters"]:
        check(f"overview regex: {phrase!r}",
              rag_qa._is_document_overview_question(phrase) is True)
    check("non-overview not flagged",
          rag_qa._is_document_overview_question("what is osmosis?") is False)

    # 5. end-to-end: empty global retrieval -> scoped retry on prev sources
    calls = {"scoped": []}

    def fake_rag_tool(**kw):
        return []  # global similarity finds nothing

    def fake_query(query_text, top_k, metadata_filter=None):
        if metadata_filter:
            calls["scoped"].append(metadata_filter)
            return [{"text": "cells", "metadata": {"source_file": "biology_book.pdf", "page": 3}}]
        return []

    captured = {}

    def fake_llm(prompt, **kw):
        captured["prompt"] = prompt
        return ("The book covers cells, genetics and ecology.", "gemini", False)

    with patch.object(rag_qa, "RAG_Search_Tool", side_effect=fake_rag_tool), \
         patch.object(rag_qa.vector_store, "query", side_effect=fake_query), \
         patch.object(rag_qa.vector_store, "get_by_source", return_value=[]), \
         patch.object(rag_qa, "_call_llm", side_effect=fake_llm), \
         patch.object(rag_qa, "_rewrite_followup_query", return_value="topics covered in biology_book.pdf"):
        res = rag_qa.answer_question(
            "what else are the covered topics?",
            history=history, top_k=3)

    check("scoped retry hit previous source file",
          {"source_file": "biology_book.pdf"} in calls["scoped"], str(calls["scoped"]))
    check("answer produced from scoped chunks", res["chunks_used"] >= 1, str(res["chunks_used"]))
    check("sources returned", len(res["sources"]) >= 1)

    # 6. nothing anywhere -> honest 'couldn't find' only after both fail
    with patch.object(rag_qa, "RAG_Search_Tool", side_effect=fake_rag_tool), \
         patch.object(rag_qa.vector_store, "query", return_value=[]), \
         patch.object(rag_qa.vector_store, "get_by_source", return_value=[]), \
         patch.object(rag_qa, "_rewrite_followup_query", return_value="obscure query"):
        res2 = rag_qa.answer_question("tell me about unobtainium", history=None, top_k=3)
    check("empty retrieval -> couldn't-find answer", res2["chunks_used"] == 0
          and "couldn't find" in res2["answer"].lower(), res2["answer"][:80])

    failed = [c for c in CHECKS if not c[1]]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
