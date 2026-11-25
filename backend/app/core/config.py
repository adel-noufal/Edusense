from functools import lru_cache
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Persistent JWT signing secret. Must accept the documented env names so a
    # restart keeps existing sessions valid instead of silently falling back to
    # the built-in default.
    secret_key: str = Field(
        default="dev-only-change-me",
        validation_alias=AliasChoices(
            "SECRET_KEY", "EDUSENSE_SECRET_KEY", "secret_key"
        ),
    )
    database_url: str = "postgresql://edusense:edusense@localhost:5432/edusense"
    access_token_minutes: int = 1440
    engagement_threshold: int = 62
    allow_paid_models: bool = Field(default=False, validation_alias=AliasChoices("ALLOW_PAID_MODELS", "allow_paid_models"))
    ai_provider: str = "auto"
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_API_KEY", "EDUSENSE_GEMINI_API_KEY", "gemini_api_key")
    )
    # Empty by default: the model is chosen from the key's live catalog, never
    # from a hardcoded (possibly retired) name.
    gemini_model: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_MODEL", "EDUSENSE_GEMINI_MODEL", "gemini_model")
    )
    # Ordered model fallback chains (comma-separated). Task-specific chains
    # override the default. See app/services/gemini.py GeminiRotator.
    gemini_models: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_MODELS", "EDUSENSE_GEMINI_MODELS", "gemini_models")
    )
    gemini_models_chat: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_MODELS_CHAT", "EDUSENSE_GEMINI_MODELS_CHAT", "gemini_models_chat")
    )
    gemini_models_script: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_MODELS_SCRIPT", "EDUSENSE_GEMINI_MODELS_SCRIPT", "gemini_models_script")
    )
    # Maps Gemini key_index -> quota group (keys in the same Google project
    # share quota). Format: "0:1,1:2,2:2". Default: each key its own group.
    gemini_key_groups: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_KEY_GROUPS", "EDUSENSE_GEMINI_KEY_GROUPS", "gemini_key_groups")
    )

    # ── Additional LLM providers (comma-separated keys; OpenAI-compatible) ──
    groq_api_keys: str = Field(default="", validation_alias=AliasChoices("GROQ_API_KEYS", "EDUSENSE_GROQ_API_KEYS", "groq_api_keys"))
    openrouter_api_keys: str = Field(default="", validation_alias=AliasChoices("OPENROUTER_API_KEYS", "EDUSENSE_OPENROUTER_API_KEYS", "openrouter_api_keys"))
    nvidia_api_keys: str = Field(default="", validation_alias=AliasChoices("NVIDIA_API_KEYS", "EDUSENSE_NVIDIA_API_KEYS", "nvidia_api_keys"))
    deepinfra_api_keys: str = Field(default="", validation_alias=AliasChoices("DEEPINFRA_API_KEYS", "EDUSENSE_DEEPINFRA_API_KEYS", "deepinfra_api_keys"))
    cerebras_api_keys: str = Field(default="", validation_alias=AliasChoices("CEREBRAS_API_KEYS", "EDUSENSE_CEREBRAS_API_KEYS", "cerebras_api_keys"))
    groq_models: str = Field(default="", validation_alias=AliasChoices("GROQ_MODELS", "EDUSENSE_GROQ_MODELS", "groq_models"))
    openrouter_models: str = Field(default="", validation_alias=AliasChoices("OPENROUTER_MODELS", "EDUSENSE_OPENROUTER_MODELS", "openrouter_models"))
    nvidia_models: str = Field(default="", validation_alias=AliasChoices("NVIDIA_MODELS", "EDUSENSE_NVIDIA_MODELS", "nvidia_models"))
    deepinfra_models: str = Field(default="", validation_alias=AliasChoices("DEEPINFRA_MODELS", "EDUSENSE_DEEPINFRA_MODELS", "deepinfra_models"))
    cerebras_models: str = Field(default="", validation_alias=AliasChoices("CEREBRAS_MODELS", "EDUSENSE_CEREBRAS_MODELS", "cerebras_models"))

    # ── Video generation ──────────────────────────────────────────────────────
    # Narration pace used to map requested duration -> target script word count
    video_narration_wpm: float = Field(
        default=140.0,
        validation_alias=AliasChoices("VIDEO_NARRATION_WPM", "EDUSENSE_VIDEO_NARRATION_WPM", "video_narration_wpm")
    )
    # Allowed deviation from target word count (0.10 = ±10%)
    video_script_tolerance: float = Field(
        default=0.10,
        validation_alias=AliasChoices("VIDEO_SCRIPT_TOLERANCE", "EDUSENSE_VIDEO_SCRIPT_TOLERANCE", "video_script_tolerance")
    )
    # Per-scene TTS timeout (seconds)
    video_tts_timeout: float = Field(
        default=45.0,
        validation_alias=AliasChoices("VIDEO_TTS_TIMEOUT", "EDUSENSE_VIDEO_TTS_TIMEOUT", "video_tts_timeout")
    )

    # ── Reports ───────────────────────────────────────────────────────────────
    # Minimum data before AI insights/scores are generated
    # A short class (10-15 min) must still get an analysis: 3 real samples and
    # half a minute of attendance are enough to show measured data.
    report_min_emotion_samples: int = Field(
        default=3,
        validation_alias=AliasChoices("REPORT_MIN_EMOTION_SAMPLES", "EDUSENSE_REPORT_MIN_EMOTION_SAMPLES", "report_min_emotion_samples")
    )
    report_min_attended_minutes: float = Field(
        default=0.5,
        validation_alias=AliasChoices("REPORT_MIN_ATTENDED_MINUTES", "EDUSENSE_REPORT_MIN_ATTENDED_MINUTES", "report_min_attended_minutes")
    )
    report_min_participants: int = Field(
        default=1,
        validation_alias=AliasChoices("REPORT_MIN_PARTICIPANTS", "EDUSENSE_REPORT_MIN_PARTICIPANTS", "report_min_participants")
    )
    # Sanity cap for computed attended duration (minutes). Sessions left open
    # or with broken clocks are clamped to this value, never rejected.
    report_max_attended_minutes: float = Field(
        default=720.0,
        validation_alias=AliasChoices("REPORT_MAX_ATTENDED_MINUTES", "EDUSENSE_REPORT_MAX_ATTENDED_MINUTES", "report_max_attended_minutes")
    )
    # Minutes after a scheduled start during which a never-started session is
    # still considered "upcoming"; afterwards it becomes "missed".
    session_missed_grace_minutes: int = Field(
        default=30,
        validation_alias=AliasChoices("SESSION_MISSED_GRACE_MINUTES", "EDUSENSE_SESSION_MISSED_GRACE_MINUTES", "session_missed_grace_minutes")
    )
    ollama_url: str = "http://localhost:11434/api/generate"
    ollama_model: str = "llama3.2"
    ollama_model_translation: str = "qwen2.5"
    # llama3.2 is the default local model for every feature: it is the only one
    # that answers in tens of seconds on a 4 GB GPU. mistral / llama3.1 / qwen2.5
    # stay selectable and are labelled "slow on this PC" in the UI.
    ollama_model_lesson: str = "llama3.2"
    ollama_model_quiz: str = "llama3.2"
    ollama_model_flashcard: str = "llama3.2"

    # RAG Search Settings
    rag_min_score: float = Field(
        default=0.6,
        validation_alias=AliasChoices("RAG_MIN_SCORE", "EDUSENSE_RAG_MIN_SCORE", "rag_min_score")
    )
    # Knowledge Base chat engine (addendum #11 §1.7):
    #   auto    -> Groq -> NVIDIA -> OpenRouter -> Ollama -> Gemini (cloud last)
    #   private -> local Ollama only (recommended for uploaded books)
    #   cloud   -> cloud providers only, never local Ollama
    kb_engine: str = Field(
        # F3: uploaded books are answered locally by default (llama3.2, the
        # fastest local model here); cloud is an explicit opt-in switch.
        default="private",
        validation_alias=AliasChoices("KB_ENGINE", "EDUSENSE_KB_ENGINE", "kb_engine")
    )

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:5175,http://127.0.0.1:5175,http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000"
    youtube_api_key: str = ""
    google_cloud_credentials_json: str = ""
    tavily_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("TAVILY_API_KEY", "EDUSENSE_TAVILY_API_KEY", "tavily_api_key")
    )
    frontend_url: str = "http://localhost:5173"

    # HTTP request guard: a stuck provider call is cut off instead of hanging
    # the browser tab. Long background generations are jobs, not requests.
    request_timeout_seconds: int = Field(
        default=300,
        validation_alias=AliasChoices("REQUEST_TIMEOUT_SECONDS", "EDUSENSE_REQUEST_TIMEOUT_SECONDS", "request_timeout_seconds")
    )

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

    # ── Chatbot Identity ───────────────────────────────────────────────────────
    chatbot_name: str = Field(
        default="EduSense AI",
        validation_alias=AliasChoices("CHATBOT_NAME", "EDUSENSE_CHATBOT_NAME", "chatbot_name")
    )
    chatbot_persona: str = Field(
        default="You are EduSense AI, a helpful educational assistant. You help instructors and students with course materials, learning questions, lesson planning, and academic queries. Be concise, accurate, and encouraging.",
        validation_alias=AliasChoices("CHATBOT_PERSONA", "EDUSENSE_CHATBOT_PERSONA", "chatbot_persona")
    )
    # Optional dedicated API key for the chatbot (uses main gemini_api_key pool if not set)
    chatbot_gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("CHATBOT_GEMINI_API_KEY", "EDUSENSE_CHATBOT_GEMINI_API_KEY", "chatbot_gemini_api_key")
    )

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

        if self.chatbot_gemini_api_key:
            cb_k = self.chatbot_gemini_api_key.strip()
            if cb_k and cb_k not in keys:
                keys.append(cb_k)

        # 3. Pooled GEMINI_API_KEYS / EDUSENSE_GEMINI_API_KEYS
        for pool_var in ("GEMINI_API_KEYS", "EDUSENSE_GEMINI_API_KEYS"):
            raw_pool = os.environ.get(pool_var, "").strip()
            if raw_pool:
                for k in raw_pool.split(","):
                    k = k.strip()
                    if k and k not in keys:
                        keys.append(k)

        # 4. Named GEMINI_KEY_<LABEL> / EDUSENSE_GEMINI_KEY_<LABEL>
        gemini_named = []
        for env_name, val in os.environ.items():
            upper = env_name.upper()
            if (upper.startswith("GEMINI_KEY_") or upper.startswith("EDUSENSE_GEMINI_KEY_")) and not upper.endswith(("_GROUP", "_FEATURE", "_PRIORITY")):
                val = val.strip()
                if val:
                    gemini_named.append((upper, val))
        for _, val in sorted(gemini_named):
            if val not in keys:
                keys.append(val)

        return keys

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
