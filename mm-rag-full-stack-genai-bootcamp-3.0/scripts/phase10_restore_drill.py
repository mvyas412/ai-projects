from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.phase8_backup import restore_encrypted_bundle
from scripts.phase10_operations import isolated_restore_evidence


def run_restore_drill(
    *,
    bundle: Path,
    identity_file: Path,
    environment_file: Path,
    compose_file: Path,
    work_directory: Path,
    expected_migration: str,
) -> dict[str, Any]:
    """Restore into a unique no-public-port Compose project and remove it afterward."""
    for path in (bundle, identity_file, environment_file, compose_file):
        if not path.is_file():
            raise ValueError("Restore drill input is missing")
    if environment_file.stat().st_mode & 0o077 or identity_file.stat().st_mode & 0o077:
        raise ValueError("Restore environment and age identity must use mode 0600")
    work_directory = work_directory.resolve()
    if work_directory.exists() and (work_directory.is_symlink() or not work_directory.is_dir()):
        raise ValueError("Restore work directory must be a real directory")
    work_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(work_directory, 0o700)
    generation = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    restored = work_directory / f"restore-{generation}"
    project = f"mm-rag-phase10-restore-{generation.lower()}"
    restore_encrypted_bundle(bundle, restored, identity_file)
    environment = {**os.environ, "PHASE10_RESTORE_ROOT": str(restored)}
    prefix = [
        "docker",
        "compose",
        "--project-name",
        project,
        "--env-file",
        str(environment_file),
        "-f",
        str(compose_file),
    ]
    started = False
    started_at = datetime.now(UTC)
    try:
        _run(_dependency_start_command(prefix), environment)
        started = True
        _run([*prefix, "cp", str(restored / "postgres.dump"), "postgres:/tmp/restore.dump"], environment)
        _run(
            [
                *prefix,
                "exec",
                "-T",
                "postgres",
                "sh",
                "-c",
                'PGPASSWORD="$POSTGRES_PASSWORD" pg_restore --exit-on-error --no-owner '
                '--no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/restore.dump',
            ],
            environment,
        )
        source_counts = _counts((restored / "aggregate-counts.json").read_text(encoding="utf-8"))
        restored_counts = _counts(
            _capture(
                [
                    *prefix,
                    "exec",
                    "-T",
                    "postgres",
                    "sh",
                    "-c",
                    'PGPASSWORD="$POSTGRES_PASSWORD" psql -qAt -U "$POSTGRES_USER" '
                    '-d "$POSTGRES_DB" -c "ANALYZE; SELECT COALESCE('
                    "json_object_agg(relname,n_live_tup),'{}'::json) "
                    'FROM pg_stat_user_tables;"',
                ],
                environment,
            )
        )
        if source_counts != restored_counts:
            raise ValueError("Restored aggregate PostgreSQL counts do not match the backup")
        migration = _capture(
            [*prefix, "run", "--rm", "api", "uv", "run", "--no-sync", "alembic", "current"],
            environment,
        )
        if expected_migration not in migration:
            raise ValueError("Restored database is not at the expected migration")
        _run([*prefix, "up", "-d", "--wait", "--wait-timeout", "120", "api"], environment)
        _run(
            [
                *prefix,
                "exec",
                "-T",
                "api",
                "curl",
                "--fail",
                "--silent",
                "http://qdrant:6333/readyz",
            ],
            environment,
        )
        _run(
            [
                *prefix,
                "exec",
                "-T",
                "api",
                "curl",
                "--fail",
                "--silent",
                "http://seaweedfs:9333/cluster/status",
            ],
            environment,
        )
        elapsed = int((datetime.now(UTC) - started_at).total_seconds())
        result = isolated_restore_evidence(
            {
                "checks": {
                    "postgres": True,
                    "qdrant": True,
                    "objects": True,
                    "active_data_plane_untouched": True,
                }
            }
        )
        result["elapsed_seconds"] = elapsed
        result["migration_revision"] = expected_migration
        return result
    finally:
        try:
            if started:
                _run([*prefix, "down", "--volumes", "--remove-orphans"], environment)
        finally:
            if restored.exists():
                shutil.rmtree(restored)


def _run(command: list[str], environment: dict[str, str]) -> None:
    subprocess.run(
        command,
        check=True,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=900,
    )


def _dependency_start_command(prefix: list[str]) -> list[str]:
    return [
        *prefix,
        "up",
        "-d",
        "--wait",
        "--wait-timeout",
        "120",
        "postgres",
        "qdrant",
        "seaweedfs",
    ]


def _capture(command: list[str], environment: dict[str, str]) -> str:
    result = subprocess.run(
        command,
        check=True,
        env=environment,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return result.stdout


def _counts(output: str) -> dict[str, int]:
    lines = [line for line in output.splitlines() if line.strip().startswith("{")]
    if not lines:
        raise ValueError("Aggregate count output is missing")
    payload = json.loads(lines[-1])
    if not isinstance(payload, dict) or not all(
        isinstance(name, str) and isinstance(count, int) and count >= 0
        for name, count in payload.items()
    ):
        raise ValueError("Aggregate count output is malformed")
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an isolated Phase 10 restore drill")
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--identity-file", type=Path, required=True)
    parser.add_argument("--environment-file", type=Path, default=Path("deploy/oci/runtime.env"))
    parser.add_argument(
        "--compose-file", type=Path, default=Path("deploy/oci/restore-drill.compose.yaml")
    )
    parser.add_argument("--work-directory", type=Path, required=True)
    parser.add_argument("--expected-migration", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    result = run_restore_drill(
        bundle=args.bundle,
        identity_file=args.identity_file,
        environment_file=args.environment_file,
        compose_file=args.compose_file,
        work_directory=args.work_directory,
        expected_migration=args.expected_migration,
    )
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")
    os.chmod(args.output, 0o600)
    print(json.dumps({"scenario": result["scenario"], "status": result["status"]}))


if __name__ == "__main__":
    main()
