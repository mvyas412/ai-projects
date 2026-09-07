"""Add immutable normalized Phase 6 table structure.

Revision ID: 20260907_0015
Revises: 20260903_0014
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_0015"
down_revision: str | None = "20260903_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "table_regions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("generation_id", sa.Uuid(), nullable=False),
        sa.Column("region_id", sa.Uuid(), nullable=False),
        sa.Column("creation_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("source_crop_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("normalized_artifact_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("header_row_count", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("structure_schema_revision", sa.String(40), nullable=False),
        sa.Column("structure_sha256", sa.String(64), nullable=False),
        sa.Column("extractor_name", sa.String(80), nullable=False),
        sa.Column("extractor_revision", sa.String(80), nullable=False),
        sa.Column("validation_state", sa.String(24), nullable=False),
        sa.Column("validation_codes", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("page_number > 0", name="ck_table_regions_page_number"),
        sa.CheckConstraint(
            "row_count > 0 AND column_count > 0 AND header_row_count >= 0 "
            "AND header_row_count <= row_count",
            name="ck_table_regions_dimensions",
        ),
        sa.CheckConstraint(
            "validation_state IN ('validated', 'retrieval_only', 'rejected')",
            name="ck_table_regions_validation_state",
        ),
        sa.CheckConstraint(
            "length(structure_sha256) = 64", name="ck_table_regions_structure_hash"
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_table_regions_confidence",
        ),
        sa.ForeignKeyConstraint(
            [
                "region_id",
                "generation_id",
                "document_version_id",
                "workspace_id",
                "creation_attempt_id",
            ],
            [
                "content_regions.id",
                "content_regions.generation_id",
                "content_regions.document_version_id",
                "content_regions.workspace_id",
                "content_regions.creation_attempt_id",
            ],
            ondelete="CASCADE",
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
        sa.ForeignKeyConstraint(
            ["source_crop_artifact_id", "generation_id", "workspace_id"],
            [
                "content_artifacts.id",
                "content_artifacts.generation_id",
                "content_artifacts.workspace_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["normalized_artifact_id", "generation_id", "workspace_id"],
            [
                "content_artifacts.id",
                "content_artifacts.generation_id",
                "content_artifacts.workspace_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_table_regions"),
        sa.UniqueConstraint("region_id", name="uq_table_regions_region_id"),
        sa.UniqueConstraint(
            "id",
            "generation_id",
            "document_version_id",
            "document_id",
            "workspace_id",
            "creation_attempt_id",
            name="uq_table_regions_scoped_id",
        ),
    )
    _create_indexes(
        "table_regions",
        (
            "workspace_id",
            "document_id",
            "document_version_id",
            "generation_id",
            "region_id",
            "creation_attempt_id",
            "validation_state",
        ),
    )

    table_scope = (
        [
            "table_id",
            "generation_id",
            "document_version_id",
            "document_id",
            "workspace_id",
            "creation_attempt_id",
        ],
        [
            "table_regions.id",
            "table_regions.generation_id",
            "table_regions.document_version_id",
            "table_regions.document_id",
            "table_regions.workspace_id",
            "table_regions.creation_attempt_id",
        ],
    )
    op.create_table(
        "table_columns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("generation_id", sa.Uuid(), nullable=False),
        sa.Column("creation_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("table_id", sa.Uuid(), nullable=False),
        sa.Column("column_index", sa.Integer(), nullable=False),
        sa.Column("raw_header", sa.Text(), nullable=False),
        sa.Column("normalized_header", sa.Text(), nullable=False),
        sa.Column("logical_type", sa.String(16), nullable=False),
        sa.Column("unit", sa.String(32)),
        sa.Column("currency", sa.String(3)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("column_index >= 0", name="ck_table_columns_index"),
        sa.CheckConstraint(
            "logical_type IN ('text', 'integer', 'decimal', 'percentage', 'currency', 'date')",
            name="ck_table_columns_logical_type",
        ),
        sa.ForeignKeyConstraint(*table_scope, ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_table_columns"),
        sa.UniqueConstraint("table_id", "column_index", name="uq_table_columns_position"),
    )
    _create_indexes(
        "table_columns",
        ("workspace_id", "document_id", "document_version_id", "generation_id", "table_id"),
    )

    op.create_table(
        "table_cells",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("generation_id", sa.Uuid(), nullable=False),
        sa.Column("creation_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("table_id", sa.Uuid(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("column_index", sa.Integer(), nullable=False),
        sa.Column("row_span", sa.Integer(), nullable=False),
        sa.Column("column_span", sa.Integer(), nullable=False),
        sa.Column("is_header", sa.Boolean(), nullable=False),
        sa.Column("header_associations", sa.JSON(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("logical_type", sa.String(16), nullable=False),
        sa.Column("normalized_value", sa.Text()),
        sa.Column("unit", sa.String(32)),
        sa.Column("currency", sa.String(3)),
        sa.Column("bbox_x", sa.Float()),
        sa.Column("bbox_y", sa.Float()),
        sa.Column("bbox_width", sa.Float()),
        sa.Column("bbox_height", sa.Float()),
        sa.Column("confidence", sa.Float()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "row_index >= 0 AND column_index >= 0", name="ck_table_cells_position"
        ),
        sa.CheckConstraint(
            "row_span > 0 AND column_span > 0", name="ck_table_cells_span"
        ),
        sa.CheckConstraint(
            "logical_type IN ('text', 'integer', 'decimal', 'percentage', 'currency', 'date')",
            name="ck_table_cells_logical_type",
        ),
        sa.CheckConstraint(
            "(bbox_x IS NULL AND bbox_y IS NULL AND bbox_width IS NULL AND bbox_height IS NULL) "
            "OR (bbox_x >= 0 AND bbox_y >= 0 AND bbox_width > 0 AND bbox_height > 0 "
            "AND bbox_x + bbox_width <= 1.000001 "
            "AND bbox_y + bbox_height <= 1.000001)",
            name="ck_table_cells_bbox",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_table_cells_confidence",
        ),
        sa.ForeignKeyConstraint(*table_scope, ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_table_cells"),
        sa.UniqueConstraint(
            "table_id", "row_index", "column_index", name="uq_table_cells_position"
        ),
    )
    _create_indexes(
        "table_cells",
        ("workspace_id", "document_id", "document_version_id", "generation_id", "table_id"),
    )
    if op.get_bind().dialect.name == "postgresql":
        _add_postgresql_controls()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in ("table_cells", "table_columns", "table_regions"):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
            op.execute(f"DROP POLICY IF EXISTS phase6_table_scope ON {table}")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for table, columns in (
        (
            "table_cells",
            ("workspace_id", "document_id", "document_version_id", "generation_id", "table_id"),
        ),
        (
            "table_columns",
            ("workspace_id", "document_id", "document_version_id", "generation_id", "table_id"),
        ),
        (
            "table_regions",
            (
                "workspace_id",
                "document_id",
                "document_version_id",
                "generation_id",
                "region_id",
                "creation_attempt_id",
                "validation_state",
            ),
        ),
    ):
        for column in reversed(columns):
            op.drop_index(f"ix_{table}_{column}", table_name=table)
        op.drop_table(table)


def _create_indexes(table: str, columns: tuple[str, ...]) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])


def _add_postgresql_controls() -> None:
    tables = "table_regions, table_columns, table_cells"
    op.execute(f"GRANT SELECT ON {tables} TO mm_rag_api")
    op.execute(f"GRANT SELECT, INSERT ON {tables} TO mm_rag_worker")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tables} TO mm_rag_operations")
    for table in ("table_regions", "table_columns", "table_cells"):
        scope = (
            "current_setting('mm_rag.purpose', true) = 'operations' OR ("
            "current_setting('mm_rag.purpose', true) = 'worker' AND "
            f"{table}.workspace_id = NULLIF("
            "current_setting('mm_rag.workspace_id', true), '')::uuid AND EXISTS ("
            "SELECT 1 FROM ingestion_generations generation WHERE "
            f"generation.id = {table}.generation_id AND generation.job_id = NULLIF("
            "current_setting('mm_rag.job_id', true), '')::uuid)) OR EXISTS ("
            "SELECT 1 FROM documents document WHERE "
            f"document.id = {table}.document_id AND "
            f"document.workspace_id = {table}.workspace_id)"
        )
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY phase6_table_scope ON {table} "
            f"USING ({scope}) WITH CHECK ({scope})"
        )
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION mm_rag_reject_phase6_provenance_mutation()"
        )
