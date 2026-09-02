from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence
from uuid import UUID, uuid4, uuid5

import tiktoken
from langchain_openai import OpenAIEmbeddings
from qdrant_client import QdrantClient, models

from backend.app.core.config import Settings
from backend.app.rag.engine import (
    RAGDocumentScope,
    RAGRequest,
    _authorized_candidate,
    _retrieval_filter,
)
from backend.app.retrieval.evaluation import (
    QUALITY_CONTRACT_V1,
    QUALITY_CONTRACT_V2,
    EvaluationDocument,
    EvaluationMetrics,
    EvaluationQuery,
    EvaluationResult,
    evaluate,
    evaluate_by_class,
    phase5_gate,
)
from backend.app.retrieval.ranking import (
    FastEmbedCandidateReranker,
    RetrievalCandidate,
    diversify_candidates,
    hybrid_v2_profile_fingerprint,
    reciprocal_rank_fusion,
    rerank_with_timeout,
    select_hybrid_v2_fusion,
)
from backend.app.retrieval.scope import ensure_scope_payload_indexes
from backend.app.retrieval.sparse import SPARSE_VECTOR_NAME, FastEmbedBM25Encoder

BENCHMARK_NAMESPACE = UUID("43557cc4-1ed6-4b60-8f73-13d29fb76c0a")
BENCHMARK_WORKSPACE_ID = uuid5(BENCHMARK_NAMESPACE, "phase5-workspace")
PROFILE_NAMES = ("dense-v1", "hybrid-v1", "hybrid-v2", "hybrid-rerank-v1")


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    profiles: dict[str, dict[str, EvaluationMetrics]]
    class_metrics: dict[str, dict[str, dict[str, EvaluationMetrics]]]
    candidate_profile: str
    quality_contract_revision: str
    candidate_fingerprint: str
    embedding_model: str
    embedding_input_tokens: int
    provider_calls: int
    estimated_cost_usd: float
    validation_passed: bool
    validation_failures: tuple[str, ...]
    holdout_evaluated: bool
    holdout_passed: bool | None
    holdout_failures: tuple[str, ...]


def run_benchmark(
    *,
    settings: Settings,
    qdrant: QdrantClient,
    documents: dict[str, EvaluationDocument],
    queries: Sequence[EvaluationQuery],
    output_dir: Path,
    embedding_cost_per_million_tokens: float,
) -> BenchmarkReport:
    if settings.openai_api_key is None:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    if embedding_cost_per_million_tokens < 0:
        raise ValueError("Embedding cost must be nonnegative")
    dataset_revisions = {query.dataset_revision for query in queries}
    if len(dataset_revisions) != 1:
        raise ValueError("Benchmark queries must use one dataset revision")
    dataset_revision = next(iter(dataset_revisions))
    if dataset_revision == "phase5-retrieval-v3":
        candidate_profile = "hybrid-v2"
        quality_contract_revision = QUALITY_CONTRACT_V2
        _validate_v3_candidate_bounds(settings)
    else:
        candidate_profile = "hybrid-v1"
        quality_contract_revision = QUALITY_CONTRACT_V1

    ordered_documents = [documents[key] for key in sorted(documents)]
    embedding_inputs = [item.content for item in ordered_documents] + [
        query.query for query in queries
    ]
    started = time.perf_counter()
    dense_vectors = OpenAIEmbeddings(
        api_key=settings.openai_api_key,
        model=settings.openai_embedding_model,
    ).embed_documents(embedding_inputs)
    embedding_latency_ms = (time.perf_counter() - started) * 1000
    document_vectors = dense_vectors[: len(ordered_documents)]
    query_vectors = dense_vectors[len(ordered_documents) :]
    input_tokens = _embedding_token_count(settings.openai_embedding_model, embedding_inputs)
    estimated_cost = input_tokens * embedding_cost_per_million_tokens / 1_000_000

    sparse_encoder = FastEmbedBM25Encoder(settings.phase5_model_cache_dir)
    reranker = FastEmbedCandidateReranker(
        settings.phase5_model_cache_dir,
        threads=settings.rag_model_threads,
        max_characters=settings.rag_rerank_max_characters,
    )
    sparse_documents = sparse_encoder.embed_documents([item.content for item in ordered_documents])
    collection = f"phase5_benchmark_{uuid4().hex}"
    point_to_chunk = {
        str(uuid5(BENCHMARK_NAMESPACE, item.chunk_id)): item.chunk_id for item in ordered_documents
    }
    try:
        _create_collection(qdrant, collection, len(document_vectors[0]))
        _upsert_documents(
            qdrant,
            collection,
            ordered_documents,
            document_vectors,
            sparse_documents,
        )
        per_profile: dict[str, list[EvaluationResult]] = {profile: [] for profile in PROFILE_NAMES}
        embedding_share_ms = embedding_latency_ms / max(len(queries), 1)

        def run_query(index: int, query: EvaluationQuery) -> None:
            dense_vector = query_vectors[index]
            request = _request_for(query, ordered_documents)
            dense, dense_ms = _search_dense(qdrant, collection, request, dense_vector, settings)
            sparse, sparse_ms = _search_sparse(
                qdrant,
                collection,
                request,
                sparse_encoder.embed_query(query.query),
                settings,
            )
            fused_started = time.perf_counter()
            fused_v1 = diversify_candidates(
                reciprocal_rank_fusion(dense, sparse, k=settings.rag_fusion_k),
                document_count=len(query.allowed_document_ids),
                max_per_document=settings.rag_max_candidates_per_document,
                limit=settings.rag_rerank_candidate_limit,
            )
            v2_policy = select_hybrid_v2_fusion(query.query)
            fused_v2 = diversify_candidates(
                reciprocal_rank_fusion(
                    dense,
                    sparse,
                    k=v2_policy.k,
                    dense_weight=v2_policy.dense_weight,
                    sparse_weight=v2_policy.sparse_weight,
                ),
                document_count=len(query.allowed_document_ids),
                max_per_document=settings.rag_max_candidates_per_document,
                limit=settings.rag_rerank_candidate_limit,
            )
            fusion_ms = (time.perf_counter() - fused_started) * 1000
            rerank_started = time.perf_counter()
            reranked = rerank_with_timeout(
                reranker,
                query.query,
                fused_v1,
                timeout_seconds=settings.rag_rerank_timeout_seconds,
            )
            rerank_ms = (time.perf_counter() - rerank_started) * 1000
            first_result = not per_profile["dense-v1"]
            provider_calls = 1 if first_result else 0
            cost = estimated_cost if first_result else 0.0
            per_profile["dense-v1"].append(
                _result(
                    query,
                    dense,
                    point_to_chunk,
                    embedding_share_ms + dense_ms,
                    provider_calls,
                    cost,
                )
            )
            per_profile["hybrid-v1"].append(
                _result(
                    query,
                    fused_v1,
                    point_to_chunk,
                    embedding_share_ms + dense_ms + sparse_ms + fusion_ms,
                    provider_calls,
                    cost,
                )
            )
            per_profile["hybrid-v2"].append(
                _result(
                    query,
                    fused_v2,
                    point_to_chunk,
                    embedding_share_ms + dense_ms + sparse_ms + fusion_ms,
                    provider_calls,
                    cost,
                )
            )
            per_profile["hybrid-rerank-v1"].append(
                _result(
                    query,
                    reranked,
                    point_to_chunk,
                    embedding_share_ms + dense_ms + sparse_ms + fusion_ms + rerank_ms,
                    provider_calls,
                    cost,
                )
            )

        # Tune and validation are scored first. Holdout retrieval is not executed until
        # the accepted validation gate passes, preventing accidental holdout tuning.
        for index, query in enumerate(queries):
            if query.split != "holdout":
                run_query(index, query)

        profiles = {
            profile: {
                split: evaluate(documents, queries, results, split=split)
                for split in ("tune", "validation")
            }
            for profile, results in per_profile.items()
        }
        class_metrics = {
            profile: {
                split: evaluate_by_class(documents, queries, results, split=split)
                for split in ("tune", "validation")
            }
            for profile, results in per_profile.items()
        }
        validation_passed, validation_failures = phase5_gate(
            profiles["dense-v1"]["validation"],
            profiles[candidate_profile]["validation"],
            quality_contract_revision=quality_contract_revision,
            dense_by_class=class_metrics["dense-v1"]["validation"],
            hybrid_by_class=class_metrics[candidate_profile]["validation"],
        )
        holdout_passed: bool | None = None
        holdout_failures: list[str] = []
        if validation_passed:
            for index, query in enumerate(queries):
                if query.split == "holdout":
                    run_query(index, query)
            for profile, results in per_profile.items():
                profiles[profile]["holdout"] = evaluate(
                    documents, queries, results, split="holdout"
                )
                class_metrics[profile]["holdout"] = evaluate_by_class(
                    documents, queries, results, split="holdout"
                )
            holdout_passed, holdout_failures = phase5_gate(
                profiles["dense-v1"]["holdout"],
                profiles[candidate_profile]["holdout"],
                quality_contract_revision=quality_contract_revision,
                dense_by_class=class_metrics["dense-v1"]["holdout"],
                hybrid_by_class=class_metrics[candidate_profile]["holdout"],
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        for profile, results in per_profile.items():
            _write_results(output_dir / f"{profile}.jsonl", results)
        return BenchmarkReport(
            profiles=profiles,
            class_metrics=class_metrics,
            candidate_profile=candidate_profile,
            quality_contract_revision=quality_contract_revision,
            candidate_fingerprint=hybrid_v2_profile_fingerprint(),
            embedding_model=settings.openai_embedding_model,
            embedding_input_tokens=input_tokens,
            provider_calls=1,
            estimated_cost_usd=estimated_cost,
            validation_passed=validation_passed,
            validation_failures=tuple(validation_failures),
            holdout_evaluated=validation_passed,
            holdout_passed=holdout_passed,
            holdout_failures=tuple(holdout_failures),
        )
    finally:
        if qdrant.collection_exists(collection):
            qdrant.delete_collection(collection)


def report_json(report: BenchmarkReport) -> str:
    return json.dumps(asdict(report), sort_keys=True, indent=2)


def _validate_v3_candidate_bounds(settings: Settings) -> None:
    actual = (
        settings.rag_dense_candidate_limit,
        settings.rag_sparse_candidate_limit,
        settings.rag_rerank_candidate_limit,
        settings.rag_retrieval_limit,
        settings.rag_max_candidates_per_document,
    )
    if actual != (30, 30, 20, 8, 3):
        raise ValueError("Phase 5 v3 requires the frozen 30/30/20/8 candidate and diversity bounds")


def _create_collection(qdrant: QdrantClient, collection: str, vector_size: int) -> None:
    qdrant.create_collection(
        collection_name=collection,
        vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: models.SparseVectorParams(modifier=models.Modifier.IDF)
        },
    )
    ensure_scope_payload_indexes(qdrant, collection)


def _upsert_documents(
    qdrant: QdrantClient,
    collection: str,
    documents: Sequence[EvaluationDocument],
    dense_vectors: Sequence[list[float]],
    sparse_vectors: Sequence[models.SparseVector],
) -> None:
    points: list[models.PointStruct] = []
    for index, (document, dense, sparse) in enumerate(
        zip(documents, dense_vectors, sparse_vectors, strict=True)
    ):
        document_id, version_id, generation_id = _document_identity(document.document_id)
        points.append(
            models.PointStruct(
                id=str(uuid5(BENCHMARK_NAMESPACE, document.chunk_id)),
                vector={"": dense, SPARSE_VECTOR_NAME: sparse},
                payload={
                    "tenant_id": str(BENCHMARK_WORKSPACE_ID),
                    "workspace_id": str(BENCHMARK_WORKSPACE_ID),
                    "document_id": str(document_id),
                    "document_version_id": str(version_id),
                    "generation_id": str(generation_id),
                    "document_title": document.document_id,
                    "content_type": "text/plain",
                    "content": document.content,
                    "chunk_index": index,
                },
            )
        )
    qdrant.upsert(collection_name=collection, points=points, wait=True)


def _request_for(query: EvaluationQuery, documents: Sequence[EvaluationDocument]) -> RAGRequest:
    known = {document.document_id for document in documents}
    if not query.allowed_document_ids <= known:
        raise RuntimeError("Benchmark query contains an unknown document scope")
    scopes = tuple(
        RAGDocumentScope(*_document_identity(document_id), sparse_available=True)
        for document_id in sorted(query.allowed_document_ids)
    )
    return RAGRequest(BENCHMARK_WORKSPACE_ID, scopes, query.query, ())


def _search_dense(
    qdrant: QdrantClient,
    collection: str,
    request: RAGRequest,
    vector: list[float],
    settings: Settings,
) -> tuple[list[RetrievalCandidate], float]:
    started = time.perf_counter()
    points = qdrant.query_points(
        collection_name=collection,
        query=vector,
        query_filter=_retrieval_filter(request),
        limit=settings.rag_dense_candidate_limit,
        with_payload=True,
    ).points
    return (
        [_authorized_candidate(point, request) for point in points],
        (time.perf_counter() - started) * 1000,
    )


def _search_sparse(
    qdrant: QdrantClient,
    collection: str,
    request: RAGRequest,
    vector: models.SparseVector,
    settings: Settings,
) -> tuple[list[RetrievalCandidate], float]:
    started = time.perf_counter()
    points = qdrant.query_points(
        collection_name=collection,
        query=vector,
        using=SPARSE_VECTOR_NAME,
        query_filter=_retrieval_filter(request),
        limit=settings.rag_sparse_candidate_limit,
        with_payload=True,
    ).points
    return (
        [_authorized_candidate(point, request) for point in points],
        (time.perf_counter() - started) * 1000,
    )


def _result(
    query: EvaluationQuery,
    candidates: Sequence[RetrievalCandidate],
    point_to_chunk: dict[str, str],
    latency_ms: float,
    provider_calls: int,
    estimated_cost_usd: float,
) -> EvaluationResult:
    return EvaluationResult(
        query_id=query.query_id,
        ranked_chunk_ids=tuple(
            point_to_chunk.get(candidate.point_id, f"unknown:{candidate.point_id}")
            for candidate in candidates[:10]
        ),
        latency_ms=latency_ms,
        provider_calls=provider_calls,
        estimated_cost_usd=estimated_cost_usd,
    )


def _document_identity(document_id: str) -> tuple[UUID, UUID, UUID]:
    return (
        uuid5(BENCHMARK_NAMESPACE, document_id),
        uuid5(BENCHMARK_NAMESPACE, f"{document_id}:version"),
        uuid5(BENCHMARK_NAMESPACE, f"{document_id}:generation"),
    )


def _embedding_token_count(model: str, inputs: Sequence[str]) -> int:
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return sum(len(encoding.encode(text)) for text in inputs)


def _write_results(path: Path, results: Sequence[EvaluationResult]) -> None:
    path.write_text(
        "".join(json.dumps(asdict(result), sort_keys=True) + "\n" for result in results),
        encoding="utf-8",
    )
