import json

import pytest

from backend.app.core.config import PROJECT_ROOT
from backend.app.evaluation.release import evaluate_release, load_cases, load_results
from scripts.run_phase7_evaluation import rendered_summary

ROOT = PROJECT_ROOT / "evaluation/phase7/v1"


def test_phase7_validation_and_holdout_pass_without_provider_calls() -> None:
    cases = load_cases(ROOT / "cases.jsonl")
    results = load_results(ROOT / "baseline-results.jsonl")

    validation = evaluate_release(cases, results, split="validation")
    holdout = evaluate_release(cases, results, split="holdout")

    assert validation.passed
    assert holdout.passed
    assert validation.provider_calls == 0
    assert validation.authorization_escape_count == 0
    assert validation.invalid_citation_count == 0


def test_phase7_gate_withholds_holdout_when_validation_fails(tmp_path) -> None:
    rows = [
        json.loads(line)
        for line in (ROOT / "baseline-results.jsonl").read_text().splitlines()
    ]
    rows[0]["outcome"] = "fail"
    path = tmp_path / "failed-results.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))

    report = json.loads(rendered_summary(path))

    assert report["gate"]["passed"] is False
    assert report["holdout"] is None
    assert "outcome_accuracy" in report["gate"]["failures"]


def test_phase7_rejects_unknown_result_identity(tmp_path) -> None:
    path = tmp_path / "unknown.jsonl"
    path.write_text(
        '{"case_id":"unknown","outcome":"pass","evidence_ids":[],"duration_ms":1,"provider_calls":0}\n'
    )

    with pytest.raises(ValueError, match="unknown case"):
        evaluate_release(load_cases(ROOT / "cases.jsonl"), load_results(path), split="validation")
