from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validate_phase8_deployment import (
    _parse_example_environment,
    validate_phase8_deployment,
)


def test_phase8_oci_deployment_contract_is_safe_and_complete() -> None:
    result = validate_phase8_deployment()

    assert result == {
        "image_contracts": 9,
        "public_tcp_ports": [80, 443],
        "schema_revision": "phase8-oci-deployment-contract-v4",
        "status": "valid",
    }


def test_example_environment_parser_rejects_malformed_lines(tmp_path: Path) -> None:
    candidate = tmp_path / "runtime.env.example"
    candidate.write_text("MISSING_SEPARATOR\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid example environment line"):
        _parse_example_environment(candidate)
