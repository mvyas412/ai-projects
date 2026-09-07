from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from backend.app.models.feedback import FeedbackReason, FeedbackReviewStatus


class FeedbackCreate(BaseModel):
    rating: int = Field(ge=-1, le=1)
    reason: FeedbackReason
    comment: str | None = Field(default=None, max_length=1000)
    comment_consent: bool = False
    snapshot_consent: bool = False

    @model_validator(mode="after")
    def validate_consent(self):
        normalized = self.comment.strip() if self.comment else None
        self.comment = normalized or None
        if self.rating not in {-1, 1}:
            raise ValueError("rating must be -1 or 1")
        if self.comment is not None and not self.comment_consent:
            raise ValueError("comment consent is required")
        if self.comment is None and self.comment_consent:
            raise ValueError("comment consent requires a comment")
        return self


class FeedbackReview(BaseModel):
    status: FeedbackReviewStatus
    promoted_case_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{2,79}$")

    @model_validator(mode="after")
    def validate_promotion(self):
        if self.status == FeedbackReviewStatus.PENDING:
            raise ValueError("review cannot return feedback to pending")
        if (self.status == FeedbackReviewStatus.PROMOTED) != (self.promoted_case_id is not None):
            raise ValueError("promoted feedback requires exactly one regression case ID")
        return self


class FeedbackResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    conversation_id: UUID
    assistant_message_id: UUID
    submitter_user_id: UUID
    rating: int
    reason: FeedbackReason
    comment: str | None
    comment_consent: bool
    snapshot_consent: bool
    review_status: FeedbackReviewStatus
    reviewer_user_id: UUID | None
    reviewed_at: datetime | None
    promoted_case_id: str | None
    retention_expires_at: datetime
    created_at: datetime
    updated_at: datetime
