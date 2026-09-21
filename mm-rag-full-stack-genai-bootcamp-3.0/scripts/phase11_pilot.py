from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "mm-rag-phase11-pilot-policy-v1"
EVIDENCE_SCHEMA = "mm-rag-phase11-pilot-evidence-v1"
REQUIRED_SCENARIOS = {
    "access-revocation",
    "backup-rollback",
    "grounded-chat-citations",
    "library-ready",
    "login-logout",
    "personal-workspace-default",
    "structured-feedback",
    "support-pause",
    "upload-progress-cancel-retry",
}
FORBIDDEN_KEYS = {
    "access_token",
    "answer",
    "authorization",
    "client_secret",
    "credential",
    "document_content",
    "email",
    "id_token",
    "password",
    "private_key",
    "prompt",
    "provider_id",
    "refresh_token",
    "secret",
    "token",
    "user_id",
}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON input must be an object")
    return payload


def validate_policy(payload: dict[str, Any]) -> dict[str, Any]:
    """Fail closed when the approved bounded-pilot boundary drifts."""
    _reject_sensitive_fields(payload)
    if payload.get("schema") != POLICY_SCHEMA:
        raise ValueError("Unsupported Phase 11 policy schema")
    _require_values(
        _mapping(payload, "scope"),
        invitation_only=True,
        maximum_registered_users=10,
        public_signup=False,
        production_sla=False,
    )
    _require_values(
        _mapping(payload, "product"),
        authoritative_frontend="streamlit",
        nextjs_promoted=False,
        personal_workspace_first=True,
    )
    evidence = _mapping(payload, "evidence")
    _require_values(
        evidence,
        aggregate_only=True,
        raw_content_allowed=False,
        identities_allowed=False,
        retention_days_after_closure=30,
        automatic_deletion=False,
    )
    categories = evidence.get("voluntary_feedback_categories")
    if not isinstance(categories, list) or not categories or not all(
        isinstance(item, str) and item for item in categories
    ):
        raise ValueError("voluntary feedback categories must be non-empty strings")
    _require_values(
        _mapping(payload, "consent"),
        participant_notice="docs/PHASE11_PILOT_CONSENT.md",
        status="accepted",
        accepted_on="2026-09-20",
    )
    _require_values(
        _mapping(payload, "operations"),
        infrastructure_budget_usd=0,
        external_notifications=False,
        automatic_retention_apply=False,
        paid_acceptance=False,
        access_approver_role="owner",
        support_response_target_business_days=1,
    )
    stages = [
        {"name": "internal-rehearsal", "maximum_users": 0, "minimum_active_users": 0, "minimum_days": 0},
        {"name": "canary-2", "maximum_users": 2, "minimum_active_users": 2, "minimum_days": 3},
        {"name": "cohort-5", "maximum_users": 5, "minimum_active_users": 3, "minimum_days": 7},
        {"name": "cohort-10", "maximum_users": 10, "minimum_active_users": 5, "minimum_days": 14},
    ]
    _require_values(
        _mapping(payload, "rollout"),
        stages=stages,
        live_stages_enabled=True,
        separate_live_authorization_required=True,
        live_execution_authorized=True,
        approved_participant_count=2,
        participant_identities_tracked=False,
    )
    _require_values(
        _mapping(payload, "acceptance"),
        minimum_core_journey_completion_percent=90,
        required_safeguard_pass_percent=100,
    )
    return {
        "schema": POLICY_SCHEMA,
        "status": "valid",
        "policy_sha256": _payload_hash(payload),
    }


def synthetic_rehearsal(policy: dict[str, Any]) -> dict[str, Any]:
    validation = validate_policy(policy)
    scenarios = [
        {"name": name, "status": "pass"}
        for name in sorted(REQUIRED_SCENARIOS)
    ]
    return {
        "schema": EVIDENCE_SCHEMA,
        "recorded_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "stage": "internal-rehearsal",
        "synthetic": True,
        "status": "pass",
        "registered_user_count": 0,
        "provider_calls": 0,
        "paid_cost_usd": 0,
        "policy_sha256": validation["policy_sha256"],
        "scenarios": scenarios,
    }


def evidence_gate(payload: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    validation = validate_policy(policy)
    _reject_sensitive_fields(payload)
    if payload.get("schema") != EVIDENCE_SCHEMA:
        raise ValueError("Unsupported Phase 11 evidence schema")
    _require_values(
        payload,
        stage="internal-rehearsal",
        synthetic=True,
        registered_user_count=0,
        provider_calls=0,
        paid_cost_usd=0,
        policy_sha256=validation["policy_sha256"],
    )
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("scenarios must be a list")
    names: set[str] = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise ValueError("scenario entries must be objects")
        if scenario.get("status") != "pass" or not isinstance(scenario.get("name"), str):
            raise ValueError("every synthetic scenario must pass")
        name = scenario["name"]
        if name in names:
            raise ValueError(f"duplicate scenario: {name}")
        names.add(name)
    missing = sorted(REQUIRED_SCENARIOS - names)
    unexpected = sorted(names - REQUIRED_SCENARIOS)
    status = "pass" if not missing and not unexpected and payload.get("status") == "pass" else "incomplete"
    return {
        "schema": EVIDENCE_SCHEMA,
        "status": status,
        "scenario_count": len(names),
        "missing": missing,
        "unexpected": unexpected,
    }


def canary_readiness(policy: dict[str, Any]) -> dict[str, Any]:
    """Report readiness without persisting participant identities."""
    validate_policy(policy)
    return {
        "schema": EVIDENCE_SCHEMA,
        "status": "blocked",
        "target_stage": "canary-2",
        "approved_defaults_complete": True,
        "consent_accepted": True,
        "live_execution_authorized": True,
        "approved_participant_count": 2,
        "blockers": ["participant-activation-and-consent"],
    }


def _mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _require_values(payload: dict[str, Any], **expected: Any) -> None:
    for key, value in expected.items():
        if key not in payload or payload[key] != value:
            raise ValueError(f"{key} must remain {value!r}")


def _reject_sensitive_fields(payload: object) -> None:
    exposed = sorted(FORBIDDEN_KEYS & _all_keys(payload))
    if exposed:
        raise ValueError(f"payload contains forbidden fields: {', '.join(exposed)}")


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = {str(key).lower() for key in value}
        for nested in value.values():
            keys.update(_all_keys(nested))
        return keys
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


def _payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Phase 11 pilot contracts")
    parser.add_argument("command", choices=("policy", "rehearse", "gate", "canary-readiness"))
    parser.add_argument("input", nargs="?", type=Path)
    parser.add_argument("--policy", type=Path, default=Path("operations/phase11-pilot-policy.json"))
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    policy = load_json(args.policy)
    if args.command == "policy":
        result = validate_policy(policy)
    elif args.command == "rehearse":
        result = synthetic_rehearsal(policy)
    elif args.command == "canary-readiness":
        result = canary_readiness(policy)
    else:
        if args.input is None:
            raise SystemExit("gate requires an evidence JSON path")
        result = evidence_gate(load_json(args.input), policy)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
