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
from app.agents.prompts.scope_guardrail import build_guardrail_prompt, sanitize_user_facing_answer
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
        r"what is this about|what does (?:this|the) (?:pdf|document|file) (?:cover|discuss))\b",
        question,
        re.IGNORECASE,
    ))


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
              rag_source_count: int = 0) -> tuple[str, str, bool]:
    """
    Try Gemini first, fall back to Ollama, fall back to a polite refusal.
    Returns (response, model_used, fallback_used).
    """
    settings = get_settings()
    if settings.gemini_api_key and settings.ai_provider in ("auto", "gemini"):
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
                response = generate_content(prompt)
                audit_ctx.set_response(response, model_used="gemini", fallback_used=False)
            return response, "gemini", False
        except Exception as exc:
            print(f"[RAG-QA] Gemini unavailable ({exc}), trying Ollama...")
    if settings.ai_provider in ("auto", "gemini", "ollama"):
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
                response = generate_via_ollama(prompt)
                audit_ctx.set_response(response, model_used="ollama", fallback_used=True)
            return response, "ollama", True
        except Exception as exc:
            print(f"[RAG-QA] Ollama unavailable ({exc}), using fallback answer.")
    # Use template fallback with scope check
    llm = LocalLLM()
    # Extract query from prompt for scope check
    query_for_check = topic or prompt
    fallback = llm._template(prompt, subject=subject, grade_level=grade_level)
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


# ── public API ─────────────────────────────────────────────────────────────

def answer_question(
    question: str,
    subject: Optional[str] = None,
    grade_level: Optional[str] = None,
    top_k: int = 5,
    min_score: Optional[float] = None,
    source_file: Optional[str] = None,
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

    chunks = RAG_Search_Tool(
        query=question,
        subject=subject,
        grade_level=grade_level,
        top_k=top_k,
        min_score=threshold,
    )

    referenced_source = source_file or _find_referenced_source(question)
    if referenced_source:
        source_chunks = vector_store.get_by_source(referenced_source)
        if source_chunks:
            scoped_results = vector_store.query(
                query_text=question,
                top_k=top_k,
                metadata_filter={"source_file": referenced_source},
            )
            if not scoped_results:
                scoped_results = vector_store.query(
                    query_text=question,
                    top_k=top_k,
                    metadata_filter={"source_id": referenced_source},
                )
            if _is_document_overview_question(question):
                selected_chunks = _representative_chunks(source_chunks, top_k)
            else:
                selected_chunks = scoped_results or _representative_chunks(source_chunks, top_k)
            chunks = _format_vector_chunks(selected_chunks)

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
        }

    context_block, _ = _format_context(chunks)

    # Build guardrail prompt with context
    guardrail = build_guardrail_prompt(
        subject=subject,
        grade_level=grade_level,
        agent_name="RAG_QA_Service (Chatbot API)",
        has_rag_sources=True,
    )

    prompt = f"""{guardrail}

You are a helpful, accurate educational assistant for EduSense.
A student has asked the following question:

QUESTION: {question}

Use ONLY the source material below to answer. If the sources do not contain enough
information to answer fully, say so explicitly — do NOT invent facts.
Be concise, clear, and student-friendly. Cite sources where helpful using [Source: label] format.

=== SOURCE MATERIAL ===
{context_block}
=== END SOURCE MATERIAL ===

Answer:"""

    answer, _, _ = _call_llm(
        prompt,
        subject=subject,
        grade_level=grade_level,
        topic=question,
        has_rag_sources=True,
        rag_source_count=len(chunks),
    )
    answer = sanitize_user_facing_answer(answer).strip()

    return {
        "question":     question,
        "answer":       answer,
        "sources":      source_meta,
        "chunks_used":  len(chunks),
        "subject":      subject,
        "grade_level":  grade_level,
        "unverified":   False,
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
