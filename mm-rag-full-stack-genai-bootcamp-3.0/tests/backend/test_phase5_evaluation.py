import json
from dataclasses import replace

import pytest

from backend.app.core.config import PROJECT_ROOT
from backend.app.retrieval.evaluation import (
    ANSWERABLE_QUERY_CLASSES,
    QUALITY_CONTRACT_V2,
    EvaluationContractError,
    EvaluationMetrics,
    EvaluationResult,
    _validate_v2_contract,
    evaluate,
    evaluate_by_class,
    load_dataset,
    phase5_gate,
    phase5_recall_target,
)
from scripts.build_phase5_v3_fixture import rendered_files

DATASET = PROJECT_ROOT / "evaluation/phase5/v3"
V2_DATASET = PROJECT_ROOT / "evaluation/phase5/v2"


def test_phase5_dataset_is_hashed_balanced_and_split() -> None:
    documents, queries = load_dataset(DATASET)

    assert len(documents) == 120
    assert len(queries) == 80
    assert sum(query.split == "tune" for query in queries) == 48
    assert sum(query.split == "validation" for query in queries) == 16
    assert sum(query.split == "holdout" for query in queries) == 16
    assert {query.query_class for query in queries} == {
        "semantic_paraphrase",
        "exact_identifier",
        "multi_document",
        "negative",
    }
    assert len(queries[0].allowed_document_ids) == 12
    assert sum(document.fixture_role == "evidence" for document in documents.values()) == 24
    assert sum(document.fixture_role == "confounder" for document in documents.values()) == 96
    negatives = [query for query in queries if query.query_class == "negative"]
    assert sum(query.negative_kind == "unanswerable" for query in negatives) == 10
    assert sum(query.negative_kind == "unauthorized_scope" for query in negatives) == 10
    for split in ("tune", "validation", "holdout"):
        split_queries = [query for query in queries if query.split == split]
        assert all(
            sum(query.query_class == query_class for query in split_queries) >= 4
            for query_class in ANSWERABLE_QUERY_CLASSES
        )
        split_negatives = [query for query in split_queries if query.query_class == "negative"]
        assert {query.negative_kind for query in split_negatives} == {
            "unanswerable",
            "unauthorized_scope",
        }


def test_phase5_v3_fixture_is_reproducible_and_rotates_protected_queries() -> None:
    for name, expected in rendered_files().items():
        assert (DATASET / name).read_bytes() == expected

    _, v2_queries = load_dataset(V2_DATASET)
    _, v3_queries = load_dataset(DATASET)
    v2_protected = {
        query.query.casefold() for query in v2_queries if query.split in {"validation", "holdout"}
    }
    v3_protected = {
        query.query.casefold() for query in v3_queries if query.split in {"validation", "holdout"}
    }
    assert v2_protected.isdisjoint(v3_protected)
    assert {query.query_id for query in v2_queries}.isdisjoint(
        query.query_id for query in v3_queries
    )


def test_phase5_metrics_validate_identity_scope_and_negatives() -> None:
    documents, queries = load_dataset(DATASET)
    results = [
        EvaluationResult(
            query_id=query.query_id,
            ranked_chunk_ids=tuple(
                chunk_id
                for chunk_id, _ in sorted(
                    query.relevance.items(), key=lambda item: (-item[1], item[0])
                )
            ),
            latency_ms=10,
        )
        for query in queries
    ]

    metrics = evaluate(documents, queries, results)

    assert metrics.recall_at_10 == 1
    assert metrics.mrr_at_10 == 1
    assert metrics.ndcg_at_10 == 1
    assert metrics.source_coverage_at_10 == 1
    assert metrics.unanswerable_empty_accuracy == 1
    assert metrics.excluded_candidate_count == 0
    assert metrics.unauthorized_candidate_count == 0
    assert metrics.unknown_candidate_count == 0
    assert evaluate(documents, queries, results, split="holdout").query_count == 16

    unauthorized = next(query for query in queries if query.negative_kind == "unauthorized_scope")
    unsafe_results = [
        replace(result, ranked_chunk_ids=tuple(unauthorized.excluded_relevant_chunk_ids))
        if result.query_id == unauthorized.query_id
        else result
        for result in results
    ]
    unsafe_metrics = evaluate(documents, queries, unsafe_results)
    assert unsafe_metrics.excluded_candidate_count == 1
    assert unsafe_metrics.unauthorized_candidate_count == 1


def test_phase5_v2_preflight_rejects_an_undersized_quality_pool() -> None:
    documents, queries = load_dataset(V2_DATASET)
    manifest = json.loads((V2_DATASET / "manifest.json").read_text(encoding="utf-8"))
    first = queries[0]
    narrowed = replace(
        first,
        allowed_document_ids=frozenset({next(iter(first.allowed_document_ids))}),
    )

    with pytest.raises(EvaluationContractError, match="undersized candidate pool"):
        _validate_v2_contract(manifest, documents, [narrowed, *queries[1:]])


def test_phase5_metrics_reject_incomplete_result_coverage() -> None:
    documents, queries = load_dataset(DATASET)

    with pytest.raises(EvaluationContractError, match="coverage mismatch"):
        evaluate(documents, queries, [])


def test_phase5_gate_enforces_quality_security_latency_and_cost() -> None:
    dense = EvaluationMetrics(
        query_count=10,
        recall_at_10=0.5,
        mrr_at_10=0.7,
        ndcg_at_10=0.6,
        source_coverage_at_10=0.5,
        unanswerable_empty_accuracy=1,
        excluded_candidate_count=0,
        unauthorized_candidate_count=0,
        unknown_candidate_count=0,
        p50_latency_ms=50,
        p95_latency_ms=100,
        provider_calls=10,
        estimated_cost_usd=0.01,
    )
    passing = replace(
        dense,
        recall_at_10=0.56,
        ndcg_at_10=0.64,
        mrr_at_10=0.69,
        p95_latency_ms=200,
        unanswerable_empty_accuracy=0,
    )
    failing = replace(passing, excluded_candidate_count=1)

    dense_by_class = {query_class: dense for query_class in ANSWERABLE_QUERY_CLASSES}
    passing_by_class = {query_class: passing for query_class in ANSWERABLE_QUERY_CLASSES}
    assert phase5_gate(
        dense,
        passing,
        quality_contract_revision=QUALITY_CONTRACT_V2,
        dense_by_class=dense_by_class,
        hybrid_by_class=passing_by_class,
    ) == (True, [])
    passed, failures = phase5_gate(
        dense,
        failing,
        quality_contract_revision=QUALITY_CONTRACT_V2,
        dense_by_class=dense_by_class,
        hybrid_by_class=passing_by_class,
    )
    assert passed is False
    assert "Authorization" in failures[0]


def test_phase5_ceiling_aware_recall_targets_use_raw_values() -> None:
    boundary = 10 / 11

    assert phase5_recall_target(0.5, quality_contract_revision=QUALITY_CONTRACT_V2) == 0.55
    assert phase5_recall_target(
        boundary, quality_contract_revision=QUALITY_CONTRACT_V2
    ) == pytest.approx(1.0)
    assert phase5_recall_target(
        0.9375, quality_contract_revision=QUALITY_CONTRACT_V2
    ) == pytest.approx(0.94375)
    assert phase5_recall_target(1.0, quality_contract_revision=QUALITY_CONTRACT_V2) == 1.0


def test_phase5_class_metrics_and_guardrails_detect_hidden_regression() -> None:
    documents, queries = load_dataset(DATASET)
    results = [
        EvaluationResult(
            query_id=query.query_id,
            ranked_chunk_ids=tuple(query.relevance),
            latency_ms=1,
        )
        for query in queries
    ]
    class_metrics = evaluate_by_class(documents, queries, results, split="validation")

    assert set(class_metrics) == set(ANSWERABLE_QUERY_CLASSES)
    assert all(metrics.query_count == 4 for metrics in class_metrics.values())

    dense = class_metrics["semantic_paraphrase"]
    regressed = replace(dense, recall_at_10=dense.recall_at_10 - 0.01)
    candidate_classes = dict(class_metrics)
    candidate_classes["semantic_paraphrase"] = regressed
    passed, failures = phase5_gate(
        dense,
        replace(dense, ndcg_at_10=dense.ndcg_at_10 * 1.05),
        dense_by_class=class_metrics,
        hybrid_by_class=candidate_classes,
    )

    assert passed is False
    assert "semantic_paraphrase Recall@10 regressed" in failures
