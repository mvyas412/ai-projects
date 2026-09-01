from dataclasses import replace

import pytest

from backend.app.core.config import PROJECT_ROOT
from backend.app.retrieval.evaluation import (
    EvaluationContractError,
    EvaluationMetrics,
    EvaluationResult,
    evaluate,
    load_dataset,
    phase5_gate,
)

DATASET = PROJECT_ROOT / "evaluation/phase5/v1"


def test_phase5_dataset_is_hashed_balanced_and_split() -> None:
    documents, queries = load_dataset(DATASET)

    assert len(documents) == 24
    assert len(queries) == 50
    assert sum(query.split == "tune" for query in queries) == 30
    assert sum(query.split == "validation" for query in queries) == 10
    assert sum(query.split == "holdout" for query in queries) == 10
    assert {query.query_class for query in queries} == {
        "semantic_paraphrase",
        "exact_identifier",
        "multi_document",
        "negative",
    }
    assert len(queries[0].allowed_document_ids) == 12


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
    assert metrics.negative_empty_accuracy == 1
    assert metrics.unauthorized_candidate_count == 0
    assert metrics.unknown_candidate_count == 0
    assert evaluate(documents, queries, results, split="holdout").query_count == 10


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
        negative_empty_accuracy=1,
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
    )
    failing = replace(passing, unauthorized_candidate_count=1)

    assert phase5_gate(dense, passing) == (True, [])
    passed, failures = phase5_gate(dense, failing)
    assert passed is False
    assert "Authorization" in failures[0]
