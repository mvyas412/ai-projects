from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

DATASET_REVISION = "phase5-retrieval-v1"
QUERY_CLASSES = {
    "semantic_paraphrase",
    "exact_identifier",
    "multi_document",
    "negative",
}
SPLIT_COUNTS = {"tune": 30, "validation": 10, "holdout": 10}


class EvaluationContractError(ValueError):
    """Raised when fixtures, judgments, or results violate the evaluation contract."""


@dataclass(frozen=True, slots=True)
class EvaluationDocument:
    chunk_id: str
    document_id: str
    content: str


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
    negative_empty_accuracy: float
    unauthorized_candidate_count: int
    unknown_candidate_count: int
    p50_latency_ms: float
    p95_latency_ms: float
    provider_calls: int
    estimated_cost_usd: float


def load_dataset(root: Path) -> tuple[dict[str, EvaluationDocument], list[EvaluationQuery]]:
    verify_manifest(root)
    document_rows = _jsonl(root / "documents.jsonl")
    judgment_rows = _jsonl(root / "judgments.jsonl")
    documents = _parse_documents(document_rows)
    queries = _parse_queries(judgment_rows, documents)
    _validate_distribution(queries)
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
    negative_correct: list[float] = []
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
        else:
            negative_correct.append(1.0 if not known_ranked else 0.0)
        latencies.append(result.latency_ms)
        provider_calls += result.provider_calls
        cost += result.estimated_cost_usd

    return EvaluationMetrics(
        query_count=len(selected),
        recall_at_10=_mean(recall),
        mrr_at_10=_mean(reciprocal_ranks),
        ndcg_at_10=_mean(ndcg),
        source_coverage_at_10=_mean(source_coverage),
        negative_empty_accuracy=_mean(negative_correct),
        unauthorized_candidate_count=unauthorized,
        unknown_candidate_count=unknown,
        p50_latency_ms=statistics.median(latencies),
        p95_latency_ms=_percentile(latencies, 0.95),
        provider_calls=provider_calls,
        estimated_cost_usd=cost,
    )


def phase5_gate(dense: EvaluationMetrics, hybrid: EvaluationMetrics) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if hybrid.recall_at_10 < dense.recall_at_10 * 1.10:
        failures.append("Recall@10 did not improve by 10% relative")
    if hybrid.ndcg_at_10 < dense.ndcg_at_10 * 1.05:
        failures.append("nDCG@10 did not improve by 5% relative")
    if hybrid.mrr_at_10 < dense.mrr_at_10 * 0.98:
        failures.append("MRR@10 regressed beyond 2%")
    if hybrid.unauthorized_candidate_count or hybrid.unknown_candidate_count:
        failures.append("Authorization or citation identity validation failed")
    if hybrid.negative_empty_accuracy < dense.negative_empty_accuracy:
        failures.append("Unanswerable-query false positives regressed")
    latency_limit = max(dense.p95_latency_ms * 1.5, dense.p95_latency_ms + 200)
    if hybrid.p95_latency_ms > latency_limit:
        failures.append("p95 retrieval latency exceeded the accepted bound")
    if hybrid.provider_calls > dense.provider_calls:
        failures.append("Hybrid retrieval added paid/provider calls")
    return not failures, failures


def verify_manifest(root: Path) -> None:
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationContractError("Dataset manifest is unreadable") from exc
    if manifest.get("dataset_revision") != DATASET_REVISION:
        raise EvaluationContractError("Dataset revision is invalid")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise EvaluationContractError("Dataset file hashes are missing")
    for relative_name, expected_hash in files.items():
        if not isinstance(relative_name, str) or not isinstance(expected_hash, str):
            raise EvaluationContractError("Dataset file hash entry is invalid")
        if _file_sha256(root / relative_name) != expected_hash:
            raise EvaluationContractError(f"Dataset file hash mismatch: {relative_name}")


def _parse_documents(rows: list[dict[str, Any]]) -> dict[str, EvaluationDocument]:
    documents: dict[str, EvaluationDocument] = {}
    for row in rows:
        if row.get("dataset_revision") != DATASET_REVISION:
            raise EvaluationContractError("Document dataset revision is invalid")
        chunk_id = _required_text(row, "chunk_id")
        if chunk_id in documents:
            raise EvaluationContractError(f"Duplicate chunk_id: {chunk_id}")
        documents[chunk_id] = EvaluationDocument(
            chunk_id=chunk_id,
            document_id=_required_text(row, "document_id"),
            content=_required_text(row, "content"),
        )
    if not documents:
        raise EvaluationContractError("Evaluation corpus is empty")
    return documents


def _parse_queries(
    rows: list[dict[str, Any]], documents: dict[str, EvaluationDocument]
) -> list[EvaluationQuery]:
    queries: list[EvaluationQuery] = []
    seen: set[str] = set()
    workspace_documents = frozenset(document.document_id for document in documents.values())
    for row in rows:
        if row.get("dataset_revision") != DATASET_REVISION:
            raise EvaluationContractError("Judgment dataset revision is invalid")
        query_id = _required_text(row, "query_id")
        if query_id in seen:
            raise EvaluationContractError(f"Duplicate query_id: {query_id}")
        seen.add(query_id)
        split = row.get("split")
        query_class = row.get("query_class")
        if split not in SPLIT_COUNTS or query_class not in QUERY_CLASSES:
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


def _validate_distribution(queries: list[EvaluationQuery]) -> None:
    if len(queries) < 50:
        raise EvaluationContractError("The first Phase 5 dataset requires at least 50 queries")
    split_counts = Counter(query.split for query in queries)
    if split_counts != SPLIT_COUNTS:
        raise EvaluationContractError(f"Invalid dataset split: {dict(split_counts)}")
    class_counts = Counter(query.query_class for query in queries)
    if (
        set(class_counts) != QUERY_CLASSES
        or max(class_counts.values()) - min(class_counts.values()) > 1
    ):
        raise EvaluationContractError("Query classes are not balanced")


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
