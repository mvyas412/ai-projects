from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.conversation import ConversationMessage, MessageRole
from backend.app.models.feedback import AnswerFeedback, FeedbackReviewStatus
from backend.app.models.user import User
from backend.app.schemas.feedback import FeedbackCreate, FeedbackReview
from backend.app.services.audit import record_audit_event
from backend.app.services.policy import PolicyAction, PolicyService, resource_context

CONSENT_POLICY_REVISION = "phase7-feedback-consent-v1"


class FeedbackNotFoundError(Exception):
    pass


class FeedbackService:
    def __init__(self, session: Session, *, retention_days: int) -> None:
        self._session = session
        self._retention_days = retention_days
        self._policy = PolicyService(session)

    def submit(
        self,
        *,
        user: User,
        workspace_id: UUID,
        conversation_id: UUID,
        message_id: UUID,
        payload: FeedbackCreate,
    ) -> AnswerFeedback:
        from backend.app.repositories.conversations import ConversationRepository

        conversation = ConversationRepository(self._session).get(workspace_id, conversation_id)
        if conversation is None:
            raise FeedbackNotFoundError
        self._policy.require(
            user=user,
            workspace_id=workspace_id,
            action=PolicyAction.CONVERSATION_READ,
            resource=resource_context(conversation),
        )
        self._policy.require(
            user=user, workspace_id=workspace_id, action=PolicyAction.FEEDBACK_SUBMIT
        )
        message = self._session.scalar(
            select(ConversationMessage).where(
                ConversationMessage.id == message_id,
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.workspace_id == workspace_id,
                ConversationMessage.role == MessageRole.ASSISTANT.value,
            )
        )
        if message is None:
            raise FeedbackNotFoundError
        existing = self._session.scalar(
            select(AnswerFeedback).where(
                AnswerFeedback.assistant_message_id == message_id,
                AnswerFeedback.submitter_user_id == user.id,
            )
        )
        snapshot = self._snapshot(message) if payload.snapshot_consent else None
        now = datetime.now(UTC)
        if existing is None:
            feedback = AnswerFeedback(
                workspace_id=workspace_id,
                conversation_id=conversation_id,
                assistant_message_id=message_id,
                submitter_user_id=user.id,
                rating=payload.rating,
                reason=payload.reason.value,
                comment=payload.comment,
                comment_consent=payload.comment_consent,
                snapshot_consent=payload.snapshot_consent,
                diagnostic_snapshot=snapshot,
                consent_policy_revision=CONSENT_POLICY_REVISION,
                retention_expires_at=now + timedelta(days=self._retention_days),
            )
            self._session.add(feedback)
        else:
            feedback = existing
            feedback.rating = payload.rating
            feedback.reason = payload.reason.value
            feedback.comment = payload.comment
            feedback.comment_consent = payload.comment_consent
            feedback.snapshot_consent = payload.snapshot_consent
            feedback.diagnostic_snapshot = snapshot
            feedback.consent_policy_revision = CONSENT_POLICY_REVISION
            feedback.review_status = FeedbackReviewStatus.PENDING.value
            feedback.reviewer_user_id = None
            feedback.reviewed_at = None
            feedback.promoted_case_id = None
            feedback.retention_expires_at = now + timedelta(days=self._retention_days)
        self._session.flush()
        record_audit_event(
            self._session,
            workspace_id=workspace_id,
            actor_user_id=user.id,
            action="feedback.submitted",
            resource_type="conversation",
            resource_id=conversation_id,
            details={
                "feedback_id": str(feedback.id),
                "rating": payload.rating,
                "reason": payload.reason.value,
                "comment_consent": payload.comment_consent,
                "snapshot_consent": payload.snapshot_consent,
            },
        )
        self._session.commit()
        return feedback

    def list_for_review(self, *, user: User, workspace_id: UUID) -> list[AnswerFeedback]:
        self._policy.require(
            user=user, workspace_id=workspace_id, action=PolicyAction.FEEDBACK_REVIEW
        )
        return list(
            self._session.scalars(
                select(AnswerFeedback)
                .where(AnswerFeedback.workspace_id == workspace_id)
                .order_by(AnswerFeedback.created_at.desc(), AnswerFeedback.id)
            )
        )

    def review(
        self,
        *,
        user: User,
        workspace_id: UUID,
        feedback_id: UUID,
        payload: FeedbackReview,
    ) -> AnswerFeedback:
        self._policy.require(
            user=user, workspace_id=workspace_id, action=PolicyAction.FEEDBACK_REVIEW
        )
        feedback = self._session.scalar(
            select(AnswerFeedback).where(
                AnswerFeedback.id == feedback_id,
                AnswerFeedback.workspace_id == workspace_id,
            )
        )
        if feedback is None:
            raise FeedbackNotFoundError
        feedback.review_status = payload.status.value
        feedback.reviewer_user_id = user.id
        feedback.reviewed_at = datetime.now(UTC)
        feedback.promoted_case_id = payload.promoted_case_id
        record_audit_event(
            self._session,
            workspace_id=workspace_id,
            actor_user_id=user.id,
            action="feedback.reviewed",
            resource_type="conversation",
            resource_id=feedback.conversation_id,
            details={
                "feedback_id": str(feedback.id),
                "review_status": payload.status.value,
                "promoted_case_id": payload.promoted_case_id,
            },
        )
        self._session.commit()
        return feedback

    @staticmethod
    def _snapshot(message: ConversationMessage) -> dict[str, object]:
        citations = message.citations if isinstance(message.citations, list) else []
        return {
            "schema_revision": "phase7-feedback-snapshot-v1",
            "model_name": message.model_name,
            "citation_count": len(citations),
            "evidence_refs": [
                {
                    "document_id": item.get("document_id"),
                    "document_version_id": item.get("document_version_id"),
                    "generation_id": item.get("generation_id"),
                    "region_id": item.get("region_id"),
                    "table_id": item.get("table_id"),
                }
                for item in citations[:20]
                if isinstance(item, dict)
            ],
        }
