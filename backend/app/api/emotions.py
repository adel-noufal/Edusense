from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.agents.emotion_agent import EmotionAnalysisAgent
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.models import EmotionLog, User
from app.schemas.schemas import EmotionFrameIn, EmotionLogIn

router = APIRouter(prefix="/emotions", tags=["Emotion Logs"])
agent = EmotionAnalysisAgent()


@router.post("/analyze")
def analyze_frame(payload: EmotionFrameIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return agent.analyze_frame(db, payload.session_id, user.id, payload.image).data


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
