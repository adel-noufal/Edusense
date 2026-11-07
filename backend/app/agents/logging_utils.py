"""
Shared Audit Logging Utility for EduSense LLM Calls

Provides prompt+output audit logging for every LLM call across all agents
(Lesson, Quiz, Flashcard, Chatbot). Logs are structured for debugging,
compliance, and quality monitoring.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Configure logger
logger = logging.getLogger("edusense.llm_audit")
logger.setLevel(logging.INFO)

# File handler for persistent audit logs
_log_dir = Path(__file__).parent.parent.parent.parent / "logs" / "llm_audit"
_log_dir.mkdir(parents=True, exist_ok=True)

_file_handler = logging.FileHandler(_log_dir / "llm_audit.log", encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(message)s"))  # Raw JSON lines
logger.addHandler(_file_handler)
logger.propagate = False


@dataclass
class LLMAuditEntry:
    """Structured audit entry for a single LLM call."""
    timestamp: str
    agent_name: str
    method_name: str
    prompt_hash: str
    prompt_length: int
    response_length: int
    duration_ms: float
    model_used: str
    subject: Optional[str] = None
    grade_level: Optional[str] = None
    topic: Optional[str] = None
    has_rag_sources: bool = False
    rag_source_count: int = 0
    has_web_sources: bool = False
    web_source_count: int = 0
    error: Optional[str] = None
    fallback_used: bool = False

    def to_json_line(self) -> str:
        """Convert to JSON line for structured logging."""
        return json.dumps(asdict(self), ensure_ascii=False)


def _hash_prompt(prompt: str) -> str:
    """Generate a short hash of the prompt for identification without logging full content."""
    import hashlib
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


def log_llm_call(
    agent_name: str,
    method_name: str,
    prompt: str,
    response: str,
    duration_ms: float,
    model_used: str,
    subject: Optional[str] = None,
    grade_level: Optional[str] = None,
    topic: Optional[str] = None,
    has_rag_sources: bool = False,
    rag_source_count: int = 0,
    has_web_sources: bool = False,
    web_source_count: int = 0,
    error: Optional[str] = None,
    fallback_used: bool = False,
) -> None:
    """
    Log an LLM call with full audit metadata.

    Args:
        agent_name: Name of the agent (e.g., "LessonGenerationAgent")
        method_name: Method that made the call (e.g., "generate")
        prompt: Full prompt sent to LLM
        response: Full response from LLM
        duration_ms: Call duration in milliseconds
        model_used: Model identifier (e.g., "gemini-2.5-flash", "ollama:mistral", "template")
        subject: Academic subject context
        grade_level: Grade level context
        topic: Topic being processed
        has_rag_sources: Whether RAG sources were provided
        rag_source_count: Number of RAG source chunks
        has_web_sources: Whether web sources were provided
        web_source_count: Number of web search results
        error: Error message if call failed
        fallback_used: Whether a fallback (template/Ollama) was used
    """
    entry = LLMAuditEntry(
        timestamp=datetime.utcnow().isoformat() + "Z",
        agent_name=agent_name,
        method_name=method_name,
        prompt_hash=_hash_prompt(prompt),
        prompt_length=len(prompt),
        response_length=len(response) if response else 0,
        duration_ms=duration_ms,
        model_used=model_used,
        subject=subject,
        grade_level=grade_level,
        topic=topic,
        has_rag_sources=has_rag_sources,
        rag_source_count=rag_source_count,
        has_web_sources=has_web_sources,
        web_source_count=web_source_count,
        error=error,
        fallback_used=fallback_used,
    )
    logger.info(entry.to_json_line())


class LLMAuditContext:
    """
    Context manager for timing and logging an LLM call.

    Usage:
        with LLMAuditContext("LessonGenerationAgent", "generate", subject="Biology", grade_level="10") as ctx:
            response = llm.generate(prompt)
            ctx.set_response(response, model_used="gemini-2.5-flash")
    """

    def __init__(
        self,
        agent_name: str,
        method_name: str,
        subject: Optional[str] = None,
        grade_level: Optional[str] = None,
        topic: Optional[str] = None,
        has_rag_sources: bool = False,
        rag_source_count: int = 0,
        has_web_sources: bool = False,
        web_source_count: int = 0,
    ):
        self.agent_name = agent_name
        self.method_name = method_name
        self.subject = subject
        self.grade_level = grade_level
        self.topic = topic
        self.has_rag_sources = has_rag_sources
        self.rag_source_count = rag_source_count
        self.has_web_sources = has_web_sources
        self.web_source_count = web_source_count
        self.start_time: float = 0
        self.prompt: str = ""
        self.response: str = ""
        self.model_used: str = "unknown"
        self.error: Optional[str] = None
        self.fallback_used: bool = False

    def __enter__(self) -> "LLMAuditContext":
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Ensure logging happens even if set_response wasn't called explicitly."""
        if self.prompt and not self.response:
            # Log with error if response was never set
            self._log()
        return False  # Don't suppress exceptions

    def set_prompt(self, prompt: str) -> None:
        """Set the prompt that will be sent to the LLM."""
        self.prompt = prompt

    def set_response(
        self,
        response: str,
        model_used: str,
        fallback_used: bool = False,
        error: Optional[str] = None,
    ) -> None:
        """Set the response and log the audit entry."""
        self.response = response
        self.model_used = model_used
        self.fallback_used = fallback_used
        self.error = error
        self._log()

    def _log(self) -> None:
        duration_ms = (time.perf_counter() - self.start_time) * 1000
        log_llm_call(
            agent_name=self.agent_name,
            method_name=self.method_name,
            prompt=self.prompt,
            response=self.response,
            duration_ms=duration_ms,
            model_used=self.model_used,
            subject=self.subject,
            grade_level=self.grade_level,
            topic=self.topic,
            has_rag_sources=self.has_rag_sources,
            rag_source_count=self.rag_source_count,
            has_web_sources=self.has_web_sources,
            web_source_count=self.web_source_count,
            error=self.error,
            fallback_used=self.fallback_used,
        )


def get_audit_log_path() -> Path:
    """Get the path to the audit log file."""
    return _log_dir / "llm_audit.log"