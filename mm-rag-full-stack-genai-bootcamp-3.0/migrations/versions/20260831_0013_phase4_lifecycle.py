"""Add governed tombstones, holds, and durable deletion plans.

Revision ID: 20260831_0013
Revises: 20260831_0012
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0013"
down_revision: str | None = "20260831_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("documents", "conversations"):
        op.add_column(table, sa.Column("tombstoned_at", sa.DateTime(timezone=True)))
        op.add_column(table, sa.Column("tombstone_expires_at", sa.DateTime(timezone=True)))
        op.add_column(table, sa.Column("tombstoned_by_user_id", sa.Uuid()))
        op.create_foreign_key(
            f"fk_{table}_tombstoned_by_user_id_users",
            table,
            "users",
            ["tombstoned_by_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_check_constraint(
            f"ck_{table}_tombstone_contract",
            table,
            "(tombstoned_at IS NULL AND tombstone_expires_at IS NULL AND "
            "tombstoned_by_user_id IS NULL) OR (tombstoned_at IS NOT NULL AND "
            "tombstone_expires_at > tombstoned_at AND tombstoned_by_user_id IS NOT NULL)",
        )
        op.create_index(f"ix_{table}_tombstoned_at", table, ["tombstoned_at"])

    op.create_table(
        "lifecycle_deletion_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("resource_type", sa.String(20), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("policy_revision", sa.String(80), nullable=False),
        sa.Column("state", sa.String(20), server_default="recoverable", nullable=False),
        sa.Column("execute_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("jobs_fenced_at", sa.DateTime(timezone=True)),
        sa.Column("vectors_deleted_at", sa.DateTime(timezone=True)),
        sa.Column("artifacts_deleted_at", sa.DateTime(timezone=True)),
        sa.Column("originals_deleted_at", sa.DateTime(timezone=True)),
        sa.Column("metadata_deleted_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_vector_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("deleted_object_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error_code", sa.String(80)),
        sa.Column("last_error_message", sa.String(300)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "resource_type IN ('document', 'conversation')",
            name="ck_lifecycle_plans_resource_type",
        ),
        sa.CheckConstraint(
            "state IN ('recoverable', 'purging', 'blocked', 'completed')",
            name="ck_lifecycle_plans_state",
        ),
        sa.CheckConstraint(
            "deleted_vector_count >= 0 AND deleted_object_count >= 0",
            name="ck_lifecycle_plans_nonnegative_counts",
        ),
        sa.CheckConstraint(
            "(state = 'completed' AND completed_at IS NOT NULL AND "
            "metadata_deleted_at IS NOT NULL) OR "
            "(state != 'completed' AND completed_at IS NULL)",
            name="ck_lifecycle_plans_completion",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lifecycle_deletion_plans"),
        sa.UniqueConstraint(
            "workspace_id",
            "resource_type",
            "resource_id",
            name="uq_lifecycle_plans_resource",
        ),
    )
    op.create_index(
        "ix_lifecycle_deletion_plans_workspace_id",
        "lifecycle_deletion_plans",
        ["workspace_id"],
    )
    op.create_index(
        "ix_lifecycle_deletion_plans_resource_id",
        "lifecycle_deletion_plans",
        ["resource_id"],
    )
    op.create_index(
        "ix_lifecycle_deletion_plans_state",
        "lifecycle_deletion_plans",
        ["state"],
    )
    op.create_index(
        "ix_lifecycle_deletion_plans_execute_after",
        "lifecycle_deletion_plans",
        ["execute_after"],
    )

    op.create_table(
        "retention_holds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("resource_type", sa.String(20), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("placed_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "resource_type IN ('document', 'conversation')",
            name="ck_retention_holds_resource_type",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["placed_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_retention_holds"),
        sa.UniqueConstraint(
            "workspace_id",
            "resource_type",
            "resource_id",
            name="uq_retention_holds_resource",
        ),
    )
    op.create_index("ix_retention_holds_workspace_id", "retention_holds", ["workspace_id"])
    op.create_index("ix_retention_holds_resource_id", "retention_holds", ["resource_id"])

    op.create_table(
        "orphan_object_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("storage_class", sa.String(16), nullable=False),
        sa.Column("object_key", sa.String(1024), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "storage_class IN ('originals', 'artifacts')",
            name="ck_orphan_object_evidence_storage_class",
        ),
        sa.CheckConstraint(
            "evidence_count > 0", name="ck_orphan_object_evidence_positive_count"
        ),
        sa.CheckConstraint(
            "last_seen_at >= first_seen_at",
            name="ck_orphan_object_evidence_seen_window",
        ),
        sa.CheckConstraint(
            "byte_size >= 0", name="ck_orphan_object_evidence_nonnegative_size"
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_orphan_object_evidence"),
        sa.UniqueConstraint(
            "workspace_id",
            "storage_class",
            "object_key",
            name="uq_orphan_object_evidence_key",
        ),
    )
    op.create_index(
        "ix_orphan_object_evidence_workspace_id",
        "orphan_object_evidence",
        ["workspace_id"],
    )
    op.create_index(
        "ix_orphan_object_evidence_first_seen_at",
        "orphan_object_evidence",
        ["first_seen_at"],
    )

    if op.get_bind().dialect.name == "postgresql":
        _add_postgresql_controls()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in (
            "orphan_object_evidence",
            "retention_holds",
            "lifecycle_deletion_plans",
        ):
            op.execute(f"DROP POLICY IF EXISTS phase4_scope ON {table}")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_index(
        "ix_orphan_object_evidence_first_seen_at",
        table_name="orphan_object_evidence",
    )
    op.drop_index(
        "ix_orphan_object_evidence_workspace_id",
        table_name="orphan_object_evidence",
    )
    op.drop_table("orphan_object_evidence")
    op.drop_index("ix_retention_holds_resource_id", table_name="retention_holds")
    op.drop_index("ix_retention_holds_workspace_id", table_name="retention_holds")
    op.drop_table("retention_holds")
    for index in (
        "ix_lifecycle_deletion_plans_execute_after",
        "ix_lifecycle_deletion_plans_state",
        "ix_lifecycle_deletion_plans_resource_id",
        "ix_lifecycle_deletion_plans_workspace_id",
    ):
        op.drop_index(index, table_name="lifecycle_deletion_plans")
    op.drop_table("lifecycle_deletion_plans")
    for table in ("conversations", "documents"):
        op.drop_index(f"ix_{table}_tombstoned_at", table_name=table)
        op.drop_constraint(f"ck_{table}_tombstone_contract", table, type_="check")
        op.drop_constraint(
            f"fk_{table}_tombstoned_by_user_id_users", table, type_="foreignkey"
        )
        op.drop_column(table, "tombstoned_by_user_id")
        op.drop_column(table, "tombstone_expires_at")
        op.drop_column(table, "tombstoned_at")


def _add_postgresql_controls() -> None:
    for table in (
        "lifecycle_deletion_plans",
        "retention_holds",
        "orphan_object_evidence",
    ):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO mm_rag_api")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO mm_rag_operations")
        expression = (
            "current_setting('mm_rag.purpose', true) = 'operations' OR ("
            "workspace_id = NULLIF(current_setting('mm_rag.workspace_id', true), '')::uuid "
            "AND mm_rag_is_member(workspace_id))"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY phase4_scope ON {table} USING ({expression}) "
            f"WITH CHECK ({expression})"
        )
