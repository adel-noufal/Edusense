from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import threading
import time
from app.api.deps import get_current_user
from app.core.audit import log_auth_event
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.models import Profile, User
from app.schemas.schemas import ForgotPasswordRequest, LoginRequest, ResetPasswordRequest, TokenOut, UserCreate, UserOut
from app.services.email import send_reset_password_email

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Rate limiter for auth endpoints: 100 requests per minute per IP (allows test suites + retries)
# In-memory only — correct for single-process deployment.
# For multi-worker deployments, replace with a shared store (e.g., Redis).
class _AuthRateLimiter:
    def __init__(self, rate: int = 100, per: int = 60):
        self.rate = rate
        self.per = per
        self._buckets: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            bucket = self._buckets.get(key, [])
            # Remove expired tokens
            bucket = [t for t in bucket if now - t < self.per]
            if len(bucket) >= self.rate:
                return False
            bucket.append(now)
            self._buckets[key] = bucket
            return True


_auth_rate_limiter = _AuthRateLimiter(rate=100, per=60)


def _check_auth_rate_limit(request: Request) -> None:
    """Check rate limit based on client IP."""
    # Get client IP (handle proxies)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"

    if not _auth_rate_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded: max 100 requests per minute")


@router.post("/register", response_model=TokenOut)
def register(payload: UserCreate, request: Request, db: Session = Depends(get_db)):
    _check_auth_rate_limit(request)
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(409, "Email already registered")
    user = User(name=payload.name, email=payload.email, role=payload.role, password_hash=hash_password(payload.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(500, "Database error — please try again")
    db.refresh(user)
    db.add(Profile(user_id=user.id))
    db.commit()
    token = create_access_token(user.email, user.role)

    # Audit: user registration
    log_auth_event(db, action="register", user=user, request=request)

    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    _check_auth_rate_limit(request)
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        # Audit: failed login attempt
        log_auth_event(db, action="login_failed", request=request, details={"email": payload.email})
        raise HTTPException(401, "Invalid email or password")

    # Audit: successful login
    log_auth_event(db, action="login_success", user=user, request=request)

    return TokenOut(access_token=create_access_token(user.email, user.role), user=UserOut.model_validate(user))


@router.post("/logout")
def logout(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Audit: user logout
    log_auth_event(db, action="logout", user=user, request=request)
    return {"message": "Client token removed"}


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    _check_auth_rate_limit(request)
    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        # We still return 200 so attackers can't enumerate emails
        # Audit: password reset requested for non-existent email (but don't reveal)
        log_auth_event(db, action="password_reset_requested", request=request, details={"email": payload.email, "user_found": False})
        return {"message": "If that email is registered, a reset link has been sent."}
    
    # Create a token specifically for resetting, expires in 15 mins
    reset_token = create_access_token(user.email, role="reset")
    reset_link = f"http://localhost:5173/reset-password?token={reset_token}"
    
    await send_reset_password_email(user.email, reset_link)

    # Audit: password reset requested
    log_auth_event(db, action="password_reset_requested", user=user, request=request, details={"email": payload.email, "user_found": True})

    return {"message": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    _check_auth_rate_limit(request)
    try:
        decoded = decode_access_token(payload.token)
        email = decoded.get("sub")
        role = decoded.get("role")
        if not email or role != "reset":
            raise HTTPException(400, "Invalid reset token")
    except ValueError:
        # Audit: invalid/expired reset token
        log_auth_event(db, action="password_reset_failed", request=request, details={"reason": "invalid_token"})
        raise HTTPException(400, "Invalid or expired reset token")
        
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # Audit: reset token for non-existent user
        log_auth_event(db, action="password_reset_failed", request=request, details={"reason": "user_not_found", "email": email})
        raise HTTPException(404, "User not found")
        
    user.password_hash = hash_password(payload.new_password)
    db.commit()

    # Audit: password successfully reset
    log_auth_event(db, action="password_reset_success", user=user, request=request)

    return {"message": "Password successfully reset"}
