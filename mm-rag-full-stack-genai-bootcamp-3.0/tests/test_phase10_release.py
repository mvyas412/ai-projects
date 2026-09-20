from __future__ import annotations

import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import scripts.phase10_release as release


def _plan(tmp_path: Path) -> dict[str, Any]:
    digest = "1" * 64
    images = {
        "app": f"example/app@sha256:{digest}",
        "caddy": f"caddy@sha256:{digest}",
        "postgres": f"postgres@sha256:{digest}",
        "qdrant": f"qdrant/qdrant@sha256:{digest}",
        "rabbitmq": f"rabbitmq@sha256:{digest}",
        "seaweedfs": f"chrislusf/seaweedfs@sha256:{digest}",
    }
    deploy = tmp_path / "deploy" / "oci"
    deploy.mkdir(parents=True)
    (deploy / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    environment = deploy / "runtime.env"
    environment.write_text(
        "\n".join(
            (
                f"MM_RAG_IMAGE={images['app']}",
                f'CADDY_IMAGE="{images["caddy"]}"',
                f"POSTGRES_IMAGE='{images['postgres']}'",
                f"QDRANT_IMAGE={images['qdrant']}",
                f"RABBITMQ_IMAGE={images['rabbitmq']}",
                f"SEAWEEDFS_IMAGE={images['seaweedfs']}",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    os.chmod(environment, 0o600)
    manifest: dict[str, Any] = {
        "schema": "mm-rag-phase8-release-v1",
        "initial_release": True,
        "git_revision": "b" * 40,
        "migration_revision": "20260919_0019",
        "images": images,
        "rollback_manifest": None,
    }
    (deploy / "release.json").write_text(json.dumps(manifest), encoding="utf-8")
    current_manifest = {**manifest, "git_revision": "a" * 40}
    (deploy / "current-release.json").write_text(
        json.dumps(current_manifest), encoding="utf-8"
    )
    return {
        "schema": release.SCHEMA,
        "action": "upgrade",
        "current_revision": "a" * 40,
        "target_revision": "b" * 40,
        "backup_verified_at": "2026-09-20T10:00:00Z",
        "compose_file": "deploy/oci/compose.yaml",
        "environment_file": "deploy/oci/runtime.env",
        "current_release_manifest": "deploy/oci/current-release.json",
        "release_manifest": "deploy/oci/release.json",
        "state_directory": "operations/private/release-state",
        "migration_strategy": "forward-only",
        "application_services": ["api", "dispatcher", "ui", "edge"],
        "operator_authorized": False,
        "checks": {
            "digest_pinned": True,
            "backup_fresh": True,
            "migration_compatible": True,
            "disk_headroom": True,
            "jobs_quiesced": True,
            "health_ready": True,
            "rollback_or_restore_available": True,
        },
    }


def test_release_plan_validates_exact_manifest_and_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(release, "PROJECT_ROOT", tmp_path)
    result = release.validate_plan(
        _plan(tmp_path), now=datetime(2026, 9, 20, 11, tzinfo=UTC)
    )
    assert result["status"] == "ready"
    assert result["operator_authorized"] is False


def test_release_execution_requires_exact_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(release, "PROJECT_ROOT", tmp_path)
    payload = _plan(tmp_path)
    with pytest.raises(ValueError, match="Exact plan hash"):
        release.execute_plan(
            payload,
            confirmation="wrong",
            authorized=True,
            runner=lambda _command, _cwd: None,
            now=datetime(2026, 9, 20, 11, tzinfo=UTC),
        )


def test_release_execution_is_bounded_and_records_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(release, "PROJECT_ROOT", tmp_path)
    payload = _plan(tmp_path)
    commands: list[list[str]] = []

    def capture(command: Sequence[str], _cwd: Path) -> None:
        commands.append(list(command))

    result = release.execute_plan(
        payload,
        confirmation=release.plan_hash(payload),
        authorized=True,
        runner=capture,
        now=datetime(2026, 9, 20, 11, tzinfo=UTC),
    )
    assert result["status"] == "executed-awaiting-verification"
    assert len(commands) == 8
    assert commands[2][-3:] == ["stop", "dispatcher", "worker"]
    assert any(command[-3:] == ["run", "--rm", "migrate"] for command in commands)
    assert (
        tmp_path / "operations" / "private" / "release-state" / "deployed-revision"
    ).read_text(encoding="utf-8").strip() == "b" * 40


def test_rollback_preserves_forward_only_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(release, "PROJECT_ROOT", tmp_path)
    payload = _plan(tmp_path)
    payload["action"] = "rollback"
    commands: list[list[str]] = []

    release.execute_plan(
        payload,
        confirmation=release.plan_hash(payload),
        authorized=True,
        runner=lambda command, _cwd: commands.append(list(command)),
        now=datetime(2026, 9, 20, 11, tzinfo=UTC),
    )

    assert len(commands) == 6
    assert not any(command[-3:] == ["run", "--rm", "migrate"] for command in commands)
    assert not any(command[-3:] == ["run", "--rm", "models"] for command in commands)
    assert "--no-deps" in commands[4]


def test_restore_execution_requires_isolated_runbook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(release, "PROJECT_ROOT", tmp_path)
    payload = _plan(tmp_path)
    payload["action"] = "restore"

    with pytest.raises(ValueError, match="isolated restore runbook"):
        release.execute_plan(
            payload,
            confirmation=release.plan_hash(payload),
            authorized=True,
            runner=lambda _command, _cwd: None,
            now=datetime(2026, 9, 20, 11, tzinfo=UTC),
        )


def test_release_plan_rejects_stale_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(release, "PROJECT_ROOT", tmp_path)
    with pytest.raises(ValueError, match="older than 48 hours"):
        release.validate_plan(
            _plan(tmp_path), now=datetime(2026, 9, 23, 11, tzinfo=UTC)
        )
