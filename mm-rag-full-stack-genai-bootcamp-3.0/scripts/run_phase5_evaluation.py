from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from backend.app.core.config import PROJECT_ROOT
from backend.app.retrieval.evaluation import evaluate, load_dataset, load_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate or score the Phase 5 benchmark")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=PROJECT_ROOT / "evaluation/phase5/v1",
    )
    parser.add_argument("--results", type=Path)
    parser.add_argument("--split", choices=("tune", "validation", "holdout"))
    args = parser.parse_args()

    documents, queries = load_dataset(args.dataset)
    if args.results is None:
        print(f"validated {len(documents)} chunks and {len(queries)} judged queries")
        return
    metrics = evaluate(documents, queries, load_results(args.results), split=args.split)
    print(json.dumps(asdict(metrics), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
