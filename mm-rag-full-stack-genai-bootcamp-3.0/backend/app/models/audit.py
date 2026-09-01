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
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class AuditActorKind(StrEnum):
    USER = "user"
    SERVICE = "service"


class AuditResult(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "actor_kind IN ('user', 'service')", name="ck_audit_events_actor_kind"
        ),
        CheckConstraint(
            "result IN ('allowed', 'denied', 'succeeded', 'failed')",
            name="ck_audit_events_result",
        ),
        CheckConstraint("schema_version > 0", name="ck_audit_events_schema_version"),
        CheckConstraint(
            "(actor_kind = 'user' AND actor_user_id IS NOT NULL AND service_actor IS NULL) "
            "OR (actor_kind = 'service' AND actor_user_id IS NULL "
            "AND service_actor IS NOT NULL)",
            name="ck_audit_events_one_actor",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AuditActorKind.USER.value, index=True
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    service_actor: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    result: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AuditResult.SUCCEEDED.value, index=True
    )
    policy_revision: Mapped[str] = mapped_column(String(80), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class ComplianceExport(Base):
    __tablename__ = "compliance_exports"
    __table_args__ = (
        CheckConstraint("status IN ('ready', 'failed')", name="ck_compliance_exports_status"),
        CheckConstraint("schema_version > 0", name="ck_compliance_exports_schema_version"),
        CheckConstraint("event_count >= 0", name="ck_compliance_exports_event_count"),
        CheckConstraint("byte_size > 0", name="ck_compliance_exports_byte_size"),
        CheckConstraint(
            "length(content_sha256) = 64", name="ck_compliance_exports_content_hash"
        ),
        CheckConstraint("range_start < range_end", name="ck_compliance_exports_range"),
        UniqueConstraint(
            "workspace_id",
            "range_start",
            "range_end",
            "schema_version",
            name="uq_compliance_exports_range_schema",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    range_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    range_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ready")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
