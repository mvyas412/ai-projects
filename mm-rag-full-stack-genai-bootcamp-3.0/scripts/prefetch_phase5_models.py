from __future__ import annotations

import argparse
from pathlib import Path

from backend.app.core.config import PROJECT_ROOT
from backend.app.retrieval.artifacts import (
    RERANK_MODEL,
    SPARSE_MODEL,
    prefetch_model,
    resolve_local_model,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision pinned Phase 5 local models")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=PROJECT_ROOT / "data/runtime/models",
    )
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    loader = resolve_local_model if args.verify_only else prefetch_model
    for spec in (SPARSE_MODEL, RERANK_MODEL):
        loader(spec, args.cache_dir)
        print(f"verified {spec.name}@{spec.revision} {spec.tree_sha256}")


if __name__ == "__main__":
    main()
