from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.mixins import TimestampMixin


class LifecycleResourceType(StrEnum):
    DOCUMENT = "document"
    CONVERSATION = "conversation"


class LifecyclePlanState(StrEnum):
    RECOVERABLE = "recoverable"
    PURGING = "purging"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class LifecycleDeletionPlan(TimestampMixin, Base):
    __tablename__ = "lifecycle_deletion_plans"
    __table_args__ = (
        CheckConstraint(
            "resource_type IN ('document', 'conversation')",
            name="ck_lifecycle_plans_resource_type",
        ),
        CheckConstraint(
            "state IN ('recoverable', 'purging', 'blocked', 'completed')",
            name="ck_lifecycle_plans_state",
        ),
        CheckConstraint(
            "deleted_vector_count >= 0 AND deleted_object_count >= 0",
            name="ck_lifecycle_plans_nonnegative_counts",
        ),
        CheckConstraint(
            "(state = 'completed' AND completed_at IS NOT NULL AND "
            "metadata_deleted_at IS NOT NULL) OR "
            "(state != 'completed' AND completed_at IS NULL)",
            name="ck_lifecycle_plans_completion",
        ),
        UniqueConstraint(
            "workspace_id",
            "resource_type",
            "resource_id",
            name="uq_lifecycle_plans_resource",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    policy_revision: Mapped[str] = mapped_column(String(80), nullable=False)
    state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=LifecyclePlanState.RECOVERABLE.value,
        server_default=LifecyclePlanState.RECOVERABLE.value,
        index=True,
    )
    execute_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    jobs_fenced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    vectors_deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    artifacts_deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    originals_deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_vector_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    deleted_object_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(300), nullable=True)


class RetentionHold(TimestampMixin, Base):
    __tablename__ = "retention_holds"
    __table_args__ = (
        CheckConstraint(
            "resource_type IN ('document', 'conversation')",
            name="ck_retention_holds_resource_type",
        ),
        UniqueConstraint(
            "workspace_id",
            "resource_type",
            "resource_id",
            name="uq_retention_holds_resource",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    placed_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)


class OrphanObjectEvidence(TimestampMixin, Base):
    __tablename__ = "orphan_object_evidence"
    __table_args__ = (
        CheckConstraint(
            "storage_class IN ('originals', 'artifacts')",
            name="ck_orphan_object_evidence_storage_class",
        ),
        CheckConstraint(
            "evidence_count > 0", name="ck_orphan_object_evidence_positive_count"
        ),
        CheckConstraint(
            "last_seen_at >= first_seen_at",
            name="ck_orphan_object_evidence_seen_window",
        ),
        CheckConstraint(
            "byte_size >= 0", name="ck_orphan_object_evidence_nonnegative_size"
        ),
        UniqueConstraint(
            "workspace_id",
            "storage_class",
            "object_key",
            name="uq_orphan_object_evidence_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_class: Mapped[str] = mapped_column(String(16), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
