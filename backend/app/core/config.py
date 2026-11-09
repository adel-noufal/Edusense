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
    tavily_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("TAVILY_API_KEY", "EDUSENSE_TAVILY_API_KEY", "tavily_api_key")
    )
    frontend_url: str = "http://localhost:5173"

    # Security: Disable default/demo accounts in production
    disable_default_accounts: bool = Field(
        default=False,
        validation_alias=AliasChoices("DISABLE_DEFAULT_ACCOUNTS", "EDUSENSE_DISABLE_DEFAULT_ACCOUNTS", "disable_default_accounts")
    )

    # Email Settings
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None

    # ── Vector Store ──────────────────────────────────────────────────────────
    chroma_persist_dir: str = Field(
        default="data/chroma",
        validation_alias=AliasChoices("CHROMA_PERSIST_DIR", "EDUSENSE_CHROMA_PERSIST_DIR", "chroma_persist_dir")
    )
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        validation_alias=AliasChoices("EMBEDDING_MODEL", "EDUSENSE_EMBEDDING_MODEL", "embedding_model")
    )

    model_config = SettingsConfigDict(env_prefix="EDUSENSE_", env_file=".env", extra="ignore")


    @property
    def gemini_api_keys(self) -> list[str]:
        """
        Return all configured Gemini API keys in priority order:
        1. Comma-separated or single key in GEMINI_API_KEY / EDUSENSE_GEMINI_API_KEY
        2. Numbered environment variables like GEMINI_API_KEY_1, GEMINI_API_KEY_2, etc.
        """
        import os
        keys: list[str] = []
        if self.gemini_api_key:
            for k in self.gemini_api_key.split(","):
                k = k.strip()
                if k and k not in keys:
                    keys.append(k)

        numbered_keys = []
        for env_name in os.environ:
            upper = env_name.upper()
            if upper.startswith("GEMINI_API_KEY_") or upper.startswith("EDUSENSE_GEMINI_API_KEY_"):
                val = os.environ[env_name].strip()
                if val:
                    numbered_keys.append((upper, val))
        for _, val in sorted(numbered_keys):
            if val not in keys:
                keys.append(val)
        return keys

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

