from __future__ import annotations

import argparse
from pathlib import Path

from backend.app.core.config import PROJECT_ROOT
from backend.app.visual.artifacts import (
    DOCLING_MODEL_TREE_SHA256,
    inspect_docling_artifacts,
    verify_docling_artifacts,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision the pinned Phase 6 Docling structural model profile"
    )
    parser.add_argument(
        "--artifacts-path",
        type=Path,
        default=PROJECT_ROOT / "data/runtime/docling-models",
    )
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()

    if not args.verify_only and not args.inspect:
        from docling.utils.model_downloader import download_models

        download_models(
            output_dir=args.artifacts_path,
            with_layout=True,
            with_tableformer=True,
            with_tableformer_v2=False,
            with_code_formula=False,
            with_picture_classifier=False,
            with_smolvlm=False,
            with_granitedocling=False,
            with_granitedocling_mlx=False,
            with_granitedocling_2stage=False,
            with_smoldocling=False,
            with_smoldocling_mlx=False,
            with_granite_vision=False,
            with_granite_chart_extraction=False,
            with_granite_chart_extraction_v4=False,
            with_rapidocr=False,
            with_easyocr=False,
            with_nemotron_ocr=False,
        )
    status = (
        inspect_docling_artifacts(args.artifacts_path)
        if args.inspect or DOCLING_MODEL_TREE_SHA256 == "pending"
        else verify_docling_artifacts(args.artifacts_path)
    )
    print(
        f"verified {status.profile} package={status.package_version} "
        f"files={status.file_count} bytes={status.byte_size} "
        f"tree_sha256={status.tree_sha256} expected={DOCLING_MODEL_TREE_SHA256}"
    )


if __name__ == "__main__":
    main()
