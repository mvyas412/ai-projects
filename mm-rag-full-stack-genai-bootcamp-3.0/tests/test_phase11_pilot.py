from __future__ import annotations

import json
from pathlib import Path

import pytest

from frontend.pilot import PILOT_LABEL, PILOT_NOTICE, PILOT_SUPPORT
from scripts.phase11_pilot import (
    canary_readiness,
    evidence_gate,
    synthetic_rehearsal,
    technical_evidence_gate,
    technical_rehearsal_template,
    validate_policy,
)

ROOT = Path(__file__).parents[1]
POLICY_PATH = ROOT / "operations" / "phase11-pilot-policy.json"
CLOSURE_SCOPE_PATH = ROOT / "operations" / "phase11-closure-scope-v1.json"
ACCEPTANCE_PATH = ROOT / "operations" / "phase11-acceptance-v1.json"


@pytest.fixture
def policy() -> dict[str, object]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def test_accepted_policy_preserves_bounded_live_boundary(policy: dict[str, object]) -> None:
    assert validate_policy(policy)["status"] == "valid"
    changed = json.loads(json.dumps(policy))
    changed["rollout"]["participant_identities_tracked"] = True
    with pytest.raises(ValueError, match="participant_identities_tracked"):
        validate_policy(changed)


def test_pilot_ui_copy_preserves_learning_and_support_boundaries() -> None:
    assert "Phase 11" in PILOT_LABEL
    assert "invitation-only learning pilot" in PILOT_NOTICE
    assert "not a production service" in PILOT_NOTICE
    assert "authorized, non-sensitive material" in PILOT_NOTICE
    assert "voluntary" in PILOT_NOTICE
    assert "workspace Owner" in PILOT_SUPPORT
    assert "one business day" in PILOT_SUPPORT
    assert "no emergency" in PILOT_SUPPORT


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


def test_canary_readiness_separates_account_rehearsal_from_user_validation(
    policy: dict[str, object],
) -> None:
    result = canary_readiness(policy)
    assert result["status"] == "ready"
    assert result["target_stage"] == "technical-rehearsal-2-accounts"
    assert result["approved_defaults_complete"] is True
    assert result["consent_accepted"] is True
    assert result["live_execution_authorized"] is True
    assert result["approved_account_count"] == 2
    assert result["formal_canary_status"] == "blocked"
    assert result["formal_canary_blockers"] == ["second-independent-human-participant"]


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


def test_technical_template_is_incomplete_and_non_validating(
    policy: dict[str, object],
) -> None:
    evidence = technical_rehearsal_template(policy)
    result = technical_evidence_gate(evidence, policy)
    assert result["status"] == "incomplete"
    assert result["formal_product_validation"] is False
    assert result["scenario_count"] == 10
    assert len(result["incomplete"]) == 10


def test_completed_technical_rehearsal_passes_without_product_validation(
    policy: dict[str, object],
) -> None:
    evidence = technical_rehearsal_template(policy)
    evidence["status"] = "pass"
    for scenario in evidence["scenarios"]:
        scenario["status"] = "pass"
    result = technical_evidence_gate(evidence, policy)
    assert result == {
        "schema": "mm-rag-phase11-technical-rehearsal-evidence-v1",
        "status": "pass",
        "formal_product_validation": False,
        "scenario_count": 10,
        "missing": [],
        "unexpected": [],
        "incomplete": [],
    }


def test_technical_evidence_rejects_identity_fields(policy: dict[str, object]) -> None:
    evidence = technical_rehearsal_template(policy)
    evidence["email"] = "not-allowed@example.invalid"
    with pytest.raises(ValueError, match="forbidden fields"):
        technical_evidence_gate(evidence, policy)


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


@pytest.fixture
def closure_scope() -> dict[str, object]:
    return json.loads(CLOSURE_SCOPE_PATH.read_text(encoding="utf-8"))


def test_approved_closure_scope_defers_larger_cohorts(
    closure_scope: dict[str, object],
) -> None:
    assert closure_scope["schema"] == "mm-rag-phase11-closure-scope-v1"
    assert closure_scope["decision"] == "ADR-0064"
    assert closure_scope["scope_approved_on"] == "2026-10-11"
    assert closure_scope["scope"] == {
        "objective": "two-person-learning-pilot",
        "invitation_only": True,
        "maximum_participants": 2,
        "minimum_independent_human_participants": 2,
        "required_stage": "canary-2",
        "deferred_unvalidated_stages": ["cohort-5", "cohort-10"],
        "production_readiness_claim": False,
        "larger_cohort_validation_claim": False,
    }


def test_scope_approval_preserves_all_closure_gates(
    closure_scope: dict[str, object],
) -> None:
    assert closure_scope["retained_gates"] == {
        "minimum_eligible_elapsed_hours": 72,
        "exclude_recovery_and_unverified_time": True,
        "minimum_core_journey_completion_percent": 90,
        "required_safeguard_pass_percent": 100,
        "personal_consent_required": True,
        "human_journey_ledger_required": True,
        "accessibility_and_scope_clarity_required": True,
        "actual_aggregate_usage_and_cost_required": True,
        "safeguard_evidence_and_freshness_required": True,
        "fresh_read_only_operational_checkpoint_required": True,
        "structured_feedback_required": False,
        "explicit_final_decision_required": True,
    }


def test_scope_approval_does_not_accept_phase_or_enable_execution(
    closure_scope: dict[str, object],
) -> None:
    assert closure_scope["authority"] == {
        "scope_approved": True,
        "phase11_accepted": False,
        "final_acceptance_authorized": False,
        "paid_execution_authorized": False,
        "worker_start_authorized": False,
        "additional_enrollment_authorized": False,
        "operational_mutation_authorized": False,
        "git_publication_authorized": False,
    }


def test_closure_scope_keeps_historical_evidence_separate(
    closure_scope: dict[str, object],
    policy: dict[str, object],
) -> None:
    assert closure_scope["evidence_governance"] == {
        "aggregate_only": True,
        "raw_content_allowed": False,
        "identities_allowed": False,
        "historical_rehearsal_policy": "operations/phase11-pilot-policy.json",
        "historical_evidence_rewrite_allowed": False,
        "technical_rehearsal_is_human_product_validation": False,
        "retention_days_after_actual_closure": 30,
        "automatic_deletion": False,
    }
    assert validate_policy(policy)["policy_sha256"] == (
        "33bb1ad99b2b931ac6ee469cfc2893057737d6c498e7fa138400876184c35815"
    )


def test_explicit_acceptance_is_limited_and_preserves_historical_scope(
    closure_scope: dict[str, object],
) -> None:
    acceptance = json.loads(ACCEPTANCE_PATH.read_text(encoding="utf-8"))
    assert acceptance["schema"] == "mm-rag-phase11-acceptance-v1"
    assert acceptance["phase11_accepted"] is True
    assert acceptance["accepted_at"] == "2026-10-18T23:10:45Z"
    assert acceptance["scope"] == {
        "objective": "two-person-guided-learning-pilot",
        "independent_human_participants": 2,
        "deferred_unvalidated_stages": ["cohort-5", "cohort-10"],
        "production_readiness_claim": False,
        "unassisted_discovery_claim": False,
        "fresh_live_negative_tenant_audit_claim": False,
    }
    # Scope approval alone remains a non-executing historical decision.
    historical_authority = closure_scope["authority"]
    assert isinstance(historical_authority, dict)
    assert historical_authority["phase11_accepted"] is False
    assert acceptance["authority"] == {
        "acceptance_recording_authorized": True,
        "git_publication_authorized": False,
        "merge_or_release_tag_authorized": False,
        "operational_mutation_authorized": False,
        "paid_execution_authorized": False,
        "worker_start_authorized": False,
        "additional_enrollment_authorized": False,
        "automatic_deletion_authorized": False,
    }


def test_acceptance_preserves_cost_provenance_and_manual_retention() -> None:
    acceptance = json.loads(ACCEPTANCE_PATH.read_text(encoding="utf-8"))
    assert acceptance["cost"]["openai_exported_usd"] == "0.00151422"
    assert acceptance["cost"]["oci_reported_usd"] == "0"
    assert acceptance["cost"]["oci_source"] == "operator-report"
    assert acceptance["cost"]["oci_independent_billing_audit"] is False
    assert acceptance["operating_state"]["worker_remains_stopped"] is True
    assert acceptance["retention"] == {
        "applies_to": "aggregate-pilot-evidence",
        "days_after_closure": 30,
        "manual_review_due_at": "2026-11-17T23:10:45Z",
        "automatic_deletion": False,
        "automatic_retention_apply": False,
        "deletion_requires_reviewed_manual_operation": True,
    }
