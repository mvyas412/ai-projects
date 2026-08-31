"""Add the transactional ingestion outbox.

Revision ID: 20260830_0007
Revises: 20260830_0006
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0007"
down_revision: str | None = "20260830_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingestion_outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("dispatch_sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column(
            "schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "publication_attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("lease_owner", sa.String(length=200), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publication_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discard_reason", sa.String(length=80), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('ingestion.job.available')",
            name="ck_ingestion_outbox_event_type",
        ),
        sa.CheckConstraint(
            "dispatch_sequence > 0",
            name="ck_ingestion_outbox_dispatch_sequence",
        ),
        sa.CheckConstraint(
            "schema_version > 0",
            name="ck_ingestion_outbox_schema_version",
        ),
        sa.CheckConstraint(
            "publication_attempt_count >= 0",
            name="ck_ingestion_outbox_publication_attempt_count",
        ),
        sa.CheckConstraint(
            "(lease_owner IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_ingestion_outbox_lease",
        ),
        sa.CheckConstraint(
            "publication_started_at IS NULL OR "
            "(lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_ingestion_outbox_publication_started_lease",
        ),
        sa.CheckConstraint(
            "published_at IS NULL OR discarded_at IS NULL",
            name="ck_ingestion_outbox_one_terminal_marker",
        ),
        sa.CheckConstraint(
            "(discarded_at IS NULL AND discard_reason IS NULL) OR "
            "(discarded_at IS NOT NULL AND discard_reason IS NOT NULL)",
            name="ck_ingestion_outbox_discard",
        ),
        sa.CheckConstraint(
            "(last_error_code IS NULL AND last_error_at IS NULL) OR "
            "(last_error_code IS NOT NULL AND last_error_at IS NOT NULL)",
            name="ck_ingestion_outbox_last_error",
        ),
        sa.CheckConstraint(
            "(published_at IS NULL AND discarded_at IS NULL) OR "
            "(lease_owner IS NULL AND lease_expires_at IS NULL)",
            name="ck_ingestion_outbox_terminal_lease",
        ),
        sa.ForeignKeyConstraint(
            ["job_id", "workspace_id"],
            ["ingestion_jobs.id", "ingestion_jobs.workspace_id"],
            name="fk_ingestion_outbox_job_workspace_ingestion_jobs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_outbox_events"),
        sa.UniqueConstraint(
            "job_id",
            "dispatch_sequence",
            name="uq_ingestion_outbox_job_dispatch_sequence",
        ),
    )
    op.create_index(
        "ix_ingestion_outbox_events_available_at",
        "ingestion_outbox_events",
        ["available_at"],
    )
    op.create_index(
        "ix_ingestion_outbox_events_discarded_at",
        "ingestion_outbox_events",
        ["discarded_at"],
    )
    op.create_index(
        "ix_ingestion_outbox_events_job_id",
        "ingestion_outbox_events",
        ["job_id"],
    )
    op.create_index(
        "ix_ingestion_outbox_events_lease_expires_at",
        "ingestion_outbox_events",
        ["lease_expires_at"],
    )
    op.create_index(
        "ix_ingestion_outbox_events_published_at",
        "ingestion_outbox_events",
        ["published_at"],
    )
    op.create_index(
        "ix_ingestion_outbox_events_workspace_id",
        "ingestion_outbox_events",
        ["workspace_id"],
    )
    op.create_index(
        "ix_ingestion_outbox_due",
        "ingestion_outbox_events",
        ["available_at", "created_at"],
        postgresql_where=sa.text("published_at IS NULL AND discarded_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_outbox_due", table_name="ingestion_outbox_events")
    op.drop_index(
        "ix_ingestion_outbox_events_workspace_id",
        table_name="ingestion_outbox_events",
    )
    op.drop_index(
        "ix_ingestion_outbox_events_published_at",
        table_name="ingestion_outbox_events",
    )
    op.drop_index(
        "ix_ingestion_outbox_events_lease_expires_at",
        table_name="ingestion_outbox_events",
    )
    op.drop_index(
        "ix_ingestion_outbox_events_job_id",
        table_name="ingestion_outbox_events",
    )
    op.drop_index(
        "ix_ingestion_outbox_events_discarded_at",
        table_name="ingestion_outbox_events",
    )
    op.drop_index(
        "ix_ingestion_outbox_events_available_at",
        table_name="ingestion_outbox_events",
    )
    op.drop_table("ingestion_outbox_events")
