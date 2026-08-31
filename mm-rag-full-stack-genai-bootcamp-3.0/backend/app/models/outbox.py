from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
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


class IngestionOutboxEventType(StrEnum):
    JOB_AVAILABLE = "ingestion.job.available"


class IngestionOutboxEvent(TimestampMixin, Base):
    __tablename__ = "ingestion_outbox_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('ingestion.job.available')",
            name="ck_ingestion_outbox_event_type",
        ),
        CheckConstraint(
            "dispatch_sequence > 0",
            name="ck_ingestion_outbox_dispatch_sequence",
        ),
        CheckConstraint(
            "schema_version > 0",
            name="ck_ingestion_outbox_schema_version",
        ),
        CheckConstraint(
            "publication_attempt_count >= 0",
            name="ck_ingestion_outbox_publication_attempt_count",
        ),
        CheckConstraint(
            "(lease_owner IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_ingestion_outbox_lease",
        ),
        CheckConstraint(
            "publication_started_at IS NULL OR "
            "(lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_ingestion_outbox_publication_started_lease",
        ),
        CheckConstraint(
            "published_at IS NULL OR discarded_at IS NULL",
            name="ck_ingestion_outbox_one_terminal_marker",
        ),
        CheckConstraint(
            "(discarded_at IS NULL AND discard_reason IS NULL) OR "
            "(discarded_at IS NOT NULL AND discard_reason IS NOT NULL)",
            name="ck_ingestion_outbox_discard",
        ),
        CheckConstraint(
            "(last_error_code IS NULL AND last_error_at IS NULL) OR "
            "(last_error_code IS NOT NULL AND last_error_at IS NOT NULL)",
            name="ck_ingestion_outbox_last_error",
        ),
        CheckConstraint(
            "(published_at IS NULL AND discarded_at IS NULL) OR "
            "(lease_owner IS NULL AND lease_expires_at IS NULL)",
            name="ck_ingestion_outbox_terminal_lease",
        ),
        ForeignKeyConstraint(
            ["job_id", "workspace_id"],
            ["ingestion_jobs.id", "ingestion_jobs.workspace_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "job_id",
            "dispatch_sequence",
            name="uq_ingestion_outbox_job_dispatch_sequence",
        ),
        Index(
            "ix_ingestion_outbox_due",
            "available_at",
            "created_at",
            postgresql_where=text("published_at IS NULL AND discarded_at IS NULL"),
            sqlite_where=text("published_at IS NULL AND discarded_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    dispatch_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    publication_attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    lease_owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    publication_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    discarded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    discard_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
