from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    secret_key: str = "dev-only-change-me"
    database_url: str = "postgresql://edusense:edusense@localhost:5432/edusense"
    access_token_minutes: int = 1440
    engagement_threshold: int = 62
    ai_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    ollama_url: str = "http://localhost:11434/api/generate"
    ollama_model: str = "llama3.2"
    ollama_model_translation: str = "qwen2.5"
    ollama_model_lesson: str = "mistral"
    ollama_model_quiz: str = "llama3.1"
    ollama_model_flashcard: str = "llama3.2"



    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000"
    youtube_api_key: str = ""
    google_cloud_credentials_json: str = ""
    frontend_url: str = "http://localhost:5173"

    # Email Settings
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None

    model_config = SettingsConfigDict(env_prefix="EDUSENSE_", env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

