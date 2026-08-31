"""Add the Phase 4 security-audit and compliance-export contracts.

Revision ID: 20260831_0012
Revises: 20260831_0011
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0012"
down_revision: str | None = "20260831_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("actor_kind", sa.String(16), nullable=True))
    op.add_column("audit_events", sa.Column("service_actor", sa.String(80), nullable=True))
    op.add_column("audit_events", sa.Column("result", sa.String(16), nullable=True))
    op.add_column(
        "audit_events", sa.Column("policy_revision", sa.String(80), nullable=True)
    )
    op.add_column(
        "audit_events", sa.Column("correlation_id", sa.String(128), nullable=True)
    )
    op.add_column("audit_events", sa.Column("schema_version", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE audit_events SET actor_kind = 'user', result = 'succeeded', "
        "policy_revision = 'legacy-phase3', correlation_id = 'legacy', schema_version = 1"
    )
    for column in (
        "actor_kind",
        "result",
        "policy_revision",
        "correlation_id",
        "schema_version",
    ):
        op.alter_column("audit_events", column, nullable=False)
    op.alter_column("audit_events", "actor_user_id", nullable=True)
    op.create_check_constraint(
        "ck_audit_events_actor_kind",
        "audit_events",
        "actor_kind IN ('user', 'service')",
    )
    op.create_check_constraint(
        "ck_audit_events_result",
        "audit_events",
        "result IN ('allowed', 'denied', 'succeeded', 'failed')",
    )
    op.create_check_constraint(
        "ck_audit_events_schema_version", "audit_events", "schema_version > 0"
    )
    op.create_check_constraint(
        "ck_audit_events_one_actor",
        "audit_events",
        "(actor_kind = 'user' AND actor_user_id IS NOT NULL AND service_actor IS NULL) "
        "OR (actor_kind = 'service' AND actor_user_id IS NULL "
        "AND service_actor IS NOT NULL)",
    )
    op.create_index("ix_audit_events_actor_kind", "audit_events", ["actor_kind"])
    op.create_index("ix_audit_events_service_actor", "audit_events", ["service_actor"])
    op.create_index("ix_audit_events_result", "audit_events", ["result"])
    op.create_index("ix_audit_events_correlation_id", "audit_events", ["correlation_id"])

    op.create_table(
        "compliance_exports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("range_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("range_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.String(1024), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('ready', 'failed')", name="ck_compliance_exports_status"
        ),
        sa.CheckConstraint(
            "schema_version > 0", name="ck_compliance_exports_schema_version"
        ),
        sa.CheckConstraint(
            "event_count >= 0", name="ck_compliance_exports_event_count"
        ),
        sa.CheckConstraint("byte_size > 0", name="ck_compliance_exports_byte_size"),
        sa.CheckConstraint(
            "length(content_sha256) = 64", name="ck_compliance_exports_content_hash"
        ),
        sa.CheckConstraint(
            "range_start < range_end", name="ck_compliance_exports_range"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_compliance_exports"),
        sa.UniqueConstraint("object_key", name="uq_compliance_exports_object_key"),
        sa.UniqueConstraint(
            "workspace_id",
            "range_start",
            "range_end",
            "schema_version",
            name="uq_compliance_exports_range_schema",
        ),
    )
    op.create_index(
        "ix_compliance_exports_workspace_id", "compliance_exports", ["workspace_id"]
    )
    op.create_index(
        "ix_compliance_exports_created_at", "compliance_exports", ["created_at"]
    )

    if op.get_bind().dialect.name == "postgresql":
        _add_postgresql_controls()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON audit_events")
        op.execute("DROP FUNCTION IF EXISTS mm_rag_reject_audit_mutation()")
        op.execute("DROP POLICY IF EXISTS phase4_scope ON compliance_exports")
        op.execute("ALTER TABLE compliance_exports DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_compliance_exports_created_at", table_name="compliance_exports")
    op.drop_index("ix_compliance_exports_workspace_id", table_name="compliance_exports")
    op.drop_table("compliance_exports")

    op.execute(
        "UPDATE audit_events SET actor_user_id = ("
        "SELECT created_by_user_id FROM workspaces "
        "WHERE workspaces.id = audit_events.workspace_id) "
        "WHERE actor_user_id IS NULL"
    )
    op.drop_index("ix_audit_events_correlation_id", table_name="audit_events")
    op.drop_index("ix_audit_events_result", table_name="audit_events")
    op.drop_index("ix_audit_events_service_actor", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_kind", table_name="audit_events")
    op.drop_constraint("ck_audit_events_one_actor", "audit_events", type_="check")
    op.drop_constraint("ck_audit_events_schema_version", "audit_events", type_="check")
    op.drop_constraint("ck_audit_events_result", "audit_events", type_="check")
    op.drop_constraint("ck_audit_events_actor_kind", "audit_events", type_="check")
    op.alter_column("audit_events", "actor_user_id", nullable=False)
    for column in (
        "schema_version",
        "correlation_id",
        "policy_revision",
        "result",
        "service_actor",
        "actor_kind",
    ):
        op.drop_column("audit_events", column)


def _add_postgresql_controls() -> None:
    op.execute(
        "GRANT SELECT, INSERT ON compliance_exports TO mm_rag_api"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON compliance_exports TO mm_rag_operations"
    )
    scope = (
        "current_setting('mm_rag.purpose', true) = 'operations' OR ("
        "workspace_id = NULLIF(current_setting('mm_rag.workspace_id', true), '')::uuid "
        "AND mm_rag_is_member(workspace_id))"
    )
    op.execute("ALTER TABLE compliance_exports ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY phase4_scope ON compliance_exports "
        f"USING ({scope}) WITH CHECK ({scope})"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION mm_rag_reject_audit_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            IF current_user IN ('mm_rag_api', 'mm_rag_worker', 'mm_rag_dispatcher') THEN
                RAISE EXCEPTION 'audit events are append-only';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION mm_rag_reject_audit_mutation()"
    )
