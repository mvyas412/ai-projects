from __future__ import annotations

from pathlib import Path

import pytest

from scripts.phase8_backup import build_manifest, verify_manifest


def _staged_backup(root: Path) -> Path:
    (root / "postgres.dump").write_bytes(b"postgres")
    (root / "qdrant").mkdir()
    (root / "qdrant" / "snapshot.bin").write_bytes(b"vectors")
    (root / "objects").mkdir()
    (root / "objects" / "content.bin").write_bytes(b"object")
    return root


def test_backup_manifest_round_trip(tmp_path: Path) -> None:
    staged = _staged_backup(tmp_path)
    manifest = build_manifest(staged)

    verify_manifest(staged, manifest)

    assert manifest["schema"] == "mm-rag-phase8-backup-v1"
    assert len(manifest["files"]) == 3


def test_backup_manifest_detects_tampering(tmp_path: Path) -> None:
    staged = _staged_backup(tmp_path)
    manifest = build_manifest(staged)
    (staged / "postgres.dump").write_bytes(b"changed")

    with pytest.raises(ValueError, match="integrity verification"):
        verify_manifest(staged, manifest)


def test_backup_manifest_rejects_missing_service_export(tmp_path: Path) -> None:
    (tmp_path / "postgres.dump").write_bytes(b"postgres")

    with pytest.raises(ValueError, match="missing qdrant"):
        build_manifest(tmp_path)
