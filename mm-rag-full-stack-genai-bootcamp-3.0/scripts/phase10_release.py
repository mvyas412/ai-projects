from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.phase8_release import validate_release_manifest
from scripts.phase10_operations import load_json, release_preflight_evidence

SCHEMA = "mm-rag-phase10-release-plan-v1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_ENV = {
    "app": "MM_RAG_IMAGE",
    "caddy": "CADDY_IMAGE",
    "postgres": "POSTGRES_IMAGE",
    "qdrant": "QDRANT_IMAGE",
    "rabbitmq": "RABBITMQ_IMAGE",
    "seaweedfs": "SEAWEEDFS_IMAGE",
}
REQUIRED_APPLICATION_SERVICES = {"api", "dispatcher", "ui", "edge"}
ALLOWED_APPLICATION_SERVICES = REQUIRED_APPLICATION_SERVICES | {"worker"}
Runner = Callable[[Sequence[str], Path], None]


def validate_plan(payload: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Validate exact inputs without authorizing or changing deployment state."""
    if payload.get("schema") != SCHEMA:
        raise ValueError("Unsupported Phase 10 release-plan schema")
    if payload.get("operator_authorized") is not False:
        raise ValueError("Stored plans must remain unauthorized")
    if payload.get("migration_strategy") != "forward-only":
        raise ValueError("Only forward-only migration plans are supported")
    application_services = payload.get("application_services")
    if (
        not isinstance(application_services, list)
        or not all(isinstance(item, str) for item in application_services)
        or len(application_services) != len(set(application_services))
        or not REQUIRED_APPLICATION_SERVICES.issubset(application_services)
        or not set(application_services).issubset(ALLOWED_APPLICATION_SERVICES)
    ):
        raise ValueError("application_services must use the exact approved service allowlist")

    preflight = release_preflight_evidence(payload)
    if preflight["status"] != "ready":
        raise ValueError("Release preflight is blocked")
    backup_at = _timestamp(payload.get("backup_verified_at"))
    current_time = now or datetime.now(UTC)
    if current_time.astimezone(UTC) - backup_at > timedelta(hours=48):
        raise ValueError("Verified backup is older than 48 hours")

    compose = _project_file(payload, "compose_file")
    environment = _project_file(payload, "environment_file")
    current_manifest_path = _project_file(payload, "current_release_manifest")
    manifest_path = _project_file(payload, "release_manifest")
    state_directory = _project_path(payload, "state_directory")
    if not all(
        path.is_file()
        for path in (compose, environment, current_manifest_path, manifest_path)
    ):
        raise ValueError("Release plan references a missing deployment file")
    if environment.stat().st_mode & 0o077:
        raise ValueError("Release environment file permissions must be 0600")
    validate_release_manifest(manifest_path)
    validate_release_manifest(current_manifest_path)
    manifest = load_json(manifest_path)
    current_manifest = load_json(current_manifest_path)
    if current_manifest.get("git_revision") != payload.get("current_revision"):
        raise ValueError("Current release manifest does not match current_revision")
    if manifest.get("git_revision") != payload.get("target_revision"):
        raise ValueError("Release manifest revision does not match target_revision")
    _validate_images(environment, manifest)
    if state_directory.exists() and state_directory.is_symlink():
        raise ValueError("Release state directory cannot be a symlink")
    deployed_revision = state_directory / "deployed-revision"
    if deployed_revision.is_file() and (
        deployed_revision.read_text(encoding="utf-8").strip()
        != payload.get("current_revision")
    ):
        raise ValueError("Recorded deployed revision changed after planning")
    return {
        "schema": SCHEMA,
        "status": "ready",
        "action": payload["action"],
        "plan_sha256": plan_hash(payload),
        "target_revision": payload["target_revision"],
        "operator_authorized": False,
    }


def execute_plan(
    payload: dict[str, Any],
    *,
    confirmation: str,
    authorized: bool,
    runner: Runner | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Execute a reviewed immutable plan; rollback remains a separate reviewed plan."""
    validated = validate_plan(payload, now=now)
    expected = validated["plan_sha256"]
    if not authorized or confirmation != expected:
        raise ValueError("Exact plan hash and explicit operator authorization are required")
    run = runner or _run
    compose = _project_file(payload, "compose_file")
    environment = _project_file(payload, "environment_file")
    state_directory = _project_path(payload, "state_directory")
    state_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(state_directory, 0o700)
    lock_path = state_directory / "release.lock"
    if lock_path.is_symlink():
        raise ValueError("Release lock cannot be a symlink")
    prefix = [
        "docker",
        "compose",
        "--env-file",
        str(environment),
        "-f",
        str(compose),
    ]
    application_services = list(payload["application_services"])
    commands = [
        [*prefix, "config", "--quiet"],
        [*prefix, "pull"],
        [*prefix, "stop", "dispatcher", "worker"],
        [*prefix, "run", "--rm", "migrate"],
        [*prefix, "run", "--rm", "models"],
        [*prefix, "up", "-d", "postgres", "qdrant", "seaweedfs", "rabbitmq"],
        [
            *prefix,
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            "180",
            *application_services,
        ],
        [*prefix, "ps"],
    ]
    with lock_path.open("a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another release operation holds the lease") from exc
        for command in commands:
            run(command, PROJECT_ROOT)
        revision_path = state_directory / "deployed-revision"
        revision_path.write_text(str(payload["target_revision"]) + "\n", encoding="utf-8")
        os.chmod(revision_path, 0o600)
    return {
        "schema": SCHEMA,
        "status": "executed-awaiting-verification",
        "action": payload["action"],
        "plan_sha256": expected,
        "target_revision": payload["target_revision"],
    }


def plan_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_images(environment: Path, manifest: dict[str, Any]) -> None:
    values: dict[str, str] = {}
    for raw in environment.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    images = manifest.get("images")
    if not isinstance(images, dict):
        raise ValueError("Release manifest images are missing")
    mismatched = [
        name for name, env_name in IMAGE_ENV.items() if values.get(env_name) != images.get(name)
    ]
    if mismatched:
        raise ValueError(f"Runtime environment image mismatch: {', '.join(mismatched)}")


def _project_file(payload: dict[str, Any], key: str) -> Path:
    return _project_path(payload, key)


def _project_path(payload: dict[str, Any], key: str) -> Path:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a project-relative path")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{key} must stay within the project")
    resolved = (PROJECT_ROOT / relative).resolve()
    if resolved != PROJECT_ROOT and PROJECT_ROOT not in resolved.parents:
        raise ValueError(f"{key} must stay within the project")
    return resolved


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("backup_verified_at must be an ISO-8601 timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("backup_verified_at must include a timezone")
    return parsed.astimezone(UTC)


def _run(command: Sequence[str], cwd: Path) -> None:
    subprocess.run(
        list(command),
        cwd=cwd,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=900,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan or execute a Phase 10 release")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("input", type=Path)
    execute = commands.add_parser("execute")
    execute.add_argument("input", type=Path)
    execute.add_argument("--authorize", action="store_true")
    execute.add_argument("--confirm-plan-sha", required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    payload = load_json(args.input)
    if args.command == "plan":
        result = validate_plan(payload)
    else:
        result = execute_plan(
            payload,
            confirmation=args.confirm_plan_sha,
            authorized=args.authorize,
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
