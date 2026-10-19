from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SVG_NS = {"svg": "http://www.w3.org/2000/svg"}


def test_demo_record_keeps_operator_limits_separate_from_runtime_enforcement() -> None:
    record = json.loads((ROOT / "operations/phase11-demo-v1.json").read_text())
    assert record["schema"] == "mm-rag-phase11-demo-v1"
    assert record["decision"] == "ADR-0065"
    assert record["mode"] == "retained-inspection-demo"
    assert record["runtime_change_authorized"] is False
    assert record["worker"] == {
        "state": "stopped",
        "restart_policy": "no",
        "start_authorized": False,
    }
    demo = record["demo"]
    assert demo["worker_stop_blocks_api_chat"] is False
    assert (
        demo["enforcement"] == "operator-controlled-instructions-not-a-new-runtime-or-ui-interlock"
    )
    for key in (
        "new_questions_authorized",
        "uploads_authorized",
        "retry_rebuild_reindex_authorized",
        "connector_sync_authorized",
        "provider_calls_authorized",
    ):
        assert demo[key] is False
    assert record["access"]["existing_authorized_accounts_only"] is True
    assert record["access"]["additional_enrollment_authorized"] is False
    assert record["access"]["public_signup_authorized"] is False
    assert not any(record["publication"].values())


def test_demo_record_preserves_maintenance_cost_and_manual_retention_boundaries() -> None:
    record = json.loads((ROOT / "operations/phase11-demo-v1.json").read_text())
    maintenance = record["maintenance"]
    assert (ROOT / maintenance["policy"]).is_file()
    assert maintenance["existing_backup_and_capacity_schedules"] == "unchanged"
    assert maintenance["existing_private_backup_destination"] == "unchanged"
    for key in (
        "new_observability_stack_authorized",
        "automatic_retention_apply",
        "automatic_deletion",
        "unattended_upgrades_authorized",
    ):
        assert maintenance[key] is False
    resources = record["resources"]
    assert resources["existing_cost_guardrails"] == "unchanged"
    for key in (
        "new_resources_authorized",
        "paid_capacity_authorized",
        "new_paid_calls_authorized",
        "historical_zero_oci_report_guarantees_future_zero_cost",
    ):
        assert resources[key] is False
    assert record["retention"] == {
        "aggregate_manual_review_due_at": "2026-11-17T23:10:45Z",
        "product_records_automatically_deleted": False,
        "automatic_deletion": False,
    }
    assert record["scope_limits"] == {
        "production_sla": False,
        "five_ten_user_validation": "deferred-unvalidated",
        "nextjs_promoted": False,
    }
    assert (ROOT / record["acceptance_record"]).is_file()


@pytest.mark.parametrize("name", ["mm-rag-demo-architecture", "mm-rag-phase11-closure-demo"])
def test_current_demo_svgs_are_accessible_local_assets(name: str) -> None:
    path = ROOT / "docs/architecture/current" / f"{name}.svg"
    tree = ET.parse(path)
    root = tree.getroot()
    assert root.attrib["role"] == "img"
    assert root.find("svg:title", SVG_NS) is not None
    assert root.find("svg:desc", SVG_NS) is not None
    assert not root.findall(".//svg:script", SVG_NS)
    assert not root.findall(".//svg:image", SVG_NS)
    text = " ".join(root.itertext()).lower()
    assert "worker" in text and "stopped" in text
    assert "maintenance" in text and "unchanged" in text
    assert "768a67f" in text and "0065" in text
    assert "november 17" in text
    assert "does not" in text and "api chat" in text


def test_primary_documentation_links_current_demo_record_and_diagrams() -> None:
    for name in ("README.md", "docs/PROJECT_PLAN.md", "docs/architecture/ARCHITECTURE.md"):
        text = (ROOT / name).read_text()
        assert "0065" in text
        assert "768a67f" in text
    gallery = (ROOT / "docs/architecture/ARCHITECTURE_POSTERS.md").read_text()
    for name in ("mm-rag-demo-architecture", "mm-rag-phase11-closure-demo"):
        assert f"current/{name}.svg" in gallery
    runbook = (ROOT / "docs/DEMO_RUNBOOK.md").read_text()
    assert "not" in runbook and "interlock" in runbook
    assert "Historical developer demonstrations" in runbook
