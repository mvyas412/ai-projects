from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from scripts import phase8_evidence
from scripts.phase8_evidence import (
    PROGRESSIVE_USER_STAGES,
    REQUIRED_SCENARIOS,
    SCHEMA,
    validate_release_evidence,
)


def _write_evidence(root: Path) -> None:
    for scenario in REQUIRED_SCENARIOS:
        payload: dict[str, object] = {
            "schema": SCHEMA,
            "scenario": scenario,
            "outcome": "pass",
        }
        if scenario == "bounded-load":
            payload["stages"] = [
                {
                    "users": users,
                    "requests": 30,
                    "error_count": 0,
                    "p50_ms": 21.0,
                    "p95_ms": 42.0,
                }
                for users in PROGRESSIVE_USER_STAGES
            ]
        elif scenario == "backup-restore":
            payload.update(rpo_hours=1.0, rto_hours=0.5)
        elif scenario == "rollback":
            payload["data_integrity_verified"] = True
        (root / f"{scenario}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_release_evidence_gate_accepts_complete_evidence(tmp_path: Path) -> None:
    _write_evidence(tmp_path)

    assert validate_release_evidence(tmp_path) == {
        "schema": SCHEMA,
        "scenarios": 10,
        "status": "pass",
    }


def test_release_evidence_gate_rejects_missing_scenario(tmp_path: Path) -> None:
    _write_evidence(tmp_path)
    (tmp_path / "disk-pressure.json").unlink()

    with pytest.raises(ValueError, match="disk-pressure"):
        validate_release_evidence(tmp_path)


def test_release_evidence_gate_enforces_recovery_objectives(tmp_path: Path) -> None:
    _write_evidence(tmp_path)
    path = tmp_path / "backup-restore.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["rto_hours"] = 9
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="RPO/RTO"):
        validate_release_evidence(tmp_path)


def test_release_evidence_gate_rejects_duplicate_scenarios(tmp_path: Path) -> None:
    _write_evidence(tmp_path)
    duplicate = json.loads((tmp_path / "worker-restart.json").read_text(encoding="utf-8"))
    (tmp_path / "duplicate.json").write_text(json.dumps(duplicate), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate"):
        validate_release_evidence(tmp_path)


def test_release_evidence_gate_requires_zero_load_errors(tmp_path: Path) -> None:
    _write_evidence(tmp_path)
    path = tmp_path / "bounded-load.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["stages"][-1]["error_count"] = 1
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="zero-error"):
        validate_release_evidence(tmp_path)


def test_release_evidence_gate_requires_every_progressive_stage(tmp_path: Path) -> None:
    _write_evidence(tmp_path)
    path = tmp_path / "bounded-load.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["stages"].pop()
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="1/3/5/10-user"):
        validate_release_evidence(tmp_path)


def test_progressive_probe_runs_each_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    observed_users: list[int] = []

    async def fake_probe(**kwargs: object) -> dict[str, object]:
        users_value = kwargs["users"]
        assert isinstance(users_value, int)
        users = users_value
        observed_users.append(users)
        return {
            "users": users,
            "requests": kwargs["requests"],
            "error_count": 0,
            "p50_ms": 1.0,
            "p95_ms": 2.0,
            "status": "observed",
        }

    monkeypatch.setattr(phase8_evidence, "run_bounded_probe", fake_probe)
    result = asyncio.run(
        phase8_evidence.run_progressive_probe(
            base_url="https://rag.example",
            token="",
            paths=["/api/v1/health/ready"],
            requests_per_stage=30,
        )
    )

    assert observed_users == [1, 3, 5, 10]
    assert [stage["users"] for stage in result["stages"]] == observed_users


def test_release_evidence_gate_requires_rollback_integrity(tmp_path: Path) -> None:
    _write_evidence(tmp_path)
    path = tmp_path / "rollback.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["data_integrity_verified"] = False
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="data integrity"):
        validate_release_evidence(tmp_path)
