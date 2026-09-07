"""Add governed Phase 7 answer feedback.

Revision ID: 20260907_0018
Revises: 20260907_0017
Create Date: 2026-09-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_0018"
down_revision: str | None = "20260907_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("conversation_messages") as batch:
        batch.create_unique_constraint(
            "uq_conversation_messages_feedback_identity",
            ["id", "conversation_id", "workspace_id"],
        )
    op.create_table(
        "answer_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("assistant_message_id", sa.Uuid(), nullable=False),
        sa.Column("submitter_user_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("comment_consent", sa.Boolean(), nullable=False),
        sa.Column("snapshot_consent", sa.Boolean(), nullable=False),
        sa.Column("diagnostic_snapshot", sa.JSON(none_as_null=True)),
        sa.Column("consent_policy_revision", sa.String(64), nullable=False),
        sa.Column("review_status", sa.String(16), nullable=False),
        sa.Column("reviewer_user_id", sa.Uuid()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("promoted_case_id", sa.String(80)),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("rating IN (-1, 1)", name="ck_answer_feedback_rating"),
        sa.CheckConstraint(
            "reason IN ('helpful', 'incorrect', 'incomplete', 'unsupported', "
            "'citation_issue', 'unsafe', 'other')",
            name="ck_answer_feedback_reason",
        ),
        sa.CheckConstraint(
            "review_status IN ('pending', 'reviewed', 'dismissed', 'promoted')",
            name="ck_answer_feedback_review_status",
        ),
        sa.CheckConstraint(
            "(comment IS NULL AND comment_consent = false) OR "
            "(comment IS NOT NULL AND comment_consent = true)",
            name="ck_answer_feedback_comment_consent",
        ),
        sa.CheckConstraint(
            "(diagnostic_snapshot IS NULL AND snapshot_consent = false) OR "
            "(diagnostic_snapshot IS NOT NULL AND snapshot_consent = true)",
            name="ck_answer_feedback_snapshot_consent",
        ),
        sa.CheckConstraint(
            "(review_status = 'pending' AND reviewer_user_id IS NULL AND reviewed_at IS NULL) "
            "OR (review_status != 'pending' AND reviewer_user_id IS NOT NULL "
            "AND reviewed_at IS NOT NULL)",
            name="ck_answer_feedback_review_contract",
        ),
        sa.CheckConstraint(
            "(review_status = 'promoted' AND promoted_case_id IS NOT NULL) OR "
            "(review_status != 'promoted' AND promoted_case_id IS NULL)",
            name="ck_answer_feedback_promotion_contract",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "workspace_id"],
            ["conversations.id", "conversations.workspace_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assistant_message_id", "conversation_id", "workspace_id"],
            [
                "conversation_messages.id",
                "conversation_messages.conversation_id",
                "conversation_messages.workspace_id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["submitter_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_answer_feedback"),
        sa.UniqueConstraint(
            "assistant_message_id",
            "submitter_user_id",
            name="uq_answer_feedback_message_submitter",
        ),
    )
    for column in (
        "workspace_id",
        "conversation_id",
        "assistant_message_id",
        "submitter_user_id",
        "retention_expires_at",
        "review_status",
    ):
        op.create_index(f"ix_answer_feedback_{column}", "answer_feedback", [column])
    if op.get_bind().dialect.name == "postgresql":
        _add_postgresql_controls()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for policy in (
            "phase7_feedback_operations",
            "phase7_feedback_update",
            "phase7_feedback_insert",
            "phase7_feedback_select",
        ):
            op.execute(f"DROP POLICY IF EXISTS {policy} ON answer_feedback")
        op.execute("ALTER TABLE answer_feedback DISABLE ROW LEVEL SECURITY")
        op.execute("DROP FUNCTION IF EXISTS mm_rag_is_workspace_admin(uuid)")
    for column in reversed(
        (
            "workspace_id",
            "conversation_id",
            "assistant_message_id",
            "submitter_user_id",
            "retention_expires_at",
            "review_status",
        )
    ):
        op.drop_index(f"ix_answer_feedback_{column}", table_name="answer_feedback")
    op.drop_table("answer_feedback")
    with op.batch_alter_table("conversation_messages") as batch:
        batch.drop_constraint("uq_conversation_messages_feedback_identity", type_="unique")


def _add_postgresql_controls() -> None:
    op.execute("GRANT SELECT, INSERT, UPDATE ON answer_feedback TO mm_rag_api")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON answer_feedback TO mm_rag_operations")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION mm_rag_is_workspace_admin(target_workspace uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM public.workspace_memberships membership
                WHERE membership.workspace_id = target_workspace
                  AND membership.user_id = NULLIF(
                      current_setting('mm_rag.principal_id', true), ''
                  )::uuid
                  AND membership.role IN ('owner', 'admin')
            )
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION mm_rag_is_workspace_admin(uuid) FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION mm_rag_is_workspace_admin(uuid) TO mm_rag_api, mm_rag_operations"
    )
    principal = "NULLIF(current_setting('mm_rag.principal_id', true), '')::uuid"
    workspace = "NULLIF(current_setting('mm_rag.workspace_id', true), '')::uuid"
    member_scope = f"workspace_id = {workspace} AND mm_rag_is_member(workspace_id)"
    review_scope = "mm_rag_is_workspace_admin(workspace_id)"
    submitter_scope = f"submitter_user_id = {principal}"
    op.execute("ALTER TABLE answer_feedback ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY phase7_feedback_select ON answer_feedback FOR SELECT "
        f"USING ({member_scope} AND ({submitter_scope} OR {review_scope}))"
    )
    op.execute(
        "CREATE POLICY phase7_feedback_insert ON answer_feedback FOR INSERT "
        f"WITH CHECK ({member_scope} AND {submitter_scope} AND review_status = 'pending')"
    )
    op.execute(
        "CREATE POLICY phase7_feedback_update ON answer_feedback FOR UPDATE "
        f"USING ({member_scope} AND ({submitter_scope} OR {review_scope})) "
        f"WITH CHECK ({member_scope} AND ({submitter_scope} OR {review_scope}))"
    )
    op.execute(
        "CREATE POLICY phase7_feedback_operations ON answer_feedback FOR ALL "
        "USING (current_setting('mm_rag.purpose', true) = 'operations') "
        "WITH CHECK (current_setting('mm_rag.purpose', true) = 'operations')"
    )
