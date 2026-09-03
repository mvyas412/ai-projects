import hashlib

import pytest

from backend.app.retrieval.artifacts import (
    ModelArtifactError,
    ModelArtifactSpec,
    verify_model_snapshot,
)


def _tree_hash(name: str, content: bytes) -> str:
    file_hash = hashlib.sha256(content).hexdigest()
    digest = hashlib.sha256()
    digest.update(f"{name}\0{len(content)}\0{file_hash}\n".encode())
    return digest.hexdigest()


def test_model_artifact_verification_fails_closed_on_tampering(tmp_path) -> None:
    content = b"pinned model artifact"
    (tmp_path / "model.bin").write_bytes(content)
    spec = ModelArtifactSpec(
        name="fixture/model",
        revision="a" * 40,
        license="apache-2.0",
        files=("model.bin",),
        tree_sha256=_tree_hash("model.bin", content),
    )

    verify_model_snapshot(tmp_path, spec)
    (tmp_path / "model.bin").write_bytes(b"changed")

    with pytest.raises(ModelArtifactError, match="checksum"):
        verify_model_snapshot(tmp_path, spec)
