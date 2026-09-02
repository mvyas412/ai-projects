from __future__ import annotations

import argparse
from pathlib import Path

from qdrant_client import QdrantClient

from backend.app.core.config import PROJECT_ROOT, get_settings
from backend.app.retrieval.benchmark import report_json, run_benchmark
from backend.app.retrieval.evaluation import load_dataset


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the paid Phase 5 dense/hybrid retrieval comparison"
    )
    parser.add_argument("--allow-paid-openai", action="store_true")
    parser.add_argument("--embedding-cost-per-million-tokens", type=float, required=True)
    parser.add_argument("--dataset", type=Path, default=PROJECT_ROOT / "evaluation/phase5/v4")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "evaluation/phase5/results/latest",
    )
    args = parser.parse_args()
    if not args.allow_paid_openai:
        parser.error("--allow-paid-openai is required because this command embeds text")

    settings = get_settings()
    documents, queries = load_dataset(args.dataset)
    qdrant = QdrantClient(
        url=settings.qdrant_url,
        api_key=(
            settings.qdrant_api_key.get_secret_value()
            if settings.qdrant_api_key is not None
            else None
        ),
        timeout=max(settings.qdrant_timeout_seconds, 30),
        check_compatibility=False,
    )
    try:
        report = run_benchmark(
            settings=settings,
            qdrant=qdrant,
            documents=documents,
            queries=queries,
            output_dir=args.output_dir,
            embedding_cost_per_million_tokens=args.embedding_cost_per_million_tokens,
        )
    finally:
        qdrant.close()
    print(report_json(report))
    if not report.validation_passed:
        raise SystemExit(
            "Phase 5 validation gate failed; holdout was not evaluated: "
            + "; ".join(report.validation_failures)
        )
    if report.holdout_passed is not True:
        raise SystemExit("Phase 5 holdout gate failed: " + "; ".join(report.holdout_failures))


if __name__ == "__main__":
    main()
