from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.mixins import TimestampMixin


class IngestionGenerationState(StrEnum):
    BUILDING = "building"
    VALIDATED = "validated"
    PROMOTED = "promoted"
    ABANDONED = "abandoned"


class IngestionGeneration(TimestampMixin, Base):
    __tablename__ = "ingestion_generations"
    __table_args__ = (
        CheckConstraint(
            "state IN ('building', 'validated', 'promoted', 'abandoned')",
            name="ck_ingestion_generations_state",
        ),
        CheckConstraint(
            "length(pipeline_fingerprint) = 64",
            name="ck_ingestion_generations_pipeline_hash",
        ),
        CheckConstraint(
            "chunk_count IS NULL OR chunk_count >= 0",
            name="ck_ingestion_generations_chunk_count",
        ),
        CheckConstraint(
            "vector_count IS NULL OR vector_count >= 0",
            name="ck_ingestion_generations_vector_count",
        ),
        CheckConstraint(
            "(manifest_object_key IS NULL AND manifest_sha256 IS NULL) OR "
            "(manifest_object_key IS NOT NULL AND manifest_sha256 IS NOT NULL)",
            name="ck_ingestion_generations_manifest_identity",
        ),
        CheckConstraint(
            "state != 'promoted' OR (validated_at IS NOT NULL AND promoted_at IS NOT NULL)",
            name="ck_ingestion_generations_active_timestamps",
        ),
        ForeignKeyConstraint(
            ["job_id", "workspace_id"],
            ["ingestion_jobs.id", "ingestion_jobs.workspace_id"],
            ondelete="CASCADE",
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
        UniqueConstraint(
            "id",
            "document_version_id",
            "workspace_id",
            name="uq_ingestion_generations_id_version_workspace",
        ),
        UniqueConstraint("attempt_id", name="uq_ingestion_generations_attempt_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    attempt_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ingestion_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pipeline_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=IngestionGenerationState.BUILDING.value,
        server_default=IngestionGenerationState.BUILDING.value,
        index=True,
    )
    manifest: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    manifest_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    manifest_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    vector_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    abandoned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
