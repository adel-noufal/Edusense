"""Session emotion analytics.

Face detection and expression recognition run in the student's browser
(@vladmandic/face-api, MIT). The browser sends only the resulting label,
confidence and timestamp, which this agent stores and aggregates.

The old server-side TensorFlow/DeepFace/EfficientNet path is gone: it took up to
80 s per frame on CPU, blocked the request, and was the reason the emotion
feature "did not work" during a live session. No image is uploaded any more.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.models import EmotionLog
from app.services.timefmt import iso_z

SUPPORTED_EMOTIONS = ("angry", "disgust", "fear", "happy", "neutral", "sad", "surprise")
UNCERTAIN = "uncertain"


@dataclass
class AgentResult:
    agent_name: str
    data: dict


class EmotionAnalysisAgent:
    """Stores browser-computed emotion events and reports distributions."""

    name = "Emotion Analytics Agent"

    def warm_up(self) -> None:
        """Nothing to load: recognition is in the browser."""
        return None

    def record(
        self,
        db: Session,
        session_id: int,
        student_id: int,
        emotion: str,
        confidence: float,
        timestamp: datetime | None = None,
    ) -> AgentResult:
        """Persist one browser-computed event and update attendance.

        Only a real classification is stored; "uncertain" and "no face" frames
        never reach this method, so distributions are not polluted.
        """
        log = EmotionLog(
            session_id=session_id,
            student_id=student_id,
            emotion=emotion,
            confidence=float(confidence or 0.0),
        )
        if timestamp is not None:
            log.timestamp = timestamp
        db.add(log)

        try:
            from app.models.models import SessionRegistration

            reg = (
                db.query(SessionRegistration)
                .filter_by(session_id=session_id, student_id=student_id)
                .first()
            )
            if reg:
                now_ts = datetime.now(timezone.utc)
                if not getattr(reg, "joined_at", None):
                    reg.joined_at = now_ts
                reg.left_at = now_ts
                reg.attended = True
        except Exception:
            pass

        db.commit()
        db.refresh(log)
        return AgentResult(
            self.name,
            {
                "id": log.id,
                "session_id": session_id,
                "emotion": log.emotion,
                "confidence": log.confidence,
                "timestamp": iso_z(log.timestamp),
            },
        )

    def distributions(self, db: Session, session_id: int) -> AgentResult:
        logs = db.query(EmotionLog).filter(EmotionLog.session_id == session_id).all()
        total = max(len(logs), 1)
        counts = Counter(log.emotion for log in logs)
        data = {
            emotion: round(counts.get(emotion, 0) * 100 / total, 2)
            for emotion in SUPPORTED_EMOTIONS
        }
        return AgentResult(
            self.name,
            {
                "session_id": session_id,
                "distribution": data,
                "samples": len(logs),
                "generated_at": iso_z(datetime.now(timezone.utc)),
            },
        )
