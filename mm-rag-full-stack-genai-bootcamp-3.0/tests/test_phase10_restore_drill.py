from __future__ import annotations

from pathlib import Path

import pytest

from scripts.phase10_restore_drill import _counts, _dependency_start_command

ROOT = Path(__file__).parents[1]


def test_restore_drill_compose_is_network_restricted_and_has_no_ports() -> None:
    compose = (ROOT / "deploy" / "oci" / "restore-drill.compose.yaml").read_text(
        encoding="utf-8"
    )
    assert "internal: true" in compose
    assert "ports:" not in compose
    assert "postgres_restore" in compose
    assert "PHASE10_RESTORE_ROOT" in compose


def test_restore_aggregate_count_parser_is_strict() -> None:
    assert _counts('ANALYZE\n{"documents": 2, "workspaces": 1}\n') == {
        "documents": 2,
        "workspaces": 1,
    }
    with pytest.raises(ValueError, match="malformed"):
        _counts('{"documents": "two"}\n')


def test_restore_waits_for_dependency_health_before_import() -> None:
    command = _dependency_start_command(["docker", "compose"])
    assert command == [
        "docker",
        "compose",
        "up",
        "-d",
        "--wait",
        "--wait-timeout",
        "120",
        "postgres",
        "qdrant",
        "seaweedfs",
    ]
