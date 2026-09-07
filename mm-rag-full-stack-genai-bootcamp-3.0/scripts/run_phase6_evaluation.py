from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from backend.app.core.config import PROJECT_ROOT
from backend.app.visual.evaluation import (
    evaluate,
    evaluate_by_class,
    lexical_baseline_results,
    load_dataset,
)

DATASET = PROJECT_ROOT / "evaluation/phase6/v1"
SUMMARY = DATASET / "baseline-summary.json"


def summary() -> dict[str, object]:
    regions, questions = load_dataset(DATASET)
    split_metrics: dict[str, object] = {}
    class_metrics: dict[str, object] = {}
    for split in ("tune", "validation"):
        results = lexical_baseline_results(regions, questions, split=split)
        split_metrics[split] = asdict(evaluate(regions, questions, results, split=split))
        class_metrics[split] = {
            name: asdict(metrics)
            for name, metrics in evaluate_by_class(
                regions, questions, results, split=split
            ).items()
        }
    return {
        "dataset_revision": "phase6-visual-table-v1",
        "profile": "ocr-markdown-baseline-v1",
        "holdout_evaluated": False,
        "provider_calls": 0,
        "splits": split_metrics,
        "classes": class_metrics,
    }


def rendered_summary() -> bytes:
    return (json.dumps(summary(), indent=2, sort_keys=True) + "\n").encode()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the free Phase 6 OCR/Markdown baseline")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = rendered_summary()
    if args.write:
        SUMMARY.write_bytes(rendered)
    elif args.check:
        if not SUMMARY.is_file() or SUMMARY.read_bytes() != rendered:
            raise SystemExit("Phase 6 baseline summary drift")
    else:
        print(rendered.decode(), end="")


if __name__ == "__main__":
    main()
