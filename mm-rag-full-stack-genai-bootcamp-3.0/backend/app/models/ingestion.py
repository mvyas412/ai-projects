from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.mixins import TimestampMixin


class IngestionOperation(StrEnum):
    INDEX_DOCUMENT_VERSION = "index_document_version"


class IngestionJobState(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_SCHEDULED = "retry_scheduled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IngestionAttemptState(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    RETRYABLE_FAILURE = "retryable_failure"
    PERMANENT_FAILURE = "permanent_failure"
    CANCELLED = "cancelled"
    LEASE_EXPIRED = "lease_expired"


class IngestionProgressStage(StrEnum):
    LOADING_ORIGINAL = "loading_original"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    WRITING_OUTPUTS = "writing_outputs"
    VALIDATING = "validating"
    PROMOTING = "promoting"


class IngestionJob(TimestampMixin, Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('index_document_version')",
            name="ck_ingestion_jobs_operation",
        ),
        CheckConstraint(
            "state IN ('pending', 'queued', 'running', 'retry_scheduled', "
            "'succeeded', 'failed', 'cancelled')",
            name="ck_ingestion_jobs_state",
        ),
        CheckConstraint("length(pipeline_fingerprint) = 64", name="ck_jobs_pipeline_hash"),
        CheckConstraint("length(request_hash) = 64", name="ck_jobs_request_hash"),
        CheckConstraint("length(idempotency_key) > 0", name="ck_jobs_idempotency_key"),
        CheckConstraint("revision > 0", name="ck_ingestion_jobs_revision"),
        CheckConstraint("attempt_count >= 0", name="ck_ingestion_jobs_attempt_count"),
        CheckConstraint("max_attempts > 0", name="ck_ingestion_jobs_max_attempts"),
        CheckConstraint(
            "attempt_count <= max_attempts",
            name="ck_ingestion_jobs_attempt_budget",
        ),
        CheckConstraint("fencing_token >= 0", name="ck_ingestion_jobs_fencing_token"),
        CheckConstraint(
            "(state = 'retry_scheduled' AND next_attempt_at IS NOT NULL) OR "
            "(state != 'retry_scheduled' AND next_attempt_at IS NULL)",
            name="ck_ingestion_jobs_retry_schedule",
        ),
        CheckConstraint(
            "(state IN ('succeeded', 'failed', 'cancelled') AND completed_at IS NOT NULL) "
            "OR (state NOT IN ('succeeded', 'failed', 'cancelled') "
            "AND completed_at IS NULL)",
            name="ck_ingestion_jobs_terminal_timestamp",
        ),
        CheckConstraint(
            "(cancel_requested_at IS NULL AND cancel_requested_by_user_id IS NULL) OR "
            "(cancel_requested_at IS NOT NULL AND cancel_requested_by_user_id IS NOT NULL)",
            name="ck_ingestion_jobs_cancel_request",
        ),
        ForeignKeyConstraint(
            ["document_version_id", "document_id", "workspace_id"],
            [
                "document_versions.id",
                "document_versions.document_id",
                "document_versions.workspace_id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["predecessor_job_id", "workspace_id"],
            ["ingestion_jobs.id", "ingestion_jobs.workspace_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("id", "workspace_id", name="uq_ingestion_jobs_id_workspace_id"),
        UniqueConstraint(
            "workspace_id",
            "operation",
            "idempotency_key",
            name="uq_ingestion_jobs_workspace_operation_idempotency",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    predecessor_job_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    pipeline_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=IngestionJobState.PENDING.value,
        server_default=IngestionJobState.PENDING.value,
        index=True,
    )
    revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    fencing_token: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_requested_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    first_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)


class IngestionAttempt(TimestampMixin, Base):
    __tablename__ = "ingestion_attempts"
    __table_args__ = (
        CheckConstraint(
            "state IN ('running', 'succeeded', 'retryable_failure', "
            "'permanent_failure', 'cancelled', 'lease_expired')",
            name="ck_ingestion_attempts_state",
        ),
        CheckConstraint("attempt_number > 0", name="ck_ingestion_attempts_number"),
        CheckConstraint("fencing_token > 0", name="ck_ingestion_attempts_fencing_token"),
        CheckConstraint(
            "progress_completed IS NULL OR progress_completed >= 0",
            name="ck_ingestion_attempts_progress_completed",
        ),
        CheckConstraint(
            "progress_total IS NULL OR progress_total > 0",
            name="ck_ingestion_attempts_progress_total",
        ),
        CheckConstraint(
            "progress_completed IS NULL OR progress_total IS NULL "
            "OR progress_completed <= progress_total",
            name="ck_ingestion_attempts_progress_bounds",
        ),
        CheckConstraint(
            "(state = 'running' AND finished_at IS NULL) OR "
            "(state != 'running' AND finished_at IS NOT NULL)",
            name="ck_ingestion_attempts_finished_timestamp",
        ),
        ForeignKeyConstraint(
            ["job_id", "workspace_id"],
            ["ingestion_jobs.id", "ingestion_jobs.workspace_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "job_id", "attempt_number", name="uq_ingestion_attempts_job_number"
        ),
        UniqueConstraint(
            "job_id", "fencing_token", name="uq_ingestion_attempts_job_fencing_token"
        ),
        Index(
            "uq_ingestion_attempts_one_running_job",
            "job_id",
            unique=True,
            postgresql_where=text("state = 'running'"),
            sqlite_where=text("state = 'running'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=IngestionAttemptState.RUNNING.value,
        server_default=IngestionAttemptState.RUNNING.value,
        index=True,
    )
    worker_id: Mapped[str] = mapped_column(String(200), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    progress_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    progress_completed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    progress_total: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    progress_unit: Mapped[str | None] = mapped_column(String(24), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
