"""
Agent Orchestrator - Routes queries through online/offline paths with failover.

Online Path: RAG + Web Search + LLM (Gemini/Ollama)
Offline Path: RAG + Template Fallback

4 Failover States:
1. Online RAG+Web+LLM Success
2. Online RAG Only (Web fails)
3. Offline RAG+Template
4. Offline Template Only (RAG fails)

Tool Timeouts:
- RAG Search: 2 seconds (near-instant local vector search)
- Web Search: 5 seconds (external API call)
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, AsyncGenerator, Callable
import asyncio
import json
import concurrent.futures
from functools import partial
from concurrent.futures import ThreadPoolExecutor

from app.agents.base import LocalLLM, AgentResult
from app.agents.logging_utils import LLMAuditContext
from app.agents.prompts.scope_guardrail import build_guardrail_prompt
from app.agents.tools import RAG_Search_Tool, Web_Search_Tool
from app.core.config import get_settings


async def _run_with_timeout(func: Callable, timeout: float, *args, **kwargs):
    """Run a synchronous function with a timeout using ThreadPoolExecutor."""
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = loop.run_in_executor(executor, partial(func, *args, **kwargs))
        return await asyncio.wait_for(future, timeout=timeout)


@dataclass
class OrchestratorResult:
    """Result from orchestrator with full provenance."""
    answer: str
    sources: List[str]  # RAG source labels
    web_sources: List[Dict[str, Any]]  # Web search results
    mode: str  # "online_rag_web_llm", "online_rag_only", "offline_rag_template", "offline_template_only"
    rag_chunks_used: int
    web_results_used: int
    fallback_reason: Optional[str] = None
    unverified: bool = False  # True when no RAG sources grounded the answer


class AgentOrchestrator:
    """
    Orchestrates multi-source educational Q&A with graceful degradation.

    Flow:
    1. Try RAG search (always attempted)
    2. If online: try Web Search
    3. Try LLM (Gemini -> Ollama -> Template)
    4. Return result with mode indicating which path succeeded
    """

    def __init__(self):
        self.llm = LocalLLM()
        self.settings = get_settings()

    def _is_online(self) -> bool:
        """Check if we should attempt online providers."""
        return (
            self.settings.ai_provider in ("auto", "gemini")
            and self.settings.gemini_api_key
        )

    async def _build_rag_context(
        self,
        query: str,
        subject: Optional[str],
        grade_level: Optional[str],
        top_k: int = 5
    ) -> tuple[str, List[str], int]:
        """
        Returns (context_block, source_labels, chunk_count).
        Times out after 2 seconds (near-instant local vector search).
        """
        try:
            chunks = await _run_with_timeout(
                RAG_Search_Tool, 2.0,
                query=query,
                subject=subject,
                grade_level=grade_level,
                top_k=top_k,
            )
        except asyncio.TimeoutError:
            print(f"[Orchestrator] RAG lookup timed out after 2s")
            return "", [], 0
        except Exception as exc:
            print(f"[Orchestrator] RAG lookup failed: {exc}")
            return "", [], 0

        if not chunks:
            return "", [], 0

        lines = []
        sources: List[str] = []
        for chunk in chunks:
            src = chunk.get("source_file", "")
            page = chunk.get("page", "")
            label = f"{src} p.{page}" if src and page else (src or "unknown")
            if label not in sources:
                sources.append(label)
            lines.append(f"[Source: {label}]\n{chunk['text']}")

        context_block = "\n\n".join(lines)
        return context_block, sources, len(chunks)

    async def _build_web_context(self, query: str, max_results: int = 3) -> tuple[str, List[Dict[str, Any]], int]:
        """
        Returns (context_block, web_results, result_count).
        Times out after 5 seconds (external API call).
        """
        try:
            results = await _run_with_timeout(
                Web_Search_Tool, 5.0,
                query=query,
                max_results=max_results,
            )
        except asyncio.TimeoutError:
            print(f"[Orchestrator] Web search timed out after 5s")
            return "", [], 0
        except Exception as exc:
            print(f"[Orchestrator] Web search failed: {exc}")
            return "", [], 0

        if not results:
            return "", [], 0

        lines = []
        for i, result in enumerate(results):
            title = result.get("title", "")
            url = result.get("url", "")
            content = result.get("content", "")
            lines.append(f"[Web {i+1}: {title}]({url})\n{content}")

        context_block = "\n\n".join(lines)
        return context_block, results, len(results)

    def _build_prompt(
        self,
        query: str,
        rag_context: str,
        web_context: str,
        subject: Optional[str] = None,
        grade_level: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Build the full prompt for the LLM with scope guardrail."""
        history_block = ""
        if conversation_history:
            history_lines = []
            for msg in conversation_history[-6:]:  # Last 6 messages
                role = msg.get("role", "user")
                content = msg.get("content", "")
                history_lines.append(f"{role.capitalize()}: {content}")
            history_block = "\n\nConversation History:\n" + "\n".join(history_lines) + "\n"

        context_parts = []
        if rag_context:
            context_parts.append("=== KNOWLEDGE BASE (RAG) ===\n" + rag_context)
        if web_context:
            context_parts.append("=== WEB SEARCH RESULTS ===\n" + web_context)

        context_block = "\n\n".join(context_parts) if context_parts else "No external sources available."

        # Build guardrail prompt with context
        guardrail = build_guardrail_prompt(
            subject=subject,
            grade_level=grade_level,
            agent_name="AgentOrchestrator (Chatbot)",
            has_rag_sources=bool(rag_context),
            has_web_sources=bool(web_context),
        )

        return f"""{guardrail}

You are an expert educational assistant. Answer the user's question accurately and comprehensively.

{context_block}
{history_block}
Current Question: {query}

Instructions:
- If RAG sources are provided, prioritize them as your primary factual basis.
- If web sources are provided, use them for current events or recent information not in the knowledge base.
- Cite sources inline using [Source: label] for RAG and [Web N: title] for web results.
- If no sources are available, clearly state that your answer is based on general knowledge.
- Be educational, clear, and well-structured.
"""

    def run(
        self,
        query: str,
        subject: Optional[str] = None,
        grade_level: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> OrchestratorResult:
        """
        Run the orchestrator synchronously with tool timeouts.

        Returns OrchestratorResult with mode indicating which path was taken.
        """
        return asyncio.run(self._run_async(query, subject, grade_level, conversation_history))

    async def _run_async(
        self,
        query: str,
        subject: Optional[str] = None,
        grade_level: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> OrchestratorResult:
        """
        Run the orchestrator asynchronously with tool timeouts.

        Returns OrchestratorResult with mode indicating which path was taken.
        """
        # Step 1: RAG Search (always attempted, 2s timeout)
        rag_context, rag_sources, rag_count = await self._build_rag_context(
            query, subject, grade_level
        )

        # Step 2: Web Search (if online, 5s timeout)
        web_context = ""
        web_results = []
        web_count = 0
        web_failed = False

        if self._is_online():
            web_context, web_results, web_count = await self._build_web_context(query)
            if web_count == 0:
                web_failed = True

        # Step 3: LLM Generation with fallback chain
        prompt = self._build_prompt(query, rag_context, web_context, subject, grade_level, conversation_history)

        # Try online LLM first
        answer = ""
        mode = ""
        fallback_reason = None
        model_used = "unknown"
        fallback_used = False

        if self._is_online():
            # Try with both RAG and Web
            if rag_count > 0 and web_count > 0:
                try:
                    with LLMAuditContext(
                        agent_name="AgentOrchestrator",
                        method_name="run",
                        subject=subject,
                        grade_level=grade_level,
                        topic=query,
                        has_rag_sources=rag_count > 0,
                        rag_source_count=rag_count,
                        has_web_sources=web_count > 0,
                        web_source_count=web_count,
                    ) as audit_ctx:
                        audit_ctx.set_prompt(prompt)
                        answer = self.llm.generate(prompt)
                        audit_ctx.set_response(answer, model_used="gemini", fallback_used=False)
                    mode = "online_rag_web_llm"
                    model_used = "gemini"
                except Exception as exc:
                    fallback_reason = f"LLM generation failed: {exc}"
                    # Fall through to RAG only
            elif rag_count > 0:
                try:
                    with LLMAuditContext(
                        agent_name="AgentOrchestrator",
                        method_name="run",
                        subject=subject,
                        grade_level=grade_level,
                        topic=query,
                        has_rag_sources=True,
                        rag_source_count=rag_count,
                        has_web_sources=False,
                        web_source_count=0,
                    ) as audit_ctx:
                        audit_ctx.set_prompt(prompt)
                        answer = self.llm.generate(prompt)
                        audit_ctx.set_response(answer, model_used="gemini", fallback_used=False)
                    mode = "online_rag_only"
                    model_used = "gemini"
                except Exception as exc:
                    fallback_reason = f"LLM generation failed: {exc}"
                    # Fall through to offline
            elif web_count > 0:
                try:
                    with LLMAuditContext(
                        agent_name="AgentOrchestrator",
                        method_name="run",
                        subject=subject,
                        grade_level=grade_level,
                        topic=query,
                        has_rag_sources=False,
                        rag_source_count=0,
                        has_web_sources=True,
                        web_source_count=web_count,
                    ) as audit_ctx:
                        audit_ctx.set_prompt(prompt)
                        answer = self.llm.generate(prompt)
                        audit_ctx.set_response(answer, model_used="gemini", fallback_used=False)
                    mode = "online_web_only"
                    model_used = "gemini"
                except Exception as exc:
                    fallback_reason = f"LLM generation failed: {exc}"
            else:
                try:
                    with LLMAuditContext(
                        agent_name="AgentOrchestrator",
                        method_name="run",
                        subject=subject,
                        grade_level=grade_level,
                        topic=query,
                        has_rag_sources=False,
                        rag_source_count=0,
                        has_web_sources=False,
                        web_source_count=0,
                    ) as audit_ctx:
                        audit_ctx.set_prompt(prompt)
                        answer = self.llm.generate(prompt)
                        audit_ctx.set_response(answer, model_used="gemini", fallback_used=False)
                    mode = "online_general_llm"
                    model_used = "gemini"
                except Exception as exc:
                    fallback_reason = f"LLM generation failed: {exc}"
                    web_failed = True

        # Offline path: RAG + Template
        if not answer and rag_count > 0:
            try:
                # Use template fallback with RAG context
                with LLMAuditContext(
                    agent_name="AgentOrchestrator",
                    method_name="run",
                    subject=subject,
                    grade_level=grade_level,
                    topic=query,
                    has_rag_sources=rag_count > 0,
                    rag_source_count=rag_count,
                    has_web_sources=web_count > 0,
                    web_source_count=web_count,
                ) as audit_ctx:
                    audit_ctx.set_prompt(prompt)
                    answer = self.llm._template(prompt, subject=subject, grade_level=grade_level)
                    audit_ctx.set_response(answer, model_used="template", fallback_used=True)
                mode = "offline_rag_template"
                model_used = "template"
                fallback_used = True
                if fallback_reason:
                    fallback_reason += "; fell back to offline RAG+template"
            except Exception as exc:
                fallback_reason = f"Offline RAG+template failed: {exc}"
                # Fall through to template only

        # Final fallback: Template only
        if not answer:
            with LLMAuditContext(
                agent_name="AgentOrchestrator",
                method_name="run",
                subject=subject,
                grade_level=grade_level,
                topic=query,
                has_rag_sources=False,
                rag_source_count=0,
                has_web_sources=False,
                web_source_count=0,
            ) as audit_ctx:
                audit_ctx.set_prompt(query)  # template uses just the query
                answer = self.llm._template(query, subject=subject, grade_level=grade_level)
                audit_ctx.set_response(answer, model_used="template", fallback_used=True)
            mode = "offline_template_only"
            model_used = "template"
            fallback_used = True
            if fallback_reason:
                fallback_reason += "; fell back to template only"

        return OrchestratorResult(
            answer=answer,
            sources=rag_sources,
            web_sources=web_results,
            mode=mode,
            rag_chunks_used=rag_count,
            web_results_used=web_count,
            fallback_reason=fallback_reason,
            unverified=(rag_count == 0 and web_count == 0),
        )

    async def run_stream(
        self,
        query: str,
        subject: Optional[str] = None,
        grade_level: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Run the orchestrator with streaming response.
        Yields answer chunks as they're generated.
        """
        # Run the async orchestrator
        result = await self._run_async(query, subject, grade_level, conversation_history)

        # Simple chunking by sentences for streaming effect
        sentences = result.answer.split(". ")
        for i, sentence in enumerate(sentences):
            if sentence.strip():
                yield sentence.strip() + (". " if i < len(sentences) - 1 else "")
                await asyncio.sleep(0.01)  # Small delay for streaming effect

        # Yield metadata at the end
        metadata = {
            "sources": result.sources,
            "web_sources": result.web_sources,
            "mode": result.mode,
            "rag_chunks_used": result.rag_chunks_used,
            "web_results_used": result.web_results_used,
        }
        yield f"\n\n__METADATA__{json.dumps(metadata)}"


# Convenience function for simple usage
def answer_question(
    query: str,
    subject: Optional[str] = None,
    grade_level: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> OrchestratorResult:
    """Simple one-off question answering."""
    orchestrator = AgentOrchestrator()
    return orchestrator.run(query, subject, grade_level, conversation_history)