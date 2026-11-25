from collections import defaultdict
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents.emotion_agent import SUPPORTED_EMOTIONS, EmotionAnalysisAgent
from app.api.deps import get_current_user, require_consent, _check_consent
from app.db.session import get_db
from app.models.models import EmotionLog, User, ConsentRecord, utcnow
from app.schemas.schemas import EmotionLogIn, ConsentRecordOut, ConsentGiveRequest, ConsentCheckResponse
from app.core.audit import log_audit_event

router = APIRouter(prefix="/emotions", tags=["emotions"])
_agent = EmotionAnalysisAgent()

# --- Simple in-memory rate limiter (per user, max ~1 event per 0.9 s) ---
_last_call: dict[int, float] = defaultdict(float)
_RATE_LIMIT_SECONDS = 0.9


class EmotionEventIn(BaseModel):
    """One label produced by the browser face model. No image, ever."""

    session_id: int
    emotion: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    timestamp: datetime | None = None
    face_detected: bool = True
    quiz_monitoring: bool = False
    attempt_id: int | None = None


def _check_rate_limit(user_id: int):
    import time

    now = time.monotonic()
    if now - _last_call[user_id] < _RATE_LIMIT_SECONDS:
        raise HTTPException(
            status_code=429,
            detail=f"Emotion event rate limited — wait {_RATE_LIMIT_SECONDS}s between events.",
        )
    _last_call[user_id] = now


def _validate_emotion(emotion: str | None, face_detected: bool) -> str:
    if not face_detected:
        return ""
    label = (emotion or "").strip().lower()
    if label not in SUPPORTED_EMOTIONS:
        raise HTTPException(
            422,
            detail=(
                "emotion must be one of " + ", ".join(SUPPORTED_EMOTIONS)
                + " (or face_detected=false when no face was found)"
            ),
        )
    return label


@router.post("/event")
def emotion_event(
    payload: EmotionEventIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Receive a browser-computed emotion label for session analytics.

    Consent required: ``quiz_anti_cheat`` for proctored-quiz monitoring,
    ``emotion_detection`` for classroom emotion analytics.
    """
    consent_type = "quiz_anti_cheat" if payload.quiz_monitoring else "emotion_detection"
    _check_consent(db, user.id, consent_type)
    _check_rate_limit(user.id)

    emotion = _validate_emotion(payload.emotion, payload.face_detected)

    if payload.quiz_monitoring:
        log_audit_event(
            db,
            action="quiz_camera_frame",
            user=user,
            resource_type="quiz_attempt",
            resource_id=str(payload.attempt_id or ""),
            request=request,
            details={
                "session_id": payload.session_id,
                "face_detected": payload.face_detected,
                "emotion": emotion or None,
                "confidence": payload.confidence,
            },
        )

    if not emotion:
        return {"stored": False, "face_detected": False}

    result = _agent.record(
        db,
        payload.session_id,
        user.id,
        emotion,
        payload.confidence,
        payload.timestamp,
    )
    return {"stored": True, "face_detected": True, **result.data}


@router.post("")
def log_emotion(payload: EmotionLogIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    student_id = payload.student_id or user.id
    log = EmotionLog(session_id=payload.session_id, student_id=student_id, emotion=payload.emotion.lower(), confidence=payload.confidence)
    db.add(log)
    db.commit()
    return {"message": "Emotion logged", "id": log.id}


@router.get("/session/{session_id}")
def session_emotions(session_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [dict(id=log.id, student_id=log.student_id, emotion=log.emotion, confidence=log.confidence, timestamp=log.timestamp) for log in db.query(EmotionLog).filter_by(session_id=session_id).all()]


@router.get("/session/{session_id}/distribution")
def distribution(session_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _agent.distributions(db, session_id).data


# ─── Consent Endpoints ────────────────────────────────────────────────────────

@router.post("/consent/give", response_model=ConsentRecordOut)
def give_consent(
    payload: ConsentGiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Grant consent for a specific data processing purpose.
    consent_type: "emotion_detection" or "quiz_anti_cheat"
    """
    valid_types = ["emotion_detection", "quiz_anti_cheat"]
    if payload.consent_type not in valid_types:
        raise HTTPException(400, f"Invalid consent_type. Must be one of: {valid_types}")

    # Upsert consent record
    consent = db.query(ConsentRecord).filter_by(
        user_id=user.id,
        consent_type=payload.consent_type
    ).first()

    if consent:
        consent.given = True
        consent.version = payload.version
        consent.timestamp = utcnow()
        consent.withdrawn_at = None
    else:
        consent = ConsentRecord(
            user_id=user.id,
            consent_type=payload.consent_type,
            given=True,
            version=payload.version,
        )
        db.add(consent)

    db.commit()
    db.refresh(consent)

    # Audit
    log_audit_event(db, action="consent_given", user=user, resource_type="consent", resource_id=str(consent.id), request=request, details={
        "consent_type": payload.consent_type,
        "version": payload.version,
    })

    return ConsentRecordOut.model_validate(consent)


@router.get("/consent/check/{consent_type}", response_model=ConsentCheckResponse)
def check_consent(
    consent_type: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Check if user has given consent for a specific type.
    Returns consent status, version, and timestamp.
    """
    valid_types = ["emotion_detection", "quiz_anti_cheat"]
    if consent_type not in valid_types:
        raise HTTPException(400, f"Invalid consent_type. Must be one of: {valid_types}")

    consent = db.query(ConsentRecord).filter_by(
        user_id=user.id,
        consent_type=consent_type,
        given=True
    ).first()

    has_consent = consent is not None and consent.withdrawn_at is None
    return ConsentCheckResponse(
        has_consent=has_consent,
        consent_type=consent_type,
        version=consent.version if has_consent else None,
        timestamp=consent.timestamp if has_consent else None,
    )


@router.get("/consent/list", response_model=list[ConsentRecordOut])
def list_consents(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """List all consent records for the current user."""
    consents = db.query(ConsentRecord).filter_by(user_id=user.id).all()
    return [ConsentRecordOut.model_validate(c) for c in consents]


@router.post("/consent/withdraw/{consent_type}")
def withdraw_consent(
    consent_type: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Withdraw consent for a specific type.
    This will prevent future camera access for that purpose.
    """
    valid_types = ["emotion_detection", "quiz_anti_cheat"]
    if consent_type not in valid_types:
        raise HTTPException(400, f"Invalid consent_type. Must be one of: {valid_types}")

    consent = db.query(ConsentRecord).filter_by(
        user_id=user.id,
        consent_type=consent_type
    ).first()

    if not consent:
        raise HTTPException(404, "Consent record not found")

    consent.given = False
    consent.withdrawn_at = utcnow()
    db.commit()

    # Audit
    log_audit_event(db, action="consent_withdrawn", user=user, resource_type="consent", resource_id=str(consent.id), request=request, details={
        "consent_type": consent_type,
    })

    return {"message": f"Consent for {consent_type} withdrawn"}
