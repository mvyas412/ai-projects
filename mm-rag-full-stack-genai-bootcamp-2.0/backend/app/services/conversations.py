from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.models.conversation import (
    Conversation,
    ConversationMessage,
    ConversationTargetType,
    MessageRole,
)
from backend.app.models.document import Document, DocumentVersion
from backend.app.models.user import User
from backend.app.rag.engine import RAGDocumentScope, RAGEngine, RAGRequest
from backend.app.repositories.conversations import ConversationRepository
from backend.app.repositories.documents import CollectionRepository, DocumentRepository
from backend.app.repositories.workspaces import WorkspaceRepository
from backend.app.schemas.conversations import Citation, ConversationCreate
from backend.app.services.audit import record_audit_event


class ConversationError(Exception):
    """Base class for safe conversation failures."""


class ConversationNotFoundError(ConversationError):
    pass


class InvalidConversationTargetError(ConversationError):
    pass


class NoIndexedEvidenceError(ConversationError):
    pass


class UnsafeCitationError(ConversationError):
    pass


class ConversationService:
    def __init__(self, session: Session, rag_engine: RAGEngine) -> None:
        self._session = session
        self._rag_engine = rag_engine
        self._conversations = ConversationRepository(session)
        self._documents = DocumentRepository(session)
        self._collections = CollectionRepository(session)
        self._workspaces = WorkspaceRepository(session)

    def list_conversations(
        self, *, user: User, workspace_id: UUID
    ) -> list[tuple[Conversation, int, list[UUID]]]:
        self._require_workspace(user, workspace_id)
        return [
            (
                conversation,
                count,
                self._conversations.document_ids(workspace_id, conversation.id),
            )
            for conversation, count in self._conversations.list_for_workspace(workspace_id)
        ]

    def create_conversation(
        self, *, user: User, workspace_id: UUID, payload: ConversationCreate
    ) -> tuple[Conversation, list[UUID]]:
        document_ids = list(payload.document_ids)
        with self._session.begin():
            self._require_workspace(user, workspace_id)
            if payload.target_type == ConversationTargetType.COLLECTION:
                collection_id = payload.collection_id
                if collection_id is None or self._collections.get_collection(
                    workspace_id, collection_id
                ) is None:
                    raise ConversationNotFoundError
            elif payload.target_type == ConversationTargetType.DOCUMENTS:
                if any(
                    self._documents.get_document(workspace_id, document_id) is None
                    for document_id in document_ids
                ):
                    raise ConversationNotFoundError
            conversation = Conversation(
                workspace_id=workspace_id,
                created_by_user_id=user.id,
                title=payload.title,
                target_type=payload.target_type.value,
                collection_id=payload.collection_id,
            )
            self._conversations.add(conversation, document_ids)
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="conversation.created",
                resource_type="conversation",
                resource_id=conversation.id,
                details={"target_type": payload.target_type.value, "title": payload.title},
            )
        return conversation, document_ids

    def get_conversation(
        self, *, user: User, workspace_id: UUID, conversation_id: UUID
    ) -> tuple[Conversation, list[UUID], list[ConversationMessage]]:
        self._require_workspace(user, workspace_id)
        conversation = self._conversations.get(workspace_id, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError
        return (
            conversation,
            self._conversations.document_ids(workspace_id, conversation_id),
            self._conversations.messages(workspace_id, conversation_id),
        )

    def ask(
        self,
        *,
        user: User,
        workspace_id: UUID,
        conversation_id: UUID,
        content: str,
    ) -> tuple[ConversationMessage, ConversationMessage]:
        conversation, _, prior_messages = self.get_conversation(
            user=user,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
        )
        resolved = self._ready_scope(conversation)
        if not resolved:
            raise NoIndexedEvidenceError("No indexed document is available for this scope")

        answer = self._rag_engine.answer(
            RAGRequest(
                workspace_id=workspace_id,
                documents=tuple(
                    RAGDocumentScope(document.id, version.id)
                    for document, version in resolved
                ),
                query=content,
                history=tuple((message.role, message.content) for message in prior_messages),
            )
        )
        # Treat model citations as untrusted output and revalidate every source
        # against the backend-resolved scope before anything is persisted.
        allowed = {(document.id, version.id) for document, version in resolved}
        if any(
            (citation.document_id, citation.document_version_id) not in allowed
            for citation in answer.citations
        ):
            raise UnsafeCitationError("The generated answer contained unauthorized evidence")

        first_sequence = self._conversations.next_sequence(workspace_id, conversation_id)
        user_message = ConversationMessage(
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            user_id=user.id,
            sequence_number=first_sequence,
            role=MessageRole.USER.value,
            content=content,
            citations=[],
        )
        citation_payload = [
            Citation(
                document_id=item.document_id,
                document_version_id=item.document_version_id,
                document_title=item.document_title,
                page_number=item.page_number,
                content_type=item.content_type,
                excerpt=item.excerpt,
                score=item.score,
            ).model_dump(mode="json")
            for item in answer.citations
        ]
        assistant_message = ConversationMessage(
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            sequence_number=first_sequence + 1,
            role=MessageRole.ASSISTANT.value,
            content=answer.content,
            citations=citation_payload,
            model_name=answer.model_name,
            prompt_tokens=answer.prompt_tokens,
            completion_tokens=answer.completion_tokens,
        )
        try:
            self._conversations.add_messages(user_message, assistant_message)
            # Message activity drives recent-conversation ordering in the UI.
            conversation.updated_at = datetime.now(UTC)
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="conversation.message_created",
                resource_type="conversation",
                resource_id=conversation_id,
                details={
                    "assistant_message_id": str(assistant_message.id),
                    "citation_count": len(citation_payload),
                },
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        return user_message, assistant_message

    def _ready_scope(
        self, conversation: Conversation
    ) -> list[tuple[Document, DocumentVersion]]:
        target = ConversationTargetType(conversation.target_type)
        if target == ConversationTargetType.WORKSPACE:
            documents = self._documents.list_documents(conversation.workspace_id)
        elif target == ConversationTargetType.COLLECTION:
            if conversation.collection_id is None:
                raise InvalidConversationTargetError
            documents = self._collections.list_documents(
                conversation.workspace_id, conversation.collection_id
            )
        else:
            documents = []
            for document_id in self._conversations.document_ids(
                conversation.workspace_id, conversation.id
            ):
                document = self._documents.get_document(
                    conversation.workspace_id, document_id
                )
                if document is not None:
                    documents.append(document)

        resolved: list[tuple[Document, DocumentVersion]] = []
        for document in documents:
            version = self._documents.latest_ready_version(
                conversation.workspace_id, document.id
            )
            if version is not None:
                resolved.append((document, version))
        return resolved

    def _require_workspace(self, user: User, workspace_id: UUID) -> None:
        if self._workspaces.get_for_user(workspace_id, user.id) is None:
            raise ConversationNotFoundError
