from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OPENAI_CHAT_MODEL = "gpt-4.1-mini"
DEFAULT_OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"


class Settings(BaseSettings):
    """Validated process configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "MM-RAG API"
    app_version: str = "3.0.0"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    api_v1_prefix: str = "/api/v1"

    auth0_issuer: str | None = None
    auth0_audience: str | None = None
    auth0_jwks_url: str | None = None
    auth0_jwks_cache_seconds: int = Field(default=300, ge=60, le=86400)
    auth0_jwks_timeout_seconds: int = Field(default=5, ge=1, le=30)

    local_storage_root: Path = PROJECT_ROOT / "data/runtime/storage"
    max_upload_bytes: int = Field(default=25 * 1024 * 1024, ge=1024, le=250 * 1024 * 1024)
    object_storage_backend: Literal["local", "s3"] = "local"
    s3_endpoint_url: str | None = "http://127.0.0.1:8333"
    s3_region: str = "us-east-1"
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_originals_bucket: str = "mm-rag-phase3-originals"
    s3_artifacts_bucket: str = "mm-rag-phase3-artifacts"
    s3_path_style: bool = True
    s3_connect_timeout_seconds: int = Field(default=3, ge=1, le=30)
    s3_read_timeout_seconds: int = Field(default=30, ge=1, le=300)

    database_url: SecretStr | None = None
    database_echo: bool = False
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    database_pool_recycle_seconds: int = Field(default=1800, ge=60)
    database_connect_timeout_seconds: int = Field(default=3, ge=1, le=30)

    rabbitmq_url: SecretStr | None = None
    rabbitmq_exchange: str = "mm-rag.ingestion"
    rabbitmq_queue: str = "mm-rag.ingestion.jobs"
    rabbitmq_routing_key: str = "ingestion.job.available"
    rabbitmq_dead_letter_exchange: str = "mm-rag.ingestion.dlx"
    rabbitmq_dead_letter_queue: str = "mm-rag.ingestion.dead"
    rabbitmq_dead_letter_routing_key: str = "ingestion.job.dead"
    rabbitmq_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)
    rabbitmq_publish_timeout_seconds: int = Field(default=10, ge=1, le=60)
    dispatcher_batch_size: int = Field(default=50, ge=1, le=50)
    dispatcher_lease_seconds: int = Field(default=30, ge=5, le=300)
    dispatcher_poll_seconds: float = Field(default=1.0, ge=0.1, le=30)
    worker_lease_seconds: int = Field(default=60, ge=15, le=600)
    worker_heartbeat_seconds: int = Field(default=15, ge=5, le=300)
    worker_shutdown_seconds: int = Field(default=120, ge=5, le=600)
    worker_recovery_poll_seconds: int = Field(default=15, ge=5, le=300)
    runtime_health_directory: Path = PROJECT_ROOT / "data/runtime/health"
    outbox_terminal_retention_days: int = Field(default=30, ge=1, le=365)
    outbox_alert_attempts: int = Field(default=10, ge=1, le=1000)
    outbox_alert_age_seconds: int = Field(default=900, ge=60, le=86400)

    qdrant_url: str = "http://127.0.0.1:6337"
    qdrant_api_key: SecretStr | None = None
    qdrant_timeout_seconds: int = Field(default=3, ge=1, le=30)
    qdrant_collection_name: str = "mm_rag_phase3_documents"
    rag_retrieval_limit: int = Field(default=8, ge=1, le=30)

    openai_api_key: SecretStr | None = None
    openai_chat_model: str = DEFAULT_OPENAI_CHAT_MODEL
    openai_embedding_model: str = DEFAULT_OPENAI_EMBEDDING_MODEL

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

    @field_validator("s3_endpoint_url", mode="before")
    @classmethod
    def blank_s3_endpoint_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("s3_endpoint_url")
    @classmethod
    def normalize_s3_endpoint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("S3_ENDPOINT_URL must use http:// or https://")
        return normalized

    @field_validator("s3_originals_bucket", "s3_artifacts_bucket")
    @classmethod
    def validate_s3_bucket(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", normalized):
            raise ValueError("S3 bucket names must be DNS-compatible")
        return normalized

    @field_validator("auth0_issuer", "auth0_audience", "auth0_jwks_url", mode="before")
    @classmethod
    def blank_auth_setting_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("auth0_issuer")
    @classmethod
    def normalize_auth0_issuer(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized.startswith("https://"):
            raise ValueError("AUTH0_ISSUER must use https://")
        return f"{normalized.rstrip('/')}/"

    @field_validator("auth0_jwks_url")
    @classmethod
    def validate_auth0_jwks_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized.startswith("https://"):
            raise ValueError("AUTH0_JWKS_URL must use https://")
        return normalized

    @model_validator(mode="after")
    def validate_auth0_configuration(self) -> Self:
        configured = (self.auth0_issuer is not None, self.auth0_audience is not None)
        if any(configured) and not all(configured):
            raise ValueError("AUTH0_ISSUER and AUTH0_AUDIENCE must be configured together")
        return self

    @field_validator(
        "qdrant_api_key",
        "openai_api_key",
        "s3_access_key_id",
        "s3_secret_access_key",
        "rabbitmq_url",
        mode="before",
    )
    @classmethod
    def blank_secret_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_s3_configuration(self) -> Self:
        credentials = (
            self.s3_access_key_id is not None
            and bool(self.s3_access_key_id.get_secret_value().strip()),
            self.s3_secret_access_key is not None
            and bool(self.s3_secret_access_key.get_secret_value().strip()),
        )
        if any(credentials) and not all(credentials):
            raise ValueError(
                "S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY must be configured together"
            )
        if self.object_storage_backend == "s3" and not all(credentials):
            raise ValueError("S3 credentials are required when OBJECT_STORAGE_BACKEND=s3")
        return self

    @field_validator(
        "rabbitmq_exchange",
        "rabbitmq_queue",
        "rabbitmq_routing_key",
        "rabbitmq_dead_letter_exchange",
        "rabbitmq_dead_letter_queue",
        "rabbitmq_dead_letter_routing_key",
    )
    @classmethod
    def validate_rabbitmq_name(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", normalized):
            raise ValueError("RabbitMQ names must use safe non-empty identifiers")
        return normalized

    @model_validator(mode="after")
    def validate_worker_timing(self) -> Self:
        if self.worker_heartbeat_seconds * 2 >= self.worker_lease_seconds:
            raise ValueError("WORKER_HEARTBEAT_SECONDS must be less than half the lease")
        return self

    @field_validator("openai_chat_model", mode="before")
    @classmethod
    def blank_chat_model_uses_default(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or DEFAULT_OPENAI_CHAT_MODEL
        return value

    @field_validator("openai_embedding_model", mode="before")
    @classmethod
    def blank_embedding_model_uses_default(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or DEFAULT_OPENAI_EMBEDDING_MODEL
        return value

    def require_database_url(self) -> str:
        """Return the database URL without ever including it in model repr output."""

        if self.database_url is None:
            raise RuntimeError("DATABASE_URL is required to start the backend")
        return self.database_url.get_secret_value()

    def require_rabbitmq_url(self) -> str:
        """Return the broker URL only to dispatcher and worker process builders."""

        if self.rabbitmq_url is None:
            raise RuntimeError("RABBITMQ_URL is required for asynchronous ingestion")
        return self.rabbitmq_url.get_secret_value()

    @property
    def auth0_is_configured(self) -> bool:
        return self.auth0_issuer is not None and self.auth0_audience is not None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
