from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from scripts.phase8_backup import _validate_archive_members, build_manifest, verify_manifest


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


def test_backup_manifest_rejects_symlinks(tmp_path: Path) -> None:
    staged = _staged_backup(tmp_path)
    (staged / "objects" / "unsafe-link").symlink_to(staged / "postgres.dump")

    with pytest.raises(ValueError, match="contains a symlink"):
        build_manifest(staged)


def test_backup_manifest_rejects_unmanifested_files(tmp_path: Path) -> None:
    staged = _staged_backup(tmp_path)
    manifest = build_manifest(staged)
    (staged / "objects" / "unexpected.bin").write_bytes(b"unexpected")

    with pytest.raises(ValueError, match="unmanifested"):
        verify_manifest(staged, manifest)


def test_backup_manifest_rejects_duplicate_paths(tmp_path: Path) -> None:
    staged = _staged_backup(tmp_path)
    manifest = build_manifest(staged)
    manifest["files"].append(dict(manifest["files"][0]))

    with pytest.raises(ValueError, match="duplicate path"):
        verify_manifest(staged, manifest)


def test_backup_manifest_rejects_parent_traversal(tmp_path: Path) -> None:
    staged = _staged_backup(tmp_path)
    manifest = build_manifest(staged)
    manifest["files"][0]["path"] = "../outside.dump"

    with pytest.raises(ValueError, match="unsafe path"):
        verify_manifest(staged, manifest)


def test_backup_verification_requires_every_service_export(tmp_path: Path) -> None:
    staged = _staged_backup(tmp_path)
    manifest = build_manifest(staged)
    (staged / "postgres.dump").unlink()

    with pytest.raises(ValueError, match="required member"):
        verify_manifest(staged, manifest)


@pytest.mark.parametrize("member_name", ["../outside", "/absolute"])
def test_backup_archive_rejects_unsafe_paths(tmp_path: Path, member_name: str) -> None:
    archive_path = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        member = tarfile.TarInfo(member_name)
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))

    with tarfile.open(archive_path, "r:gz") as archive:
        with pytest.raises(ValueError, match="unsafe member"):
            _validate_archive_members(archive)


def test_backup_archive_rejects_links(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe-link.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        member = tarfile.TarInfo("objects/link")
        member.type = tarfile.SYMTYPE
        member.linkname = "../postgres.dump"
        archive.addfile(member)

    with tarfile.open(archive_path, "r:gz") as archive:
        with pytest.raises(ValueError, match="unsafe member"):
            _validate_archive_members(archive)
