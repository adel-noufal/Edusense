"""Shared failure types for user-facing content generation.

Addendum #13 / demo day F1: when every model provider is unavailable the
agents must stop and say so. Previously each agent swallowed the exception
and wrote a generic "expert" template, which reached the user as fabricated
content (lessons about "architectural principles" for a Photosynthesis
topic, quiz questions about "system throughput", flashcards built from web
titles). This exception is the single honest exit: the API turns it into a
503 with a retry hint and nothing is stored.
"""

from __future__ import annotations

_FEATURE_LABEL = {
    "lesson": "lesson",
    "quiz": "quiz",
    "flashcards": "flashcard deck",
    "video": "video script",
    "answer": "answer",
    "report": "report",
}


class ContentGenerationUnavailable(RuntimeError):
    """No provider could produce real content; nothing was generated."""

    code = "providers_unavailable"

    def __init__(self, feature: str = "content", detail: object = "") -> None:
        self.feature = feature
        self.detail = " ".join(str(detail).split())[:300]
        label = _FEATURE_LABEL.get(feature, feature)
        super().__init__(
            f"No AI provider could generate this {label} right now, so nothing "
            f"was created (no placeholder content). Press Retry in a moment."
        )

    def payload(self) -> dict:
        return {
            "detail": str(self),
            "code": self.code,
            "feature": self.feature,
            "retry": True,
            "provider_error": self.detail,
        }
