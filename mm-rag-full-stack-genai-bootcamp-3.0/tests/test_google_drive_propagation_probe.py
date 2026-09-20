from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from backend.app.connectors.base import (
    ChangeKind,
    ConnectorChange,
    ConnectorObject,
    ConnectorPage,
    PermissionSnapshot,
    Principal,
    PrincipalKind,
)
from scripts.google_drive_propagation_probe import (
    capture_baseline,
    verify_deletion,
    verify_permission_transition,
)


class _FakeConnector:
    def __init__(self) -> None:
        self.object_id = "opaque-object"
        self.fixture_name = "fixture.pdf"
        self.permission_fingerprint = "a" * 64
        self.principal_count = 1
        self.change_kind = ChangeKind.UPSERT
        self.discoverable = True

    def discover(self, context):  # noqa: ANN001
        if self.discoverable:
            yield ConnectorObject(
                external_id=self.object_id,
                name=self.fixture_name,
                media_type="application/pdf",
                modified_at=datetime.now(UTC),
            )

    def get_permissions(self, context, *, object_external_id):  # noqa: ANN001
        assert object_external_id == self.object_id
        principals = tuple(
            Principal(PrincipalKind.USER, f"principal-{index}", "reader")
            for index in range(self.principal_count)
        )
        return PermissionSnapshot(
            object_external_id=self.object_id,
            fingerprint=self.permission_fingerprint,
            principals=principals,
            observed_at=datetime.now(UTC),
        )

    def list_changes(self, context, *, cursor):  # noqa: ANN001
        if cursor is None:
            return ConnectorPage((), None, False, checkpoint_cursor="checkpoint-1")
        return ConnectorPage(
            (
                ConnectorChange(
                    sequence="sequence",
                    kind=self.change_kind,
                    object_external_id=self.object_id,
                ),
            ),
            None,
            False,
            checkpoint_cursor=f"{cursor}-next",
        )


def test_propagation_probe_records_only_private_ids_and_aggregate_output(
    tmp_path: Path,
) -> None:
    connector = _FakeConnector()
    evidence_path = tmp_path / "evidence.json"
    context = SimpleNamespace()

    baseline = capture_baseline(
        connector,  # type: ignore[arg-type]
        context,  # type: ignore[arg-type]
        fixture_name=connector.fixture_name,
        evidence_path=evidence_path,
    )
    private_evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert baseline == {
        "fixture_discovered": True,
        "baseline_captured": True,
        "principal_count": 1,
        "content_downloaded": False,
    }
    assert private_evidence["object_external_id"] == connector.object_id
    assert connector.object_id not in json.dumps(baseline)
    assert evidence_path.stat().st_mode & 0o777 == 0o600


def test_propagation_probe_verifies_expansion_contraction_and_deletion(
    tmp_path: Path,
) -> None:
    connector = _FakeConnector()
    evidence_path = tmp_path / "evidence.json"
    context = SimpleNamespace()
    capture_baseline(
        connector,  # type: ignore[arg-type]
        context,  # type: ignore[arg-type]
        fixture_name=connector.fixture_name,
        evidence_path=evidence_path,
    )

    connector.permission_fingerprint = "b" * 64
    connector.principal_count = 2
    expanded = verify_permission_transition(
        connector,  # type: ignore[arg-type]
        context,  # type: ignore[arg-type]
        evidence_path=evidence_path,
        expect_restored=False,
    )
    connector.permission_fingerprint = "a" * 64
    connector.principal_count = 1
    restored = verify_permission_transition(
        connector,  # type: ignore[arg-type]
        context,  # type: ignore[arg-type]
        evidence_path=evidence_path,
        expect_restored=True,
    )
    connector.change_kind = ChangeKind.DELETE
    connector.discoverable = False
    deleted = verify_deletion(
        connector,  # type: ignore[arg-type]
        context,  # type: ignore[arg-type]
        evidence_path=evidence_path,
    )

    assert expanded["permission_change_observed"] is True
    assert restored["permission_restored"] is True
    assert deleted == {
        "delete_change_observed": True,
        "fixture_absent_from_discovery": True,
        "content_downloaded": False,
    }
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["permission_expansion_observed"] is True
    assert evidence["permission_contraction_observed"] is True
    assert evidence["deletion_observed"] is True
