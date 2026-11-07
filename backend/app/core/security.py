from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import get_settings

# Use argon2 as primary scheme with pbkdf2_sha256 as deprecated for backward compatibility
# argon2 is the winner of the Password Hashing Competition and resistant to GPU/ASIC attacks
# Note: Requires 'argon2-cffi' package. Falls back to pbkdf2_sha256 if not available.
try:
    import argon2  # noqa: F401
    HAS_ARGON2 = True
except ImportError:
    HAS_ARGON2 = False

if HAS_ARGON2:
    pwd_context = CryptContext(schemes=["argon2", "pbkdf2_sha256"], deprecated="auto")
else:
    # Fallback to pbkdf2_sha256 if argon2 not available
    # (bcrypt has 72-byte password limit issues on some platforms)
    pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str, role: str) -> str:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    payload = {"sub": subject, "role": role, "exp": expires}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc

