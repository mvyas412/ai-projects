from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.conversation import (
    Conversation,
    ConversationDocument,
    ConversationMessage,
)


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, conversation: Conversation, document_ids: list[UUID]) -> None:
        self._session.add(conversation)
        self._session.flush()
        self._session.add_all(
            ConversationDocument(
                conversation_id=conversation.id,
                document_id=document_id,
                workspace_id=conversation.workspace_id,
            )
            for document_id in document_ids
        )

    def list_for_workspace(self, workspace_id: UUID) -> list[tuple[Conversation, int]]:
        statement = (
            select(Conversation, func.count(ConversationMessage.id))
            .outerjoin(
                ConversationMessage,
                (ConversationMessage.conversation_id == Conversation.id)
                & (ConversationMessage.workspace_id == Conversation.workspace_id),
            )
            .where(
                Conversation.workspace_id == workspace_id,
                Conversation.archived_at.is_(None),
            )
            .group_by(Conversation.id)
            .order_by(Conversation.updated_at.desc(), Conversation.id)
        )
        return [(row[0], row[1]) for row in self._session.execute(statement).all()]

    def get(self, workspace_id: UUID, conversation_id: UUID) -> Conversation | None:
        return self._session.scalar(
            select(Conversation).where(
                Conversation.workspace_id == workspace_id,
                Conversation.id == conversation_id,
                Conversation.archived_at.is_(None),
            )
        )

    def document_ids(self, workspace_id: UUID, conversation_id: UUID) -> list[UUID]:
        return list(
            self._session.scalars(
                select(ConversationDocument.document_id)
                .where(
                    ConversationDocument.workspace_id == workspace_id,
                    ConversationDocument.conversation_id == conversation_id,
                )
                .order_by(ConversationDocument.document_id)
            )
        )

    def messages(self, workspace_id: UUID, conversation_id: UUID) -> list[ConversationMessage]:
        return list(
            self._session.scalars(
                select(ConversationMessage)
                .where(
                    ConversationMessage.workspace_id == workspace_id,
                    ConversationMessage.conversation_id == conversation_id,
                )
                .order_by(ConversationMessage.sequence_number)
            )
        )

    def next_sequence(self, workspace_id: UUID, conversation_id: UUID) -> int:
        current = self._session.scalar(
            select(func.max(ConversationMessage.sequence_number)).where(
                ConversationMessage.workspace_id == workspace_id,
                ConversationMessage.conversation_id == conversation_id,
            )
        )
        return (current or 0) + 1

    def add_messages(self, *messages: ConversationMessage) -> None:
        self._session.add_all(messages)
