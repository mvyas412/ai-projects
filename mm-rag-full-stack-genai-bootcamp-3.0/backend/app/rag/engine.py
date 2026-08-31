from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from qdrant_client import QdrantClient, models

from backend.app.core.config import Settings
from backend.app.retrieval.scope import workspace_filter


class RAGUnavailableError(Exception):
    """Raised when retrieval or generation cannot serve a request safely."""


@dataclass(frozen=True, slots=True)
class RAGDocumentScope:
    document_id: UUID
    document_version_id: UUID
    generation_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class RAGRequest:
    workspace_id: UUID
    documents: tuple[RAGDocumentScope, ...]
    query: str
    history: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class RAGCitation:
    document_id: UUID
    document_version_id: UUID
    document_title: str
    content_type: str
    excerpt: str
    page_number: int | None = None
    score: float | None = None


@dataclass(frozen=True, slots=True)
class RAGAnswer:
    content: str
    citations: tuple[RAGCitation, ...]
    model_name: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class RAGEngine(Protocol):
    def answer(self, request: RAGRequest) -> RAGAnswer: ...


class UnavailableRAGEngine:
    def answer(self, request: RAGRequest) -> RAGAnswer:
        raise RAGUnavailableError("RAG generation is not configured in this environment")


class QdrantOpenAIRAGEngine:
    def __init__(self, settings: Settings, qdrant: QdrantClient) -> None:
        self._settings = settings
        self._qdrant = qdrant

    def answer(self, request: RAGRequest) -> RAGAnswer:
        if not request.documents:
            raise RAGUnavailableError("No indexed document version is available for this scope")
        if not self._qdrant.collection_exists(self._settings.qdrant_collection_name):
            raise RAGUnavailableError("The document index is not available")

        api_key = self._settings.openai_api_key
        if api_key is None:
            raise RAGUnavailableError("RAG generation is not configured in this environment")
        try:
            embeddings = OpenAIEmbeddings(
                api_key=api_key,
                model=self._settings.openai_embedding_model,
            )
            vector = embeddings.embed_query(request.query)
            # Scope is resolved by the backend and applied inside Qdrant, so the
            # retriever never receives candidates from an unauthorized version.
            points = self._qdrant.query_points(
                collection_name=self._settings.qdrant_collection_name,
                query=vector,
                query_filter=_retrieval_filter(request),
                limit=self._settings.rag_retrieval_limit,
                with_payload=True,
            ).points
        except Exception as exc:
            raise RAGUnavailableError("The retrieval service is temporarily unavailable") from exc
        citations = tuple(
            _authorized_citation(point, request) for point in points if point.payload
        )
        if not citations:
            return RAGAnswer(
                content="I could not find authorized evidence to answer that question.",
                citations=(),
                model_name=self._settings.openai_chat_model,
            )

        evidence = "\n\n".join(
            f"[{index}] {item.document_title}"
            f"{f' p.{item.page_number}' if item.page_number else ''}: {item.excerpt}"
            for index, item in enumerate(citations, start=1)
        )
        # Keep evidence in the system message and bound persisted chat history to
        # control prompt size while preserving useful conversational context.
        messages: list[BaseMessage] = [
            SystemMessage(
                content=(
                    "Answer only from the authorized evidence. Cite supporting items using "
                    "[1], [2], and so on. State clearly when evidence is insufficient.\n\n"
                    f"Evidence:\n{evidence}"
                )
            )
        ]
        for role, content in request.history[-10:]:
            message = HumanMessage(content=content) if role == "user" else AIMessage(content=content)
            messages.append(message)
        messages.append(HumanMessage(content=request.query))
        try:
            response = ChatOpenAI(
                api_key=api_key,
                model=self._settings.openai_chat_model,
                temperature=0,
            ).invoke(messages)
        except Exception as exc:
            raise RAGUnavailableError("The generation service is temporarily unavailable") from exc
        usage = response.usage_metadata
        return RAGAnswer(
            content=str(response.content),
            citations=citations,
            model_name=self._settings.openai_chat_model,
            prompt_tokens=usage.get("input_tokens") if usage else None,
            completion_tokens=usage.get("output_tokens") if usage else None,
        )


def build_rag_engine(settings: Settings, qdrant: QdrantClient) -> RAGEngine:
    if settings.openai_api_key is None:
        return UnavailableRAGEngine()
    return QdrantOpenAIRAGEngine(settings, qdrant)


def _retrieval_filter(request: RAGRequest) -> models.Filter:
    if not request.documents or len(request.documents) > 100:
        raise RAGUnavailableError("Authorized retrieval scope is invalid")
    if any(scope.generation_id is None for scope in request.documents):
        raise RAGUnavailableError("Authorized retrieval scope is incomplete")
    identities = {
        (scope.document_id, scope.document_version_id, scope.generation_id)
        for scope in request.documents
    }
    if len(identities) != len(request.documents):
        raise RAGUnavailableError("Authorized retrieval scope is invalid")
    base = workspace_filter(request.workspace_id)
    document_conditions: list[models.Filter | models.FieldCondition] = [
        models.Filter(
            must=[
                models.FieldCondition(
                    key="document_id", match=models.MatchValue(value=str(scope.document_id))
                ),
                models.FieldCondition(
                    key="document_version_id",
                    match=models.MatchValue(value=str(scope.document_version_id)),
                ),
                models.FieldCondition(
                    key="generation_id",
                    match=models.MatchValue(value=str(scope.generation_id)),
                ),
            ]
        )
        for scope in request.documents
    ]
    return models.Filter(
        must=[
            *(base.must or []),
            models.Filter(should=document_conditions),  # type: ignore[arg-type]
        ]
    )


def _authorized_citation(point: Any, request: RAGRequest) -> RAGCitation:
    payload = point.payload or {}
    try:
        workspace_id = UUID(str(payload["workspace_id"]))
        tenant_id = UUID(str(payload["tenant_id"]))
        document_id = UUID(str(payload["document_id"]))
        version_id = UUID(str(payload["document_version_id"]))
        generation_id = UUID(str(payload["generation_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise RAGUnavailableError("Retrieved evidence failed authorization validation") from exc
    allowed = {
        (scope.document_id, scope.document_version_id, scope.generation_id)
        for scope in request.documents
    }
    if (
        workspace_id != request.workspace_id
        or tenant_id != request.workspace_id
        or (document_id, version_id, generation_id) not in allowed
    ):
        raise RAGUnavailableError("Retrieved evidence failed authorization validation")
    return RAGCitation(
        document_id=document_id,
        document_version_id=version_id,
        document_title=str(payload.get("document_title", "Document")),
        page_number=(int(payload["page_number"]) if payload.get("page_number") else None),
        content_type=str(payload.get("content_type", "text")),
        excerpt=str(payload.get("content", ""))[:1000],
        score=float(point.score) if point.score is not None else None,
    )
