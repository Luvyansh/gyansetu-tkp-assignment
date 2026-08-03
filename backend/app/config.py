"""Application configuration via pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = Field(..., description="Google AI Studio API key")
    groq_api_key: str | None = Field(default=None, description="Optional Groq API key")
    database_url: str = Field(..., description="Async SQLAlchemy Postgres URL")
    backend_api_key: str = Field(..., min_length=8, description="Shared secret for X-API-Key")
    environment: Literal["local", "production"] = "local"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:8501"

    max_upload_bytes: int = 25 * 1024 * 1024
    max_validation_retries: int = 2
    faithfulness_threshold: float = 0.50
    # Must match local MiniLM (all-MiniLM-L6-v2) + pgvector column / Alembic 0002.
    embedding_dim: int = 384

    @field_validator("groq_api_key", mode="before")
    @classmethod
    def empty_groq_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def groq_enabled(self) -> bool:
        return bool(self.groq_api_key)


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton. Raises ValidationError if required vars missing."""
    return Settings()  # type: ignore[call-arg]
