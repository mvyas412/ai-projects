from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user, get_rag_engine
from backend.app.db.session import get_db_session
from backend.app.models.conversation import (
    Conversation,
    ConversationMessage,
    ConversationTargetType,
    MessageRole,
)
from backend.app.models.user import User
from backend.app.rag.engine import RAGEngine, RAGUnavailableError
from backend.app.schemas.conversations import (
    Citation,
    ConversationCreate,
    ConversationDetail,
    ConversationMessageResponse,
    ConversationSummary,
    MessageCreate,
    MessageExchangeResponse,
)
from backend.app.services.conversations import (
    ConversationError,
    ConversationNotFoundError,
    ConversationService,
    NoIndexedEvidenceError,
    UnsafeCitationError,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/conversations", tags=["conversations"])


def _message(message: ConversationMessage) -> ConversationMessageResponse:
    return ConversationMessageResponse(
        id=message.id,
        sequence_number=message.sequence_number,
        role=MessageRole(message.role),
        content=message.content,
        citations=[Citation.model_validate(item) for item in message.citations],
        model_name=message.model_name,
        created_at=message.created_at,
    )


def _summary(
    conversation: Conversation, message_count: int, document_ids: list[UUID]
) -> ConversationSummary:
    return ConversationSummary(
        id=conversation.id,
        workspace_id=conversation.workspace_id,
        title=conversation.title,
        target_type=ConversationTargetType(conversation.target_type),
        collection_id=conversation.collection_id,
        document_ids=document_ids,
        message_count=message_count,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, ConversationNotFoundError):
        return HTTPException(status_code=404, detail="Resource not found")
    if isinstance(exc, NoIndexedEvidenceError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (RAGUnavailableError, UnsafeCitationError)):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The assistant is temporarily unavailable",
        )
    return HTTPException(status_code=500, detail="The conversation operation failed")


@router.get("", response_model=list[ConversationSummary])
def list_conversations(
    workspace_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    rag_engine: Annotated[RAGEngine, Depends(get_rag_engine)],
) -> list[ConversationSummary]:
    try:
        rows = ConversationService(session, rag_engine).list_conversations(
            user=user, workspace_id=workspace_id
        )
    except ConversationError as exc:
        raise _translate(exc) from exc
    return [_summary(conversation, count, ids) for conversation, count, ids in rows]


@router.post("", response_model=ConversationSummary, status_code=201)
def create_conversation(
    workspace_id: UUID,
    payload: ConversationCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    rag_engine: Annotated[RAGEngine, Depends(get_rag_engine)],
) -> ConversationSummary:
    try:
        conversation, document_ids = ConversationService(
            session, rag_engine
        ).create_conversation(user=user, workspace_id=workspace_id, payload=payload)
    except ConversationError as exc:
        raise _translate(exc) from exc
    return _summary(conversation, 0, document_ids)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    workspace_id: UUID,
    conversation_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    rag_engine: Annotated[RAGEngine, Depends(get_rag_engine)],
) -> ConversationDetail:
    try:
        conversation, document_ids, messages = ConversationService(
            session, rag_engine
        ).get_conversation(
            user=user, workspace_id=workspace_id, conversation_id=conversation_id
        )
    except ConversationError as exc:
        raise _translate(exc) from exc
    summary = _summary(conversation, len(messages), document_ids)
    return ConversationDetail(
        **summary.model_dump(), messages=[_message(message) for message in messages]
    )


@router.post("/{conversation_id}/messages", response_model=MessageExchangeResponse)
def create_message(
    workspace_id: UUID,
    conversation_id: UUID,
    payload: MessageCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    rag_engine: Annotated[RAGEngine, Depends(get_rag_engine)],
) -> MessageExchangeResponse:
    try:
        user_message, assistant_message = ConversationService(session, rag_engine).ask(
            user=user,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            content=payload.content,
        )
    except (ConversationError, RAGUnavailableError) as exc:
        raise _translate(exc) from exc
    return MessageExchangeResponse(
        user_message=_message(user_message), assistant_message=_message(assistant_message)
    )
