"""Add durable ingestion jobs and fenced execution attempts.

Revision ID: 20260830_0006
Revises: 20260830_0005
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260830_0006"
down_revision: str | None = "20260830_0005"
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
    op.create_unique_constraint(
        "uq_document_versions_id_document_workspace",
        "document_versions",
        ["id", "document_id", "workspace_id"],
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("predecessor_job_id", sa.Uuid(), nullable=True),
        sa.Column("operation", sa.String(length=40), nullable=False),
        sa.Column("pipeline_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "state",
            sa.String(length=24),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("first_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("last_error_message", sa.String(length=500), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "operation IN ('index_document_version')",
            name="ck_ingestion_jobs_operation",
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'queued', 'running', 'retry_scheduled', "
            "'succeeded', 'failed', 'cancelled')",
            name="ck_ingestion_jobs_state",
        ),
        sa.CheckConstraint(
            "length(pipeline_fingerprint) = 64", name="ck_jobs_pipeline_hash"
        ),
        sa.CheckConstraint("length(request_hash) = 64", name="ck_jobs_request_hash"),
        sa.CheckConstraint("length(idempotency_key) > 0", name="ck_jobs_idempotency_key"),
        sa.CheckConstraint("revision > 0", name="ck_ingestion_jobs_revision"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_ingestion_jobs_attempt_count"),
        sa.CheckConstraint("max_attempts > 0", name="ck_ingestion_jobs_max_attempts"),
        sa.CheckConstraint(
            "attempt_count <= max_attempts", name="ck_ingestion_jobs_attempt_budget"
        ),
        sa.CheckConstraint("fencing_token >= 0", name="ck_ingestion_jobs_fencing_token"),
        sa.CheckConstraint(
            "(state = 'retry_scheduled' AND next_attempt_at IS NOT NULL) OR "
            "(state != 'retry_scheduled' AND next_attempt_at IS NULL)",
            name="ck_ingestion_jobs_retry_schedule",
        ),
        sa.CheckConstraint(
            "(state IN ('succeeded', 'failed', 'cancelled') AND completed_at IS NOT NULL) "
            "OR (state NOT IN ('succeeded', 'failed', 'cancelled') "
            "AND completed_at IS NULL)",
            name="ck_ingestion_jobs_terminal_timestamp",
        ),
        sa.CheckConstraint(
            "(cancel_requested_at IS NULL AND cancel_requested_by_user_id IS NULL) OR "
            "(cancel_requested_at IS NOT NULL AND cancel_requested_by_user_id IS NOT NULL)",
            name="ck_ingestion_jobs_cancel_request",
        ),
        sa.ForeignKeyConstraint(
            ["cancel_requested_by_user_id"],
            ["users.id"],
            name="fk_ingestion_jobs_cancel_requested_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id", "document_id", "workspace_id"],
            ["document_versions.id", "document_versions.document_id", "document_versions.workspace_id"],
            name="fk_ingestion_jobs_document_version_workspace_document_versions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["predecessor_job_id", "workspace_id"],
            ["ingestion_jobs.id", "ingestion_jobs.workspace_id"],
            name="fk_ingestion_jobs_predecessor_workspace_ingestion_jobs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            name="fk_ingestion_jobs_requested_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_jobs"),
        sa.UniqueConstraint("id", "workspace_id", name="uq_ingestion_jobs_id_workspace_id"),
        sa.UniqueConstraint(
            "workspace_id",
            "operation",
            "idempotency_key",
            name="uq_ingestion_jobs_workspace_operation_idempotency",
        ),
    )
    op.create_index("ix_ingestion_jobs_document_id", "ingestion_jobs", ["document_id"])
    op.create_index(
        "ix_ingestion_jobs_document_version_id",
        "ingestion_jobs",
        ["document_version_id"],
    )
    op.create_index(
        "ix_ingestion_jobs_next_attempt_at", "ingestion_jobs", ["next_attempt_at"]
    )
    op.create_index(
        "ix_ingestion_jobs_requested_by_user_id",
        "ingestion_jobs",
        ["requested_by_user_id"],
    )
    op.create_index("ix_ingestion_jobs_state", "ingestion_jobs", ["state"])
    op.create_index("ix_ingestion_jobs_workspace_id", "ingestion_jobs", ["workspace_id"])

    op.create_table(
        "ingestion_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column(
            "state",
            sa.String(length=24),
            server_default=sa.text("'running'"),
            nullable=False,
        ),
        sa.Column("worker_id", sa.String(length=200), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("progress_stage", sa.String(length=40), nullable=True),
        sa.Column("progress_completed", sa.BigInteger(), nullable=True),
        sa.Column("progress_total", sa.BigInteger(), nullable=True),
        sa.Column("progress_unit", sa.String(length=24), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "state IN ('running', 'succeeded', 'retryable_failure', "
            "'permanent_failure', 'cancelled', 'lease_expired')",
            name="ck_ingestion_attempts_state",
        ),
        sa.CheckConstraint("attempt_number > 0", name="ck_ingestion_attempts_number"),
        sa.CheckConstraint("fencing_token > 0", name="ck_ingestion_attempts_fencing_token"),
        sa.CheckConstraint(
            "progress_completed IS NULL OR progress_completed >= 0",
            name="ck_ingestion_attempts_progress_completed",
        ),
        sa.CheckConstraint(
            "progress_total IS NULL OR progress_total > 0",
            name="ck_ingestion_attempts_progress_total",
        ),
        sa.CheckConstraint(
            "progress_completed IS NULL OR progress_total IS NULL "
            "OR progress_completed <= progress_total",
            name="ck_ingestion_attempts_progress_bounds",
        ),
        sa.CheckConstraint(
            "(state = 'running' AND finished_at IS NULL) OR "
            "(state != 'running' AND finished_at IS NOT NULL)",
            name="ck_ingestion_attempts_finished_timestamp",
        ),
        sa.ForeignKeyConstraint(
            ["job_id", "workspace_id"],
            ["ingestion_jobs.id", "ingestion_jobs.workspace_id"],
            name="fk_ingestion_attempts_job_workspace_ingestion_jobs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_attempts"),
        sa.UniqueConstraint(
            "job_id", "fencing_token", name="uq_ingestion_attempts_job_fencing_token"
        ),
        sa.UniqueConstraint(
            "job_id", "attempt_number", name="uq_ingestion_attempts_job_number"
        ),
    )
    op.create_index(
        "ix_ingestion_attempts_job_id", "ingestion_attempts", ["job_id"]
    )
    op.create_index(
        "ix_ingestion_attempts_lease_expires_at",
        "ingestion_attempts",
        ["lease_expires_at"],
    )
    op.create_index("ix_ingestion_attempts_state", "ingestion_attempts", ["state"])
    op.create_index(
        "ix_ingestion_attempts_workspace_id", "ingestion_attempts", ["workspace_id"]
    )
    op.create_index(
        "uq_ingestion_attempts_one_running_job",
        "ingestion_attempts",
        ["job_id"],
        unique=True,
        postgresql_where=sa.text("state = 'running'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_ingestion_attempts_one_running_job", table_name="ingestion_attempts"
    )
    op.drop_index("ix_ingestion_attempts_workspace_id", table_name="ingestion_attempts")
    op.drop_index("ix_ingestion_attempts_state", table_name="ingestion_attempts")
    op.drop_index(
        "ix_ingestion_attempts_lease_expires_at", table_name="ingestion_attempts"
    )
    op.drop_index("ix_ingestion_attempts_job_id", table_name="ingestion_attempts")
    op.drop_table("ingestion_attempts")
    op.drop_index("ix_ingestion_jobs_workspace_id", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_state", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_requested_by_user_id", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_next_attempt_at", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_document_version_id", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_document_id", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_constraint(
        "uq_document_versions_id_document_workspace",
        "document_versions",
        type_="unique",
    )
