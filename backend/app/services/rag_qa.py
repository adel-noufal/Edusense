"""
rag_qa.py — RAG-grounded Q&A and knowledge-base suggestion service.

Provides two public functions:
  answer_question()  — used by POST /api/rag/ask  (students)
  suggest_chunks()   — used by GET  /api/rag/suggest (instructors)
"""
from __future__ import annotations

import re
from typing import Optional

from app.agents.base import LocalLLM
from app.agents.logging_utils import LLMAuditContext
from app.agents.prompts.scope_guardrail import (
    build_guardrail_prompt,
    ensure_clean_user_answer,
    sanitize_user_facing_answer,
)
from app.agents.tools import RAG_Search_Tool
from app.services import vector_store
from app.services.gemini import generate_content, generate_via_ollama
from app.core.config import get_settings
from app.services.ingestion import get_indexed_sources


def _find_referenced_source(question: str) -> str | None:
    lowered_question = question.casefold()
    matches = []
    for source in get_indexed_sources():
        source_id = str(source.get("source_id") or "")
        source_file = str(source.get("source_file") or "")
        for alias in {source_id, source_file} - {""}:
            if alias.casefold() in lowered_question:
                matches.append((alias, source_id or source_file))
    return max(matches, key=lambda match: len(match[0]))[1] if matches else None


def _chunk_order(chunk: dict) -> tuple[int, int]:
    metadata = chunk.get("metadata") or {}
    try:
        page = int(metadata.get("page") or 0)
    except (TypeError, ValueError):
        page = 0
    try:
        index = int(metadata.get("chunk_index") or 0)
    except (TypeError, ValueError):
        index = 0
    return page, index


def _representative_chunks(chunks: list[dict], count: int) -> list[dict]:
    ordered = sorted(chunks, key=_chunk_order)
    if len(ordered) <= count:
        return ordered
    if count <= 1:
        return ordered[:count]
    indexes = [round(i * (len(ordered) - 1) / (count - 1)) for i in range(count)]
    return [ordered[index] for index in indexes]


def _format_vector_chunks(chunks: list[dict]) -> list[dict]:
    formatted = []
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        distance = chunk.get("distance")
        score = round(max(0.0, min(1.0, 1.0 - float(distance))), 4) if distance is not None else 1.0
        formatted.append({
            "text": chunk.get("text", ""),
            "source_file": str(metadata.get("source_file") or metadata.get("source_id") or ""),
            "page": metadata.get("page", 1),
            "subject": str(metadata.get("subject", "")),
            "grade_level": str(metadata.get("grade_level", "")),
            "topic": str(metadata.get("topic", "")),
            "score": score,
        })
    return formatted


def _is_document_overview_question(question: str) -> bool:
    return bool(re.search(
        r"\b(?:summar(?:y|ize|ise)|overview|main idea|what is it talking about|"
        r"what is this about|what does (?:this|the|that) (?:\w+ )?(?:pdf|document|file|book|"
        r"textbook|chapter|material)s? (?:cover|discuss|contain|include)|"
        r"(?:what|which) topics?|covered topics?|table of contents|"
        r"(?:list|outline) (?:the )?(?:main )?(?:topics|chapters|sections)|"
        r"what(?:'s| is) in (?:this|the|that))\b",
        question,
        re.IGNORECASE,
    ))


_FOLLOWUP_RE = re.compile(
    r"\b(?:it|that|this|they|them|those|these|the book|the document|the file|"
    r"the chapter|the topic|the material|the above|previous|earlier|"
    r"what else|and what|also|too)\b",
    re.IGNORECASE,
)


def _needs_rewrite(question: str, history: list[dict] | None) -> bool:
    """Follow-ups are short or contain anaphora referring to earlier turns."""
    if not history:
        return False
    words = question.split()
    # Very short questions are almost always follow-ups; longer ones only
    # when they contain an explicit anaphora/reference to earlier turns.
    return len(words) <= 6 or (len(words) <= 15 and bool(_FOLLOWUP_RE.search(question)))


def _rewrite_followup_query(question: str, history: list[dict] | None) -> str:
    """
    Rewrite a follow-up into a standalone retrieval query using recent turns.
    Falls back to the raw question when no rewrite is possible — retrieval
    then behaves exactly as before.
    """
    if not _needs_rewrite(question, history):
        return question
    try:
        from app.services import llm
        convo = []
        for turn in (history or [])[-6:]:
            role = "User" if turn.get("role") == "user" else "Assistant"
            convo.append(f"{role}: {str(turn.get('content', ''))[:400]}")
        prompt = (
            "Rewrite the latest user question as a standalone search query that "
            "resolves pronouns and references (\"the book\", \"it\", \"that topic\") "
            "using the conversation. Output ONLY the rewritten query, no explanation.\n\n"
            + "\n".join(convo)
            + f"\n\nLatest question: {question}\n\nStandalone query:"
        )
        rewritten = llm.chat(prompt, task_type="chat", temperature=0.0,
                             max_output_tokens=80, timeout=20.0).strip().strip('"')
        if rewritten and len(rewritten) > 3 and rewritten.casefold() != question.casefold():
            return rewritten
    except Exception:
        pass
    return question


def _history_source_files(history: list[dict] | None) -> list[str]:
    """Source files the assistant grounded recent answers in (newest first)."""
    files: list[str] = []
    for turn in reversed(history or []):
        for src in turn.get("sources") or []:
            if src and src not in files:
                files.append(src)
    return files


# ── helpers ────────────────────────────────────────────────────────────────

def _format_context(chunks: list[dict]) -> tuple[str, list[str]]:
    """
    Turn RAG chunk results into a prompt-ready context block and a
    deduplicated list of source labels ("filename p.N").
    """
    lines: list[str] = []
    sources: list[str] = []
    for chunk in chunks:
        src   = chunk.get("source_file", "")
        page  = chunk.get("page", "")
        label = f"{src} p.{page}" if src and page else (src or "unknown")
        if label not in sources:
            sources.append(label)
        lines.append(f"[Source: {label}]\n{chunk['text']}")
    return "\n\n".join(lines), sources


def _call_llm(prompt: str, subject: Optional[str] = None, grade_level: Optional[str] = None,
              topic: Optional[str] = None, has_rag_sources: bool = False,
              rag_source_count: int = 0, engine: str = "auto",
              cache_key: Optional[str] = None) -> tuple[str, str, bool]:
    """
    Answer through the multi-provider router (addendum #11 §1.7).

    engine:
      auto    -> Groq -> NVIDIA -> OpenRouter -> Ollama -> Gemini (cloud last)
      private -> local Ollama only (recommended for uploaded books)
      cloud   -> cloud providers only, no local Ollama

    Returns (response, model_used, fallback_used).
    """
    from app.services import llm as _llm

    settings = get_settings()
    engine = (engine or getattr(settings, "kb_engine", "auto") or "auto").lower()
    attempts: list[dict] = []
    if engine == "private":
        attempts.append({"only_provider": "ollama", "label": "ollama"})
    elif engine == "cloud":
        attempts.append({"exclude_provider": "ollama", "label": "cloud"})
    else:
        attempts.append({"label": "auto"})

    for attempt in attempts:
        kwargs = {k: v for k, v in attempt.items() if k != "label"}
        try:
            with LLMAuditContext(
                agent_name="RAG_QA_Service",
                method_name="answer_question",
                subject=subject,
                grade_level=grade_level,
                topic=topic,
                has_rag_sources=has_rag_sources,
                rag_source_count=rag_source_count,
            ) as audit_ctx:
                audit_ctx.set_prompt(prompt)
                response = _llm.chat(
                    prompt, task_type="kb_chat", temperature=0.3,
                    max_output_tokens=1200, timeout=90.0,
                    touch_student_data=True,
                    cache_key=cache_key, cache_ttl=3600.0,
                    **kwargs,
                )
                audit_ctx.set_response(
                    response,
                    model_used=attempt["label"],
                    fallback_used=attempt["label"] != "auto",
                )
            return response, attempt["label"], attempt["label"] != "auto"
        except Exception as exc:
            # Never surface provider JSON to the user; log and try the next tier.
            print(f"[RAG-QA] KB engine {attempt['label']} unavailable ({str(exc)[:160]})")

    # Auto/cloud/private exhausted: honest template fallback with scope check.
    # Private mode never silently calls a cloud provider.
    llm = LocalLLM()
    fallback = llm._template(
        prompt, subject=subject, grade_level=grade_level, query=topic or None
    )
    with LLMAuditContext(
        agent_name="RAG_QA_Service",
        method_name="answer_question",
        subject=subject,
        grade_level=grade_level,
        topic=topic,
        has_rag_sources=has_rag_sources,
        rag_source_count=rag_source_count,
    ) as audit_ctx:
        audit_ctx.set_prompt(prompt)
        audit_ctx.set_response(fallback, model_used="template", fallback_used=True)
    return fallback, "template", True


_PAGE_RANGE_RE = re.compile(
    r"(?:^|[^A-Za-z])pages?[ 	]+([0-9]{1,4})(?:[ 	]*(?:-|–|to|until)[ 	]*([0-9]{1,4}))?",
    re.IGNORECASE,
)


def _page_span(question: str) -> Optional[tuple[int, int]]:
    """Extract an explicit page reference ("page 40", "pages 40-45")."""
    match = _PAGE_RANGE_RE.search(question or "")
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2) or start)
    if end < start:
        start, end = end, start
    return start, end


def _chunk_page(chunk: dict) -> int:
    try:
        return int(chunk.get("page") or 0)
    except (TypeError, ValueError):
        return 0


# ── public API ─────────────────────────────────────────────────────────────

def answer_question(
    question: str,
    subject: Optional[str] = None,
    grade_level: Optional[str] = None,
    top_k: int = 5,
    min_score: Optional[float] = None,
    source_file: Optional[str] = None,
    history: Optional[list[dict]] = None,
    source_ids: Optional[list[str]] = None,
    engine: Optional[str] = None,
) -> dict:
    """
    Retrieve relevant chunks from the vector store and use them to answer
    the student's question with an AI response grounded in source material.

    Returns:
        {
          "question": str,
          "answer": str,
          "sources": [{"source_file", "page", "subject", "grade_level", "topic", "score"}],
          "chunks_used": int,
          "subject": str | None,
          "grade_level": str | None,
        }
    """
    settings = get_settings()
    threshold = min_score if min_score is not None else settings.rag_min_score

    # Follow-up questions ("what else does the book cover?") fail similarity
    # search because pronouns don't match document text — rewrite to a
    # standalone query first.
    search_query = _rewrite_followup_query(question, history)

    if source_ids:
        # B10: retrieval restricted to the user-selected documents only.
        ids = [str(s) for s in source_ids]
        scoped = vector_store.query(
            query_text=search_query,
            top_k=top_k * 2,
            metadata_filter={"source_id": {"": ids}},
        )
        if not scoped:
            scoped = vector_store.query(
                query_text=search_query,
                top_k=top_k * 2,
                metadata_filter={"source_file": {"": ids}},
            )
        chunks = _format_vector_chunks(scoped)
    else:
        chunks = RAG_Search_Tool(
            query=search_query,
            subject=subject,
            grade_level=grade_level,
            top_k=top_k,
            min_score=threshold,
        )

    referenced_source = source_file or _find_referenced_source(search_query) or _find_referenced_source(question)
    if referenced_source:
        source_chunks = vector_store.get_by_source(referenced_source)
        if source_chunks:
            scoped_results = vector_store.query(
                query_text=search_query,
                top_k=top_k,
                metadata_filter={"source_file": referenced_source},
            )
            if not scoped_results:
                scoped_results = vector_store.query(
                    query_text=search_query,
                    top_k=top_k,
                    metadata_filter={"source_id": referenced_source},
                )
            if _is_document_overview_question(question):
                selected_chunks = _representative_chunks(source_chunks, top_k)
            else:
                selected_chunks = scoped_results or _representative_chunks(source_chunks, top_k)
            chunks = _format_vector_chunks(selected_chunks)

    # Follow-up fallback: retrieval found nothing, but the previous answer was
    # grounded in specific documents — retry scoped to those sources before
    # declaring "nothing found".
    if not chunks:
        prev_files = _history_source_files(history)
        for prev_file in prev_files[:2]:
            scoped = vector_store.query(
                query_text=search_query,
                top_k=top_k,
                metadata_filter={"source_file": prev_file},
            )
            if not scoped:
                scoped = vector_store.query(
                    query_text=search_query,
                    top_k=top_k,
                    metadata_filter={"source_id": prev_file},
                )
            if scoped:
                chunks = _format_vector_chunks(scoped)
                break

    # Overview questions without an explicit document name: similarity search
    # only surfaces the most similar chunks, which misses the document's
    # structure. Anchor on the dominant source among the hits and pull
    # representative chunks (head/middle/tail) from it instead.
    if chunks and _is_document_overview_question(question) and not referenced_source:
        from collections import Counter
        dominant = Counter(
            c.get("source_file") or c.get("source_id") or ""
            for c in chunks
        ).most_common(1)[0][0]
        if dominant:
            source_chunks = vector_store.get_by_source(dominant)
            if source_chunks:
                chunks = _format_vector_chunks(_representative_chunks(source_chunks, top_k))

    # Page/section awareness: "explain X on page 40" or "pages 40-45" filters
    # to those pages plus one neighbour on each side.
    page_span = _page_span(question)
    if page_span and chunks:
        span_start, span_end = page_span
        in_range = [c for c in chunks if span_start - 1 <= _chunk_page(c) <= span_end + 1]
        if not in_range:
            # Similarity hits landed elsewhere: pull the referenced pages
            # directly from the named/dominant source.
            from collections import Counter
            target = referenced_source or Counter(
                c.get("source_file") or "" for c in chunks if c.get("source_file")
            ).most_common(1)[0][0]
            direct = vector_store.get_by_source(target) if target else []
            direct_chunks = _format_vector_chunks(direct) if direct else []
            in_range = [c for c in direct_chunks
                        if span_start - 1 <= _chunk_page(c) <= span_end + 1]
        if in_range:
            chunks = in_range[:max(top_k, 6)]

    cache_key = None
    if chunks:
        import hashlib
        digest = hashlib.sha256(
            (
                question.strip().lower()
                + "|" + ",".join(sorted(source_ids or []))
                + "|" + ",".join(
                    f"{c.get('source_file')}:{c.get('page')}" for c in chunks
                )
            ).encode("utf-8")
        ).hexdigest()
        cache_key = f"rag:{digest}"

    source_meta = [
        {
            "source_file":  c.get("source_file", ""),
            "page":         c.get("page", ""),
            "subject":      c.get("subject", ""),
            "grade_level":  c.get("grade_level", ""),
            "topic":        c.get("topic", ""),
            "score":        c.get("score", 0.0),
        }
        for c in chunks
    ]

    if not chunks:
        # Knowledge Base is strictly document-grounded: when nothing relevant is
        # indexed, say so plainly instead of answering from general knowledge.
        scope = f" for {subject}" if subject else ""
        scope += f" (grade {grade_level})" if grade_level else ""
        if source_ids:
            answer = (
                "I couldn't find an answer to that in the selected files. "
                "Try a different question, add more files, or ask without a file filter."
            )
        else:
            answer = (
                "I couldn't find anything about that in the uploaded course materials"
                f"{scope}. The Knowledge Base only answers from indexed documents — "
                "please ask your instructor to upload relevant material, or try the AI "
                "Chatbot for general questions."
            )

        return {
            "question":     question,
            "answer":       answer,
            "sources":      [],
            "chunks_used":  0,
            "subject":      subject,
            "grade_level":  grade_level,
            "unverified":   True,
            "scoped_to":    source_ids or None,
        }

    context_block, _ = _format_context(chunks)

    # Build guardrail prompt with context
    guardrail = build_guardrail_prompt(
        subject=subject,
        grade_level=grade_level,
        agent_name="RAG_QA_Service (Chatbot API)",
        has_rag_sources=True,
    )

    # Bounded conversation context (already windowed by the caller)
    history_block = ""
    if history:
        lines = []
        for turn in history[-12:]:
            role = "Student" if turn.get("role") == "user" else "Assistant"
            content = str(turn.get("content", ""))[:600]
            if content.strip():
                lines.append(f"{role}: {content}")
        if lines:
            history_block = (
                "\n\nCONVERSATION SO FAR (for context only — answer the latest question):\n"
                + "\n".join(lines)
                + "\n"
            )

    prompt = f"""{guardrail}

You are a helpful, accurate educational assistant for EduSense.
A student has asked the following question:{history_block}
QUESTION: {question}

Use ONLY the source material below to answer. If the sources do not contain enough
information to answer fully, say so explicitly — do NOT invent facts.
Be concise, clear, and student-friendly. Cite sources where helpful using [Source: label] format.

=== SOURCE MATERIAL ===
{context_block}
=== END SOURCE MATERIAL ===

Answer:"""

    answer, model_used, _ = _call_llm(
        prompt,
        subject=subject,
        grade_level=grade_level,
        topic=question,
        has_rag_sources=True,
        rag_source_count=len(chunks),
        engine=engine or getattr(settings, "kb_engine", "auto"),
        cache_key=cache_key,
    )

    if model_used == "template":
        # Every LLM tier failed — be honest instead of showing a pseudo-answer.
        # The grounded source excerpts are still returned below for the user.
        answer = (
            "The AI writing service is temporarily unavailable, so I can't generate "
            "a written answer right now. The most relevant excerpts from your uploaded "
            "documents are shown below — please try again in a moment."
        )
    answer = ensure_clean_user_answer(answer)

    return {
        "question":     question,
        "answer":       answer,
        "sources":      source_meta,
        "chunks_used":  len(chunks),
        "subject":      subject,
        "grade_level":  grade_level,
        "unverified":   False,
        "scoped_to":    source_ids or None,
    }


def suggest_chunks(
    topic: str,
    subject: Optional[str] = None,
    grade_level: Optional[str] = None,
    top_k: int = 8,
    min_score: Optional[float] = None,
) -> dict:
    """
    Return the top-k RAG chunks matching a topic — used by instructors to
    preview what source material exists before generating a lesson/quiz.

    Returns:
        {
          "topic": str,
          "subject": str | None,
          "grade_level": str | None,
          "total": int,
          "chunks": [{"text", "source_file", "page", "subject", "grade_level", "topic", "score"}]
        }
    """
    settings = get_settings()
    threshold = min_score if min_score is not None else settings.rag_min_score

    chunks = RAG_Search_Tool(
        query=topic,
        subject=subject,
        grade_level=grade_level,
        top_k=top_k,
        min_score=threshold,
    )

    return {
        "topic":        topic,
        "subject":      subject,
        "grade_level":  grade_level,
        "total":        len(chunks),
        "chunks":       chunks,
    }
