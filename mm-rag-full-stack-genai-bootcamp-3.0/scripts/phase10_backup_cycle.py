from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.phase8_backup import build_manifest, create_encrypted_bundle
from scripts.phase10_operations import backup_verification_evidence

Runner = Callable[[Sequence[str], Path, Any], None]
Bundler = Callable[[Path, Path, str], None]


def run_backup_cycle(
    *,
    compose_file: Path,
    environment_file: Path,
    work_directory: Path,
    output_directory: Path,
    recipient: str,
    upload_bucket: str | None = None,
    upload_namespace: str | None = None,
    runner: Runner | None = None,
    bundler: Bundler = create_encrypted_bundle,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create one encrypted backup while keeping plaintext bounded and local."""
    compose_file = compose_file.resolve()
    environment_file = environment_file.resolve()
    work_directory = work_directory.resolve()
    output_directory = output_directory.resolve()
    _validate_inputs(compose_file, environment_file, work_directory, output_directory, recipient)
    run = runner or _run
    work_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(work_directory, 0o700)
    output_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(output_directory, 0o700)
    lock_path = work_directory / "backup.lock"
    if lock_path.is_symlink():
        raise ValueError("Backup lease cannot be a symlink")
    recorded_at = (now or datetime.now(UTC)).astimezone(UTC)
    generation = recorded_at.strftime("%Y%m%dT%H%M%SZ")
    staging = work_directory / f"staging-{generation}"
    bundle = output_directory / f"mm-rag-{generation}.tar.gz.age"
    if staging.exists() or bundle.exists():
        raise ValueError("Backup generation already exists")

    prefix = [
        "docker",
        "compose",
        "--env-file",
        str(environment_file),
        "-f",
        str(compose_file),
    ]
    with lock_path.open("a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another backup operation holds the lease") from exc
        staging.mkdir(mode=0o700)
        (staging / "qdrant").mkdir(mode=0o700)
        (staging / "objects").mkdir(mode=0o700)
        stopped_storage = False
        application_services: list[str] = []
        try:
            running_path = staging / "running-services.txt"
            with running_path.open("wb") as running_services:
                run(
                    [*prefix, "ps", "--services", "--status", "running"],
                    compose_file.parent,
                    running_services,
                )
            running = set(running_path.read_text(encoding="utf-8").splitlines())
            running_path.unlink()
            application_services = [
                service
                for service in ("api", "dispatcher", "worker", "ui")
                if service in running
            ]
            if application_services:
                run(
                    [*prefix, "stop", *application_services],
                    compose_file.parent,
                    None,
                )
            with (staging / "postgres.dump").open("wb") as postgres_dump:
                run(
                    [
                        *prefix,
                        "exec",
                        "-T",
                        "postgres",
                        "sh",
                        "-c",
                        'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" '
                        '-d "$POSTGRES_DB" -Fc',
                    ],
                    compose_file.parent,
                    postgres_dump,
                )
            with (staging / "aggregate-counts.json").open("wb") as counts:
                run(
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
                    compose_file.parent,
                    counts,
                )
            run([*prefix, "stop", "qdrant", "seaweedfs"], compose_file.parent, None)
            stopped_storage = True
            run(
                [*prefix, "cp", "qdrant:/qdrant/storage/.", str(staging / "qdrant")],
                compose_file.parent,
                None,
            )
            run(
                [*prefix, "cp", "seaweedfs:/data/.", str(staging / "objects")],
                compose_file.parent,
                None,
            )
            manifest = build_manifest(staging)
            bundler(staging, bundle, recipient)
            bundle_digest = _sha256(bundle)
            if upload_bucket:
                if not upload_namespace:
                    raise ValueError("OCI namespace is required for upload")
                run(
                    [
                        "oci",
                        "os",
                        "object",
                        "put",
                        "--auth",
                        "instance_principal",
                        "--namespace-name",
                        upload_namespace,
                        "--bucket-name",
                        upload_bucket,
                        "--name",
                        bundle.name,
                        "--file",
                        str(bundle),
                        "--no-multipart",
                        "--verify-checksum",
                        "--opc-checksum-algorithm",
                        "SHA256",
                        "--force",
                    ],
                    compose_file.parent,
                    None,
                )
            evidence = backup_verification_evidence(
                {
                    "manifest_sha256": hashlib.sha256(
                        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest(),
                    "encrypted_bundle_sha256": bundle_digest,
                    "file_count": len(manifest["files"]),
                    "total_bytes": sum(int(item["bytes"]) for item in manifest["files"]),
                }
            )
            evidence["uploaded"] = upload_bucket is not None
            return evidence
        finally:
            try:
                if stopped_storage:
                    run(
                        [*prefix, "up", "-d", "qdrant", "seaweedfs"],
                        compose_file.parent,
                        None,
                    )
            finally:
                try:
                    if application_services:
                        run(
                            [*prefix, "up", "-d", *application_services],
                            compose_file.parent,
                            None,
                        )
                finally:
                    if staging.exists():
                        shutil.rmtree(staging)


def _validate_inputs(
    compose_file: Path,
    environment_file: Path,
    work_directory: Path,
    output_directory: Path,
    recipient: str,
) -> None:
    if not compose_file.is_file() or not environment_file.is_file():
        raise ValueError("Compose and environment files must exist")
    if environment_file.stat().st_mode & 0o077:
        raise ValueError("Environment file permissions must be 0600")
    normalized_recipient = recipient.strip()
    if not (
        normalized_recipient.startswith("age1")
        or normalized_recipient.startswith("ssh-ed25519 ")
        or normalized_recipient.startswith("ssh-rsa ")
    ):
        raise ValueError("A public age recipient is required")
    for directory in (work_directory, output_directory):
        if directory.exists() and (directory.is_symlink() or not directory.is_dir()):
            raise ValueError("Backup directories must be real directories")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _run(command: Sequence[str], cwd: Path, stdout: Any) -> None:
    subprocess.run(
        list(command),
        cwd=cwd,
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=stdout if stdout is not None else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=900,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one bounded Phase 10 backup cycle")
    parser.add_argument("--compose-file", type=Path, default=Path("deploy/oci/compose.yaml"))
    parser.add_argument("--environment-file", type=Path, default=Path("deploy/oci/runtime.env"))
    parser.add_argument("--work-directory", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--recipient-file", type=Path, required=True)
    parser.add_argument("--upload", action="store_true")
    return parser


def main() -> None:
    args = _parser().parse_args()
    recipient = args.recipient_file.read_text(encoding="utf-8").strip()
    bucket = os.environ.get("PHASE10_OCI_BACKUP_BUCKET") if args.upload else None
    namespace = os.environ.get("PHASE10_OCI_NAMESPACE") if args.upload else None
    if args.upload and not bucket:
        raise ValueError("PHASE10_OCI_BACKUP_BUCKET is required for upload")
    if args.upload and not namespace:
        raise ValueError("PHASE10_OCI_NAMESPACE is required for upload")
    result = run_backup_cycle(
        compose_file=args.compose_file,
        environment_file=args.environment_file,
        work_directory=args.work_directory,
        output_directory=args.output_directory,
        recipient=recipient,
        upload_bucket=bucket,
        upload_namespace=namespace,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
