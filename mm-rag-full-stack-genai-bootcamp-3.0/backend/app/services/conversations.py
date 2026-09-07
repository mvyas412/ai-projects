from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.core.telemetry import observed_span
from backend.app.ingestion.pipeline import manifest_supports_sparse
from backend.app.models.conversation import (
    Conversation,
    ConversationMessage,
    ConversationTargetType,
    MessageRole,
)
from backend.app.models.document import Document, DocumentVersion
from backend.app.models.user import User
from backend.app.rag.engine import (
    INSUFFICIENT_EVIDENCE_MESSAGE,
    RAGAnswer,
    RAGCitation,
    RAGDocumentScope,
    RAGEngine,
    RAGRequest,
)
from backend.app.repositories.conversations import ConversationRepository
from backend.app.repositories.documents import CollectionRepository, DocumentRepository
from backend.app.schemas.conversations import Citation, ConversationCreate
from backend.app.services.audit import record_audit_event
from backend.app.services.policy import (
    PolicyAction,
    PolicyDeniedError,
    PolicyNotFoundError,
    PolicyService,
    resource_context,
)
from backend.app.tables.calculation import (
    CalculationEvidence,
    PostgresTableCalculationEngine,
    TableCalculationRequest,
    TableCalculationScope,
    format_calculation_answer,
)
from backend.app.visual.retrieval import TEXT_ONLY_ROUTE, select_visual_route


class ConversationError(Exception):
    """Base class for safe conversation failures."""


class ConversationNotFoundError(ConversationError):
    pass


class ConversationPermissionError(ConversationError):
    pass


class InvalidConversationTargetError(ConversationError):
    pass


class NoIndexedEvidenceError(ConversationError):
    pass


class UnsafeCitationError(ConversationError):
    pass


def _calculation_answer(evidence: CalculationEvidence | None) -> RAGAnswer:
    if evidence is None:
        return RAGAnswer(content=INSUFFICIENT_EVIDENCE_MESSAGE, citations=())
    return RAGAnswer(
        content=format_calculation_answer(evidence),
        citations=(
            RAGCitation(
                document_id=evidence.document_id,
                document_version_id=evidence.document_version_id,
                document_title=evidence.document_title,
                page_number=evidence.page_number,
                content_type="application/vnd.mm-rag.table-calculation+json",
                excerpt=(
                    f"Exact {evidence.operator.value} from "
                    f"{len(evidence.cell_ids)} validated table cell(s)."
                ),
                evidence_kind="calculation",
                generation_id=evidence.generation_id,
                region_id=evidence.region_id,
                table_id=evidence.table_id,
                cell_ids=evidence.cell_ids,
                calculation_trace_id=evidence.trace_id,
            ),
        ),
        model_name="deterministic-table-v1",
    )


def should_attempt_table_calculation(query: str) -> bool:
    """Give explicit visual intent precedence over generic lookup wording."""

    return select_visual_route(query) == TEXT_ONLY_ROUTE


class ConversationService:
    def __init__(
        self,
        session: Session,
        rag_engine: RAGEngine,
        *,
        table_calculation_enabled: bool = False,
    ) -> None:
        self._session = session
        self._rag_engine = rag_engine
        self._conversations = ConversationRepository(session)
        self._documents = DocumentRepository(session)
        self._collections = CollectionRepository(session)
        self._policy = PolicyService(session)
        self._table_calculator = (
            PostgresTableCalculationEngine(session) if table_calculation_enabled else None
        )

    def list_conversations(
        self, *, user: User, workspace_id: UUID
    ) -> list[tuple[Conversation, int, list[UUID]]]:
        self._require_policy(user, workspace_id, PolicyAction.CONVERSATION_READ)
        return [
            (
                conversation,
                count,
                self._conversations.document_ids(workspace_id, conversation.id),
            )
            for conversation, count in self._conversations.list_for_workspace(workspace_id)
            if self._policy.can_read(user=user, resource=resource_context(conversation))
        ]

    def create_conversation(
        self, *, user: User, workspace_id: UUID, payload: ConversationCreate
    ) -> tuple[Conversation, list[UUID]]:
        document_ids = list(payload.document_ids)
        with self._session.begin():
            self._require_policy(user, workspace_id, PolicyAction.CONVERSATION_CREATE)
            if payload.target_type == ConversationTargetType.COLLECTION:
                collection_id = payload.collection_id
                collection = (
                    self._collections.get_collection(workspace_id, collection_id)
                    if collection_id is not None
                    else None
                )
                if collection is None:
                    raise ConversationNotFoundError
                self._require_policy(
                    user,
                    workspace_id,
                    PolicyAction.COLLECTION_READ,
                    resource=resource_context(collection),
                )
            elif payload.target_type == ConversationTargetType.DOCUMENTS:
                for document_id in document_ids:
                    document = self._documents.get_document(workspace_id, document_id)
                    if document is None:
                        raise ConversationNotFoundError
                    self._require_policy(
                        user,
                        workspace_id,
                        PolicyAction.DOCUMENT_READ,
                        resource=resource_context(document),
                    )
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
                details={"target_type": payload.target_type.value},
            )
        return conversation, document_ids

    def get_conversation(
        self, *, user: User, workspace_id: UUID, conversation_id: UUID
    ) -> tuple[Conversation, list[UUID], list[ConversationMessage]]:
        conversation = self._conversations.get(workspace_id, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError
        self._require_policy(
            user,
            workspace_id,
            PolicyAction.CONVERSATION_READ,
            resource=resource_context(conversation),
        )
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
        self._require_policy(
            user,
            workspace_id,
            PolicyAction.CONVERSATION_MESSAGE_CREATE,
            resource=resource_context(conversation),
        )
        resolved = self._ready_scope(user, conversation)
        if not resolved:
            raise NoIndexedEvidenceError("No indexed document is available for this scope")

        rag_request = RAGRequest(
            workspace_id=workspace_id,
            documents=tuple(
                RAGDocumentScope(
                    document.id,
                    version.id,
                    version.active_generation_id,
                    manifest_supports_sparse(
                        self._documents.generation_manifest(workspace_id, version)
                    ),
                )
                for document, version in resolved
            ),
            query=content,
            history=tuple((message.role, message.content) for message in prior_messages),
        )
        calculation = (
            self._table_calculator.calculate(
                TableCalculationRequest(
                    workspace_id=workspace_id,
                    documents=tuple(
                        TableCalculationScope(
                            document.id,
                            version.id,
                            version.active_generation_id,
                            document.title,
                        )
                        for document, version in resolved
                        if version.active_generation_id is not None
                    ),
                    query=content,
                )
            )
            if self._table_calculator is not None
            and should_attempt_table_calculation(content)
            else None
        )
        answer = (
            _calculation_answer(calculation.evidence)
            if calculation is not None and calculation.attempted
            else self._rag_engine.answer(rag_request)
        )
        # Treat model citations as untrusted output and revalidate every source
        # against the backend-resolved scope before anything is persisted.
        allowed = {
            (document.id, version.id, version.active_generation_id)
            for document, version in resolved
        }
        if any(
            (
                citation.document_id,
                citation.document_version_id,
                citation.generation_id,
            )
            not in allowed
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
                evidence_schema_revision=item.evidence_schema_revision,
                document_id=item.document_id,
                document_version_id=item.document_version_id,
                document_title=item.document_title,
                page_number=item.page_number,
                content_type=item.content_type,
                excerpt=item.excerpt,
                score=item.score,
                evidence_kind=item.evidence_kind,
                generation_id=item.generation_id,
                region_id=item.region_id,
                table_id=item.table_id,
                cell_ids=list(item.cell_ids),
                calculation_trace_id=item.calculation_trace_id,
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
            with observed_span(
                "conversation.persist_exchange",
                attributes={"db.system": "postgresql", "count": 2},
            ):
                self._conversations.add_messages(user_message, assistant_message)
                # Flush UUID defaults before the audit record captures the message ID.
                self._session.flush()
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
        self, user: User, conversation: Conversation
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
            if not self._policy.can_read(user=user, resource=resource_context(document)):
                continue
            version = self._documents.latest_ready_version(
                conversation.workspace_id, document.id
            )
            if version is not None:
                resolved.append((document, version))
        return resolved

    def _require_policy(
        self,
        user: User,
        workspace_id: UUID,
        action: PolicyAction,
        *,
        resource=None,
    ) -> None:
        try:
            self._policy.require(
                user=user,
                workspace_id=workspace_id,
                action=action,
                resource=resource,
            )
        except PolicyNotFoundError as exc:
            raise ConversationNotFoundError from exc
        except PolicyDeniedError as exc:
            raise ConversationPermissionError from exc
