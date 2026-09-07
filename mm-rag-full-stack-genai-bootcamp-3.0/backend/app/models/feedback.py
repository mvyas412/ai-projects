from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.mixins import TimestampMixin


class FeedbackReason(StrEnum):
    HELPFUL = "helpful"
    INCORRECT = "incorrect"
    INCOMPLETE = "incomplete"
    UNSUPPORTED = "unsupported"
    CITATION_ISSUE = "citation_issue"
    UNSAFE = "unsafe"
    OTHER = "other"


class FeedbackReviewStatus(StrEnum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"
    PROMOTED = "promoted"


class AnswerFeedback(TimestampMixin, Base):
    __tablename__ = "answer_feedback"
    __table_args__ = (
        CheckConstraint("rating IN (-1, 1)", name="ck_answer_feedback_rating"),
        CheckConstraint(
            "reason IN ('helpful', 'incorrect', 'incomplete', 'unsupported', "
            "'citation_issue', 'unsafe', 'other')",
            name="ck_answer_feedback_reason",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'reviewed', 'dismissed', 'promoted')",
            name="ck_answer_feedback_review_status",
        ),
        CheckConstraint(
            "(comment IS NULL AND comment_consent = false) OR "
            "(comment IS NOT NULL AND comment_consent = true)",
            name="ck_answer_feedback_comment_consent",
        ),
        CheckConstraint(
            "(diagnostic_snapshot IS NULL AND snapshot_consent = false) OR "
            "(diagnostic_snapshot IS NOT NULL AND snapshot_consent = true)",
            name="ck_answer_feedback_snapshot_consent",
        ),
        CheckConstraint(
            "(review_status = 'pending' AND reviewer_user_id IS NULL AND reviewed_at IS NULL) "
            "OR (review_status != 'pending' AND reviewer_user_id IS NOT NULL "
            "AND reviewed_at IS NOT NULL)",
            name="ck_answer_feedback_review_contract",
        ),
        CheckConstraint(
            "(review_status = 'promoted' AND promoted_case_id IS NOT NULL) OR "
            "(review_status != 'promoted' AND promoted_case_id IS NULL)",
            name="ck_answer_feedback_promotion_contract",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "workspace_id"],
            ["conversations.id", "conversations.workspace_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["assistant_message_id", "conversation_id", "workspace_id"],
            [
                "conversation_messages.id",
                "conversation_messages.conversation_id",
                "conversation_messages.workspace_id",
            ],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "assistant_message_id",
            "submitter_user_id",
            name="uq_answer_feedback_message_submitter",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    conversation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    assistant_message_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    submitter_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    snapshot_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    diagnostic_snapshot: Mapped[dict[str, object] | None] = mapped_column(
        JSON(none_as_null=True), nullable=True
    )
    consent_policy_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", index=True
    )
    reviewer_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_case_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    retention_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
