from pathlib import Path

import pytest

from backend.app.visual import artifacts
from backend.app.visual.artifacts import VisualModelArtifactError


def test_artifact_tree_hash_is_stable_and_tamper_evident(tmp_path, monkeypatch) -> None:
    (tmp_path / "layout").mkdir()
    (tmp_path / "layout" / "model.bin").write_bytes(b"layout")
    (tmp_path / "table.bin").write_bytes(b"table")
    status = artifacts.inspect_docling_artifacts(tmp_path)
    monkeypatch.setattr(artifacts, "DOCLING_MODEL_TREE_SHA256", status.tree_sha256)

    assert artifacts.verify_docling_artifacts(tmp_path) == status
    (tmp_path / "table.bin").write_bytes(b"tampered")
    with pytest.raises(VisualModelArtifactError, match="checksum failed"):
        artifacts.verify_docling_artifacts(tmp_path)


def test_missing_artifact_tree_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(VisualModelArtifactError, match="unavailable"):
        artifacts.inspect_docling_artifacts(tmp_path / "missing")
