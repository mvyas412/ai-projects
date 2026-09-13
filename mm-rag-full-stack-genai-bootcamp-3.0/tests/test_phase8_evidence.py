from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.phase8_evidence import REQUIRED_SCENARIOS, SCHEMA, validate_release_evidence


def _write_evidence(root: Path) -> None:
    for scenario in REQUIRED_SCENARIOS:
        payload: dict[str, object] = {
            "schema": SCHEMA,
            "scenario": scenario,
            "outcome": "pass",
        }
        if scenario == "bounded-load":
            payload.update(users=3, error_count=0, p95_ms=42.0)
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
