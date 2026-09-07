from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_app_settings, get_current_user
from backend.app.core.config import Settings
from backend.app.db.session import get_db_session
from backend.app.models.feedback import AnswerFeedback
from backend.app.models.user import User
from backend.app.schemas.feedback import FeedbackCreate, FeedbackResponse, FeedbackReview
from backend.app.services.feedback import FeedbackNotFoundError, FeedbackService
from backend.app.services.policy import PolicyDeniedError, PolicyNotFoundError

router = APIRouter(prefix="/workspaces/{workspace_id}/feedback", tags=["feedback"])


def _response(feedback: AnswerFeedback) -> FeedbackResponse:
    return FeedbackResponse.model_validate(feedback, from_attributes=True)


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, (FeedbackNotFoundError, PolicyNotFoundError)):
        return HTTPException(status_code=404, detail="Resource not found")
    if isinstance(exc, PolicyDeniedError):
        return HTTPException(status_code=403, detail="Insufficient access")
    return HTTPException(status_code=500, detail="The feedback operation failed")


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}",
    response_model=FeedbackResponse,
)
def submit_feedback(
    workspace_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    payload: FeedbackCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> FeedbackResponse:
    try:
        feedback = FeedbackService(session, retention_days=settings.feedback_retention_days).submit(
            user=user,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            payload=payload,
        )
    except (FeedbackNotFoundError, PolicyDeniedError, PolicyNotFoundError) as exc:
        raise _translate(exc) from exc
    return _response(feedback)


@router.get("", response_model=list[FeedbackResponse])
def list_feedback(
    workspace_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> list[FeedbackResponse]:
    try:
        rows = FeedbackService(
            session, retention_days=settings.feedback_retention_days
        ).list_for_review(user=user, workspace_id=workspace_id)
    except (PolicyDeniedError, PolicyNotFoundError) as exc:
        raise _translate(exc) from exc
    return [_response(item) for item in rows]


@router.post("/{feedback_id}/review", response_model=FeedbackResponse)
def review_feedback(
    workspace_id: UUID,
    feedback_id: UUID,
    payload: FeedbackReview,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> FeedbackResponse:
    try:
        feedback = FeedbackService(session, retention_days=settings.feedback_retention_days).review(
            user=user,
            workspace_id=workspace_id,
            feedback_id=feedback_id,
            payload=payload,
        )
    except (FeedbackNotFoundError, PolicyDeniedError, PolicyNotFoundError) as exc:
        raise _translate(exc) from exc
    return _response(feedback)
