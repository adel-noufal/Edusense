from pathlib import Path
import shutil
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.models import Profile, User
from app.schemas.schemas import ProfileIn, UserOut

router = APIRouter(prefix="/users", tags=["Users"])
AVATAR_DIR = Path(__file__).resolve().parents[1] / "static" / "avatars"


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_role("instructor"))):
    return db.query(User).order_by(User.name).all()


@router.get("/students", response_model=list[UserOut])
def list_students(db: Session = Depends(get_db), _: User = Depends(require_role("instructor"))):
    return db.query(User).filter(User.role == "student").order_by(User.name).all()


@router.get("/profile")
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.user_id == user.id).first()
    return profile or {}


@router.put("/profile")
def update_profile(payload: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.user_id == user.id).first() or Profile(user_id=user.id)
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    db.add(profile)
    db.commit()
    return {"message": "Profile updated"}


@router.post("/profile/avatar")
def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(400, "Please upload an image file")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        suffix = ".png"

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    avatar_name = f"user-{user.id}-{uuid4().hex[:8]}{suffix}"
    avatar_path = AVATAR_DIR / avatar_name
    with avatar_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    profile = db.query(Profile).filter(Profile.user_id == user.id).first() or Profile(user_id=user.id)
    profile.avatar = f"/static/avatars/{avatar_name}"
    db.add(profile)
    db.commit()

    return {"message": "Avatar uploaded", "avatar": profile.avatar}
