from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Validated process configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "MM-RAG API"
    app_version: str = "2.0.0"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    api_v1_prefix: str = "/api/v1"

    database_url: SecretStr | None = None
    database_echo: bool = False
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    database_pool_recycle_seconds: int = Field(default=1800, ge=60)
    database_connect_timeout_seconds: int = Field(default=3, ge=1, le=30)

    qdrant_url: str = "http://127.0.0.1:6335"
    qdrant_api_key: SecretStr | None = None
    qdrant_timeout_seconds: int = Field(default=3, ge=1, le=30)

    openai_api_key: SecretStr | None = None
    openai_chat_model: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("api_v1_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("/"):
            raise ValueError("API_V1_PREFIX must start with '/'")
        if normalized == "/":
            raise ValueError("API_V1_PREFIX must identify a versioned path")
        if normalized.endswith("/"):
            normalized = normalized.rstrip("/")
        return normalized

    @field_validator("qdrant_url")
    @classmethod
    def normalize_qdrant_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("QDRANT_URL must use http:// or https://")
        return normalized

    @field_validator("qdrant_api_key", "openai_api_key", mode="before")
    @classmethod
    def blank_secret_is_none(cls, value: object) -> object:
        return None if value == "" else value

    def require_database_url(self) -> str:
        """Return the database URL without ever including it in model repr output."""

        if self.database_url is None:
            raise RuntimeError("DATABASE_URL is required to start the backend")
        return self.database_url.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
