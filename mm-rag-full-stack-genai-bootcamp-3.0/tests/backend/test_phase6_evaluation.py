from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from backend.app.core.config import PROJECT_ROOT
from backend.app.visual.evaluation import (
    ANSWERABLE_CLASSES,
    Phase6EvaluationError,
    VisualEvaluationMetrics,
    VisualEvaluationResult,
    evaluate,
    evaluate_by_class,
    evaluate_validation_then_holdout,
    lexical_baseline_results,
    load_dataset,
    phase6_gate,
)
from scripts.build_phase6_v1_fixture import rendered_files
from scripts.run_phase6_evaluation import rendered_summary

DATASET = PROJECT_ROOT / "evaluation/phase6/v1"


def _perfect_results(split: str) -> list[VisualEvaluationResult]:
    _, questions = load_dataset(DATASET)
    return [
        VisualEvaluationResult(
            query_id=question.query_id,
            ranked_region_ids=tuple(question.relevance),
            cited_region_ids=tuple(question.relevance),
            latency_ms=10,
            calculation_correct=True if question.query_class == "calculation" else None,
            abstained=not question.answerable,
        )
        for question in questions
        if question.split == split
    ]


def test_phase6_fixture_is_reproducible_and_balanced() -> None:
    for name, content in rendered_files().items():
        assert (DATASET / name).read_bytes() == content
    regions, questions = load_dataset(DATASET)
    assert len(regions) == 40
    assert len(questions) == 80
    assert {question.query_class for question in questions} == {
        "figure_relationship",
        "chart",
        "table_lookup",
        "calculation",
        "negative",
    }
    assert {question.split for question in questions} == {"tune", "validation", "holdout"}
    assert all(
        any(question.query_class == query_class and question.split == split for question in questions)
        for split in ("tune", "validation", "holdout")
        for query_class in (*ANSWERABLE_CLASSES, "negative")
    )


def test_phase6_baseline_is_reproducible_free_and_withholds_holdout() -> None:
    rendered = rendered_summary()
    assert (DATASET / "baseline-summary.json").read_bytes() == rendered
    summary = json.loads(rendered)
    assert summary["holdout_evaluated"] is False
    assert summary["provider_calls"] == 0
    assert set(summary["splits"]) == {"tune", "validation"}
    assert "p6v1-q" not in rendered.decode()


def test_phase6_metrics_validate_scope_citations_calculations_and_abstention() -> None:
    regions, questions = load_dataset(DATASET)
    results = _perfect_results("validation")
    metrics = evaluate(regions, questions, results, split="validation")
    assert metrics.recall_at_10 == 1
    assert metrics.mrr_at_10 == 1
    assert metrics.ndcg_at_10 == 1
    assert metrics.calculation_accuracy == 1
    assert metrics.safe_abstention_accuracy == 1
    assert metrics.excluded_candidate_count == 0
    assert metrics.unauthorized_candidate_count == 0
    assert metrics.unknown_candidate_count == 0
    assert metrics.invalid_citation_count == 0

    unsafe = replace(
        results[0],
        ranked_region_ids=("unknown-region",),
        cited_region_ids=("unknown-region",),
    )
    unsafe_metrics = evaluate(
        regions,
        questions,
        [unsafe, *results[1:]],
        split="validation",
    )
    assert unsafe_metrics.unknown_candidate_count == 1
    assert unsafe_metrics.invalid_citation_count == 1


def test_phase6_gate_enforces_every_accepted_release_boundary() -> None:
    regions, questions = load_dataset(DATASET)
    baseline_results = lexical_baseline_results(regions, questions, split="validation")
    baseline = evaluate(regions, questions, baseline_results, split="validation")
    baseline_by_class = evaluate_by_class(
        regions, questions, baseline_results, split="validation"
    )
    perfect_results = _perfect_results("validation")
    perfect = evaluate(regions, questions, perfect_results, split="validation")
    perfect_by_class = evaluate_by_class(
        regions, questions, perfect_results, split="validation"
    )
    passed = phase6_gate(
        baseline,
        perfect,
        baseline_by_class=baseline_by_class,
        candidate_by_class=perfect_by_class,
        text_baseline_recall=0.9,
        text_candidate_recall=0.9,
        text_baseline_mrr=0.9,
        text_candidate_mrr=0.9,
        max_p95_latency_ms=100,
        max_provider_calls=0,
    )
    assert passed.passed is True
    assert passed.failures == ()

    failed = phase6_gate(
        baseline,
        replace(perfect, calculation_accuracy=0.99, invalid_citation_count=1),
        baseline_by_class=baseline_by_class,
        candidate_by_class=perfect_by_class,
        text_baseline_recall=0.9,
        text_candidate_recall=0.8,
        text_baseline_mrr=0.9,
        text_candidate_mrr=0.8,
        max_p95_latency_ms=5,
        max_provider_calls=0,
    )
    assert failed.passed is False
    assert any("calculation" in failure for failure in failed.failures)
    assert any("identity" in failure for failure in failed.failures)
    assert any("Text-only" in failure for failure in failed.failures)


def test_phase6_validation_failure_never_calls_holdout() -> None:
    regions, questions = load_dataset(DATASET)
    baseline_results = lexical_baseline_results(regions, questions, split="validation")
    baseline = evaluate(regions, questions, baseline_results, split="validation")
    baseline_by_class = evaluate_by_class(
        regions, questions, baseline_results, split="validation"
    )
    called = False

    def holdout_results() -> list[VisualEvaluationResult]:
        nonlocal called
        called = True
        return _perfect_results("holdout")

    protected = evaluate_validation_then_holdout(
        regions=regions,
        questions=questions,
        baseline_validation=baseline,
        baseline_validation_by_class=baseline_by_class,
        validation_results=baseline_results,
        holdout_results_factory=holdout_results,
        text_baseline_recall=1,
        text_candidate_recall=1,
        text_baseline_mrr=1,
        text_candidate_mrr=1,
        max_p95_latency_ms=100,
        max_provider_calls=0,
    )
    assert protected.gate.passed is False
    assert protected.holdout is None
    assert called is False


def test_phase6_manifest_rejects_tampering(tmp_path: Path) -> None:
    for name in ("manifest.json", "regions.jsonl", "judgments.jsonl", "baseline-profile.json"):
        (tmp_path / name).write_bytes((DATASET / name).read_bytes())
    (tmp_path / "regions.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(Phase6EvaluationError, match="hash mismatch"):
        load_dataset(tmp_path)


def test_phase6_metrics_reject_incomplete_coverage() -> None:
    regions, questions = load_dataset(DATASET)
    with pytest.raises(Phase6EvaluationError, match="coverage mismatch"):
        evaluate(regions, questions, [], split="validation")


def test_phase6_metrics_shape_supports_budget_regressions() -> None:
    metrics = VisualEvaluationMetrics(
        query_count=1,
        recall_at_10=1,
        mrr_at_10=1,
        ndcg_at_10=1,
        source_coverage_at_10=1,
        calculation_accuracy=1,
        safe_abstention_accuracy=1,
        excluded_candidate_count=0,
        unauthorized_candidate_count=0,
        unknown_candidate_count=0,
        invalid_citation_count=0,
        p50_latency_ms=1,
        p95_latency_ms=1,
        provider_calls=0,
        estimated_cost_usd=0,
    )
    assert metrics.query_count == 1
