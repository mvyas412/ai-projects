from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = "mm-rag-phase8-backup-v1"
REQUIRED_MEMBERS = ("postgres.dump", "qdrant", "objects")


def build_manifest(source: Path) -> dict[str, Any]:
    """Describe a staged backup without following links or reading secret values."""
    source = source.resolve()
    for member in REQUIRED_MEMBERS:
        if not (source / member).exists():
            raise ValueError(f"Backup staging directory is missing {member}")

    files: list[dict[str, object]] = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Backup staging directory contains a symlink: {path.name}")
        if not path.is_file() or path.name == "manifest.json":
            continue
        relative = path.relative_to(source).as_posix()
        files.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    if not files:
        raise ValueError("Backup staging directory contains no files")
    return {"schema": SCHEMA, "files": files}


def verify_manifest(source: Path, manifest: dict[str, Any]) -> None:
    if any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("Backup contains a symlink")
    for member in REQUIRED_MEMBERS:
        if not (source / member).exists():
            raise ValueError(f"Backup is missing required member: {member}")
    if manifest.get("schema") != SCHEMA or not isinstance(manifest.get("files"), list):
        raise ValueError("Unsupported backup manifest")
    expected_paths: set[str] = set()
    for entry in manifest["files"]:
        if not isinstance(entry, dict):
            raise ValueError("Malformed backup manifest entry")
        relative = str(entry.get("path", ""))
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("Backup manifest contains an unsafe path")
        candidate = (source / relative).resolve()
        if not relative or source.resolve() not in candidate.parents:
            raise ValueError("Backup manifest contains an unsafe path")
        if relative in expected_paths:
            raise ValueError("Backup manifest contains a duplicate path")
        expected_paths.add(relative)
        if not candidate.is_file():
            raise ValueError(f"Backup member is missing: {relative}")
        if candidate.stat().st_size != entry.get("bytes") or _sha256(candidate) != entry.get(
            "sha256"
        ):
            raise ValueError(f"Backup member failed integrity verification: {relative}")

    actual_paths = {
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if actual_paths != expected_paths:
        raise ValueError("Backup contains unmanifested or missing files")


def create_encrypted_bundle(source: Path, output: Path, recipient: str) -> None:
    if not recipient.strip():
        raise ValueError("An age recipient is required")
    if output.suffix != ".age":
        raise ValueError("Encrypted backup output must use the .age suffix")
    if shutil.which("age") is None:
        raise RuntimeError("age is required to create encrypted backup bundles")

    manifest = build_manifest(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mm-rag-backup-") as temporary:
        temporary_path = Path(temporary)
        os.chmod(temporary_path, 0o700)
        manifest_path = source / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.chmod(manifest_path, 0o600)
        archive = temporary_path / "backup.tar.gz"
        try:
            with tarfile.open(archive, "w:gz") as bundle:
                for path in sorted(source.rglob("*")):
                    if path.is_file() and not path.is_symlink():
                        bundle.add(path, arcname=path.relative_to(source), recursive=False)
            subprocess.run(
                ["age", "--recipient", recipient, "--output", str(output), str(archive)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            os.chmod(output, 0o600)
        except Exception:
            output.unlink(missing_ok=True)
            raise
        finally:
            manifest_path.unlink(missing_ok=True)


def restore_encrypted_bundle(bundle: Path, destination: Path, identity: Path) -> None:
    """Decrypt, safely extract, and verify a backup before promoting it."""
    if bundle.suffix != ".age" or not bundle.is_file():
        raise ValueError("Encrypted backup input must be an existing .age file")
    if not identity.is_file():
        raise ValueError("An existing age identity file is required")
    if destination.exists():
        raise ValueError("Restore destination must not already exist")
    if shutil.which("age") is None:
        raise RuntimeError("age is required to restore encrypted backup bundles")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="mm-rag-restore-", dir=destination.parent
    ) as temporary:
        temporary_path = Path(temporary)
        os.chmod(temporary_path, 0o700)
        archive = temporary_path / "backup.tar.gz"
        extracted = temporary_path / "extracted"
        extracted.mkdir(mode=0o700)
        subprocess.run(
            [
                "age",
                "--decrypt",
                "--identity",
                str(identity),
                "--output",
                str(archive),
                str(bundle),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with tarfile.open(archive, "r:gz") as encrypted_archive:
            _validate_archive_members(encrypted_archive)
            encrypted_archive.extractall(extracted, filter="data")
        manifest_path = extracted / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError("Backup archive is missing manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        verify_manifest(extracted, manifest)
        os.replace(extracted, destination)


def _validate_archive_members(archive: tarfile.TarFile) -> None:
    seen: set[str] = set()
    for member in archive.getmembers():
        path = Path(member.name)
        if (
            not member.name
            or path.is_absolute()
            or ".." in path.parts
            or not (member.isfile() or member.isdir())
        ):
            raise ValueError("Backup archive contains an unsafe member")
        normalized = path.as_posix()
        if normalized in seen:
            raise ValueError("Backup archive contains a duplicate member")
        seen.add(normalized)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or verify a Phase 8 backup bundle")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="create an encrypted bundle")
    create.add_argument("source", type=Path, help="staging directory containing service exports")
    create.add_argument("output", type=Path, help="encrypted .age output path")
    create.add_argument(
        "--recipient-env",
        default="PHASE8_BACKUP_AGE_RECIPIENT",
        help="environment variable containing the public age recipient",
    )
    create.add_argument(
        "--recipient-file",
        type=Path,
        help="file containing the public age recipient (overrides --recipient-env)",
    )
    verify = commands.add_parser("verify", help="verify a safely extracted bundle")
    verify.add_argument("source", type=Path, help="directory containing manifest.json")
    restore = commands.add_parser("restore", help="decrypt and verify into a new directory")
    restore.add_argument("bundle", type=Path, help="encrypted .age backup bundle")
    restore.add_argument("destination", type=Path, help="new restore destination")
    restore.add_argument(
        "--identity-file", required=True, type=Path, help="local age identity file"
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    result: dict[str, object]
    if args.command == "create":
        recipient = (
            args.recipient_file.read_text(encoding="utf-8").strip()
            if args.recipient_file
            else os.environ.get(args.recipient_env, "")
        )
        create_encrypted_bundle(args.source, args.output, recipient)
        result = {"output": str(args.output), "schema": SCHEMA, "status": "created"}
    elif args.command == "verify":
        manifest_path = args.source / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        verify_manifest(args.source, manifest)
        result = {"files": len(manifest["files"]), "schema": SCHEMA, "status": "verified"}
    else:
        restore_encrypted_bundle(args.bundle, args.destination, args.identity_file)
        result = {
            "destination": str(args.destination),
            "schema": SCHEMA,
            "status": "restored-and-verified",
        }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
