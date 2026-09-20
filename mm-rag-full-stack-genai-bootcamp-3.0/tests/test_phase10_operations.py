from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.phase10_operations import (
    EVIDENCE_SCHEMA,
    backup_retention_plan,
    backup_verification_evidence,
    capacity_evidence,
    clean_host_recovery_evidence,
    evidence_gate,
    isolated_restore_evidence,
    maintenance_evidence,
    release_preflight_evidence,
    retention_preview_evidence,
    validate_policy,
)

ROOT = Path(__file__).parents[1]
POLICY_PATH = ROOT / "operations" / "phase10-policy.json"


@pytest.fixture
def policy() -> dict[str, object]:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def test_accepted_policy_is_valid_and_rejects_paid_capacity(
    policy: dict[str, object],
) -> None:
    assert validate_policy(policy)["status"] == "valid"
    changed = json.loads(json.dumps(policy))
    changed["infrastructure_budget_usd"] = 1
    with pytest.raises(ValueError, match="USD 0"):
        validate_policy(changed)


def test_backup_plan_is_preview_only_and_preserves_last_two_verified(
    policy: dict[str, object],
) -> None:
    backups = []
    for index in range(10):
        backups.append(
            {
                "backup_id": f"daily-{index}",
                "cadence": "daily",
                "created_at": f"2026-09-{index + 1:02d}T05:30:00Z",
                "verified": True,
            }
        )
    result = backup_retention_plan({"backups": backups}, policy)
    assert result["apply_enabled"] is False
    assert result["candidate_count"] == 3
    assert "daily-9" not in result["candidate_ids"]
    assert "daily-8" not in result["candidate_ids"]


def test_backup_and_restore_evidence_are_content_free() -> None:
    digest = "a" * 64
    backup = backup_verification_evidence(
        {
            "manifest_sha256": digest,
            "encrypted_bundle_sha256": "b" * 64,
            "file_count": 6,
            "total_bytes": 1234,
        }
    )
    assert backup["scenario"] == "backup-verification"
    assert "path" not in backup

    restored = isolated_restore_evidence(
        {
            "checks": {
                "postgres": True,
                "qdrant": True,
                "objects": True,
                "active_data_plane_untouched": True,
            }
        }
    )
    assert restored["status"] == "pass"


def test_retention_report_hashes_token_and_cannot_enable_apply() -> None:
    result = retention_preview_evidence(
        {
            "mode": "preview-only",
            "automatic_apply": False,
            "preview_token": "private-one-time-preview-token",
            "policy_revision": "retention-undecided-v1",
            "counts": {"eligible": 3, "held": 1},
        }
    )
    assert result["apply_enabled"] is False
    assert result["preview_sha256"] != "private-one-time-preview-token"
    assert "preview_token" not in result

    with pytest.raises(ValueError, match="preview-only"):
        retention_preview_evidence(
            {
                "mode": "apply",
                "automatic_apply": True,
                "preview_token": "x",
                "policy_revision": "x",
                "counts": {"eligible": 1},
            }
        )


def test_maintenance_requires_rollback_proof_for_runtime_changes() -> None:
    candidate: dict[str, Any] = {
        "automatic_merge": False,
        "paid_acceptance": False,
        "ecosystems": ["python", "container"],
        "source_revision": "a" * 40,
        "candidate_revision": "b" * 40,
        "lockfile_sha256": {"uv.lock": "c" * 64},
        "runtime_database_or_image_change": True,
        "severity": "high",
        "known_exploited": False,
        "public_exploit_on_exposed_component": False,
        "exploitable_on_exposed_component": False,
        "checks": {
            "lockfiles": True,
            "tests": True,
            "vulnerability_scan": True,
            "sbom": True,
            "provenance": True,
            "arm64": True,
            "rollback_proof": False,
        },
    }
    with pytest.raises(ValueError, match="rollback proof"):
        maintenance_evidence(candidate)
    candidate["checks"]["rollback_proof"] = True
    assert maintenance_evidence(candidate)["classification"] == "monthly"


def test_known_exploited_maintenance_is_urgent() -> None:
    result = maintenance_evidence(
        {
            "automatic_merge": False,
            "paid_acceptance": False,
            "ecosystems": ["javascript"],
            "source_revision": "a" * 40,
            "candidate_revision": "b" * 40,
            "lockfile_sha256": {"package-lock.json": "c" * 64},
            "runtime_database_or_image_change": False,
            "known_exploited": True,
            "checks": {
                "lockfiles": True,
                "tests": True,
                "vulnerability_scan": True,
                "sbom": True,
                "provenance": True,
                "arm64": True,
            },
        }
    )
    assert result["classification"] == "urgent"


def test_capacity_guardrails_report_review_and_critical(
    policy: dict[str, object],
) -> None:
    metrics = {
        "cpu_percent": 82,
        "memory_percent": 50,
        "disk_percent": 40,
        "inode_percent": 20,
        "sustained_minutes": 15,
        "verified_backup_age_hours": 2,
        "certificate_days_remaining": 30,
        "oldest_queue_age_minutes": 0,
        "queue_age_critical": False,
        "unexpected_paid_resources": False,
    }
    assert capacity_evidence({"metrics": metrics}, policy)["status"] == "review"
    metrics["unexpected_paid_resources"] = True
    result = capacity_evidence({"metrics": metrics}, policy)
    assert result["status"] == "critical"
    assert "unexpected-paid-resource" in result["reasons"]


def test_healthy_capacity_passes_with_resolved_thresholds(
    policy: dict[str, object],
) -> None:
    result = capacity_evidence(
        {
            "metrics": {
                "cpu_percent": 20,
                "memory_percent": 30,
                "disk_percent": 40,
                "inode_percent": 10,
                "sustained_minutes": 0,
                "verified_backup_age_hours": 8,
                "certificate_days_remaining": 60,
                "oldest_queue_age_minutes": 0,
                "queue_age_critical": False,
                "unexpected_paid_resources": False,
            }
        },
        policy,
    )
    assert result["status"] == "pass"
    assert result["unresolved_thresholds"] == []


def test_queue_and_certificate_thresholds_are_critical(
    policy: dict[str, object],
) -> None:
    metrics = {
        "cpu_percent": 20,
        "memory_percent": 30,
        "disk_percent": 40,
        "inode_percent": 10,
        "sustained_minutes": 0,
        "verified_backup_age_hours": 8,
        "certificate_days_remaining": 14,
        "oldest_queue_age_minutes": 15,
        "queue_age_critical": False,
        "unexpected_paid_resources": False,
    }
    result = capacity_evidence({"metrics": metrics}, policy)
    assert result["status"] == "critical"
    assert result["reasons"] == ["certificate-expiry", "queue-age"]


def test_release_preflight_is_plan_first_and_awaits_operator() -> None:
    payload = {
        "action": "upgrade",
        "current_revision": "a" * 40,
        "target_revision": "b" * 40,
        "operator_authorized": False,
        "checks": {
            "digest_pinned": True,
            "backup_fresh": True,
            "migration_compatible": True,
            "disk_headroom": True,
            "jobs_quiesced": True,
            "health_ready": True,
            "rollback_or_restore_available": True,
        },
    }
    result = release_preflight_evidence(payload)
    assert result["status"] == "ready"
    assert result["operator_authorized"] is False
    payload["operator_authorized"] = True
    with pytest.raises(ValueError, match="await operator authorization"):
        release_preflight_evidence(payload)


def test_clean_host_recovery_requires_approval_and_cleanup() -> None:
    payload = {
        "temporary_resources_approved": False,
        "zero_cost_plan_verified": True,
        "checks": {
            "reviewed_iac": True,
            "secrets_runtime_only": True,
            "encrypted_restore": True,
            "schema_head": True,
            "aggregate_integrity": True,
            "application_ready": True,
            "temporary_resources_removed": True,
        },
    }
    with pytest.raises(ValueError, match="separate temporary-resource approval"):
        clean_host_recovery_evidence(payload)
    payload["temporary_resources_approved"] = True
    assert clean_host_recovery_evidence(payload)["status"] == "pass"


def test_secret_fields_are_rejected() -> None:
    with pytest.raises(ValueError, match="forbidden fields"):
        backup_verification_evidence(
            {
                "manifest_sha256": "a" * 64,
                "encrypted_bundle_sha256": "b" * 64,
                "file_count": 1,
                "total_bytes": 1,
                "token": "must-not-appear",
            }
        )


def test_gate_requires_all_phase10_scenarios(tmp_path: Path) -> None:
    (tmp_path / "backup.json").write_text(
        json.dumps(
            {
                "schema": EVIDENCE_SCHEMA,
                "scenario": "backup-verification",
                "status": "pass",
            }
        ),
        encoding="utf-8",
    )
    result = evidence_gate(tmp_path)
    assert result["status"] == "incomplete"
    assert "clean-host-recovery" in result["missing"]
