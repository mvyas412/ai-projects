from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from huggingface_hub import snapshot_download


class ModelArtifactError(RuntimeError):
    """Raised when a pinned local model artifact is missing or invalid."""


@dataclass(frozen=True, slots=True)
class ModelArtifactSpec:
    name: str
    revision: str
    license: str
    files: tuple[str, ...]
    tree_sha256: str


SPARSE_MODEL = ModelArtifactSpec(
    name="Qdrant/bm25",
    revision="22b8d2af71a76161e18dd432d2cee0eefa66e412",
    license="apache-2.0",
    files=("english.txt",),
    tree_sha256="b5b32b113aefef4a29473201c9d3e702ce1c9a8838f7c4515d5a35e943834ce1",
)
RERANK_MODEL = ModelArtifactSpec(
    name="Xenova/ms-marco-MiniLM-L-6-v2",
    revision="a09144355adeed5f58c8ed011d209bf8ee5a1fec",
    license="apache-2.0",
    files=(
        "config.json",
        "onnx/model.onnx",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
    ),
    tree_sha256="f9710dcc816a1fcc95dccd344663077b157b5b9ddefc86af6285f01491442ebf",
)


def prefetch_model(spec: ModelArtifactSpec, cache_dir: Path) -> Path:
    snapshot = Path(
        snapshot_download(
            repo_id=spec.name,
            revision=spec.revision,
            cache_dir=cache_dir,
            allow_patterns=list(spec.files),
        )
    )
    verify_model_snapshot(snapshot, spec)
    return snapshot


def resolve_local_model(spec: ModelArtifactSpec, cache_dir: Path) -> Path:
    try:
        snapshot = Path(
            snapshot_download(
                repo_id=spec.name,
                revision=spec.revision,
                cache_dir=cache_dir,
                allow_patterns=list(spec.files),
                local_files_only=True,
            )
        )
    except Exception as exc:
        raise ModelArtifactError(f"Pinned model artifact is unavailable: {spec.name}") from exc
    verify_model_snapshot(snapshot, spec)
    return snapshot


def verify_model_snapshot(snapshot: Path, spec: ModelArtifactSpec) -> None:
    digest = hashlib.sha256()
    for relative_name in sorted(spec.files):
        path = snapshot / relative_name
        if not path.is_file():
            raise ModelArtifactError(f"Pinned model artifact is incomplete: {spec.name}")
        content_hash = _file_sha256(path)
        digest.update(
            f"{relative_name}\0{path.stat().st_size}\0{content_hash}\n".encode("utf-8")
        )
    if digest.hexdigest() != spec.tree_sha256:
        raise ModelArtifactError(f"Pinned model artifact checksum failed: {spec.name}")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
