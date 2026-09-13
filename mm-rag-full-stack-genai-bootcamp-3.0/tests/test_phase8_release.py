from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.phase8_release import SCHEMA, validate_release_manifest


def _manifest() -> dict[str, object]:
    digest = "0" * 64
    return {
        "schema": SCHEMA,
        "git_revision": "1" * 40,
        "migration_revision": "0012_phase7_feedback",
        "images": {
            name: f"registry.example/mm-rag/{name}@sha256:{digest}"
            for name in ("app", "caddy", "postgres", "qdrant", "rabbitmq", "seaweedfs")
        },
        "rollback_manifest": "previous-release.json",
    }


def test_release_manifest_accepts_digest_pinned_images(tmp_path: Path) -> None:
    path = tmp_path / "release.json"
    path.write_text(json.dumps(_manifest()), encoding="utf-8")

    result = validate_release_manifest(path)

    assert result["status"] == "valid"
    assert result["images"] == 6


def test_release_manifest_rejects_mutable_tag(tmp_path: Path) -> None:
    payload = _manifest()
    payload["images"]["app"] = "registry.example/mm-rag/app:latest"  # type: ignore[index]
    path = tmp_path / "release.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="not digest-pinned"):
        validate_release_manifest(path)


def test_release_manifest_rejects_secret_fields(tmp_path: Path) -> None:
    payload = _manifest()
    payload["password"] = "must-not-appear"
    path = tmp_path / "release.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="forbidden fields"):
        validate_release_manifest(path)


def test_release_manifest_requires_full_commit_sha(tmp_path: Path) -> None:
    payload = _manifest()
    payload["git_revision"] = "abc123"
    path = tmp_path / "release.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="full Git commit SHA"):
        validate_release_manifest(path)


def test_release_manifest_requires_previous_manifest(tmp_path: Path) -> None:
    payload = _manifest()
    payload["rollback_manifest"] = ""
    path = tmp_path / "release.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="rollback_manifest"):
        validate_release_manifest(path)
