from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.phase10_operations import capacity_evidence, load_json


def collect_snapshot(
    *,
    compose_file: Path,
    environment_file: Path,
    backup_directory: Path,
    inventory_status_file: Path,
    state_file: Path,
    certificate_host: str,
    policy: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Collect identifier-free host guardrails; private coordinates stay in arguments."""
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    cpu_percent = _cpu_percent()
    memory_percent = _memory_percent()
    disk_percent, inode_percent = _filesystem_percent(Path("/"))
    operations = _operations_report(compose_file, environment_file)
    oldest_seconds = operations.get("oldest_due_event_age_seconds")
    queue_age = float(oldest_seconds or 0) / 60
    queue_critical = bool(operations.get("alert")) and queue_age > 0
    backup_age = _backup_age_hours(backup_directory, observed_at)
    certificate_days = _certificate_days(certificate_host, observed_at)
    inventory = load_json(inventory_status_file)
    unexpected_paid = inventory.get("unexpected_paid_resources")
    if not isinstance(unexpected_paid, bool):
        raise ValueError("Inventory status must declare unexpected_paid_resources")
    sustained = _sustained_minutes(
        state_file,
        observed_at,
        max(cpu_percent, memory_percent, disk_percent, inode_percent)
        >= policy["capacity"]["review_percent"],
    )
    return capacity_evidence(
        {
            "metrics": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "disk_percent": disk_percent,
                "inode_percent": inode_percent,
                "sustained_minutes": sustained,
                "verified_backup_age_hours": backup_age,
                "certificate_days_remaining": certificate_days,
                "oldest_queue_age_minutes": queue_age,
                "queue_age_critical": queue_critical,
                "unexpected_paid_resources": unexpected_paid,
            }
        },
        policy,
    )


def _cpu_percent() -> float:
    first = _cpu_counters(Path("/proc/stat").read_text(encoding="utf-8"))
    time.sleep(1)
    second = _cpu_counters(Path("/proc/stat").read_text(encoding="utf-8"))
    idle = second[0] - first[0]
    total = second[1] - first[1]
    if total <= 0:
        raise ValueError("Unable to measure CPU utilization")
    return round(100 * (1 - idle / total), 2)


def _cpu_counters(content: str) -> tuple[int, int]:
    line = next((line for line in content.splitlines() if line.startswith("cpu ")), "")
    values = [int(value) for value in line.split()[1:]]
    if len(values) < 5:
        raise ValueError("Malformed /proc/stat CPU counters")
    idle = values[3] + values[4]
    return idle, sum(values)


def _memory_percent() -> float:
    values = _memory_values(Path("/proc/meminfo").read_text(encoding="utf-8"))
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if not total or available is None:
        raise ValueError("Malformed /proc/meminfo")
    return round(100 * (total - available) / total, 2)


def _memory_values(content: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in content.splitlines():
        name, separator, remainder = line.partition(":")
        if separator:
            raw = remainder.strip().split()
            if raw and raw[0].isdigit():
                values[name] = int(raw[0])
    return values


def _filesystem_percent(path: Path) -> tuple[float, float]:
    stats = os.statvfs(path)
    disk_used = stats.f_blocks - stats.f_bavail
    inode_used = stats.f_files - stats.f_favail
    disk = 100 * disk_used / stats.f_blocks if stats.f_blocks else 0
    inodes = 100 * inode_used / stats.f_files if stats.f_files else 0
    return round(disk, 2), round(inodes, 2)


def _operations_report(compose_file: Path, environment_file: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(environment_file),
            "-f",
            str(compose_file),
            "exec",
            "-T",
            "api",
            "uv",
            "run",
            "--no-sync",
            "python",
            "-m",
            "backend.app.workers.operations",
            "status",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip().startswith("{")]
    if not lines:
        raise ValueError("Operations report did not return JSON")
    payload = json.loads(lines[-1])
    if not isinstance(payload, dict):
        raise ValueError("Operations report must be an object")
    return payload


def _backup_age_hours(directory: Path, now: datetime) -> float:
    bundles = [path for path in directory.glob("*.age") if path.is_file() and not path.is_symlink()]
    if not bundles:
        return 1_000_000.0
    newest = max(datetime.fromtimestamp(path.stat().st_mtime, tz=UTC) for path in bundles)
    return round(max(0.0, (now - newest).total_seconds() / 3600), 2)


def _certificate_days(host: str, now: datetime) -> float:
    if not host or "/" in host or ":" in host:
        raise ValueError("certificate_host must be a DNS hostname without scheme or port")
    context = ssl.create_default_context()
    with socket.create_connection((host, 443), timeout=10) as raw:
        with context.wrap_socket(raw, server_hostname=host) as secured:
            certificate = secured.getpeercert()
    if certificate is None:
        raise ValueError("TLS peer did not provide a certificate")
    expires = certificate.get("notAfter")
    if not isinstance(expires, str):
        raise ValueError("TLS certificate did not provide an expiry")
    expires_at = datetime.strptime(expires, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
    return round(max(0.0, (expires_at - now).total_seconds() / 86400), 2)


def _sustained_minutes(
    state_file: Path, now: datetime, above_review_threshold: bool
) -> float:
    state_file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if state_file.exists() and state_file.is_symlink():
        raise ValueError("Capacity state cannot be a symlink")
    started_at: datetime | None = None
    if state_file.is_file():
        previous = load_json(state_file).get("above_review_since")
        if isinstance(previous, str):
            started_at = datetime.fromisoformat(previous.replace("Z", "+00:00")).astimezone(UTC)
    if above_review_threshold:
        started_at = started_at or now
        minutes = max(0.0, (now - started_at).total_seconds() / 60)
        state: dict[str, str | None] = {"above_review_since": started_at.isoformat()}
    else:
        minutes = 0.0
        state = {"above_review_since": None}
    state_file.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(state_file, 0o600)
    return round(minutes, 2)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect Phase 10 OCI capacity evidence")
    parser.add_argument("--compose-file", type=Path, default=Path("deploy/oci/compose.yaml"))
    parser.add_argument("--environment-file", type=Path, default=Path("deploy/oci/runtime.env"))
    parser.add_argument("--backup-directory", type=Path, required=True)
    parser.add_argument("--inventory-status-file", type=Path, required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--certificate-host", required=True)
    parser.add_argument("--policy", type=Path, default=Path("operations/phase10-policy.json"))
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    result = collect_snapshot(
        compose_file=args.compose_file,
        environment_file=args.environment_file,
        backup_directory=args.backup_directory,
        inventory_status_file=args.inventory_status_file,
        state_file=args.state_file,
        certificate_host=args.certificate_host,
        policy=load_json(args.policy),
    )
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")
    os.chmod(args.output, 0o600)
    print(json.dumps({"scenario": result["scenario"], "status": result["status"]}))
    if result["status"] == "critical":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
