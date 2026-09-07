from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.core.config import PROJECT_ROOT
from backend.app.evaluation.release import (
    evaluate_release,
    load_cases,
    load_results,
    metrics_dict,
    verify_manifest,
)
from backend.app.retrieval.evaluation import load_dataset as load_phase5_dataset
from scripts.run_phase6_candidate import rendered_summary as phase6_rendered_summary

ROOT = PROJECT_ROOT / "evaluation/phase7/v1"
SUMMARY = ROOT / "release-summary.json"


def _integer(manifest: dict[str, object], key: str) -> int:
    value = manifest.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Phase 7 manifest {key} is invalid")
    return value


def _number(manifest: dict[str, object], key: str) -> float:
    value = manifest.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"Phase 7 manifest {key} is invalid")
    return float(value)


def summary(results_path: Path | None = None) -> dict[str, object]:
    manifest = verify_manifest(ROOT)
    cases = load_cases(ROOT / "cases.jsonl")
    results = load_results(results_path or ROOT / "baseline-results.jsonl")
    validation = evaluate_release(
        cases,
        results,
        split="validation",
        provider_call_budget=_integer(manifest, "provider_call_budget"),
        p95_latency_budget_ms=_number(manifest, "p95_latency_budget_ms"),
    )
    if not validation.passed:
        holdout = None
    else:
        holdout = evaluate_release(
            cases,
            results,
            split="holdout",
            provider_call_budget=_integer(manifest, "provider_call_budget"),
            p95_latency_budget_ms=_number(manifest, "p95_latency_budget_ms"),
        )

    phase5_documents, phase5_queries = load_phase5_dataset(
        PROJECT_ROOT / "evaluation/phase5/v4"
    )
    phase6 = json.loads(phase6_rendered_summary())
    return {
        "schema_revision": "phase7-release-report-v1",
        "dataset_revision": manifest["dataset_revision"],
        "candidate_fingerprint_required": True,
        "deterministic_release_authority": True,
        "paid_judge_authority": False,
        "historical_suites": {
            "phase5": {
                "dataset_revision": "phase5-retrieval-v4",
                "document_count": len(phase5_documents),
                "query_count": len(phase5_queries),
                "historical_result": "closed_without_candidate_promotion",
            },
            "phase6": {
                "dataset_revision": phase6["dataset_revision"],
                "candidate_revision": phase6["candidate_revision"],
                "gate_passed": phase6["gate"]["passed"],
            },
        },
        "validation": metrics_dict(validation),
        "holdout": metrics_dict(holdout) if holdout is not None else None,
        "gate": {
            "passed": validation.passed and holdout is not None and holdout.passed,
            "failures": list(validation.failures)
            + (list(holdout.failures) if holdout is not None else ["holdout_withheld"]),
        },
    }


def rendered_summary(results_path: Path | None = None) -> bytes:
    return (json.dumps(summary(results_path), indent=2, sort_keys=True) + "\n").encode()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the free Phase 7 unified release gate")
    parser.add_argument("--results", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = rendered_summary(args.results)
    if args.write:
        SUMMARY.write_bytes(rendered)
    elif args.check:
        if not SUMMARY.is_file() or SUMMARY.read_bytes() != rendered:
            raise SystemExit("Phase 7 release summary drift")
    else:
        print(rendered.decode(), end="")


if __name__ == "__main__":
    main()
