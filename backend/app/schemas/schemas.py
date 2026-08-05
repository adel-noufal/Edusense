from datetime import date, datetime, time
from pydantic import BaseModel, Field, EmailStr


class UserCreate(BaseModel):
    name: str
    email: str
    password: str = Field(min_length=6)
    role: str = Field(pattern="^(student|instructor)$")


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=6)


class ProfileIn(BaseModel):
    phone: str | None = None
    university: str | None = None
    department: str | None = None
    avatar: str | None = None


class SessionIn(BaseModel):
    title: str
    description: str = ""
    date: date
    start_time: time
    duration: int = Field(ge=5, le=480)
    max_students: int | None = Field(default=None, ge=1, le=500)


class SessionOut(SessionIn):
    id: int
    instructor_id: int
    status: str

    model_config = {"from_attributes": True}


class EmotionFrameIn(BaseModel):
    session_id: int
    image: str


class EmotionLogIn(BaseModel):
    session_id: int
    student_id: int | None = None
    emotion: str
    confidence: float = Field(ge=0, le=1)


class LessonRequest(BaseModel):
    topic: str
    prompt: str
    language: str = "English"
    teaching_style: str = "Friendly"
    duration: int = Field(default=5, ge=1, le=60)
    additional_notes: str | None = None


class QuizRequest(BaseModel):
    session_id: int | None = None
    topic: str
    difficulty: str = "Medium"
    count: int = Field(default=8, ge=3, le=30)


class FeedbackIn(BaseModel):
    message: str


class VideoRequest(BaseModel):
    title: str
    prompt: str
    language: str = "English"
    style: str = "Friendly"
    duration: int = Field(default=5, ge=1, le=60)
    notes: str | None = None


class FlashcardRequest(BaseModel):
    topic: str
    count: int = Field(default=10, ge=3, le=40)
    language: str = "English"


class RecommendationDecision(BaseModel):
    accepted: bool
    action: str | None = None


class NoteCreate(BaseModel):
    session_id: int
    note: str
