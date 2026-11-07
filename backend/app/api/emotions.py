from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.agents.emotion_agent import EmotionAnalysisAgent
from app.api.deps import get_current_user, require_consent, _check_consent
from app.db.session import get_db
from app.models.models import EmotionLog, User, ConsentRecord, utcnow
from app.schemas.schemas import EmotionFrameIn, EmotionLogIn, ConsentRecordOut, ConsentGiveRequest, ConsentCheckResponse
from app.core.audit import log_audit_event
import time

router = APIRouter(prefix="/emotions", tags=["emotions"])
agent = EmotionAnalysisAgent()

# --- Simple in-memory rate limiter (per user, max 1 frame per 1.5 seconds) ---
_last_call: dict[int, float] = defaultdict(float)
_RATE_LIMIT_SECONDS = 1.5


def _check_rate_limit(user_id: int):
    now = time.monotonic()
    if now - _last_call[user_id] < _RATE_LIMIT_SECONDS:
        raise HTTPException(
            status_code=429,
            detail=f"Emotion frame rate limited — wait {_RATE_LIMIT_SECONDS}s between frames."
        )
    _last_call[user_id] = now


@router.post("/analyze")
def analyze_frame(
    payload: EmotionFrameIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_consent("emotion_detection"))
):
    _check_rate_limit(user.id)
    return agent.analyze_frame(db, payload.session_id, user.id, payload.image).data


@router.post("/frame")
def receive_frame(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Receive a camera frame for quiz monitoring (second device detection).
    Reuses the emotion analysis pipeline.
    Consent is checked based on quiz_monitoring flag:
    - quiz_monitoring=true: requires quiz_anti_cheat consent
    - quiz_monitoring=false: requires emotion_detection consent
    """
    session_id = payload.get('session_id')
    image = payload.get('image')
    quiz_monitoring = payload.get('quiz_monitoring', False)
    attempt_id = payload.get('attempt_id')

    if not session_id or not image:
        raise HTTPException(400, "session_id and image are required")

    # Check appropriate consent using shared function
    consent_type = "quiz_anti_cheat" if quiz_monitoring else "emotion_detection"
    _check_consent(db, user.id, consent_type)

    # For quiz monitoring, we analyze but don't rate limit as strictly
    if quiz_monitoring:
        try:
            result = agent.analyze_frame(db, session_id, user.id, image).data
            # Log audit for quiz monitoring
            log_audit_event(db, action="quiz_camera_frame", user=user, resource_type="quiz_attempt", resource_id=str(attempt_id), request=request, details={
                "session_id": session_id,
                "attempt_id": attempt_id,
                "emotion": result.get("emotion"),
                "confidence": result.get("confidence"),
            })
            return result
        except Exception as exc:
            return {"emotion": "unknown", "confidence": 0.0, "error": str(exc)}

    # Standard rate-limited analysis
    _check_rate_limit(user.id)
    return agent.analyze_frame(db, session_id, user.id, image).data


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
    return agent.distributions(db, session_id).data


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
