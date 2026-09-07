from __future__ import annotations

import hashlib
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from backend.app.retrieval.artifacts import ModelArtifactSpec

DOCLING_PACKAGE_VERSION = "2.124.0"
DOCLING_MODEL_PROFILE = "docling-layout-tableformer-v1"
DOCLING_MODEL_LICENSES = ("apache-2.0", "mit")
DOCLING_MODEL_TREE_SHA256 = "84c523c99eb4e43b36ebf5aee678b66c7017b18ff4db3de22b67dcd2ab3a92cc"
VISUAL_IMAGE_MODEL = ModelArtifactSpec(
    name="Qdrant/clip-ViT-B-32-vision",
    revision="e0c24ed0fa57fa3e4f97f30de74c51d944036ace",
    license="mit",
    files=("config.json", "model.onnx", "preprocessor_config.json"),
    tree_sha256="7c97248e0ce88dd7bd7597de5565ec56de8a5e0c8a2c67688473d51da2eb6817",
)
VISUAL_TEXT_MODEL = ModelArtifactSpec(
    name="Qdrant/clip-ViT-B-32-text",
    revision="48ca1db27cb4063eb311ec2aa7f087a808112876",
    license="mit",
    files=(
        "config.json",
        "merges.txt",
        "model.onnx",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.json",
    ),
    tree_sha256="9e1d3a144fffe99acff0338beae93283c933d98541b2394222b85e9c10fabeb7",
)


class VisualModelArtifactError(RuntimeError):
    """Raised when local Phase 6 model bytes do not match the reviewed profile."""


@dataclass(frozen=True, slots=True)
class VisualModelArtifactStatus:
    profile: str
    package_version: str
    tree_sha256: str
    file_count: int
    byte_size: int


def inspect_docling_artifacts(root: Path) -> VisualModelArtifactStatus:
    if version("docling") != DOCLING_PACKAGE_VERSION:
        raise VisualModelArtifactError("The pinned Docling package version is unavailable")
    files = tuple(_model_files(root))
    if not files:
        raise VisualModelArtifactError("Pinned visual extraction artifacts are unavailable")
    digest = hashlib.sha256()
    byte_size = 0
    for path in files:
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        checksum = _file_sha256(path)
        digest.update(f"{relative}\0{size}\0{checksum}\n".encode("utf-8"))
        byte_size += size
    return VisualModelArtifactStatus(
        profile=DOCLING_MODEL_PROFILE,
        package_version=DOCLING_PACKAGE_VERSION,
        tree_sha256=digest.hexdigest(),
        file_count=len(files),
        byte_size=byte_size,
    )


def verify_docling_artifacts(root: Path) -> VisualModelArtifactStatus:
    status = inspect_docling_artifacts(root)
    if status.tree_sha256 != DOCLING_MODEL_TREE_SHA256:
        raise VisualModelArtifactError("Pinned visual extraction artifact checksum failed")
    return status


def _model_files(root: Path):
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_file() and not any(part.startswith(".") for part in relative.parts):
            yield path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
