from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol
from uuid import UUID

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from qdrant_client import QdrantClient, models

from backend.app.core.config import Settings
from backend.app.retrieval.ranking import (
    CandidateReranker,
    FastEmbedCandidateReranker,
    RetrievalCandidate,
    diversify_candidates,
    reciprocal_rank_fusion,
    rerank_with_timeout,
)
from backend.app.retrieval.scope import workspace_filter
from backend.app.retrieval.sparse import (
    SPARSE_VECTOR_NAME,
    FastEmbedBM25Encoder,
    SparseEncoder,
)

logger = structlog.get_logger(__name__)


class RAGUnavailableError(Exception):
    """Raised when retrieval or generation cannot serve a request safely."""


@dataclass(frozen=True, slots=True)
class RAGDocumentScope:
    document_id: UUID
    document_version_id: UUID
    generation_id: UUID | None = None
    sparse_available: bool = False


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
    def __init__(
        self,
        settings: Settings,
        qdrant: QdrantClient,
        sparse_encoder: SparseEncoder | None = None,
        reranker: CandidateReranker | None = None,
    ) -> None:
        self._settings = settings
        self._qdrant = qdrant
        self._sparse_encoder = sparse_encoder
        self._reranker = reranker

    def answer(self, request: RAGRequest) -> RAGAnswer:
        if not request.documents:
            raise RAGUnavailableError("No indexed document version is available for this scope")
        if not self._qdrant.collection_exists(self._settings.qdrant_collection_name):
            raise RAGUnavailableError("The document index is not available")

        api_key = self._settings.openai_api_key
        if api_key is None:
            raise RAGUnavailableError("RAG generation is not configured in this environment")
        retrieval_started = perf_counter()
        try:
            embeddings = OpenAIEmbeddings(
                api_key=api_key,
                model=self._settings.openai_embedding_model,
            )
            vector = embeddings.embed_query(request.query)
            use_hybrid = bool(
                self._settings.rag_retrieval_profile != "dense-v1"
                and self._sparse_encoder is not None
                and all(scope.sparse_available for scope in request.documents)
            )
            # The backend-resolved filter is reused verbatim for both retrieval legs.
            dense_started = perf_counter()
            dense_points = self._qdrant.query_points(
                collection_name=self._settings.qdrant_collection_name,
                query=vector,
                query_filter=_retrieval_filter(request),
                limit=(
                    self._settings.rag_dense_candidate_limit
                    if use_hybrid
                    else self._settings.rag_retrieval_limit
                ),
                with_payload=True,
            ).points
            dense_ms = (perf_counter() - dense_started) * 1000
        except Exception as exc:
            raise RAGUnavailableError("The retrieval service is temporarily unavailable") from exc
        dense = [_authorized_candidate(point, request) for point in dense_points]
        ranked = dense
        sparse: list[RetrievalCandidate] = []
        sparse_ms = 0.0
        fusion_ms = 0.0
        rerank_ms = 0.0
        reranker_attempted = False
        if use_hybrid and self._sparse_encoder is not None:
            sparse_points: list[Any] = []
            sparse_started = perf_counter()
            try:
                sparse_vector = self._sparse_encoder.embed_query(request.query)
                sparse_points = list(
                    self._qdrant.query_points(
                        collection_name=self._settings.qdrant_collection_name,
                        query=sparse_vector,
                        using=SPARSE_VECTOR_NAME,
                        query_filter=_retrieval_filter(request),
                        limit=self._settings.rag_sparse_candidate_limit,
                        with_payload=True,
                    ).points
                )
            except Exception:
                # Sparse loss may change ranking, but never scope or dense availability.
                sparse_points = []
            sparse_ms = (perf_counter() - sparse_started) * 1000
            if sparse_points:
                sparse = [_authorized_candidate(point, request) for point in sparse_points]
                fusion_started = perf_counter()
                try:
                    fused = reciprocal_rank_fusion(
                        dense,
                        sparse,
                        k=self._settings.rag_fusion_k,
                    )
                    ranked = diversify_candidates(
                        fused,
                        document_count=len(request.documents),
                        max_per_document=self._settings.rag_max_candidates_per_document,
                        limit=self._settings.rag_rerank_candidate_limit,
                    )
                except Exception as exc:
                    raise RAGUnavailableError(
                        "Retrieved evidence failed authorization validation"
                    ) from exc
                fusion_ms = (perf_counter() - fusion_started) * 1000
                if (
                    self._settings.rag_retrieval_profile == "hybrid-rerank-v1"
                    and self._reranker is not None
                ):
                    reranker_attempted = True
                    rerank_started = perf_counter()
                    ranked = rerank_with_timeout(
                        self._reranker,
                        request.query,
                        ranked,
                        timeout_seconds=self._settings.rag_rerank_timeout_seconds,
                    )
                    rerank_ms = (perf_counter() - rerank_started) * 1000
        logger.info(
            "retrieval_ranked",
            ranking_profile=self._settings.rag_retrieval_profile,
            sparse_used=bool(sparse),
            reranker_attempted=reranker_attempted,
            dense_point_ids=[candidate.point_id for candidate in dense],
            sparse_point_ids=[candidate.point_id for candidate in sparse],
            ranked_point_ids=[candidate.point_id for candidate in ranked],
            dense_ms=round(dense_ms, 2),
            sparse_ms=round(sparse_ms, 2),
            fusion_ms=round(fusion_ms, 2),
            rerank_ms=round(rerank_ms, 2),
            total_retrieval_ms=round((perf_counter() - retrieval_started) * 1000, 2),
        )
        citations = tuple(
            _candidate_citation(candidate)
            for candidate in ranked[: self._settings.rag_retrieval_limit]
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
    sparse_encoder: SparseEncoder | None = None
    reranker: CandidateReranker | None = None
    if settings.rag_retrieval_profile != "dense-v1":
        try:
            sparse_encoder = FastEmbedBM25Encoder(settings.phase5_model_cache_dir)
        except Exception:
            sparse_encoder = None
    if settings.rag_retrieval_profile == "hybrid-rerank-v1":
        try:
            reranker = FastEmbedCandidateReranker(
                settings.phase5_model_cache_dir,
                threads=settings.rag_model_threads,
                max_characters=settings.rag_rerank_max_characters,
            )
        except Exception:
            reranker = None
    return QdrantOpenAIRAGEngine(settings, qdrant, sparse_encoder, reranker)


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
    payload, document_id, version_id, _ = _authorized_payload(point, request)
    return RAGCitation(
        document_id=document_id,
        document_version_id=version_id,
        document_title=str(payload.get("document_title", "Document")),
        page_number=_payload_page(payload),
        content_type=str(payload.get("content_type", "text")),
        excerpt=str(payload.get("content", ""))[:1000],
        score=float(point.score) if point.score is not None else None,
    )


def _authorized_candidate(point: Any, request: RAGRequest) -> RetrievalCandidate:
    payload, document_id, version_id, generation_id = _authorized_payload(point, request)
    point_id = str(getattr(point, "id", "")).strip()
    if not point_id:
        raise RAGUnavailableError("Retrieved evidence failed authorization validation")
    try:
        chunk_index = int(payload["chunk_index"])
        score = float(point.score)
    except (KeyError, TypeError, ValueError) as exc:
        raise RAGUnavailableError("Retrieved evidence failed authorization validation") from exc
    if chunk_index < 0:
        raise RAGUnavailableError("Retrieved evidence failed authorization validation")
    return RetrievalCandidate(
        point_id=point_id,
        document_id=document_id,
        document_version_id=version_id,
        generation_id=generation_id,
        document_title=str(payload.get("document_title", "Document")),
        page_number=_payload_page(payload),
        content_type=str(payload.get("content_type", "text")),
        content=str(payload.get("content", "")),
        chunk_index=chunk_index,
        score=score,
    )


def _authorized_payload(
    point: Any, request: RAGRequest
) -> tuple[dict[str, Any], UUID, UUID, UUID]:
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
    return payload, document_id, version_id, generation_id


def _candidate_citation(candidate: RetrievalCandidate) -> RAGCitation:
    return RAGCitation(
        document_id=candidate.document_id,
        document_version_id=candidate.document_version_id,
        document_title=candidate.document_title,
        content_type=candidate.content_type,
        excerpt=candidate.content[:1000],
        page_number=candidate.page_number,
        score=candidate.score,
    )


def _payload_page(payload: dict[str, Any]) -> int | None:
    value = payload.get("page_number")
    if value is None:
        return None
    try:
        page_number = int(value)
    except (TypeError, ValueError) as exc:
        raise RAGUnavailableError("Retrieved evidence failed authorization validation") from exc
    if page_number <= 0:
        raise RAGUnavailableError("Retrieved evidence failed authorization validation")
    return page_number
