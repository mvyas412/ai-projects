"""Add immutable ingestion generations and active-version promotion.

Revision ID: 20260830_0008
Revises: 20260830_0007
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0008"
down_revision: str | None = "20260830_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_generations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("pipeline_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=24), server_default="building", nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=True),
        sa.Column("manifest_object_key", sa.String(length=1024), nullable=True),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=True),
        sa.Column("chunk_count", sa.BigInteger(), nullable=True),
        sa.Column("vector_count", sa.BigInteger(), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("abandoned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "state IN ('building', 'validated', 'promoted', 'abandoned')",
            name="ck_ingestion_generations_state",
        ),
        sa.CheckConstraint(
            "length(pipeline_fingerprint) = 64",
            name="ck_ingestion_generations_pipeline_hash",
        ),
        sa.CheckConstraint(
            "chunk_count IS NULL OR chunk_count >= 0",
            name="ck_ingestion_generations_chunk_count",
        ),
        sa.CheckConstraint(
            "vector_count IS NULL OR vector_count >= 0",
            name="ck_ingestion_generations_vector_count",
        ),
        sa.CheckConstraint(
            "(manifest_object_key IS NULL AND manifest_sha256 IS NULL) OR "
            "(manifest_object_key IS NOT NULL AND manifest_sha256 IS NOT NULL)",
            name="ck_ingestion_generations_manifest_identity",
        ),
        sa.CheckConstraint(
            "state != 'promoted' OR (validated_at IS NOT NULL AND promoted_at IS NOT NULL)",
            name="ck_ingestion_generations_active_timestamps",
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id"], ["ingestion_attempts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["job_id", "workspace_id"],
            ["ingestion_jobs.id", "ingestion_jobs.workspace_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id", "document_id", "workspace_id"],
            ["document_versions.id", "document_versions.document_id", "document_versions.workspace_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_generations"),
        sa.UniqueConstraint(
            "id",
            "document_version_id",
            "workspace_id",
            name="uq_ingestion_generations_id_version_workspace",
        ),
        sa.UniqueConstraint("attempt_id", name="uq_ingestion_generations_attempt_id"),
    )
    for column in (
        "workspace_id",
        "document_id",
        "document_version_id",
        "job_id",
        "attempt_id",
        "state",
    ):
        op.create_index(f"ix_ingestion_generations_{column}", "ingestion_generations", [column])

    op.add_column("document_versions", sa.Column("active_generation_id", sa.Uuid(), nullable=True))
    op.add_column(
        "document_versions",
        sa.Column("active_generation_promoted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_document_versions_active_generation_id",
        "document_versions",
        ["active_generation_id"],
    )
    op.create_foreign_key(
        "fk_document_versions_active_generation",
        "document_versions",
        "ingestion_generations",
        ["active_generation_id", "id", "workspace_id"],
        ["id", "document_version_id", "workspace_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_document_versions_active_generation",
        "document_versions",
        type_="foreignkey",
    )
    op.drop_index("ix_document_versions_active_generation_id", table_name="document_versions")
    op.drop_column("document_versions", "active_generation_promoted_at")
    op.drop_column("document_versions", "active_generation_id")
    for column in reversed(
        ("workspace_id", "document_id", "document_version_id", "job_id", "attempt_id", "state")
    ):
        op.drop_index(f"ix_ingestion_generations_{column}", table_name="ingestion_generations")
    op.drop_table("ingestion_generations")
