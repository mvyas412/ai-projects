from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.phase11_pilot import (
    canary_readiness,
    evidence_gate,
    synthetic_rehearsal,
    validate_policy,
)

ROOT = Path(__file__).parents[1]
POLICY_PATH = ROOT / "operations" / "phase11-pilot-policy.json"


@pytest.fixture
def policy() -> dict[str, object]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def test_accepted_policy_preserves_bounded_live_boundary(policy: dict[str, object]) -> None:
    assert validate_policy(policy)["status"] == "valid"
    changed = json.loads(json.dumps(policy))
    changed["rollout"]["participant_identities_tracked"] = True
    with pytest.raises(ValueError, match="participant_identities_tracked"):
        validate_policy(changed)


def test_approved_live_defaults_are_frozen(policy: dict[str, object]) -> None:
    assert policy["operations"]["access_approver_role"] == "owner"
    assert policy["evidence"]["retention_days_after_closure"] == 30
    assert policy["rollout"]["stages"][1:] == [
        {"name": "canary-2", "maximum_users": 2, "minimum_active_users": 2, "minimum_days": 3},
        {"name": "cohort-5", "maximum_users": 5, "minimum_active_users": 3, "minimum_days": 7},
        {"name": "cohort-10", "maximum_users": 10, "minimum_active_users": 5, "minimum_days": 14},
    ]
    assert policy["acceptance"] == {
        "minimum_core_journey_completion_percent": 90,
        "required_safeguard_pass_percent": 100,
    }


def test_canary_readiness_waits_only_for_participant_activation_and_consent(
    policy: dict[str, object],
) -> None:
    result = canary_readiness(policy)
    assert result["status"] == "blocked"
    assert result["approved_defaults_complete"] is True
    assert result["consent_accepted"] is True
    assert result["live_execution_authorized"] is True
    assert result["approved_participant_count"] == 2
    assert result["blockers"] == ["participant-activation-and-consent"]


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
