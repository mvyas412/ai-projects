from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.phase11_pilot import evidence_gate, synthetic_rehearsal, validate_policy

ROOT = Path(__file__).parents[1]
POLICY_PATH = ROOT / "operations" / "phase11-pilot-policy.json"


@pytest.fixture
def policy() -> dict[str, object]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def test_accepted_policy_preserves_synthetic_only_boundary(policy: dict[str, object]) -> None:
    assert validate_policy(policy)["status"] == "valid"
    changed = json.loads(json.dumps(policy))
    changed["rollout"]["live_stages_enabled"] = True
    with pytest.raises(ValueError, match="live_stages_enabled"):
        validate_policy(changed)


def test_synthetic_rehearsal_passes_complete_gate(policy: dict[str, object]) -> None:
    evidence = synthetic_rehearsal(policy)
    result = evidence_gate(evidence, policy)
    assert result == {
        "schema": "mm-rag-phase11-pilot-evidence-v1",
        "status": "pass",
        "scenario_count": 9,
        "missing": [],
        "unexpected": [],
    }


def test_live_or_paid_evidence_is_rejected(policy: dict[str, object]) -> None:
    evidence = synthetic_rehearsal(policy)
    evidence["synthetic"] = False
    evidence["registered_user_count"] = 2
    with pytest.raises(ValueError, match="synthetic"):
        evidence_gate(evidence, policy)


def test_sensitive_evidence_is_rejected(policy: dict[str, object]) -> None:
    evidence = synthetic_rehearsal(policy)
    evidence["email"] = "not-allowed@example.invalid"
    with pytest.raises(ValueError, match="forbidden fields"):
        evidence_gate(evidence, policy)


def test_missing_scenario_is_incomplete(policy: dict[str, object]) -> None:
    evidence = synthetic_rehearsal(policy)
    evidence["scenarios"].pop()
    result = evidence_gate(evidence, policy)
    assert result["status"] == "incomplete"
    assert len(result["missing"]) == 1
