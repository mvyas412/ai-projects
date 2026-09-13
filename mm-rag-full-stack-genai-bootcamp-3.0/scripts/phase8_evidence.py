from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx

SCHEMA = "mm-rag-phase8-evidence-v1"
REQUIRED_SCENARIOS = {
    "bounded-load",
    "worker-restart",
    "broker-unavailable",
    "postgres-unavailable",
    "qdrant-unavailable",
    "object-storage-unavailable",
    "telemetry-unavailable",
    "disk-pressure",
    "backup-restore",
    "rollback",
}


async def run_bounded_probe(
    *, base_url: str, token: str, paths: Sequence[str], users: int, requests: int
) -> dict[str, Any]:
    if users < 1 or users > 3:
        raise ValueError("users must be between 1 and 3")
    if requests < 1 or requests > 300:
        raise ValueError("requests must be between 1 and 300")
    if not paths or any(not path.startswith("/api/v1/") for path in paths):
        raise ValueError("Every probe path must be an /api/v1/ path")

    queue: asyncio.Queue[tuple[int, str]] = asyncio.Queue()
    for index in range(requests):
        queue.put_nowait((index, paths[index % len(paths)]))
    observations: list[tuple[float, int]] = []
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=30.0) as client:
        async def probe() -> None:
            while not queue.empty():
                _, path = await queue.get()
                started = time.perf_counter()
                try:
                    response = await client.get(path)
                    status = response.status_code
                except httpx.HTTPError:
                    status = 0
                latency_ms = round((time.perf_counter() - started) * 1000, 3)
                observations.append((latency_ms, status))
                queue.task_done()

        await asyncio.gather(*(probe() for _ in range(users)))

    latencies = sorted(latency for latency, _ in observations)
    errors = sum(1 for _, status in observations if not 200 <= status < 400)
    return {
        "schema": SCHEMA,
        "scenario": "bounded-load",
        "users": users,
        "requests": len(observations),
        "error_count": errors,
        "p50_ms": _percentile(latencies, 0.50),
        "p95_ms": _percentile(latencies, 0.95),
        "status": "observed",
    }


def validate_release_evidence(directory: Path) -> dict[str, Any]:
    scenarios: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema") != SCHEMA:
            raise ValueError(f"Unsupported evidence schema in {path.name}")
        scenario = payload.get("scenario")
        if not isinstance(scenario, str) or scenario in scenarios:
            raise ValueError(f"Missing or duplicate scenario in {path.name}")
        scenarios[scenario] = payload

    missing = sorted(REQUIRED_SCENARIOS - scenarios.keys())
    if missing:
        raise ValueError(f"Missing Phase 8 evidence: {', '.join(missing)}")
    failed = sorted(
        name for name, payload in scenarios.items() if payload.get("outcome") != "pass"
    )
    if failed:
        raise ValueError(f"Phase 8 evidence has non-passing outcomes: {', '.join(failed)}")

    load = scenarios["bounded-load"]
    if int(load.get("users", 0)) not in range(1, 4) or int(load.get("error_count", -1)) != 0:
        raise ValueError("Bounded-load evidence violates the 1–3 user or zero-error contract")
    restore = scenarios["backup-restore"]
    if float(restore.get("rpo_hours", math.inf)) > 24 or float(
        restore.get("rto_hours", math.inf)
    ) > 8:
        raise ValueError("Restore evidence exceeds the accepted RPO/RTO")
    if not scenarios["rollback"].get("data_integrity_verified"):
        raise ValueError("Rollback evidence must verify tenant-data integrity")

    return {"schema": SCHEMA, "scenarios": len(scenarios), "status": "pass"}


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    index = max(0, math.ceil(len(values) * percentile) - 1)
    return round(values[index], 3)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect or validate bounded Phase 8 evidence")
    subparsers = parser.add_subparsers(dest="command", required=True)
    probe = subparsers.add_parser("probe", help="run a read-only HTTP capacity probe")
    probe.add_argument("--base-url", required=True)
    probe.add_argument("--path", action="append", required=True)
    probe.add_argument("--users", type=int, default=3)
    probe.add_argument("--requests", type=int, default=30)
    probe.add_argument("--token-env", default="MM_RAG_ACCESS_TOKEN")
    gate = subparsers.add_parser("gate", help="validate a completed evidence directory")
    gate.add_argument("directory", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "probe":
        payload = asyncio.run(
            run_bounded_probe(
                base_url=args.base_url,
                token=os.environ.get(args.token_env, ""),
                paths=args.path,
                users=args.users,
                requests=args.requests,
            )
        )
    else:
        payload = validate_release_evidence(args.directory)
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
