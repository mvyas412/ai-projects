"""Add Phase 4 visibility and tenant-constrained resource ACL grants.

Revision ID: 20260831_0009
Revises: 20260830_0008
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0009"
down_revision: str | None = "20260830_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name, default in (
        ("documents", "workspace"),
        ("collections", "workspace"),
        ("conversations", "restricted"),
    ):
        migration_default = "workspace" if table_name == "conversations" else default
        op.add_column(
            table_name,
            sa.Column(
                "visibility",
                sa.String(length=16),
                nullable=False,
                server_default=migration_default,
            ),
        )
        op.create_check_constraint(
            f"ck_{table_name}_visibility",
            table_name,
            "visibility IN ('workspace', 'restricted')",
        )
        if table_name == "conversations":
            op.alter_column(table_name, "visibility", server_default=default)

    op.create_table(
        "resource_acl_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("principal_user_id", sa.Uuid(), nullable=False),
        sa.Column("granted_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("collection_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(CASE WHEN document_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN collection_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN conversation_id IS NULL THEN 0 ELSE 1 END) = 1",
            name="ck_resource_acl_grants_one_resource",
        ),
        sa.ForeignKeyConstraint(
            ["principal_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["document_id", "workspace_id"],
            ["documents.id", "documents.workspace_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["collection_id", "workspace_id"],
            ["collections.id", "collections.workspace_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "workspace_id"],
            ["conversations.id", "conversations.workspace_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_resource_acl_grants"),
        sa.UniqueConstraint(
            "document_id", "principal_user_id", name="uq_acl_document_principal"
        ),
        sa.UniqueConstraint(
            "collection_id", "principal_user_id", name="uq_acl_collection_principal"
        ),
        sa.UniqueConstraint(
            "conversation_id", "principal_user_id", name="uq_acl_conversation_principal"
        ),
    )
    op.create_index(
        "ix_resource_acl_grants_workspace_id", "resource_acl_grants", ["workspace_id"]
    )
    op.create_index(
        "ix_resource_acl_grants_principal_user_id",
        "resource_acl_grants",
        ["principal_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_resource_acl_grants_principal_user_id", table_name="resource_acl_grants"
    )
    op.drop_index("ix_resource_acl_grants_workspace_id", table_name="resource_acl_grants")
    op.drop_table("resource_acl_grants")
    for table_name in ("conversations", "collections", "documents"):
        op.drop_constraint(f"ck_{table_name}_visibility", table_name, type_="check")
        op.drop_column(table_name, "visibility")
