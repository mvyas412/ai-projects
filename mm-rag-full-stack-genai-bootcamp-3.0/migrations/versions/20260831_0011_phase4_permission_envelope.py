"""Add the Phase 4 future connector permission-envelope contract.

Revision ID: 20260831_0011
Revises: 20260831_0010
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0011"
down_revision: str | None = "20260831_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_permission_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("source_namespace", sa.String(length=80), nullable=False),
        sa.Column("source_item_ref_hash", sa.String(length=64), nullable=False),
        sa.Column("sync_revision", sa.String(length=160), nullable=False),
        sa.Column("permission_revision", sa.String(length=160), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("permission_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("unresolved_principal_count", sa.Integer(), nullable=False),
        sa.Column("semantics_supported", sa.Boolean(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "schema_version > 0", name="ck_source_permissions_schema_version"
        ),
        sa.CheckConstraint(
            "length(source_item_ref_hash) = 64", name="ck_source_permissions_item_hash"
        ),
        sa.CheckConstraint(
            "length(permission_fingerprint) = 64",
            name="ck_source_permissions_fingerprint",
        ),
        sa.CheckConstraint(
            "unresolved_principal_count >= 0",
            name="ck_source_permissions_unresolved_count",
        ),
        sa.CheckConstraint(
            "verified_at < valid_until", name="ck_source_permissions_valid_window"
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id", "document_id", "workspace_id"],
            [
                "document_versions.id",
                "document_versions.document_id",
                "document_versions.workspace_id",
            ],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_source_permission_snapshots"),
        sa.UniqueConstraint(
            "workspace_id",
            "source_namespace",
            "source_item_ref_hash",
            "sync_revision",
            "permission_revision",
            name="uq_source_permissions_revision",
        ),
        sa.UniqueConstraint(
            "id", "workspace_id", name="uq_source_permission_snapshot_workspace"
        ),
    )
    op.create_index(
        "ix_source_permission_snapshots_workspace_id",
        "source_permission_snapshots",
        ["workspace_id"],
    )
    op.create_index(
        "ix_source_permission_snapshots_document_id",
        "source_permission_snapshots",
        ["document_id"],
    )
    op.create_index(
        "ix_source_permission_snapshots_document_version_id",
        "source_permission_snapshots",
        ["document_version_id"],
    )
    op.create_table(
        "source_permission_principals",
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("principal_user_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["principal_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "workspace_id"],
            ["source_permission_snapshots.id", "source_permission_snapshots.workspace_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "snapshot_id", "principal_user_id", name="pk_source_permission_principals"
        ),
    )
    op.create_index(
        "ix_source_permission_principals_workspace_id",
        "source_permission_principals",
        ["workspace_id"],
    )

    if op.get_bind().dialect.name == "postgresql":
        _add_postgresql_policy()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in ("source_permission_principals", "source_permission_snapshots"):
            op.execute(f"DROP POLICY IF EXISTS phase4_scope ON {table}")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_index(
        "ix_source_permission_principals_workspace_id",
        table_name="source_permission_principals",
    )
    op.drop_table("source_permission_principals")
    op.drop_index(
        "ix_source_permission_snapshots_document_version_id",
        table_name="source_permission_snapshots",
    )
    op.drop_index(
        "ix_source_permission_snapshots_document_id",
        table_name="source_permission_snapshots",
    )
    op.drop_index(
        "ix_source_permission_snapshots_workspace_id",
        table_name="source_permission_snapshots",
    )
    op.drop_table("source_permission_snapshots")


def _add_postgresql_policy() -> None:
    op.execute(
        "GRANT SELECT, INSERT ON source_permission_snapshots, "
        "source_permission_principals TO mm_rag_api"
    )
    op.execute(
        "GRANT SELECT ON source_permission_snapshots, source_permission_principals "
        "TO mm_rag_worker"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON source_permission_snapshots, "
        "source_permission_principals TO mm_rag_operations"
    )
    snapshot_scope = (
        "current_setting('mm_rag.purpose', true) = 'operations' OR ("
        "current_setting('mm_rag.purpose', true) = 'worker' AND workspace_id = "
        "NULLIF(current_setting('mm_rag.workspace_id', true), '')::uuid) OR EXISTS ("
        "SELECT 1 FROM documents parent_row "
        "WHERE parent_row.id = source_permission_snapshots.document_id "
        "AND parent_row.workspace_id = source_permission_snapshots.workspace_id)"
    )
    op.execute("ALTER TABLE source_permission_snapshots ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY phase4_scope ON source_permission_snapshots "
        f"USING ({snapshot_scope}) WITH CHECK ({snapshot_scope})"
    )
    principal_scope = (
        "current_setting('mm_rag.purpose', true) = 'operations' OR ("
        "current_setting('mm_rag.purpose', true) = 'worker' AND workspace_id = "
        "NULLIF(current_setting('mm_rag.workspace_id', true), '')::uuid) OR ("
        "EXISTS (SELECT 1 FROM source_permission_snapshots snapshot "
        "WHERE snapshot.id = source_permission_principals.snapshot_id "
        "AND snapshot.workspace_id = source_permission_principals.workspace_id) AND "
        "EXISTS (SELECT 1 FROM workspace_memberships membership "
        "WHERE membership.workspace_id = source_permission_principals.workspace_id "
        "AND membership.user_id = source_permission_principals.principal_user_id))"
    )
    op.execute("ALTER TABLE source_permission_principals ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY phase4_scope ON source_permission_principals "
        f"USING ({principal_scope}) WITH CHECK ({principal_scope})"
    )
