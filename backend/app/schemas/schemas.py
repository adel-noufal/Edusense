from datetime import date, datetime, time
from pydantic import BaseModel, Field, EmailStr, field_validator


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


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    current_password: str | None = None
    new_password: str | None = Field(default=None, min_length=6)



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
    prep_start_time: datetime | None = None
    instructor_name: str | None = None

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
    session_id: int | None = None
    source_session_id: int | None = None
    # RAG context filters (optional; when provided, RAG chunks are retrieved)
    subject: str | None = None
    grade_level: str | None = None


class QuizRequest(BaseModel):
    session_id: int | None = None
    source_session_id: int | None = None
    topic: str
    prompt: str = ""
    difficulty: str = "Medium"
    count: int = Field(default=8, ge=3, le=30)
    # Optional saved config to apply
    config_id: int | None = None
    # RAG context filters
    subject: str | None = None
    grade_level: str | None = None


class FeedbackIn(BaseModel):
    message: str


class VideoRequest(BaseModel):
    title: str
    prompt: str
    language: str = "English"
    style: str = "Friendly"
    duration: int = Field(default=5, ge=1, le=60)
    notes: str | None = None
    session_id: int | None = None
    source_session_id: int | None = None


class FlashcardRequest(BaseModel):
    topic: str
    prompt: str = ""
    count: int = Field(default=10, ge=3, le=40)
    language: str = "English"
    session_id: int | None = None
    source_session_id: int | None = None
    # RAG context filters
    subject: str | None = None
    grade_level: str | None = None


# Task 10 & 11 & Quiz Anti-Cheat: Quiz schemas
class PublishExamRequest(BaseModel):
    session_id: int
    time_limit_seconds: int | None = None
    time_limit_per_question_seconds: int | None = None
    lock_back_navigation: bool = False
    fullscreen_lock: bool = True
    camera_monitoring: bool = False
    due_date: datetime | None = None


class QuizOut(BaseModel):
    id: int
    session_id: int | None = None
    title: str
    difficulty: str
    questions: list[dict]
    created_at: datetime
    # Timer settings
    time_limit_seconds: int | None = None
    time_limit_per_question_seconds: int | None = None
    # Anti-cheat settings
    fullscreen_lock: bool = False
    camera_monitoring: bool = False
    # Section 3 / Section 5: Exam publishing fields
    is_published: bool = True
    is_exam: bool = False
    lock_back_navigation: bool = False
    due_date: datetime | None = None

    model_config = {"from_attributes": True}


class QuizAttemptCreate(BaseModel):
    """Start a new quiz attempt."""
    pass


class QuizAttemptOut(BaseModel):
    id: int
    quiz_id: int
    student_id: int
    session_id: int | None = None
    started_at: datetime
    submitted_at: datetime | None = None
    is_locked: bool = False
    lock_reason: str | None = None
    score: float | None = None
    max_score: float | None = None

    model_config = {"from_attributes": True}


class QuizSubmitRequest(BaseModel):
    answers: dict[int, str]  # question_index -> answer (letter for MCQ/TF, text for short answer)
    elapsed_seconds: int  # Client-reported elapsed time (validated server-side)


class QuizSubmitResponse(BaseModel):
    attempt_id: int
    score: float
    max_score: float
    percentage: float
    details: list[dict]  # Per-question breakdown: {question_index, correct, student_answer, correct_answer, explanation}
    passed: bool


class QuizViolationOut(BaseModel):
    id: int
    quiz_id: int
    attempt_id: int | None = None
    student_id: int
    event_type: str
    details: dict | None = None
    timestamp: datetime
    is_reviewed: bool = False
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None
    re_entry_approved: bool = False

    model_config = {"from_attributes": True}


class QuizAgentConfigCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    session_id: int | None = None
    subject: str | None = None
    grade_level: str | None = None
    difficulty_mix: dict[str, float] | None = None  # e.g., {"easy": 0.3, "medium": 0.5, "hard": 0.2}
    question_types: list[str] | None = None  # e.g., ["multiple_choice", "true_false", "short_answer"]
    topic_weights: dict[str, float] | None = None  # e.g., {"Photosynthesis": 0.4, "Cellular Respiration": 0.6}
    time_limit_seconds: int | None = Field(default=None, ge=30, le=7200)
    fullscreen_lock: bool = False
    camera_monitoring: bool = False
    custom_prompt: str | None = None


class QuizAgentConfigUpdate(QuizAgentConfigCreate):
    pass


class QuizAgentConfigOut(BaseModel):
    id: int
    instructor_id: int
    session_id: int | None = None
    name: str
    subject: str | None = None
    grade_level: str | None = None
    difficulty_mix: dict[str, float] | None = None
    question_types: list[str] | None = None
    topic_weights: dict[str, float] | None = None
    time_limit_seconds: int | None = None
    fullscreen_lock: bool = False
    camera_monitoring: bool = False
    custom_prompt: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("difficulty_mix", "topic_weights", mode="before")
    @classmethod
    def parse_json_dict(cls, v):
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except Exception:
                return None
        return v

    @field_validator("question_types", mode="before")
    @classmethod
    def parse_json_list(cls, v):
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except Exception:
                return None
        return v


class RecommendationDecision(BaseModel):
    accepted: bool
    action: str | None = None


class NoteCreate(BaseModel):
    session_id: int
    note: str


class ConsentRecordOut(BaseModel):
    id: int
    user_id: int
    consent_type: str
    given: bool
    version: str
    timestamp: datetime
    withdrawn_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConsentGiveRequest(BaseModel):
    consent_type: str = Field(pattern="^(emotion_detection|quiz_anti_cheat)$")
    version: str = "1.0"


class ConsentCheckResponse(BaseModel):
    has_consent: bool
    consent_type: str
    version: str | None = None
    timestamp: datetime | None = None


# ─── Section 3: Assignment schemas ───────────────────────────────────────────

class AssignmentIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    due_date: datetime | None = None
    max_points: float = Field(default=100.0, ge=0)
    session_id: int


class AssignmentOut(BaseModel):
    id: int
    session_id: int
    instructor_id: int
    title: str
    description: str | None = None
    due_date: datetime | None = None
    max_points: float
    created_at: datetime

    model_config = {"from_attributes": True}


class AssignmentSubmissionOut(BaseModel):
    id: int
    assignment_id: int
    student_id: int
    file_name: str
    file_size: int
    submitted_at: datetime
    score: float | None = None
    feedback: str | None = None

    model_config = {"from_attributes": True}
