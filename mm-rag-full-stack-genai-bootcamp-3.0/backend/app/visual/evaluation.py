from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Literal

DATASET_REVISION = "phase6-visual-table-v1"
QUALITY_CONTRACT_REVISION = "phase6-quality-v1"
QUESTION_CLASSES = (
    "figure_relationship",
    "chart",
    "table_lookup",
    "calculation",
    "negative",
)
ANSWERABLE_CLASSES = QUESTION_CLASSES[:-1]
SPLIT_CLASS_COUNTS = {
    "tune": {
        "figure_relationship": 10,
        "chart": 10,
        "table_lookup": 10,
        "calculation": 9,
        "negative": 9,
    },
    "validation": {
        "figure_relationship": 3,
        "chart": 3,
        "table_lookup": 3,
        "calculation": 4,
        "negative": 3,
    },
    "holdout": {
        "figure_relationship": 3,
        "chart": 3,
        "table_lookup": 3,
        "calculation": 3,
        "negative": 4,
    },
}


class Phase6EvaluationError(ValueError):
    """Raised when Phase 6 fixtures or results violate the accepted contract."""


@dataclass(frozen=True, slots=True)
class VisualRegion:
    region_id: str
    split: Literal["tune", "validation", "holdout"]
    document_id: str
    document_version_id: str
    generation_id: str
    page_number: int
    region_kind: str
    bbox: tuple[float, float, float, float]
    source_text: str
    baseline_text: str


@dataclass(frozen=True, slots=True)
class VisualQuestion:
    query_id: str
    split: Literal["tune", "validation", "holdout"]
    query_class: str
    query: str
    allowed_document_ids: frozenset[str]
    answerable: bool
    relevance: dict[str, int]
    negative_kind: str | None = None
    excluded_relevant_region_ids: frozenset[str] = frozenset()
    expected_operation: str | None = None
    expected_value: str | None = None
    expected_unit: str | None = None


@dataclass(frozen=True, slots=True)
class VisualEvaluationResult:
    query_id: str
    ranked_region_ids: tuple[str, ...]
    cited_region_ids: tuple[str, ...] = ()
    latency_ms: float = 0.0
    provider_calls: int = 0
    estimated_cost_usd: float = 0.0
    calculation_correct: bool | None = None
    abstained: bool = False


@dataclass(frozen=True, slots=True)
class VisualEvaluationMetrics:
    query_count: int
    recall_at_10: float
    mrr_at_10: float
    ndcg_at_10: float
    source_coverage_at_10: float
    calculation_accuracy: float
    safe_abstention_accuracy: float
    excluded_candidate_count: int
    unauthorized_candidate_count: int
    unknown_candidate_count: int
    invalid_citation_count: int
    p50_latency_ms: float
    p95_latency_ms: float
    provider_calls: int
    estimated_cost_usd: float


@dataclass(frozen=True, slots=True)
class Phase6GateResult:
    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProtectedEvaluation:
    validation: VisualEvaluationMetrics
    validation_by_class: dict[str, VisualEvaluationMetrics]
    gate: Phase6GateResult
    holdout: VisualEvaluationMetrics | None


def load_dataset(root: Path) -> tuple[dict[str, VisualRegion], list[VisualQuestion]]:
    manifest = verify_manifest(root)
    regions = _parse_regions(_jsonl(root / "regions.jsonl"))
    questions = _parse_questions(_jsonl(root / "judgments.jsonl"), regions)
    _validate_distribution(regions, questions)
    if manifest.get("region_count") != len(regions) or manifest.get("query_count") != len(
        questions
    ):
        raise Phase6EvaluationError("Manifest counts do not match the Phase 6 corpus")
    protected = [q.query.casefold().strip() for q in questions if q.split != "tune"]
    if manifest.get("protected_query_sha256") != _canonical_sha256(protected):
        raise Phase6EvaluationError("Protected query fingerprint does not match")
    return regions, questions


def verify_manifest(root: Path) -> dict[str, Any]:
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase6EvaluationError("Dataset manifest is unreadable") from exc
    if manifest.get("dataset_revision") != DATASET_REVISION:
        raise Phase6EvaluationError("Dataset revision is invalid")
    if manifest.get("quality_contract_revision") != QUALITY_CONTRACT_REVISION:
        raise Phase6EvaluationError("Quality contract revision is invalid")
    if manifest.get("holdout_policy") != "validation-before-holdout":
        raise Phase6EvaluationError("Holdout policy is invalid")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise Phase6EvaluationError("Dataset file hashes are missing")
    for name, expected_hash in files.items():
        if not isinstance(name, str) or not isinstance(expected_hash, str):
            raise Phase6EvaluationError("Dataset file hash entry is invalid")
        if _file_sha256(root / name) != expected_hash:
            raise Phase6EvaluationError(f"Dataset file hash mismatch: {name}")
    return manifest


def evaluate(
    regions: dict[str, VisualRegion],
    questions: Iterable[VisualQuestion],
    results: Iterable[VisualEvaluationResult],
    *,
    split: str,
) -> VisualEvaluationMetrics:
    all_questions = list(questions)
    result_list = list(results)
    selected = {question.query_id: question for question in all_questions if question.split == split}
    known_query_ids = {question.query_id for question in all_questions}
    supplied = {result.query_id: result for result in result_list}
    if len(supplied) != len(result_list):
        raise Phase6EvaluationError("Duplicate result query_id")
    missing = sorted(set(selected) - set(supplied))
    extra = sorted(set(supplied) - known_query_ids)
    if missing or extra:
        raise Phase6EvaluationError(f"Result coverage mismatch: missing={missing}, extra={extra}")

    recall: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcg: list[float] = []
    source_coverage: list[float] = []
    calculations: list[float] = []
    abstentions: list[float] = []
    excluded = unauthorized = unknown = invalid_citations = 0
    latencies: list[float] = []
    provider_calls = 0
    estimated_cost = 0.0

    for query_id, question in selected.items():
        result = supplied[query_id]
        ranked = result.ranked_region_ids[:10]
        known_ranked = [region_id for region_id in ranked if region_id in regions]
        unknown += len(ranked) - len(known_ranked)
        unauthorized += sum(
            regions[region_id].document_id not in question.allowed_document_ids
            for region_id in known_ranked
        )
        excluded += sum(region_id in question.excluded_relevant_region_ids for region_id in ranked)

        for citation_id in result.cited_region_ids:
            if (
                citation_id not in regions
                or citation_id not in known_ranked
                or regions[citation_id].document_id not in question.allowed_document_ids
            ):
                invalid_citations += 1

        if question.answerable:
            hits = [region_id for region_id in known_ranked if region_id in question.relevance]
            recall.append(len(set(hits)) / len(question.relevance))
            first = next(
                (
                    rank
                    for rank, region_id in enumerate(known_ranked, start=1)
                    if region_id in question.relevance
                ),
                None,
            )
            reciprocal_ranks.append(0.0 if first is None else 1.0 / first)
            gains = [question.relevance.get(region_id, 0) for region_id in known_ranked]
            ideal = sorted(question.relevance.values(), reverse=True)[:10]
            ndcg.append(_dcg(gains) / _dcg(ideal))
            relevant_documents = {
                regions[region_id].document_id for region_id in question.relevance
            }
            retrieved_documents = {regions[region_id].document_id for region_id in hits}
            source_coverage.append(len(retrieved_documents) / len(relevant_documents))
            if question.query_class == "calculation":
                calculations.append(1.0 if result.calculation_correct is True else 0.0)
        else:
            abstentions.append(1.0 if result.abstained else 0.0)

        latencies.append(result.latency_ms)
        provider_calls += result.provider_calls
        estimated_cost += result.estimated_cost_usd

    return VisualEvaluationMetrics(
        query_count=len(selected),
        recall_at_10=_mean(recall),
        mrr_at_10=_mean(reciprocal_ranks),
        ndcg_at_10=_mean(ndcg),
        source_coverage_at_10=_mean(source_coverage),
        calculation_accuracy=_mean(calculations),
        safe_abstention_accuracy=_mean(abstentions),
        excluded_candidate_count=excluded,
        unauthorized_candidate_count=unauthorized,
        unknown_candidate_count=unknown,
        invalid_citation_count=invalid_citations,
        p50_latency_ms=statistics.median(latencies),
        p95_latency_ms=_percentile(latencies, 0.95),
        provider_calls=provider_calls,
        estimated_cost_usd=estimated_cost,
    )


def evaluate_by_class(
    regions: dict[str, VisualRegion],
    questions: Iterable[VisualQuestion],
    results: Iterable[VisualEvaluationResult],
    *,
    split: str,
) -> dict[str, VisualEvaluationMetrics]:
    question_list = list(questions)
    result_list = list(results)
    output: dict[str, VisualEvaluationMetrics] = {}
    for query_class in ANSWERABLE_CLASSES:
        class_questions = [q for q in question_list if q.query_class == query_class]
        class_ids = {q.query_id for q in class_questions}
        class_results = [result for result in result_list if result.query_id in class_ids]
        output[query_class] = evaluate(
            regions,
            class_questions,
            class_results,
            split=split,
        )
    return output


def lexical_baseline_results(
    regions: dict[str, VisualRegion],
    questions: Iterable[VisualQuestion],
    *,
    split: str,
) -> list[VisualEvaluationResult]:
    """Reproduce the pre-Phase-6 OCR/Markdown-only retrieval baseline."""

    results: list[VisualEvaluationResult] = []
    for question in questions:
        if question.split != split:
            continue
        query_tokens = _tokens(question.query)
        candidates: list[tuple[int, str]] = []
        for region in regions.values():
            if region.document_id not in question.allowed_document_ids:
                continue
            score = len(query_tokens & _tokens(region.baseline_text))
            if score:
                candidates.append((score, region.region_id))
        ranked = tuple(region_id for _, region_id in sorted(candidates, key=lambda row: (-row[0], row[1])))
        results.append(
            VisualEvaluationResult(
                query_id=question.query_id,
                ranked_region_ids=ranked,
                cited_region_ids=ranked[:1],
                latency_ms=1.0,
                calculation_correct=False if question.query_class == "calculation" else None,
                abstained=not ranked,
            )
        )
    return results


def phase6_gate(
    baseline: VisualEvaluationMetrics,
    candidate: VisualEvaluationMetrics,
    *,
    baseline_by_class: dict[str, VisualEvaluationMetrics],
    candidate_by_class: dict[str, VisualEvaluationMetrics],
    text_baseline_recall: float,
    text_candidate_recall: float,
    text_baseline_mrr: float,
    text_candidate_mrr: float,
    max_p95_latency_ms: float,
    max_provider_calls: int,
) -> Phase6GateResult:
    failures: list[str] = []
    recall_target = baseline.recall_at_10 + 0.10 * (1.0 - baseline.recall_at_10)
    if candidate.recall_at_10 < recall_target:
        failures.append("Recall@10 did not reduce remaining error by 10%")
    if candidate.ndcg_at_10 < baseline.ndcg_at_10 * 1.05:
        failures.append("nDCG@10 did not improve by 5% relative")
    if set(baseline_by_class) != set(ANSWERABLE_CLASSES) or set(candidate_by_class) != set(
        ANSWERABLE_CLASSES
    ):
        failures.append("Per-class quality metrics are incomplete")
    else:
        for query_class in ANSWERABLE_CLASSES:
            baseline_class = baseline_by_class[query_class]
            candidate_class = candidate_by_class[query_class]
            if candidate_class.recall_at_10 < baseline_class.recall_at_10:
                failures.append(f"{query_class} Recall@10 regressed")
            if candidate_class.ndcg_at_10 < baseline_class.ndcg_at_10:
                failures.append(f"{query_class} nDCG@10 regressed")
    if any(
        (
            candidate.excluded_candidate_count,
            candidate.unauthorized_candidate_count,
            candidate.unknown_candidate_count,
            candidate.invalid_citation_count,
        )
    ):
        failures.append("Authorization or citation-region identity validation failed")
    if candidate.calculation_accuracy < 1.0:
        failures.append("Supported exact calculations were not 100% correct")
    if candidate.safe_abstention_accuracy < 1.0:
        failures.append("Ambiguous, unsupported, or unauthorized questions did not all abstain")
    if text_candidate_recall < text_baseline_recall * 0.98:
        failures.append("Text-only Recall@10 regressed beyond 2%")
    if text_candidate_mrr < text_baseline_mrr * 0.98:
        failures.append("Text-only MRR@10 regressed beyond 2%")
    if candidate.p95_latency_ms > max_p95_latency_ms:
        failures.append("p95 retrieval latency exceeded the frozen budget")
    if candidate.provider_calls > max_provider_calls:
        failures.append("Provider calls exceeded the frozen budget")
    return Phase6GateResult(not failures, tuple(failures))


def evaluate_validation_then_holdout(
    *,
    regions: dict[str, VisualRegion],
    questions: list[VisualQuestion],
    baseline_validation: VisualEvaluationMetrics,
    baseline_validation_by_class: dict[str, VisualEvaluationMetrics],
    validation_results: list[VisualEvaluationResult],
    holdout_results_factory: Callable[[], list[VisualEvaluationResult]],
    text_baseline_recall: float,
    text_candidate_recall: float,
    text_baseline_mrr: float,
    text_candidate_mrr: float,
    max_p95_latency_ms: float,
    max_provider_calls: int,
) -> ProtectedEvaluation:
    validation = evaluate(regions, questions, validation_results, split="validation")
    validation_by_class = evaluate_by_class(
        regions, questions, validation_results, split="validation"
    )
    gate = phase6_gate(
        baseline_validation,
        validation,
        baseline_by_class=baseline_validation_by_class,
        candidate_by_class=validation_by_class,
        text_baseline_recall=text_baseline_recall,
        text_candidate_recall=text_candidate_recall,
        text_baseline_mrr=text_baseline_mrr,
        text_candidate_mrr=text_candidate_mrr,
        max_p95_latency_ms=max_p95_latency_ms,
        max_provider_calls=max_provider_calls,
    )
    holdout = None
    if gate.passed:
        holdout = evaluate(
            regions,
            questions,
            holdout_results_factory(),
            split="holdout",
        )
    return ProtectedEvaluation(validation, validation_by_class, gate, holdout)


def _parse_regions(rows: list[dict[str, Any]]) -> dict[str, VisualRegion]:
    output: dict[str, VisualRegion] = {}
    for row in rows:
        if row.get("dataset_revision") != DATASET_REVISION:
            raise Phase6EvaluationError("Region dataset revision is invalid")
        region_id = _required_text(row, "region_id")
        if region_id in output:
            raise Phase6EvaluationError(f"Duplicate region_id: {region_id}")
        split = row.get("split")
        if split not in SPLIT_CLASS_COUNTS:
            raise Phase6EvaluationError(f"Invalid region split: {region_id}")
        bbox_raw = row.get("bbox")
        if (
            not isinstance(bbox_raw, list)
            or len(bbox_raw) != 4
            or any(not isinstance(value, (int, float)) for value in bbox_raw)
        ):
            raise Phase6EvaluationError(f"Invalid region bounding box: {region_id}")
        bbox = (
            float(bbox_raw[0]),
            float(bbox_raw[1]),
            float(bbox_raw[2]),
            float(bbox_raw[3]),
        )
        if any(value < 0 or value > 1 for value in bbox) or bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
            raise Phase6EvaluationError(f"Out-of-range region bounding box: {region_id}")
        output[region_id] = VisualRegion(
            region_id=region_id,
            split=split,
            document_id=_required_text(row, "document_id"),
            document_version_id=_required_text(row, "document_version_id"),
            generation_id=_required_text(row, "generation_id"),
            page_number=_positive_int(row, "page_number"),
            region_kind=_required_text(row, "region_kind"),
            bbox=bbox,
            source_text=_required_text(row, "source_text"),
            baseline_text=_required_text(row, "baseline_text"),
        )
    return output


def _parse_questions(
    rows: list[dict[str, Any]], regions: dict[str, VisualRegion]
) -> list[VisualQuestion]:
    output: list[VisualQuestion] = []
    seen: set[str] = set()
    all_documents = frozenset(region.document_id for region in regions.values())
    for row in rows:
        if row.get("dataset_revision") != DATASET_REVISION:
            raise Phase6EvaluationError("Question dataset revision is invalid")
        query_id = _required_text(row, "query_id")
        if query_id in seen:
            raise Phase6EvaluationError(f"Duplicate query_id: {query_id}")
        seen.add(query_id)
        split = row.get("split")
        query_class = row.get("query_class")
        if split not in SPLIT_CLASS_COUNTS or query_class not in QUESTION_CLASSES:
            raise Phase6EvaluationError(f"Invalid question classification: {query_id}")
        allowed_raw = row.get("allowed_document_ids")
        if not isinstance(allowed_raw, list) or not allowed_raw:
            raise Phase6EvaluationError(f"Invalid allowed scope: {query_id}")
        allowed = all_documents if allowed_raw == ["@workspace"] else frozenset(allowed_raw)
        relevance_raw = row.get("relevance")
        if not isinstance(relevance_raw, list):
            raise Phase6EvaluationError(f"Invalid relevance: {query_id}")
        relevance: dict[str, int] = {}
        for item in relevance_raw:
            if not isinstance(item, dict):
                raise Phase6EvaluationError(f"Invalid relevance row: {query_id}")
            region_id = _required_text(item, "region_id")
            grade = item.get("grade")
            if (
                region_id not in regions
                or not isinstance(grade, int)
                or grade not in {1, 2, 3}
                or regions[region_id].document_id not in allowed
                or regions[region_id].split != split
                or region_id in relevance
            ):
                raise Phase6EvaluationError(f"Invalid relevance identity: {query_id}")
            relevance[region_id] = grade
        answerable = row.get("answerable")
        if not isinstance(answerable, bool) or answerable != bool(relevance):
            raise Phase6EvaluationError(f"Answerability mismatch: {query_id}")
        excluded_raw = row.get("excluded_relevant_region_ids", [])
        if not isinstance(excluded_raw, list):
            raise Phase6EvaluationError(f"Invalid excluded relevance: {query_id}")
        excluded = frozenset(excluded_raw)
        if any(
            region_id not in regions or regions[region_id].document_id in allowed
            for region_id in excluded
        ):
            raise Phase6EvaluationError(f"Excluded relevance is not out of scope: {query_id}")
        negative_kind = row.get("negative_kind")
        if query_class == "negative":
            if negative_kind not in {"unanswerable", "ambiguous_calculation", "unauthorized_scope"}:
                raise Phase6EvaluationError(f"Invalid negative kind: {query_id}")
            if negative_kind == "unauthorized_scope" and not excluded:
                raise Phase6EvaluationError(f"Unauthorized negative lacks excluded relevance: {query_id}")
        elif negative_kind is not None or excluded:
            raise Phase6EvaluationError(f"Unexpected negative contract: {query_id}")
        expected_operation = row.get("expected_operation")
        expected_value = row.get("expected_value")
        if query_class == "calculation" and (not expected_operation or expected_value is None):
            raise Phase6EvaluationError(f"Calculation contract is incomplete: {query_id}")
        output.append(
            VisualQuestion(
                query_id=query_id,
                split=split,
                query_class=query_class,
                query=_required_text(row, "query"),
                allowed_document_ids=allowed,
                answerable=answerable,
                relevance=relevance,
                negative_kind=negative_kind,
                excluded_relevant_region_ids=excluded,
                expected_operation=expected_operation,
                expected_value=None if expected_value is None else str(expected_value),
                expected_unit=row.get("expected_unit"),
            )
        )
    return output


def _validate_distribution(
    regions: dict[str, VisualRegion], questions: list[VisualQuestion]
) -> None:
    if len(regions) < 40 or len(questions) < 80:
        raise Phase6EvaluationError("Phase 6 corpus is below its accepted minimum")
    split_counts = Counter(question.split for question in questions)
    expected_splits = {
        split: sum(class_counts.values()) for split, class_counts in SPLIT_CLASS_COUNTS.items()
    }
    if split_counts != expected_splits:
        raise Phase6EvaluationError("Phase 6 split distribution is invalid")
    class_counts: Counter[tuple[str, str]] = Counter(
        (question.split, question.query_class) for question in questions
    )
    for split, expected in SPLIT_CLASS_COUNTS.items():
        for query_class, count in expected.items():
            if class_counts[(split, query_class)] != count:
                raise Phase6EvaluationError("Phase 6 class distribution is invalid")
    normalized = [question.query.casefold().strip() for question in questions]
    if len(normalized) != len(set(normalized)):
        raise Phase6EvaluationError("Duplicate normalized Phase 6 query")
    protected_regions = {
        region_id for question in questions if question.split != "tune" for region_id in question.relevance
    }
    if any(regions[region_id].split == "tune" for region_id in protected_regions):
        raise Phase6EvaluationError("Protected questions reference tuning regions")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase6EvaluationError(f"Evaluation file is unreadable: {path.name}") from exc


def _required_text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise Phase6EvaluationError(f"Missing required text: {key}")
    return value.strip()


def _positive_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if not isinstance(value, int) or value < 1:
        raise Phase6EvaluationError(f"Invalid positive integer: {key}")
    return value


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _dcg(grades: list[int]) -> float:
    return sum((2**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(grades, 1))


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = math.ceil(percentile * len(ordered)) - 1
    return ordered[max(index, 0)]


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise Phase6EvaluationError(f"Evaluation file is unreadable: {path.name}") from exc


def _canonical_sha256(values: list[str]) -> str:
    payload = json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))
