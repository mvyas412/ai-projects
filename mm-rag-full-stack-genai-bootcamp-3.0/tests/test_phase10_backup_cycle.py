from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from scripts.phase10_backup_cycle import run_backup_cycle

ROOT = Path(__file__).parents[1]


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    compose = tmp_path / "compose.yaml"
    compose.write_text("services: {}\n", encoding="utf-8")
    environment = tmp_path / "runtime.env"
    environment.write_text("POSTGRES_USER=private\n", encoding="utf-8")
    os.chmod(environment, 0o600)
    return compose, environment, tmp_path / "work", tmp_path / "encrypted"


def test_backup_cycle_quiesces_copies_encrypts_and_restarts(tmp_path: Path) -> None:
    compose, environment, work, output = _inputs(tmp_path)
    commands: list[list[str]] = []

    def runner(command: Sequence[str], _cwd: Path, stdout: Any) -> None:
        args = list(command)
        commands.append(args)
        if "ps" in args and stdout is not None:
            stdout.write(b"api\ndispatcher\nworker\nui\n")
        if "exec" in args and stdout is not None:
            stdout.write(b"postgres")
        if "cp" in args:
            destination = Path(args[-1])
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "snapshot").write_bytes(b"snapshot")

    def bundler(_source: Path, destination: Path, _recipient: str) -> None:
        destination.write_bytes(b"encrypted")

    result = run_backup_cycle(
        compose_file=compose,
        environment_file=environment,
        work_directory=work,
        output_directory=output,
        recipient="age1publicrecipient",
        runner=runner,
        bundler=bundler,
        now=datetime(2026, 9, 20, 5, 30, tzinfo=UTC),
    )
    assert result["status"] == "pass"
    assert result["uploaded"] is False
    assert any(command[-5:] == ["stop", "api", "dispatcher", "worker", "ui"] for command in commands)
    assert any(command[-4:] == ["up", "-d", "qdrant", "seaweedfs"] for command in commands)
    assert not any(work.glob("staging-*"))
    assert len(list(output.glob("*.age"))) == 1


def test_backup_cycle_cleans_plaintext_and_restarts_after_failure(tmp_path: Path) -> None:
    compose, environment, work, output = _inputs(tmp_path)
    commands: list[list[str]] = []

    def runner(command: Sequence[str], _cwd: Path, stdout: Any) -> None:
        args = list(command)
        commands.append(args)
        if "ps" in args and stdout is not None:
            stdout.write(b"api\ndispatcher\nui\n")
        if "exec" in args and stdout is not None:
            stdout.write(b"postgres")

    def fail_bundle(_source: Path, _destination: Path, _recipient: str) -> None:
        raise RuntimeError("simulated encryption failure")

    with pytest.raises(RuntimeError, match="simulated encryption failure"):
        run_backup_cycle(
            compose_file=compose,
            environment_file=environment,
            work_directory=work,
            output_directory=output,
            recipient="age1publicrecipient",
            runner=runner,
            bundler=fail_bundle,
            now=datetime(2026, 9, 20, 5, 30, tzinfo=UTC),
        )
    assert not any(work.glob("staging-*"))
    assert any(command[-5:] == ["up", "-d", "api", "dispatcher", "ui"] for command in commands)


def test_backup_cycle_accepts_age_ssh_public_recipient(tmp_path: Path) -> None:
    compose, environment, work, output = _inputs(tmp_path)

    def runner(command: Sequence[str], _cwd: Path, stdout: Any) -> None:
        args = list(command)
        if "ps" in args and stdout is not None:
            stdout.write(b"")
        if "exec" in args and stdout is not None:
            stdout.write(b"postgres")
        if "cp" in args:
            Path(args[-1]).mkdir(parents=True, exist_ok=True)

    def bundler(_source: Path, destination: Path, recipient: str) -> None:
        assert recipient.startswith("ssh-ed25519 ")
        destination.write_bytes(b"encrypted")

    result = run_backup_cycle(
        compose_file=compose,
        environment_file=environment,
        work_directory=work,
        output_directory=output,
        recipient="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestOnly",
        runner=runner,
        bundler=bundler,
        now=datetime(2026, 9, 20, 5, 30, tzinfo=UTC),
    )

    assert result["status"] == "pass"


def test_backup_upload_uses_instance_principal_and_checksum(tmp_path: Path) -> None:
    compose, environment, work, output = _inputs(tmp_path)
    commands: list[list[str]] = []

    def runner(command: Sequence[str], _cwd: Path, stdout: Any) -> None:
        args = list(command)
        commands.append(args)
        if "ps" in args and stdout is not None:
            stdout.write(b"")
        if "exec" in args and stdout is not None:
            stdout.write(b"postgres")
        if "cp" in args:
            destination = Path(args[-1])
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "snapshot").write_bytes(b"snapshot")

    def bundler(_source: Path, destination: Path, _recipient: str) -> None:
        destination.write_bytes(b"encrypted")

    result = run_backup_cycle(
        compose_file=compose,
        environment_file=environment,
        work_directory=work,
        output_directory=output,
        recipient="age1publicrecipient",
        upload_bucket="backup-bucket",
        upload_namespace="learning-namespace",
        runner=runner,
        bundler=bundler,
        now=datetime(2026, 9, 20, 5, 30, tzinfo=UTC),
    )

    upload = next(command for command in commands if command[:4] == ["oci", "os", "object", "put"])
    assert upload[upload.index("--auth") + 1] == "instance_principal"
    assert upload[upload.index("--namespace-name") + 1] == "learning-namespace"
    assert upload[upload.index("--bucket-name") + 1] == "backup-bucket"
    assert "--verify-checksum" in upload
    assert upload[upload.index("--opc-checksum-algorithm") + 1] == "SHA256"
    assert result["uploaded"] is True


def test_oci_backup_identity_and_timer_examples_are_least_privilege() -> None:
    terraform = (ROOT / "deploy/oci/terraform/main.tf").read_text(encoding="utf-8")
    backup_service = (
        ROOT / "deploy/oci/systemd/mm-rag-phase10-backup.service.example"
    ).read_text(encoding="utf-8")
    capacity_service = (
        ROOT / "deploy/oci/systemd/mm-rag-phase10-capacity.service.example"
    ).read_text(encoding="utf-8")

    assert 'resource "oci_identity_dynamic_group" "backup_uploader"' in terraform
    assert "instance.id = '${oci_core_instance.app.id}'" in terraform
    assert "request.permission = 'OBJECT_CREATE'" in terraform
    assert "target.bucket.name = '${oci_objectstorage_bucket.backups.name}'" in terraform
    assert "manage object-family" not in terraform
    assert "manage buckets" not in terraform
    for unit in (backup_service, capacity_service):
        assert "/usr/bin/python3" not in unit
        assert "ExecStart=/opt/mm-rag/.tools/bin/python3.12 -m scripts." in unit
