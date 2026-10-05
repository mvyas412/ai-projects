from __future__ import annotations

import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from scripts.phase10_backup_cycle import _running_container_ids, run_backup_cycle

ROOT = Path(__file__).parents[1]
IDS = {
    service: f"{index:064x}"
    for index, service in enumerate(
        ("api", "dispatcher", "worker", "ui", "qdrant", "seaweedfs", "migrate", "models"), 1
    )
}


def _inventory(*services: str) -> bytes:
    return json.dumps(
        [{"Service": service, "ID": IDS[service], "State": "running"} for service in services]
    ).encode()


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
            stdout.write(_inventory("api", "dispatcher", "worker", "ui", "qdrant", "seaweedfs"))
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
    assert [
        "docker",
        "stop",
        *(IDS[role] for role in ("api", "dispatcher", "worker", "ui")),
    ] in commands
    assert ["docker", "start", IDS["qdrant"], IDS["seaweedfs"]] in commands
    assert commands[-1] == [
        "docker",
        "start",
        *(IDS[role] for role in ("api", "dispatcher", "worker", "ui")),
    ]
    assert not any(work.glob("staging-*"))
    assert len(list(output.glob("*.age"))) == 1


def test_backup_cycle_cleans_plaintext_and_restarts_after_failure(tmp_path: Path) -> None:
    compose, environment, work, output = _inputs(tmp_path)
    commands: list[list[str]] = []

    def runner(command: Sequence[str], _cwd: Path, stdout: Any) -> None:
        args = list(command)
        commands.append(args)
        if "ps" in args and stdout is not None:
            stdout.write(_inventory("api", "dispatcher", "ui", "qdrant", "seaweedfs"))
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
    assert ["docker", "start", IDS["api"], IDS["dispatcher"], IDS["ui"]] in commands


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
    backup_service = (ROOT / "deploy/oci/systemd/mm-rag-phase10-backup.service.example").read_text(
        encoding="utf-8"
    )
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


@pytest.mark.parametrize("json_lines", [False, True])
def test_running_inventory_accepts_compose_formats(json_lines: bool) -> None:
    entries = json.loads(_inventory("api", "ui", "migrate", "models"))
    raw = "\n".join(json.dumps(entry) for entry in entries) if json_lines else json.dumps(entries)
    assert _running_container_ids(raw) == {"api": IDS["api"], "ui": IDS["ui"]}


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[null]",
        '[{"Service":"api","State":"running"}]',
        '[{"Service":"api","State":"running","ID":"--invalid"}]',
        _inventory("api", "api").decode(),
        json.dumps([{"Service": "api", "State": "exited", "ID": IDS["api"]}]),
        json.dumps(
            [
                {"Service": service, "State": "running", "ID": IDS["api"]}
                for service in ("api", "ui")
            ]
        ),
    ],
)
def test_running_inventory_rejects_ambiguous_or_invalid_ids(raw: str) -> None:
    with pytest.raises(ValueError, match="Backup running-container inventory is invalid"):
        _running_container_ids(raw)


@pytest.mark.parametrize(
    "failure", [None, "application-stop", "storage-stop", "storage-start", "upload"]
)
def test_resume_never_starts_stopped_worker_or_dependency_jobs(
    tmp_path: Path,
    failure: str | None,
) -> None:
    compose, environment, work, output = _inputs(tmp_path)
    commands: list[list[str]] = []

    def runner(command: Sequence[str], _cwd: Path, stdout: Any) -> None:
        args = list(command)
        commands.append(args)
        if "ps" in args and stdout is not None:
            stdout.write(_inventory("api", "ui", "qdrant", "migrate", "models"))
        elif "exec" in args and stdout is not None:
            stdout.write(b"synthetic")
        if (
            (failure == "application-stop" and args == ["docker", "stop", IDS["api"], IDS["ui"]])
            or (failure == "storage-stop" and args == ["docker", "stop", IDS["qdrant"]])
            or (failure == "storage-start" and args == ["docker", "start", IDS["qdrant"]])
            or (failure == "upload" and args[:4] == ["oci", "os", "object", "put"])
        ):
            raise RuntimeError("simulated operation failure")

    def bundler(_source: Path, destination: Path, _recipient: str) -> None:
        destination.write_bytes(b"synthetic encrypted bundle")

    def cycle() -> dict[str, Any]:
        return run_backup_cycle(
            compose_file=compose,
            environment_file=environment,
            work_directory=work,
            output_directory=output,
            recipient="age1publicrecipient",
            runner=runner,
            bundler=bundler,
            upload_bucket="test-bucket",
            upload_namespace="test-namespace",
        )

    if failure:
        with pytest.raises(RuntimeError, match="simulated operation failure"):
            cycle()
    else:
        assert cycle()["status"] == "pass"
    assert not any(work.glob("staging-*"))
    assert commands[-1] == ["docker", "start", IDS["api"], IDS["ui"]]
    if failure != "application-stop":
        assert ["docker", "start", IDS["qdrant"]] in commands
    for command in commands:
        assert "up" not in command
        assert not (command[:2] == ["docker", "compose"] and "start" in command)
        assert not set(command) & {
            IDS[role] for role in ("worker", "seaweedfs", "migrate", "models")
        }


def test_invalid_inventory_fails_before_stopping_any_container(tmp_path: Path) -> None:
    compose, environment, work, output = _inputs(tmp_path)
    commands: list[list[str]] = []

    def runner(command: Sequence[str], _cwd: Path, stdout: Any) -> None:
        commands.append(list(command))
        stdout.write(_inventory("api", "api"))

    with pytest.raises(ValueError, match="Backup running-container inventory is invalid"):
        run_backup_cycle(
            compose_file=compose,
            environment_file=environment,
            work_directory=work,
            output_directory=output,
            recipient="age1publicrecipient",
            runner=runner,
        )
    assert len(commands) == 1
    assert not any(work.glob("staging-*"))
