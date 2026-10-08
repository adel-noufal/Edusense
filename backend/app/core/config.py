from functools import lru_cache
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    secret_key: str = "dev-only-change-me"
    database_url: str = "postgresql://edusense:edusense@localhost:5432/edusense"
    access_token_minutes: int = 1440
    engagement_threshold: int = 62
    ai_provider: str = "gemini"
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_API_KEY", "EDUSENSE_GEMINI_API_KEY", "gemini_api_key")
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        validation_alias=AliasChoices("GEMINI_MODEL", "EDUSENSE_GEMINI_MODEL", "gemini_model")
    )
    ollama_url: str = "http://localhost:11434/api/generate"
    ollama_model: str = "llama3.2"
    ollama_model_translation: str = "qwen2.5"
    ollama_model_lesson: str = "mistral"
    ollama_model_quiz: str = "llama3.1"
    ollama_model_flashcard: str = "llama3.2"

    # RAG Search Settings
    rag_min_score: float = Field(
        default=0.6,
        validation_alias=AliasChoices("RAG_MIN_SCORE", "EDUSENSE_RAG_MIN_SCORE", "rag_min_score")
    )

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:5175,http://127.0.0.1:5175,http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000"
    youtube_api_key: str = ""
    google_cloud_credentials_json: str = ""
    frontend_url: str = "http://localhost:5173"

    # Email Settings
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None

    # ChromaDB Vector Store (Task 1)
    chroma_persist_dir: str = Field(
        default="./data/chroma",
        validation_alias=AliasChoices("CHROMA_PERSIST_DIR", "EDUSENSE_CHROMA_PERSIST_DIR", "chroma_persist_dir")
    )
    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        validation_alias=AliasChoices("EMBEDDING_MODEL", "EDUSENSE_EMBEDDING_MODEL", "embedding_model")
    )

    model_config = SettingsConfigDict(env_prefix="EDUSENSE_", env_file=".env", extra="ignore")


    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

