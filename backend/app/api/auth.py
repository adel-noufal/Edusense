from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.models import Profile, User
from app.schemas.schemas import ForgotPasswordRequest, LoginRequest, ResetPasswordRequest, TokenOut, UserCreate, UserOut
from app.services.email import send_reset_password_email

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenOut)
def register(payload: UserCreate, db: Session = Depends(get_db)):
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
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    return TokenOut(access_token=create_access_token(user.email, user.role), user=UserOut.model_validate(user))


@router.post("/logout")
def logout():
    return {"message": "Client token removed"}


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user:
        # We still return 200 so attackers can't enumerate emails
        return {"message": "If that email is registered, a reset link has been sent."}
    
    # Create a token specifically for resetting, expires in 15 mins
    reset_token = create_access_token(user.email, role="reset")
    reset_link = f"http://localhost:5173/reset-password?token={reset_token}"
    
    await send_reset_password_email(user.email, reset_link)
    return {"message": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        decoded = decode_access_token(payload.token)
        email = decoded.get("sub")
        role = decoded.get("role")
        if not email or role != "reset":
            raise HTTPException(400, "Invalid reset token")
    except ValueError:
        raise HTTPException(400, "Invalid or expired reset token")
        
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(404, "User not found")
        
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    
    return {"message": "Password successfully reset"}
