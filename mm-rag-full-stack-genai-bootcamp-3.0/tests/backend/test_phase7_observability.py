import json
from datetime import date, timedelta

from scripts.phase7_observability import baseline_status, validate_configuration


def test_observability_configuration_keeps_privacy_and_operations_contracts() -> None:
    result = validate_configuration()

    assert result == {"status": "valid", "dashboards": 4, "alert_groups": 2}


def test_slo_baseline_requires_seven_distinct_spanning_days(tmp_path) -> None:
    path = tmp_path / "baseline.jsonl"
    start = date(2026, 9, 1)
    rows = [
        {
            "schema_revision": "phase7-slo-baseline-v1",
            "date": (start + timedelta(days=offset)).isoformat(),
            "recorded_at": f"2026-09-{offset + 1:02d}T12:00:00+00:00",
            "metrics": {
                "operation_rate": 1.0,
                "failure_ratio": 0.0,
                "p95_latency_ms": 12.0,
                "telemetry_export_failures": 0.0,
            },
        }
        for offset in range(7)
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))

    assert baseline_status(path)["ready_for_slo_review"] is True

    path.write_text("".join(json.dumps(row) + "\n" for row in rows[:6]))
    assert baseline_status(path)["ready_for_slo_review"] is False
