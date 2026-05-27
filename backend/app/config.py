from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_list_delimiter=",",
    )

    # ── Application ────────────────────────────────────────────────
    APP_NAME: str = "InferVoyage"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── Logging ────────────────────────────────────────────────────
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_FORMAT: Literal["json", "console"] = "json"

    # ── Database ───────────────────────────────────────────────────
    DATABASE_URL: str  # required

    # ── Redis ──────────────────────────────────────────────────────
    REDIS_URL: str  # required
    RATE_LIMIT_FAIL_OPEN: bool = True

    # ── Auth ───────────────────────────────────────────────────────
    SECRET_KEY: str  # required — min 32 chars enforced below
    ACCESS_TOKEN_TTL_SECONDS: int = 900       # 15 minutes
    REFRESH_TOKEN_TTL_SECONDS: int = 604800   # 7 days
    GOOGLE_CLIENT_ID: str | None = None

    # ── Email / SMTP ───────────────────────────────────────────────
    SMTP_HOST: str | None = None
    SMTP_PORT: int | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    RESEND_API_KEY: str | None = None
    RESEND_SENDER: str = "onboarding@resend.dev"

    # ── Ollama / Inference ─────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MAX_LOADED_MODELS: int = 1
    INFERENCE_TIMEOUT_SECONDS: int = 120
    INFERENCE_NUM_CTX: int = 2048
    MAX_CONCURRENT_INFERENCE: int = 4

    # ── CORS ───────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: list[str] | str = [
        "http://localhost:3000",
        "http://localhost:80",
        "https://localhost",
        "http://127.0.0.1",
        "https://127.0.0.1",
    ]

    # ── Cookies ────────────────────────────────────────────────────────────
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"

    # ── Retention ──────────────────────────────────────────────────────────────
    USAGE_LOG_RETENTION_DAYS: int = 90

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_min_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @model_validator(mode="after")
    def validate_required_secrets(self) -> "Settings":
        # Fail fast with clear messages — never silently start with defaults
        missing = []
        if not self.DATABASE_URL:
            missing.append("DATABASE_URL")
        if not self.REDIS_URL:
            missing.append("REDIS_URL")
        if not self.SECRET_KEY:
            missing.append("SECRET_KEY")
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Check your .env file or environment configuration."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings — evaluated once at startup."""
    return Settings()
