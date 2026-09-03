"""Add immutable Phase 6 content-region and artifact provenance.

Revision ID: 20260903_0014
Revises: 20260831_0013
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0014"
down_revision: str | None = "20260831_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_ingestion_generations_region_scope",
        "ingestion_generations",
        ["id", "attempt_id", "document_version_id", "workspace_id"],
    )
    op.create_table(
        "content_regions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("generation_id", sa.Uuid(), nullable=False),
        sa.Column("creation_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("bbox_x", sa.Float(), nullable=False),
        sa.Column("bbox_y", sa.Float(), nullable=False),
        sa.Column("bbox_width", sa.Float(), nullable=False),
        sa.Column("bbox_height", sa.Float(), nullable=False),
        sa.Column("page_width", sa.Float(), nullable=False),
        sa.Column("page_height", sa.Float(), nullable=False),
        sa.Column("rotation", sa.Integer(), nullable=False),
        sa.Column("locator_schema_revision", sa.String(40), nullable=False),
        sa.Column("locator_sha256", sa.String(64), nullable=False),
        sa.Column("page_render_sha256", sa.String(64), nullable=False),
        sa.Column("extractor_name", sa.String(80), nullable=False),
        sa.Column("extractor_revision", sa.String(80), nullable=False),
        sa.Column("extractor_config_sha256", sa.String(64), nullable=False),
        sa.Column("source_caption", sa.Text()),
        sa.Column("ocr_text", sa.Text()),
        sa.Column("confidence", sa.Float()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('figure', 'chart', 'diagram', 'photo', 'table', 'other')",
            name="ck_content_regions_kind",
        ),
        sa.CheckConstraint("page_number > 0", name="ck_content_regions_page_number"),
        sa.CheckConstraint("ordinal >= 0", name="ck_content_regions_ordinal"),
        sa.CheckConstraint(
            "bbox_x >= 0 AND bbox_y >= 0 AND bbox_width > 0 AND bbox_height > 0 "
            "AND bbox_x + bbox_width <= 1.000001 "
            "AND bbox_y + bbox_height <= 1.000001",
            name="ck_content_regions_normalized_bbox",
        ),
        sa.CheckConstraint(
            "page_width > 0 AND page_height > 0",
            name="ck_content_regions_page_geometry",
        ),
        sa.CheckConstraint(
            "rotation IN (0, 90, 180, 270)", name="ck_content_regions_rotation"
        ),
        sa.CheckConstraint(
            "length(locator_sha256) = 64 AND length(page_render_sha256) = 64 "
            "AND length(extractor_config_sha256) = 64",
            name="ck_content_regions_hashes",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_content_regions_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["generation_id", "creation_attempt_id", "document_version_id", "workspace_id"],
            [
                "ingestion_generations.id",
                "ingestion_generations.attempt_id",
                "ingestion_generations.document_version_id",
                "ingestion_generations.workspace_id",
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
        sa.PrimaryKeyConstraint("id", name="pk_content_regions"),
        sa.UniqueConstraint(
            "id",
            "generation_id",
            "document_version_id",
            "workspace_id",
            "creation_attempt_id",
            name="uq_content_regions_scoped_id",
        ),
        sa.UniqueConstraint(
            "generation_id",
            "locator_sha256",
            name="uq_content_regions_generation_locator",
        ),
    )
    for column in (
        "workspace_id",
        "document_id",
        "document_version_id",
        "generation_id",
        "creation_attempt_id",
        "page_number",
        "kind",
    ):
        op.create_index(f"ix_content_regions_{column}", "content_regions", [column])

    op.create_table(
        "content_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("generation_id", sa.Uuid(), nullable=False),
        sa.Column("region_id", sa.Uuid(), nullable=False),
        sa.Column("parent_artifact_id", sa.Uuid()),
        sa.Column("creation_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("object_key", sa.String(1024), nullable=False),
        sa.Column("media_type", sa.String(120), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("pixel_width", sa.Integer()),
        sa.Column("pixel_height", sa.Integer()),
        sa.Column("producer_name", sa.String(80), nullable=False),
        sa.Column("producer_revision", sa.String(80), nullable=False),
        sa.Column("schema_revision", sa.String(80), nullable=False),
        sa.Column("prompt_revision", sa.String(80)),
        sa.Column("confidence", sa.Float()),
        sa.Column("validation_state", sa.String(24), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "kind IN ('page_render', 'region_crop', 'ocr_text', 'source_caption', "
            "'deterministic_caption', 'generated_description', 'structured_table', "
            "'normalized_json', 'normalized_csv')",
            name="ck_content_artifacts_kind",
        ),
        sa.CheckConstraint(
            "validation_state IN ('validated', 'retrieval_only', 'diagnostic', 'rejected')",
            name="ck_content_artifacts_validation_state",
        ),
        sa.CheckConstraint("byte_size > 0", name="ck_content_artifacts_byte_size"),
        sa.CheckConstraint(
            "length(content_sha256) = 64", name="ck_content_artifacts_content_hash"
        ),
        sa.CheckConstraint(
            "(pixel_width IS NULL AND pixel_height IS NULL) OR "
            "(pixel_width > 0 AND pixel_height > 0)",
            name="ck_content_artifacts_dimensions",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_content_artifacts_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["generation_id", "creation_attempt_id", "document_version_id", "workspace_id"],
            [
                "ingestion_generations.id",
                "ingestion_generations.attempt_id",
                "ingestion_generations.document_version_id",
                "ingestion_generations.workspace_id",
            ],
            ondelete="CASCADE",
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
            ["parent_artifact_id", "generation_id", "workspace_id"],
            [
                "content_artifacts.id",
                "content_artifacts.generation_id",
                "content_artifacts.workspace_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_content_artifacts"),
        sa.UniqueConstraint(
            "id", "generation_id", "workspace_id", name="uq_content_artifacts_scoped_id"
        ),
        sa.UniqueConstraint("object_key", name="uq_content_artifacts_object_key"),
        sa.UniqueConstraint(
            "region_id",
            "kind",
            "content_sha256",
            name="uq_content_artifacts_region_kind_hash",
        ),
    )
    for column in (
        "workspace_id",
        "document_id",
        "document_version_id",
        "generation_id",
        "region_id",
        "parent_artifact_id",
        "creation_attempt_id",
        "kind",
        "validation_state",
    ):
        op.create_index(f"ix_content_artifacts_{column}", "content_artifacts", [column])

    if op.get_bind().dialect.name == "postgresql":
        _add_postgresql_controls()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in ("content_artifacts", "content_regions"):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
            op.execute(f"DROP POLICY IF EXISTS phase6_scope ON {table}")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute("DROP FUNCTION IF EXISTS mm_rag_reject_phase6_provenance_mutation()")
    for column in reversed(
        (
            "workspace_id",
            "document_id",
            "document_version_id",
            "generation_id",
            "region_id",
            "parent_artifact_id",
            "creation_attempt_id",
            "kind",
            "validation_state",
        )
    ):
        op.drop_index(f"ix_content_artifacts_{column}", table_name="content_artifacts")
    op.drop_table("content_artifacts")
    for column in reversed(
        (
            "workspace_id",
            "document_id",
            "document_version_id",
            "generation_id",
            "creation_attempt_id",
            "page_number",
            "kind",
        )
    ):
        op.drop_index(f"ix_content_regions_{column}", table_name="content_regions")
    op.drop_table("content_regions")
    op.drop_constraint(
        "uq_ingestion_generations_region_scope",
        "ingestion_generations",
        type_="unique",
    )


def _add_postgresql_controls() -> None:
    op.execute("GRANT SELECT ON content_regions, content_artifacts TO mm_rag_api")
    op.execute(
        "GRANT SELECT, INSERT ON content_regions, content_artifacts TO mm_rag_worker"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON content_regions, content_artifacts "
        "TO mm_rag_operations"
    )
    for table in ("content_regions", "content_artifacts"):
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
            f"CREATE POLICY phase6_scope ON {table} "
            f"USING ({scope}) WITH CHECK ({scope})"
        )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION mm_rag_reject_phase6_provenance_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            IF current_setting('mm_rag.purpose', true) != 'operations' THEN
                RAISE EXCEPTION 'phase6 provenance is immutable';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END
        $$
        """
    )
    for table in ("content_regions", "content_artifacts"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION mm_rag_reject_phase6_provenance_mutation()"
        )
