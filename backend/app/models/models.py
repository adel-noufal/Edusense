from datetime import datetime, timezone
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)
    profile: Mapped["Profile"] = relationship(back_populates="user", cascade="all, delete-orphan")


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    university: Mapped[str | None] = mapped_column(String(160), nullable=True)
    department: Mapped[str | None] = mapped_column(String(160), nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user: Mapped[User] = relationship(back_populates="profile")


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instructor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    date: Mapped[datetime] = mapped_column(Date)
    start_time: Mapped[datetime] = mapped_column(Time)
    duration: Mapped[int] = mapped_column(Integer)
    max_students: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    prep_start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    # Comma-separated list of minutes for which reminders have been sent (e.g. "15,10,5")
    reminders_sent: Mapped[str | None] = mapped_column(String(200), nullable=True)
    registrations: Mapped[list["SessionRegistration"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class SessionRegistration(Base):
    __tablename__ = "session_registrations"
    __table_args__ = (UniqueConstraint("session_id", "student_id", name="uq_session_student"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    attended: Mapped[bool] = mapped_column(Boolean, default=False)
    session: Mapped["Session"] = relationship(back_populates="registrations")


class EmotionLog(Base):
    __tablename__ = "emotion_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    emotion: Mapped[str] = mapped_column(String(30), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    summary: Mapped[str] = mapped_column(Text)
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VideoProject(Base):
    __tablename__ = "video_projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instructor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    prompt: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(40), default="English")
    style: Mapped[str] = mapped_column(String(40), default="Friendly")
    duration: Mapped[int] = mapped_column(Integer, default=5)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    video_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Quiz(Base):
    __tablename__ = "quizzes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    difficulty: Mapped[str] = mapped_column(String(40), default="Medium")
    questions_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Task 10: Quiz Timer settings
    time_limit_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Per-quiz time limit
    time_limit_per_question_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Per-question time limit
    # Quiz Anti-Cheat / Fullscreen Lockdown settings
    fullscreen_lock: Mapped[bool] = mapped_column(Boolean, default=False)
    camera_monitoring: Mapped[bool] = mapped_column(Boolean, default=False)


class QuizAttempt(Base):
    """Student quiz attempt with server-side timing validation."""
    __tablename__ = "quiz_attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    # Server-side timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Anti-cheat
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)  # Locked due to violation
    lock_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Answers and scoring
    answers_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # Student answers
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # Per-question breakdown


class QuizViolation(Base):
    """Anti-cheat violation log for quiz attempts."""
    __tablename__ = "quiz_violations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    attempt_id: Mapped[int | None] = mapped_column(ForeignKey("quiz_attempts.id", ondelete="SET NULL"), nullable=True, index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)  # exit_attempt, tab_switch, second_device_detected, etc.
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    # Instructor re-entry approval
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    re_entry_approved: Mapped[bool] = mapped_column(Boolean, default=False)


class QuizAgentConfig(Base):
    """Reusable quiz generation configuration saved by instructors."""
    __tablename__ = "quiz_agent_configs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instructor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(180))  # e.g., "Weekly Physics Quiz", "Final Exam Config"
    # Generation preferences
    subject: Mapped[str | None] = mapped_column(String(80), nullable=True)
    grade_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    difficulty_mix: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: {"easy": 0.3, "medium": 0.5, "hard": 0.2}
    question_types: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: ["multiple_choice", "true_false", "short_answer"]
    topic_weights: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: {"Photosynthesis": 0.4, "Cellular Respiration": 0.6}
    time_limit_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fullscreen_lock: Mapped[bool] = mapped_column(Boolean, default=False)
    camera_monitoring: Mapped[bool] = mapped_column(Boolean, default=False)
    # Common prompt additions
    custom_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SessionNote(Base):
    __tablename__ = "session_notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AIGeneration(Base):
    __tablename__ = "ai_generations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instructor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(40))
    topic: Mapped[str] = mapped_column(String(180))
    prompt: Mapped[str] = mapped_column(Text, default="")
    data_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GenerationJob(Base):
    """Persistent background AI generation job (survives server restarts)."""
    __tablename__ = "generation_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    instructor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_type: Mapped[str] = mapped_column(String(40), index=True)
    label: Mapped[str] = mapped_column(String(180), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SessionResource(Base):
    """Instructor-uploaded resources (slides, PDFs, presentations) linked to a session."""
    __tablename__ = "session_resources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    instructor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    file_type: Mapped[str] = mapped_column(String(80), default="file")
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatMessage(Base):
    """Chat conversation messages persisted for history."""
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # "user" or "assistant"
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # sources, mode, etc.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AuditLog(Base):
    """Audit log for security-relevant access events."""
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_user_id_created_at", "user_id", "created_at"),
        Index("ix_audit_logs_action_created_at", "action", "created_at"),
        Index("ix_audit_logs_resource_type_id", "resource_type", "resource_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(60), index=True)  # e.g., "read_student_data", "generate_report", "access_session"
    resource_type: Mapped[str | None] = mapped_column(String(60), nullable=True)  # e.g., "session", "report", "student"
    resource_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # Additional context (IP, user-agent, etc.)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ConsentRecord(Base):
    """User consent records for data processing (webcam, quiz camera, etc.)."""
    __tablename__ = "consent_records"
    __table_args__ = (UniqueConstraint("user_id", "consent_type", name="uq_user_consent_type"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    consent_type: Mapped[str] = mapped_column(String(50), index=True)  # e.g., "emotion_detection", "quiz_anti_cheat"
    given: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[str] = mapped_column(String(20))  # e.g., "1.0"
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

