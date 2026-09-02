from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

from backend.app.retrieval.ranking import (
    hybrid_v2_profile_fingerprint,
    hybrid_v3_profile_fingerprint,
)

CURRENT_DATASET_REVISION = "phase5-retrieval-v4"
PHASE5_V3_DATASET_REVISION = "phase5-retrieval-v3"
SUPPORTED_DATASET_REVISIONS = {
    "phase5-retrieval-v1",
    "phase5-retrieval-v2",
    PHASE5_V3_DATASET_REVISION,
    CURRENT_DATASET_REVISION,
}
QUALITY_CONTRACT_V1 = "phase5-quality-v1"
QUALITY_CONTRACT_V2 = "phase5-quality-v2"
QUERY_CLASSES = {
    "semantic_paraphrase",
    "exact_identifier",
    "multi_document",
    "negative",
}
ANSWERABLE_QUERY_CLASSES = (
    "semantic_paraphrase",
    "exact_identifier",
    "multi_document",
)
SPLIT_COUNTS_BY_REVISION = {
    "phase5-retrieval-v1": {"tune": 30, "validation": 10, "holdout": 10},
    "phase5-retrieval-v2": {"tune": 30, "validation": 10, "holdout": 10},
    PHASE5_V3_DATASET_REVISION: {"tune": 48, "validation": 16, "holdout": 16},
    CURRENT_DATASET_REVISION: {"tune": 48, "validation": 16, "holdout": 16},
}


class EvaluationContractError(ValueError):
    """Raised when fixtures, judgments, or results violate the evaluation contract."""


@dataclass(frozen=True, slots=True)
class EvaluationDocument:
    chunk_id: str
    document_id: str
    content: str
    fixture_role: Literal["evidence", "confounder"] | None = None


@dataclass(frozen=True, slots=True)
class EvaluationQuery:
    query_id: str
    split: Literal["tune", "validation", "holdout"]
    query_class: str
    query: str
    allowed_document_ids: frozenset[str]
    answerable: bool
    relevance: dict[str, int]
    negative_kind: Literal["unanswerable", "unauthorized_scope"] | None = None
    excluded_relevant_chunk_ids: frozenset[str] = frozenset()
    dataset_revision: str = "phase5-retrieval-v1"


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    query_id: str
    ranked_chunk_ids: tuple[str, ...]
    latency_ms: float
    provider_calls: int = 0
    estimated_cost_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    query_count: int
    recall_at_10: float
    mrr_at_10: float
    ndcg_at_10: float
    source_coverage_at_10: float
    unanswerable_empty_accuracy: float
    excluded_candidate_count: int
    unauthorized_candidate_count: int
    unknown_candidate_count: int
    p50_latency_ms: float
    p95_latency_ms: float
    provider_calls: int
    estimated_cost_usd: float


def load_dataset(root: Path) -> tuple[dict[str, EvaluationDocument], list[EvaluationQuery]]:
    manifest = verify_manifest(root)
    revision = str(manifest["dataset_revision"])
    document_rows = _jsonl(root / "documents.jsonl")
    judgment_rows = _jsonl(root / "judgments.jsonl")
    documents = _parse_documents(document_rows, revision)
    queries = _parse_queries(judgment_rows, documents, revision)
    _validate_distribution(queries, revision)
    if revision == "phase5-retrieval-v2":
        _validate_v2_contract(manifest, documents, queries)
    elif revision == PHASE5_V3_DATASET_REVISION:
        _validate_v3_contract(manifest, documents, queries)
    elif revision == CURRENT_DATASET_REVISION:
        _validate_v4_contract(root, manifest, documents, queries)
    return documents, queries


def load_results(path: Path) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    seen: set[str] = set()
    for row in _jsonl(path):
        query_id = _required_text(row, "query_id")
        if query_id in seen:
            raise EvaluationContractError(f"Duplicate result query_id: {query_id}")
        seen.add(query_id)
        ranked = row.get("ranked_chunk_ids")
        if not isinstance(ranked, list) or any(not isinstance(item, str) for item in ranked):
            raise EvaluationContractError(f"Invalid ranked_chunk_ids for {query_id}")
        if len(ranked) != len(set(ranked)):
            raise EvaluationContractError(f"Duplicate ranked candidate for {query_id}")
        results.append(
            EvaluationResult(
                query_id=query_id,
                ranked_chunk_ids=tuple(ranked),
                latency_ms=_nonnegative_number(row, "latency_ms"),
                provider_calls=int(_nonnegative_number(row, "provider_calls", default=0)),
                estimated_cost_usd=_nonnegative_number(row, "estimated_cost_usd", default=0),
            )
        )
    return results


def evaluate(
    documents: dict[str, EvaluationDocument],
    queries: Iterable[EvaluationQuery],
    results: Iterable[EvaluationResult],
    *,
    split: str | None = None,
) -> EvaluationMetrics:
    query_list = list(queries)
    selected = {query.query_id: query for query in query_list if split in {None, query.split}}
    known_query_ids = {query.query_id for query in query_list}
    supplied = {result.query_id: result for result in results}
    by_query = {query_id: supplied[query_id] for query_id in selected if query_id in supplied}
    missing = sorted(set(selected) - set(by_query))
    extra = sorted(set(supplied) - known_query_ids)
    if missing or extra:
        raise EvaluationContractError(f"Result coverage mismatch: missing={missing}, extra={extra}")

    recall: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcg: list[float] = []
    source_coverage: list[float] = []
    unanswerable_empty: list[float] = []
    excluded = 0
    unauthorized = 0
    unknown = 0
    latencies: list[float] = []
    provider_calls = 0
    cost = 0.0

    for query_id, query in selected.items():
        result = by_query[query_id]
        ranked = result.ranked_chunk_ids[:10]
        known_ranked = [chunk_id for chunk_id in ranked if chunk_id in documents]
        unknown += len(ranked) - len(known_ranked)
        unauthorized += sum(
            documents[chunk_id].document_id not in query.allowed_document_ids
            for chunk_id in known_ranked
        )
        excluded += sum(chunk_id in query.excluded_relevant_chunk_ids for chunk_id in ranked)
        relevant = query.relevance
        if query.answerable:
            hits = [chunk_id for chunk_id in known_ranked if chunk_id in relevant]
            recall.append(len(set(hits)) / len(relevant))
            first = next(
                (
                    rank
                    for rank, chunk_id in enumerate(known_ranked, start=1)
                    if chunk_id in relevant
                ),
                None,
            )
            reciprocal_ranks.append(0.0 if first is None else 1.0 / first)
            gains = [relevant.get(chunk_id, 0) for chunk_id in known_ranked]
            ideal = sorted(relevant.values(), reverse=True)[:10]
            ndcg.append(_dcg(gains) / _dcg(ideal))
            relevant_sources = {documents[chunk_id].document_id for chunk_id in relevant}
            retrieved_sources = {documents[chunk_id].document_id for chunk_id in hits}
            source_coverage.append(len(retrieved_sources) / len(relevant_sources))
        elif query.negative_kind == "unanswerable":
            # Retrieval emptiness is diagnostic only; answer-level abstention is tested separately.
            unanswerable_empty.append(1.0 if not known_ranked else 0.0)
        latencies.append(result.latency_ms)
        provider_calls += result.provider_calls
        cost += result.estimated_cost_usd

    return EvaluationMetrics(
        query_count=len(selected),
        recall_at_10=_mean(recall),
        mrr_at_10=_mean(reciprocal_ranks),
        ndcg_at_10=_mean(ndcg),
        source_coverage_at_10=_mean(source_coverage),
        unanswerable_empty_accuracy=_mean(unanswerable_empty),
        excluded_candidate_count=excluded,
        unauthorized_candidate_count=unauthorized,
        unknown_candidate_count=unknown,
        p50_latency_ms=statistics.median(latencies),
        p95_latency_ms=_percentile(latencies, 0.95),
        provider_calls=provider_calls,
        estimated_cost_usd=cost,
    )


def evaluate_by_class(
    documents: dict[str, EvaluationDocument],
    queries: Iterable[EvaluationQuery],
    results: Iterable[EvaluationResult],
    *,
    split: str,
) -> dict[str, EvaluationMetrics]:
    query_list = list(queries)
    result_list = list(results)
    by_class: dict[str, EvaluationMetrics] = {}
    for query_class in ANSWERABLE_QUERY_CLASSES:
        class_queries = [query for query in query_list if query.query_class == query_class]
        class_ids = {query.query_id for query in class_queries}
        class_results = [result for result in result_list if result.query_id in class_ids]
        by_class[query_class] = evaluate(
            documents,
            class_queries,
            class_results,
            split=split,
        )
    return by_class


def phase5_recall_target(dense_recall: float, *, quality_contract_revision: str) -> float:
    if quality_contract_revision == QUALITY_CONTRACT_V1:
        return dense_recall * 1.10
    if quality_contract_revision != QUALITY_CONTRACT_V2:
        raise EvaluationContractError("Unknown Phase 5 quality contract revision")
    if dense_recall > 10 / 11:
        return dense_recall + 0.10 * (1.0 - dense_recall)
    return dense_recall * 1.10


def phase5_gate(
    dense: EvaluationMetrics,
    hybrid: EvaluationMetrics,
    *,
    quality_contract_revision: str = QUALITY_CONTRACT_V2,
    dense_by_class: dict[str, EvaluationMetrics] | None = None,
    hybrid_by_class: dict[str, EvaluationMetrics] | None = None,
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    recall_target = phase5_recall_target(
        dense.recall_at_10,
        quality_contract_revision=quality_contract_revision,
    )
    if hybrid.recall_at_10 < recall_target:
        if quality_contract_revision == QUALITY_CONTRACT_V2 and dense.recall_at_10 > 10 / 11:
            failures.append("Recall@10 did not reduce remaining error by 10%")
        else:
            failures.append("Recall@10 did not improve by 10% relative")
    if hybrid.ndcg_at_10 < dense.ndcg_at_10 * 1.05:
        failures.append("nDCG@10 did not improve by 5% relative")
    if hybrid.mrr_at_10 < dense.mrr_at_10 * 0.98:
        failures.append("MRR@10 regressed beyond 2%")
    if (
        hybrid.excluded_candidate_count
        or hybrid.unauthorized_candidate_count
        or hybrid.unknown_candidate_count
    ):
        failures.append("Authorization or citation identity validation failed")
    latency_limit = max(dense.p95_latency_ms * 1.5, dense.p95_latency_ms + 200)
    if hybrid.p95_latency_ms > latency_limit:
        failures.append("p95 retrieval latency exceeded the accepted bound")
    if hybrid.provider_calls > dense.provider_calls:
        failures.append("Hybrid retrieval added paid/provider calls")

    if quality_contract_revision == QUALITY_CONTRACT_V2:
        if dense_by_class is None or hybrid_by_class is None:
            failures.append("Per-class quality metrics are missing")
        else:
            _apply_class_guardrails(dense_by_class, hybrid_by_class, failures)
    return not failures, failures


def _apply_class_guardrails(
    dense_by_class: dict[str, EvaluationMetrics],
    hybrid_by_class: dict[str, EvaluationMetrics],
    failures: list[str],
) -> None:
    if set(dense_by_class) != set(ANSWERABLE_QUERY_CLASSES) or set(hybrid_by_class) != set(
        ANSWERABLE_QUERY_CLASSES
    ):
        failures.append("Per-class quality metrics are incomplete")
        return

    for query_class in ANSWERABLE_QUERY_CLASSES:
        dense = dense_by_class[query_class]
        hybrid = hybrid_by_class[query_class]
        if hybrid.recall_at_10 < dense.recall_at_10:
            failures.append(f"{query_class} Recall@10 regressed")
        if hybrid.ndcg_at_10 < dense.ndcg_at_10 * 0.98:
            failures.append(f"{query_class} nDCG@10 regressed beyond 2%")
        if hybrid.mrr_at_10 < dense.mrr_at_10 * 0.98:
            failures.append(f"{query_class} MRR@10 regressed beyond 2%")

    lexical_gain = any(
        hybrid_by_class[query_class].recall_at_10 > dense_by_class[query_class].recall_at_10
        or hybrid_by_class[query_class].ndcg_at_10 > dense_by_class[query_class].ndcg_at_10
        or hybrid_by_class[query_class].source_coverage_at_10
        > dense_by_class[query_class].source_coverage_at_10
        for query_class in ("exact_identifier", "multi_document")
    )
    if not lexical_gain:
        failures.append("Exact-term and multi-document classes showed no measurable gain")


def verify_manifest(root: Path) -> dict[str, Any]:
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationContractError("Dataset manifest is unreadable") from exc
    if manifest.get("dataset_revision") not in SUPPORTED_DATASET_REVISIONS:
        raise EvaluationContractError("Dataset revision is invalid")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise EvaluationContractError("Dataset file hashes are missing")
    for relative_name, expected_hash in files.items():
        if not isinstance(relative_name, str) or not isinstance(expected_hash, str):
            raise EvaluationContractError("Dataset file hash entry is invalid")
        if _file_sha256(root / relative_name) != expected_hash:
            raise EvaluationContractError(f"Dataset file hash mismatch: {relative_name}")
    return manifest


def _parse_documents(rows: list[dict[str, Any]], revision: str) -> dict[str, EvaluationDocument]:
    documents: dict[str, EvaluationDocument] = {}
    for row in rows:
        if row.get("dataset_revision") != revision:
            raise EvaluationContractError("Document dataset revision is invalid")
        chunk_id = _required_text(row, "chunk_id")
        if chunk_id in documents:
            raise EvaluationContractError(f"Duplicate chunk_id: {chunk_id}")
        raw_fixture_role = row.get("fixture_role")
        if raw_fixture_role not in {None, "evidence", "confounder"}:
            raise EvaluationContractError(f"Invalid fixture role for {chunk_id}")
        fixture_role: Literal["evidence", "confounder"] | None
        if raw_fixture_role == "evidence":
            fixture_role = "evidence"
        elif raw_fixture_role == "confounder":
            fixture_role = "confounder"
        else:
            fixture_role = None
        documents[chunk_id] = EvaluationDocument(
            chunk_id=chunk_id,
            document_id=_required_text(row, "document_id"),
            content=_required_text(row, "content"),
            fixture_role=fixture_role,
        )
    if not documents:
        raise EvaluationContractError("Evaluation corpus is empty")
    return documents


def _parse_queries(
    rows: list[dict[str, Any]],
    documents: dict[str, EvaluationDocument],
    revision: str,
) -> list[EvaluationQuery]:
    queries: list[EvaluationQuery] = []
    seen: set[str] = set()
    workspace_documents = frozenset(document.document_id for document in documents.values())
    for row in rows:
        if row.get("dataset_revision") != revision:
            raise EvaluationContractError("Judgment dataset revision is invalid")
        query_id = _required_text(row, "query_id")
        if query_id in seen:
            raise EvaluationContractError(f"Duplicate query_id: {query_id}")
        seen.add(query_id)
        split = row.get("split")
        query_class = row.get("query_class")
        if split not in SPLIT_COUNTS_BY_REVISION[revision] or query_class not in QUERY_CLASSES:
            raise EvaluationContractError(f"Invalid classification for {query_id}")
        allowed = row.get("allowed_document_ids")
        relevance_rows = row.get("relevance")
        if (
            not isinstance(allowed, list)
            or not allowed
            or not all(isinstance(item, str) for item in allowed)
        ):
            raise EvaluationContractError(f"Invalid allowed scope for {query_id}")
        if "@workspace" in allowed:
            if allowed != ["@workspace"]:
                raise EvaluationContractError(f"Workspace scope cannot be combined for {query_id}")
            allowed_scope = workspace_documents
        else:
            allowed_scope = frozenset(allowed)
        if not isinstance(relevance_rows, list):
            raise EvaluationContractError(f"Invalid relevance for {query_id}")
        relevance: dict[str, int] = {}
        for item in relevance_rows:
            if not isinstance(item, dict):
                raise EvaluationContractError(f"Invalid relevance row for {query_id}")
            chunk_id = _required_text(item, "chunk_id")
            grade = item.get("grade")
            if chunk_id not in documents or not isinstance(grade, int) or grade not in {1, 2, 3}:
                raise EvaluationContractError(f"Invalid relevance identity for {query_id}")
            if documents[chunk_id].document_id not in allowed_scope or chunk_id in relevance:
                raise EvaluationContractError(f"Out-of-scope relevance for {query_id}")
            relevance[chunk_id] = grade
        answerable = row.get("answerable")
        if not isinstance(answerable, bool) or answerable != bool(relevance):
            raise EvaluationContractError(f"Answerability mismatch for {query_id}")
        negative_kind, excluded_relevance = _negative_contract(
            row, query_id, query_class, documents, allowed_scope
        )
        queries.append(
            EvaluationQuery(
                query_id=query_id,
                split=split,
                query_class=query_class,
                query=_required_text(row, "query"),
                allowed_document_ids=allowed_scope,
                answerable=answerable,
                relevance=relevance,
                negative_kind=negative_kind,
                excluded_relevant_chunk_ids=excluded_relevance,
                dataset_revision=revision,
            )
        )
    return queries


def _negative_contract(
    row: dict[str, Any],
    query_id: str,
    query_class: str,
    documents: dict[str, EvaluationDocument],
    allowed_scope: frozenset[str],
) -> tuple[Literal["unanswerable", "unauthorized_scope"] | None, frozenset[str]]:
    negative_kind = row.get("negative_kind")
    excluded = row.get("excluded_relevant_chunk_ids", [])
    if query_class != "negative":
        if negative_kind is not None or excluded:
            raise EvaluationContractError(f"Unexpected negative contract for {query_id}")
        return None, frozenset()
    if negative_kind not in {"unanswerable", "unauthorized_scope"}:
        raise EvaluationContractError(f"Invalid negative kind for {query_id}")
    if not isinstance(excluded, list) or any(not isinstance(item, str) for item in excluded):
        raise EvaluationContractError(f"Invalid excluded relevance for {query_id}")
    excluded_ids = frozenset(excluded)
    if negative_kind == "unanswerable" and excluded_ids:
        raise EvaluationContractError(f"Unanswerable query has excluded relevance: {query_id}")
    if negative_kind == "unauthorized_scope" and not excluded_ids:
        raise EvaluationContractError(f"Unauthorized query lacks excluded relevance: {query_id}")
    if any(
        chunk_id not in documents or documents[chunk_id].document_id in allowed_scope
        for chunk_id in excluded_ids
    ):
        raise EvaluationContractError(f"Excluded relevance is not out of scope: {query_id}")
    return negative_kind, excluded_ids


def _validate_distribution(queries: list[EvaluationQuery], revision: str) -> None:
    expected_split_counts = SPLIT_COUNTS_BY_REVISION[revision]
    if len(queries) != sum(expected_split_counts.values()):
        raise EvaluationContractError("The Phase 5 query count does not match its revision")
    split_counts = Counter(query.split for query in queries)
    if split_counts != expected_split_counts:
        raise EvaluationContractError(f"Invalid dataset split: {dict(split_counts)}")
    class_counts = Counter(query.query_class for query in queries)
    if (
        set(class_counts) != QUERY_CLASSES
        or max(class_counts.values()) - min(class_counts.values()) > 1
    ):
        raise EvaluationContractError("Query classes are not balanced")


def _validate_v2_contract(
    manifest: dict[str, Any],
    documents: dict[str, EvaluationDocument],
    queries: list[EvaluationQuery],
) -> None:
    if len(documents) < 120 or manifest.get("chunk_count") != len(documents):
        raise EvaluationContractError("Phase 5 v2 requires at least 120 hashed chunks")
    if manifest.get("query_count") != len(queries):
        raise EvaluationContractError("Phase 5 v2 manifest query count is invalid")
    if manifest.get("minimum_quality_candidate_pool") != 50:
        raise EvaluationContractError("Phase 5 v2 candidate-pool floor is invalid")
    if manifest.get("holdout_policy") != "validation-before-holdout":
        raise EvaluationContractError("Phase 5 v2 holdout policy is invalid")

    normalized_content = [_normalized(document.content) for document in documents.values()]
    normalized_queries = [_normalized(query.query) for query in queries]
    if len(normalized_content) != len(set(normalized_content)):
        raise EvaluationContractError("Phase 5 v2 contains duplicate chunk content")
    if len(normalized_queries) != len(set(normalized_queries)):
        raise EvaluationContractError("Phase 5 v2 contains duplicate query text")

    roles = Counter(document.fixture_role for document in documents.values())
    if roles != {"evidence": 24, "confounder": 96}:
        raise EvaluationContractError(f"Invalid Phase 5 v2 fixture roles: {dict(roles)}")
    per_document = Counter(document.document_id for document in documents.values())
    if len(per_document) != 12 or set(per_document.values()) != {10}:
        raise EvaluationContractError("Phase 5 v2 requires twelve ten-chunk documents")

    for query in queries:
        candidate_pool = sum(
            document.document_id in query.allowed_document_ids for document in documents.values()
        )
        if query.answerable and candidate_pool < 50:
            raise EvaluationContractError(
                f"Quality query {query.query_id} has an undersized candidate pool"
            )


def _validate_v3_contract(
    manifest: dict[str, Any],
    documents: dict[str, EvaluationDocument],
    queries: list[EvaluationQuery],
) -> None:
    _validate_v2_contract(manifest, documents, queries)
    if manifest.get("quality_contract_revision") != QUALITY_CONTRACT_V2:
        raise EvaluationContractError("Phase 5 v3 quality contract revision is invalid")
    if manifest.get("candidate_profile") != "hybrid-v2":
        raise EvaluationContractError("Phase 5 v3 candidate profile is invalid")
    if manifest.get("candidate_profile_fingerprint") != hybrid_v2_profile_fingerprint():
        raise EvaluationContractError("Phase 5 v3 candidate fingerprint is stale")
    if manifest.get("predecessor_holdout_policy") != "sealed-not-reused":
        raise EvaluationContractError("Phase 5 v3 predecessor holdout policy is invalid")

    _validate_protected_class_contract(queries, PHASE5_V3_DATASET_REVISION)


def _validate_v4_contract(
    root: Path,
    manifest: dict[str, Any],
    documents: dict[str, EvaluationDocument],
    queries: list[EvaluationQuery],
) -> None:
    _validate_v2_contract(manifest, documents, queries)
    if manifest.get("quality_contract_revision") != QUALITY_CONTRACT_V2:
        raise EvaluationContractError("Phase 5 v4 quality contract revision is invalid")
    if manifest.get("candidate_profile") != "hybrid-v3":
        raise EvaluationContractError("Phase 5 v4 candidate profile is invalid")
    if manifest.get("candidate_profile_fingerprint") != hybrid_v3_profile_fingerprint():
        raise EvaluationContractError("Phase 5 v4 candidate fingerprint is stale")
    if manifest.get("predecessor_holdout_policy") != "v1-v3-sealed-not-reused":
        raise EvaluationContractError("Phase 5 v4 predecessor holdout policy is invalid")
    if manifest.get("tuning_source_revision") != "phase5-retrieval-v3:tune":
        raise EvaluationContractError("Phase 5 v4 tuning source revision is invalid")
    _validate_protected_class_contract(queries, CURRENT_DATASET_REVISION)

    predecessor_rows = [
        row
        for revision in ("v1", "v2", "v3")
        for row in _jsonl(root.parent / revision / "judgments.jsonl")
        if row.get("split") in {"validation", "holdout"}
    ]
    predecessor_queries = {_normalized(_required_text(row, "query")) for row in predecessor_rows}
    protected_queries = {
        _normalized(query.query) for query in queries if query.split in {"validation", "holdout"}
    }
    if predecessor_queries & protected_queries:
        raise EvaluationContractError("Phase 5 v4 reuses protected predecessor query text")
    predecessor_ids = {_required_text(row, "query_id") for row in predecessor_rows}
    protected_ids = {
        query.query_id for query in queries if query.split in {"validation", "holdout"}
    }
    if predecessor_ids & protected_ids:
        raise EvaluationContractError("Phase 5 v4 reuses protected predecessor query IDs")
    if manifest.get("protected_query_sha256") != _protected_query_hash(protected_queries):
        raise EvaluationContractError("Phase 5 v4 protected query hash is invalid")
    if manifest.get("predecessor_protected_query_sha256") != _protected_query_hash(
        predecessor_queries
    ):
        raise EvaluationContractError("Phase 5 v4 predecessor query hash is invalid")

    v3_tune_rows = _jsonl(root.parent / "v3" / "judgments.jsonl")
    v3_tune_queries = {
        _normalized(_required_text(row, "query"))
        for row in v3_tune_rows
        if row.get("split") == "tune"
    }
    v4_tune_queries = {_normalized(query.query) for query in queries if query.split == "tune"}
    if v4_tune_queries != v3_tune_queries:
        raise EvaluationContractError("Phase 5 v4 tuning evidence changed from v3")


def _validate_protected_class_contract(queries: list[EvaluationQuery], revision: str) -> None:
    revision_label = revision.removeprefix("phase5-retrieval-")
    for split in SPLIT_COUNTS_BY_REVISION[revision]:
        split_queries = [query for query in queries if query.split == split]
        class_counts = Counter(query.query_class for query in split_queries)
        if any(class_counts[query_class] < 4 for query_class in QUERY_CLASSES):
            raise EvaluationContractError(
                f"Phase 5 {revision_label} {split} query classes are undersized"
            )
        negative_kinds = Counter(
            query.negative_kind for query in split_queries if query.query_class == "negative"
        )
        if not {"unanswerable", "unauthorized_scope"} <= set(negative_kinds):
            raise EvaluationContractError(
                f"Phase 5 {revision_label} {split} lacks both negative-query kinds"
            )


def _protected_query_hash(queries: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(sorted(queries)).encode()).hexdigest()


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        rows = [json.loads(line) for line in lines if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationContractError(f"Invalid JSONL file: {path.name}") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise EvaluationContractError(f"Invalid JSONL row: {path.name}")
    return rows


def _required_text(row: dict[str, Any], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EvaluationContractError(f"Missing text field: {field}")
    return value.strip()


def _nonnegative_number(
    row: dict[str, Any], field: str, *, default: float | int | None = None
) -> float:
    value = row.get(field, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise EvaluationContractError(f"Invalid numeric field: {field}")
    return float(value)


def _dcg(grades: Iterable[int]) -> float:
    return sum((2**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(grades, 1))


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 1.0


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * percentile) - 1)
    return ordered[index]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise EvaluationContractError(f"Dataset file is unreadable: {path.name}") from exc
    return digest.hexdigest()
