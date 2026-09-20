from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "mm-rag-phase10-policy-v1"
EVIDENCE_SCHEMA = "mm-rag-phase10-evidence-v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_KEYS = {
    "access_key",
    "authorization",
    "client_secret",
    "credential",
    "id_token",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "token",
}
REQUIRED_GATE_SCENARIOS = {
    "backup-verification",
    "isolated-restore",
    "retention-preview",
    "maintenance-gate",
    "capacity-guardrails",
    "upgrade-preflight",
    "rollback-drill",
    "clean-host-recovery",
}
ACCEPTED_GATE_STATUSES = {
    "backup-verification": {"pass"},
    "isolated-restore": {"pass"},
    "retention-preview": {"pass"},
    "maintenance-gate": {"pass"},
    "capacity-guardrails": {"pass"},
    "upgrade-preflight": {"ready"},
    "rollback-drill": {"ready", "pass"},
    "clean-host-recovery": {"pass"},
}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON input must be an object")
    return payload


def validate_policy(payload: dict[str, Any]) -> dict[str, Any]:
    """Enforce the approved free-first Phase 10 operating boundaries."""
    _reject_secrets(payload)
    if payload.get("schema") != POLICY_SCHEMA:
        raise ValueError("Unsupported Phase 10 policy schema")
    if payload.get("infrastructure_budget_usd") != 0:
        raise ValueError("Phase 10 infrastructure budget must remain USD 0")

    backup = _mapping(payload, "backup")
    _require_values(
        backup,
        daily_keep=7,
        monthly_keep=2,
        minimum_known_good=2,
        maximum_verified_age_hours=48,
        restore_drill_interval_days=31,
        destination="existing-private-oci-bucket",
    )
    retention = _mapping(payload, "retention")
    _require_values(
        retention,
        mode="preview-only",
        interval_days=31,
        automatic_apply=False,
        notification="application-admin-view",
        retention_days=None,
        recovery_days=None,
    )
    maintenance = _mapping(payload, "maintenance")
    _require_values(
        maintenance,
        interval_days=31,
        automatic_merge=False,
        paid_acceptance=False,
        runtime_database_image_changes_require_rollback_proof=True,
    )
    capacity = _mapping(payload, "capacity")
    _require_values(
        capacity,
        learning_users=10,
        review_percent=80,
        review_duration_minutes=15,
        critical_percent=90,
        queue_age_critical_minutes=None,
        certificate_critical_days=None,
    )
    release = _mapping(payload, "release")
    _require_values(
        release,
        plan_first=True,
        operator_authorization_required=True,
        temporary_cloud_resources_require_separate_approval=True,
    )
    return {
        "schema": POLICY_SCHEMA,
        "status": "valid",
        "policy_sha256": _payload_hash(payload),
    }


def backup_retention_plan(payload: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    """Return a non-destructive backup-retention plan; this function never deletes."""
    validate_policy(policy)
    records = payload.get("backups")
    if not isinstance(records, list) or not records:
        raise ValueError("backups must be a non-empty list")
    parsed: list[tuple[datetime, str, bool, str]] = []
    seen_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("backup entries must be objects")
        backup_id = _nonempty(record, "backup_id")
        if backup_id in seen_ids:
            raise ValueError("backup_id values must be unique")
        seen_ids.add(backup_id)
        created = _timestamp(record.get("created_at"))
        verified = record.get("verified")
        cadence = record.get("cadence")
        if not isinstance(verified, bool) or cadence not in {"daily", "monthly"}:
            raise ValueError("backup entries require verified and daily/monthly cadence")
        parsed.append((created, backup_id, verified, cadence))

    verified = sorted((item for item in parsed if item[2]), reverse=True)
    protected = {item[1] for item in verified[: policy["backup"]["minimum_known_good"]]}
    for cadence, keep in (
        ("daily", policy["backup"]["daily_keep"]),
        ("monthly", policy["backup"]["monthly_keep"]),
    ):
        protected.update(item[1] for item in verified if item[3] == cadence)
        cadence_ids = [item[1] for item in verified if item[3] == cadence]
        protected.difference_update(cadence_ids[keep:])
        protected.update(cadence_ids[:keep])
    protected.update(item[1] for item in verified[:2])
    candidates = sorted(item[1] for item in parsed if item[1] not in protected)
    return {
        "schema": EVIDENCE_SCHEMA,
        "scenario": "backup-retention-plan",
        "status": "preview-only",
        "apply_enabled": False,
        "backup_count": len(parsed),
        "protected_count": len(parsed) - len(candidates),
        "candidate_count": len(candidates),
        "candidate_ids": candidates,
        "plan_sha256": _payload_hash({"candidates": candidates}),
    }


def backup_verification_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_secrets(payload)
    required = ("manifest_sha256", "encrypted_bundle_sha256", "file_count", "total_bytes")
    for field in required[:2]:
        if not SHA256.fullmatch(str(payload.get(field, ""))):
            raise ValueError(f"{field} must be a SHA-256 digest")
    file_count = _nonnegative_int(payload, "file_count")
    total_bytes = _nonnegative_int(payload, "total_bytes")
    return evidence(
        "backup-verification",
        "pass",
        manifest_sha256=payload["manifest_sha256"],
        encrypted_bundle_sha256=payload["encrypted_bundle_sha256"],
        file_count=file_count,
        total_bytes=total_bytes,
    )


def isolated_restore_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_secrets(payload)
    checks = _boolean_checks(payload, "checks")
    required = {"postgres", "qdrant", "objects", "active_data_plane_untouched"}
    if set(checks) != required or not all(checks.values()):
        raise ValueError("isolated restore requires all aggregate checks to pass")
    return evidence("isolated-restore", "pass", checks=checks)


def retention_preview_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    """Create safe monthly evidence from the existing lifecycle preview response."""
    _reject_secrets(payload)
    if payload.get("automatic_apply") is not False or payload.get("mode") != "preview-only":
        raise ValueError("retention automation must remain preview-only")
    counts = payload.get("counts")
    if not isinstance(counts, dict) or not counts:
        raise ValueError("retention preview requires aggregate counts")
    safe_counts: dict[str, int] = {}
    for name, value in counts.items():
        if not isinstance(name, str) or not isinstance(value, int) or value < 0:
            raise ValueError("retention counts must be named non-negative integers")
        safe_counts[name] = value
    preview_token = _nonempty(payload, "preview_token")
    return evidence(
        "retention-preview",
        "pass",
        apply_enabled=False,
        counts=safe_counts,
        preview_sha256=hashlib.sha256(preview_token.encode()).hexdigest(),
        policy_revision=_nonempty(payload, "policy_revision"),
    )


def maintenance_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_secrets(payload)
    if payload.get("automatic_merge") is not False or payload.get("paid_acceptance") is not False:
        raise ValueError("maintenance automation cannot merge or run paid acceptance")
    ecosystems = payload.get("ecosystems")
    if not isinstance(ecosystems, list) or not ecosystems or not all(
        isinstance(item, str) and item for item in ecosystems
    ):
        raise ValueError("maintenance evidence requires grouped ecosystems")
    for name in ("source_revision", "candidate_revision"):
        if not GIT_SHA.fullmatch(str(payload.get(name, ""))):
            raise ValueError(f"{name} must be a full Git SHA")
    lockfiles = payload.get("lockfile_sha256")
    if not isinstance(lockfiles, dict) or not lockfiles or not all(
        isinstance(name, str) and SHA256.fullmatch(str(digest))
        for name, digest in lockfiles.items()
    ):
        raise ValueError("lockfile_sha256 must contain named SHA-256 digests")
    checks = _boolean_checks(payload, "checks")
    required = {"lockfiles", "tests", "vulnerability_scan", "sbom", "provenance", "arm64"}
    if not required.issubset(checks) or not all(checks[name] for name in required):
        raise ValueError("maintenance gate checks are incomplete")
    runtime_change = payload.get("runtime_database_or_image_change")
    if not isinstance(runtime_change, bool):
        raise ValueError("runtime_database_or_image_change must be boolean")
    if runtime_change and checks.get("rollback_proof") is not True:
        raise ValueError("runtime, database, and image changes require rollback proof")
    urgent = bool(
        payload.get("known_exploited") is True
        or payload.get("public_exploit_on_exposed_component") is True
        or (
            payload.get("severity") == "critical"
            and payload.get("exploitable_on_exposed_component") is True
        )
    )
    return evidence(
        "maintenance-gate",
        "pass",
        ecosystems=sorted(set(ecosystems)),
        source_revision=payload["source_revision"],
        candidate_revision=payload["candidate_revision"],
        lockfile_sha256=lockfiles,
        checks=checks,
        classification="urgent" if urgent else "monthly",
    )


def capacity_evidence(payload: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    validate_policy(policy)
    _reject_secrets(payload)
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("capacity input requires metrics")
    percentages = ("cpu_percent", "memory_percent", "disk_percent", "inode_percent")
    values: dict[str, float] = {}
    for name in percentages:
        value = metrics.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 100:
            raise ValueError(f"{name} must be between 0 and 100")
        values[name] = float(value)
    sustained = _nonnegative_number(metrics, "sustained_minutes")
    backup_age = _nonnegative_number(metrics, "verified_backup_age_hours")
    cert_days = _nonnegative_number(metrics, "certificate_days_remaining")
    queue_age = _nonnegative_number(metrics, "oldest_queue_age_minutes")
    queue_age_critical = metrics.get("queue_age_critical")
    if not isinstance(queue_age_critical, bool):
        raise ValueError("queue_age_critical must be boolean")
    unexpected_paid = metrics.get("unexpected_paid_resources")
    if not isinstance(unexpected_paid, bool):
        raise ValueError("unexpected_paid_resources must be boolean")

    capacity = policy["capacity"]
    state = "healthy"
    reasons: list[str] = []
    if max(values.values()) >= capacity["critical_percent"]:
        state = "critical"
        reasons.append("resource-critical")
    elif (
        max(values.values()) >= capacity["review_percent"]
        and sustained >= capacity["review_duration_minutes"]
    ):
        state = "review"
        reasons.append("sustained-resource-review")
    if backup_age > policy["backup"]["maximum_verified_age_hours"]:
        state = "critical"
        reasons.append("verified-backup-overdue")
    queue_limit = capacity["queue_age_critical_minutes"]
    certificate_limit = capacity["certificate_critical_days"]
    unresolved: list[str] = []
    if queue_limit is None:
        unresolved.append("queue-age-critical-minutes")
    elif queue_age >= queue_limit:
        state = "critical"
        reasons.append("queue-age")
    if queue_age_critical:
        state = "critical"
        reasons.append("queue-age-runtime-alert")
    if certificate_limit is None:
        unresolved.append("certificate-critical-days")
    elif cert_days <= certificate_limit:
        state = "critical"
        reasons.append("certificate-expiry")
    if unexpected_paid:
        state = "critical"
        reasons.append("unexpected-paid-resource")
    return evidence(
        "capacity-guardrails",
        "pass" if state == "healthy" else state,
        state=state,
        reasons=sorted(reasons),
        unresolved_thresholds=unresolved,
        metrics={**values, "sustained_minutes": sustained, "verified_backup_age_hours": backup_age,
                 "certificate_days_remaining": cert_days, "oldest_queue_age_minutes": queue_age,
                 "queue_age_critical": queue_age_critical,
                 "unexpected_paid_resources": unexpected_paid},
    )


def release_preflight_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_secrets(payload)
    action = payload.get("action")
    if action not in {"upgrade", "rollback", "restore"}:
        raise ValueError("release action must be upgrade, rollback, or restore")
    for name in ("current_revision", "target_revision"):
        if not GIT_SHA.fullmatch(str(payload.get(name, ""))):
            raise ValueError(f"{name} must be a full Git SHA")
    checks = _boolean_checks(payload, "checks")
    required = {
        "digest_pinned",
        "backup_fresh",
        "migration_compatible",
        "disk_headroom",
        "jobs_quiesced",
        "health_ready",
        "rollback_or_restore_available",
    }
    missing = sorted(required - checks.keys())
    if missing:
        raise ValueError(f"release preflight checks are missing: {', '.join(missing)}")
    passed = all(checks[name] for name in required)
    if payload.get("operator_authorized") is not False:
        raise ValueError("generated preflight evidence must await operator authorization")
    return evidence(
        "upgrade-preflight" if action == "upgrade" else f"{action}-drill",
        "ready" if passed else "blocked",
        action=action,
        current_revision=payload["current_revision"],
        target_revision=payload["target_revision"],
        checks=checks,
        operator_authorized=False,
    )


def clean_host_recovery_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_secrets(payload)
    if payload.get("temporary_resources_approved") is not True:
        raise ValueError("clean-host recovery requires separate temporary-resource approval")
    if payload.get("zero_cost_plan_verified") is not True:
        raise ValueError("clean-host recovery requires a verified zero-cost plan")
    checks = _boolean_checks(payload, "checks")
    required = {
        "reviewed_iac",
        "secrets_runtime_only",
        "encrypted_restore",
        "schema_head",
        "aggregate_integrity",
        "application_ready",
        "temporary_resources_removed",
    }
    if set(checks) != required or not all(checks.values()):
        raise ValueError("clean-host recovery checks are incomplete")
    return evidence("clean-host-recovery", "pass", checks=checks)


def evidence_gate(directory: Path) -> dict[str, Any]:
    scenarios: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        payload = load_json(path)
        _reject_secrets(payload)
        if payload.get("schema") != EVIDENCE_SCHEMA:
            raise ValueError(f"Unsupported evidence schema in {path.name}")
        scenario = payload.get("scenario")
        if isinstance(scenario, str):
            accepted = ACCEPTED_GATE_STATUSES.get(scenario)
            if accepted is not None and payload.get("status") not in accepted:
                raise ValueError(f"Evidence did not pass for {scenario}")
            if scenario in scenarios:
                raise ValueError(f"Duplicate evidence scenario: {scenario}")
            scenarios.add(scenario)
    missing = sorted(REQUIRED_GATE_SCENARIOS - scenarios)
    return {
        "schema": EVIDENCE_SCHEMA,
        "status": "pass" if not missing else "incomplete",
        "scenario_count": len(scenarios),
        "missing": missing,
    }


def evidence(scenario: str, status: str, **details: Any) -> dict[str, Any]:
    record = {
        "schema": EVIDENCE_SCHEMA,
        "recorded_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "scenario": scenario,
        "status": status,
        **details,
    }
    _reject_secrets(record)
    return record


def _mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _require_values(payload: dict[str, Any], **expected: Any) -> None:
    for key, value in expected.items():
        if key not in payload or payload[key] != value:
            raise ValueError(f"{key} must remain {value!r}")


def _reject_secrets(payload: object) -> None:
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
        nested_keys: set[str] = set()
        for nested in value:
            nested_keys.update(_all_keys(nested))
        return nested_keys
    return set()


def _payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("created_at must be an ISO-8601 timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _nonempty(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _nonnegative_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


def _nonnegative_number(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{key} must be non-negative")
    return float(value)


def _boolean_checks(payload: dict[str, Any], key: str) -> dict[str, bool]:
    value = payload.get(key)
    if not isinstance(value, dict) or not value or not all(
        isinstance(name, str) and isinstance(result, bool) for name, result in value.items()
    ):
        raise ValueError(f"{key} must be a non-empty object of boolean checks")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Phase 10 operational contracts")
    parser.add_argument("command", choices=("policy", "backup-plan", "backup-evidence", "restore-evidence", "retention-preview", "maintenance", "capacity", "release-preflight", "clean-host-evidence", "gate"))
    parser.add_argument("input", type=Path)
    parser.add_argument("--policy", type=Path, default=Path("operations/phase10-policy.json"))
    parser.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    payload = load_json(args.input) if args.command != "gate" else {}
    policy = load_json(args.policy)
    commands = {
        "policy": lambda: validate_policy(payload),
        "backup-plan": lambda: backup_retention_plan(payload, policy),
        "backup-evidence": lambda: backup_verification_evidence(payload),
        "restore-evidence": lambda: isolated_restore_evidence(payload),
        "retention-preview": lambda: retention_preview_evidence(payload),
        "maintenance": lambda: maintenance_evidence(payload),
        "capacity": lambda: capacity_evidence(payload, policy),
        "release-preflight": lambda: release_preflight_evidence(payload),
        "clean-host-evidence": lambda: clean_host_recovery_evidence(payload),
        "gate": lambda: evidence_gate(args.input),
    }
    result = commands[args.command]()
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
