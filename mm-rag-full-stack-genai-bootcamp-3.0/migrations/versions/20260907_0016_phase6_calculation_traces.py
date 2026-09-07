"""Add immutable Phase 6 exact-calculation traces.

Revision ID: 20260907_0016
Revises: 20260907_0015
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_0016"
down_revision: str | None = "20260907_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calculation_traces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("generation_id", sa.Uuid(), nullable=False),
        sa.Column("table_id", sa.Uuid(), nullable=False),
        sa.Column("region_id", sa.Uuid(), nullable=False),
        sa.Column("table_creation_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("operator", sa.String(16), nullable=False),
        sa.Column("operator_revision", sa.String(40), nullable=False),
        sa.Column("cell_ids", sa.JSON(), nullable=False),
        sa.Column("operand_types", sa.JSON(), nullable=False),
        sa.Column("operand_values", sa.JSON(), nullable=False),
        sa.Column("unit", sa.String(32)),
        sa.Column("currency", sa.String(3)),
        sa.Column("rounding_rule", sa.String(80), nullable=False),
        sa.Column("result_type", sa.String(16), nullable=False),
        sa.Column("result_value", sa.Text(), nullable=False),
        sa.Column("query_fingerprint", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "operator IN ('lookup', 'count', 'sum', 'average', 'minimum', "
            "'maximum', 'difference', 'ratio')",
            name="ck_calculation_traces_operator",
        ),
        sa.CheckConstraint(
            "length(query_fingerprint) = 64", name="ck_calculation_traces_query_hash"
        ),
        sa.ForeignKeyConstraint(
            [
                "table_id",
                "generation_id",
                "document_version_id",
                "document_id",
                "workspace_id",
                "table_creation_attempt_id",
            ],
            [
                "table_regions.id",
                "table_regions.generation_id",
                "table_regions.document_version_id",
                "table_regions.document_id",
                "table_regions.workspace_id",
                "table_regions.creation_attempt_id",
            ],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_calculation_traces"),
    )
    for column in (
        "workspace_id",
        "document_id",
        "document_version_id",
        "generation_id",
        "table_id",
        "region_id",
    ):
        op.create_index(
            f"ix_calculation_traces_{column}", "calculation_traces", [column]
        )
    if op.get_bind().dialect.name == "postgresql":
        _add_postgresql_controls()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS calculation_traces_immutable ON calculation_traces"
        )
        op.execute(
            "DROP POLICY IF EXISTS phase6_calculation_scope ON calculation_traces"
        )
        op.execute("ALTER TABLE calculation_traces DISABLE ROW LEVEL SECURITY")
    for column in reversed(
        (
            "workspace_id",
            "document_id",
            "document_version_id",
            "generation_id",
            "table_id",
            "region_id",
        )
    ):
        op.drop_index(
            f"ix_calculation_traces_{column}", table_name="calculation_traces"
        )
    op.drop_table("calculation_traces")


def _add_postgresql_controls() -> None:
    op.execute("GRANT SELECT, INSERT ON calculation_traces TO mm_rag_api")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON calculation_traces TO mm_rag_operations"
    )
    scope = (
        "current_setting('mm_rag.purpose', true) = 'operations' OR EXISTS ("
        "SELECT 1 FROM documents document WHERE "
        "document.id = calculation_traces.document_id AND "
        "document.workspace_id = calculation_traces.workspace_id)"
    )
    op.execute("ALTER TABLE calculation_traces ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY phase6_calculation_scope ON calculation_traces "
        f"USING ({scope}) WITH CHECK ({scope})"
    )
    op.execute(
        "CREATE TRIGGER calculation_traces_immutable BEFORE UPDATE OR DELETE "
        "ON calculation_traces FOR EACH ROW EXECUTE FUNCTION "
        "mm_rag_reject_phase6_provenance_mutation()"
    )
