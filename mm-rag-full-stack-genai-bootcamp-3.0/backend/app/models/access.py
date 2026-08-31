from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.mixins import TimestampMixin


class ResourceVisibility(StrEnum):
    WORKSPACE = "workspace"
    RESTRICTED = "restricted"


class ResourceACLGrant(TimestampMixin, Base):
    """Positive in-workspace user grant for exactly one governed resource."""

    __tablename__ = "resource_acl_grants"
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN document_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN collection_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN conversation_id IS NULL THEN 0 ELSE 1 END) = 1",
            name="ck_resource_acl_grants_one_resource",
        ),
        ForeignKeyConstraint(
            ["document_id", "workspace_id"],
            ["documents.id", "documents.workspace_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["collection_id", "workspace_id"],
            ["collections.id", "collections.workspace_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "workspace_id"],
            ["conversations.id", "conversations.workspace_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "document_id", "principal_user_id", name="uq_acl_document_principal"
        ),
        UniqueConstraint(
            "collection_id", "principal_user_id", name="uq_acl_collection_principal"
        ),
        UniqueConstraint(
            "conversation_id", "principal_user_id", name="uq_acl_conversation_principal"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    principal_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    granted_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    collection_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
