from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.models import User, ConsentRecord

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        payload = decode_access_token(token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_role(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles and user.role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user
    return checker


def _check_consent(db: Session, user_id: int, consent_type: str) -> ConsentRecord:
    """Shared consent check — returns consent record or raises 403."""
    consent = db.query(ConsentRecord).filter_by(
        user_id=user_id,
        consent_type=consent_type,
        given=True
    ).first()
    if not consent or consent.withdrawn_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Consent required for {consent_type}. Please grant consent in settings."
        )
    return consent


def require_consent(consent_type: str):
    """
    Dependency that checks if the current user has given consent for a specific type.
    Raises 403 if consent not given or withdrawn.
    """
    def checker(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        _check_consent(db, user.id, consent_type)
        return user
    return checker
