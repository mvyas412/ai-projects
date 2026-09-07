from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict

from backend.app.core.config import PROJECT_ROOT
from backend.app.visual.evaluation import (
    evaluate,
    evaluate_by_class,
    evaluate_validation_then_holdout,
    lexical_baseline_results,
    load_dataset,
    local_structured_candidate_results,
)

DATASET = PROJECT_ROOT / "evaluation/phase6/v1"
CANDIDATE_ROOT = PROJECT_ROOT / "evaluation/phase6/candidate"
PROFILE = CANDIDATE_ROOT / "visual-table-v1-profile.json"
SUMMARY = CANDIDATE_ROOT / "visual-table-v1-summary.json"


def _profile() -> dict[str, object]:
    payload = json.loads(PROFILE.read_text(encoding="utf-8"))
    if payload.get("candidate_revision") != "visual-table-v1":
        raise ValueError("Phase 6 candidate profile revision is invalid")
    return payload


def _fingerprint(profile: dict[str, object]) -> str:
    digest = hashlib.sha256()
    digest.update(json.dumps(profile, sort_keys=True, separators=(",", ":")).encode())
    sources = profile.get("fingerprinted_sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("Phase 6 candidate fingerprint sources are missing")
    for relative in sources:
        if not isinstance(relative, str):
            raise ValueError("Phase 6 candidate fingerprint source is invalid")
        path = (PROJECT_ROOT / relative).resolve()
        if not path.is_relative_to(PROJECT_ROOT) or not path.is_file():
            raise ValueError("Phase 6 candidate fingerprint source is unavailable")
        digest.update(relative.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def summary() -> dict[str, object]:
    profile = _profile()
    regions, questions = load_dataset(DATASET)
    baseline_results = lexical_baseline_results(regions, questions, split="validation")
    baseline = evaluate(regions, questions, baseline_results, split="validation")
    baseline_by_class = evaluate_by_class(
        regions, questions, baseline_results, split="validation"
    )
    validation_results = local_structured_candidate_results(
        regions, questions, split="validation"
    )
    protected = evaluate_validation_then_holdout(
        regions=regions,
        questions=questions,
        baseline_validation=baseline,
        baseline_validation_by_class=baseline_by_class,
        validation_results=validation_results,
        holdout_results_factory=lambda: local_structured_candidate_results(
            regions, questions, split="holdout"
        ),
        text_baseline_recall=_number(profile, "text_baseline_recall"),
        text_candidate_recall=_number(profile, "text_candidate_recall"),
        text_baseline_mrr=_number(profile, "text_baseline_mrr"),
        text_candidate_mrr=_number(profile, "text_candidate_mrr"),
        max_p95_latency_ms=_number(profile, "retrieval_p95_budget_ms"),
        max_provider_calls=_integer(profile, "provider_call_budget"),
    )
    return {
        "candidate_fingerprint": _fingerprint(profile),
        "candidate_revision": profile["candidate_revision"],
        "dataset_revision": profile["dataset_revision"],
        "gate": asdict(protected.gate),
        "holdout": asdict(protected.holdout) if protected.holdout is not None else None,
        "provider_calls": protected.validation.provider_calls
        + (protected.holdout.provider_calls if protected.holdout is not None else 0),
        "validation": asdict(protected.validation),
        "validation_by_class": {
            name: asdict(metrics)
            for name, metrics in protected.validation_by_class.items()
        },
    }


def rendered_summary() -> bytes:
    return (json.dumps(summary(), indent=2, sort_keys=True) + "\n").encode()


def _number(profile: dict[str, object], name: str) -> float:
    value = profile.get(name)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"Phase 6 candidate {name} is invalid")
    return float(value)


def _integer(profile: dict[str, object], name: str) -> int:
    value = profile.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Phase 6 candidate {name} is invalid")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the frozen free Phase 6 visual/table candidate"
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = rendered_summary()
    if args.write:
        SUMMARY.write_bytes(rendered)
    elif args.check:
        if not SUMMARY.is_file() or SUMMARY.read_bytes() != rendered:
            raise SystemExit("Phase 6 candidate summary drift")
    else:
        print(rendered.decode(), end="")


if __name__ == "__main__":
    main()
