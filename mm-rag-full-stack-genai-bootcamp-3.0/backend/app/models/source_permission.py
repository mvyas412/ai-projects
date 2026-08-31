from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class SourcePermissionSnapshot(Base):
    """Immutable, provider-neutral source permission evidence for future connectors."""

    __tablename__ = "source_permission_snapshots"
    __table_args__ = (
        CheckConstraint("schema_version > 0", name="ck_source_permissions_schema_version"),
        CheckConstraint(
            "length(source_item_ref_hash) = 64",
            name="ck_source_permissions_item_hash",
        ),
        CheckConstraint(
            "length(permission_fingerprint) = 64",
            name="ck_source_permissions_fingerprint",
        ),
        CheckConstraint(
            "unresolved_principal_count >= 0",
            name="ck_source_permissions_unresolved_count",
        ),
        CheckConstraint(
            "verified_at < valid_until",
            name="ck_source_permissions_valid_window",
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
            "workspace_id",
            "source_namespace",
            "source_item_ref_hash",
            "sync_revision",
            "permission_revision",
            name="uq_source_permissions_revision",
        ),
        UniqueConstraint(
            "id", "workspace_id", name="uq_source_permission_snapshot_workspace"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    document_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    source_namespace: Mapped[str] = mapped_column(String(80), nullable=False)
    source_item_ref_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sync_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    permission_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    permission_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    unresolved_principal_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    semantics_supported: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SourcePermissionPrincipal(Base):
    __tablename__ = "source_permission_principals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["snapshot_id", "workspace_id"],
            ["source_permission_snapshots.id", "source_permission_snapshots.workspace_id"],
            ondelete="CASCADE",
        ),
    )

    snapshot_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    principal_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
