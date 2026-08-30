"""Add tenant-scoped documents, versions, and collections.

Revision ID: 20260830_0003
Revises: 20260829_0002
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0003"
down_revision: str | None = "20260829_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_documents_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_documents_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.UniqueConstraint("id", "workspace_id", name="uq_documents_id_workspace_id"),
    )
    op.create_index("ix_documents_workspace_id", "documents", ["workspace_id"])

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("ingestion_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("failure_reason", sa.String(length=500), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "version_number > 0", name="ck_document_versions_positive_number"
        ),
        sa.CheckConstraint("byte_size > 0", name="ck_document_versions_positive_size"),
        sa.CheckConstraint(
            "status IN ('uploaded', 'processing', 'ready', 'failed')",
            name="ck_document_versions_status",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_document_versions_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "workspace_id"],
            ["documents.id", "documents.workspace_id"],
            name="fk_document_versions_document_workspace_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_versions"),
        sa.UniqueConstraint(
            "document_id", "version_number", name="uq_document_versions_document_number"
        ),
        sa.UniqueConstraint(
            "document_id",
            "content_sha256",
            "ingestion_fingerprint",
            name="uq_document_versions_document_content_config",
        ),
        sa.UniqueConstraint(
            "id", "workspace_id", name="uq_document_versions_id_workspace_id"
        ),
        sa.UniqueConstraint("object_key", name="uq_document_versions_object_key"),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])
    op.create_index("ix_document_versions_workspace_id", "document_versions", ["workspace_id"])

    op.create_table(
        "collections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_collections_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_collections_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_collections"),
        sa.UniqueConstraint("id", "workspace_id", name="uq_collections_id_workspace_id"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_collections_workspace_name"),
    )
    op.create_index("ix_collections_workspace_id", "collections", ["workspace_id"])

    op.create_table(
        "collection_documents",
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("added_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["added_by_user_id"],
            ["users.id"],
            name="fk_collection_documents_added_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["collection_id", "workspace_id"],
            ["collections.id", "collections.workspace_id"],
            name="fk_collection_documents_collection_workspace_collections",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "workspace_id"],
            ["documents.id", "documents.workspace_id"],
            name="fk_collection_documents_document_workspace_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "collection_id", "document_id", name="pk_collection_documents"
        ),
    )
    op.create_index(
        "ix_collection_documents_workspace_id", "collection_documents", ["workspace_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_collection_documents_workspace_id", table_name="collection_documents")
    op.drop_table("collection_documents")
    op.drop_index("ix_collections_workspace_id", table_name="collections")
    op.drop_table("collections")
    op.drop_index("ix_document_versions_workspace_id", table_name="document_versions")
    op.drop_index("ix_document_versions_document_id", table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_index("ix_documents_workspace_id", table_name="documents")
    op.drop_table("documents")
