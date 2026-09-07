from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import yaml  # type: ignore[import-untyped]

from backend.app.core.config import PROJECT_ROOT

OBSERVABILITY_ROOT = PROJECT_ROOT / "observability"
BASELINE_PATH = PROJECT_ROOT / "data/runtime/observability/baseline.jsonl"

_QUERIES = {
    "operation_rate": "sum(rate(mm_rag_operations_total[5m]))",
    "failure_ratio": (
        'sum(rate(mm_rag_operations_total{outcome="failure"}[5m])) / '
        "clamp_min(sum(rate(mm_rag_operations_total[5m])), 0.000001)"
    ),
    "p95_latency_ms": (
        "histogram_quantile(0.95, sum(rate("
        "mm_rag_operation_duration_milliseconds_bucket[5m])) by (le))"
    ),
    "telemetry_export_failures": "sum(increase(otelcol_exporter_send_failed_spans_total[5m]))",
}


def _json_url(url: str) -> dict[str, object]:
    with urlopen(url, timeout=3) as response:  # noqa: S310 - configured local endpoint
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("Observability response is invalid")
    return payload


def _probe_url(url: str) -> None:
    with urlopen(url, timeout=3) as response:  # noqa: S310 - configured local endpoint
        if response.status < 200 or response.status >= 300:
            raise ValueError("Observability endpoint is unavailable")


def status() -> dict[str, object]:
    endpoints = {
        "collector": os.getenv("OTEL_HEALTH_URL", "http://127.0.0.1:13133/"),
        "grafana": os.getenv("GRAFANA_HEALTH_URL", "http://127.0.0.1:3003/api/health"),
    }
    checks: dict[str, str] = {}
    for name, url in endpoints.items():
        try:
            _probe_url(url)
            checks[name] = "ready"
        except (OSError, URLError, ValueError, json.JSONDecodeError):
            checks[name] = "unavailable"
    return {
        "status": "ready" if set(checks.values()) == {"ready"} else "not_ready",
        "checks": checks,
    }


def record_baseline() -> dict[str, object]:
    prometheus = os.getenv("PROMETHEUS_URL", "http://127.0.0.1:9093").rstrip("/")
    values: dict[str, float] = {}
    for name, query in _QUERIES.items():
        payload = _json_url(f"{prometheus}/api/v1/query?{urlencode({'query': query})}")
        data = payload.get("data")
        results = data.get("result") if isinstance(data, dict) else None
        value = results[0].get("value") if isinstance(results, list) and results else None
        values[name] = float(value[1]) if isinstance(value, list) and len(value) == 2 else 0.0
    date_key = date.today().isoformat()
    row: dict[str, object] = {
        "schema_revision": "phase7-slo-baseline-v1",
        "date": date_key,
        "recorded_at": datetime.now(UTC).isoformat(),
        "metrics": values,
    }
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = _baseline_rows()
    rows[date_key] = row
    temporary = BASELINE_PATH.with_suffix(".tmp")
    temporary.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in rows.values()),
        encoding="utf-8",
    )
    temporary.replace(BASELINE_PATH)
    return baseline_status()


def baseline_status(path: Path = BASELINE_PATH) -> dict[str, object]:
    rows = _baseline_rows(path)
    days = sorted(rows)
    ready = (
        len(days) >= 7 and (date.fromisoformat(days[-1]) - date.fromisoformat(days[0])).days >= 6
    )
    return {
        "schema_revision": "phase7-slo-baseline-status-v1",
        "distinct_days": len(days),
        "required_days": 7,
        "first_date": days[0] if days else None,
        "last_date": days[-1] if days else None,
        "ready_for_slo_review": ready,
    }


def validate_configuration() -> dict[str, object]:
    collector = yaml.safe_load((OBSERVABILITY_ROOT / "otel-collector.yaml").read_text())
    prometheus = yaml.safe_load((OBSERVABILITY_ROOT / "prometheus.yaml").read_text())
    rules = yaml.safe_load((OBSERVABILITY_ROOT / "alerts/phase7-rules.yaml").read_text())
    dashboards = list((OBSERVABILITY_ROOT / "grafana/dashboards").glob("*.json"))
    for path in dashboards:
        json.loads(path.read_text(encoding="utf-8"))
    actions = collector["processors"]["attributes/privacy"]["actions"]
    deleted = {item["key"] for item in actions if item.get("action") == "delete"}
    required = {
        "authorization",
        "cookie",
        "db.statement",
        "exception.stacktrace",
        "prompt",
        "token",
    }
    if not required.issubset(deleted):
        raise ValueError("Collector privacy deletions are incomplete")
    if not rules.get("groups") or len(dashboards) < 1:
        raise ValueError("Phase 7 operational configuration is incomplete")
    if "/otel-lgtm/prometheus-rules/*.yaml" not in prometheus.get("rule_files", []):
        raise ValueError("Phase 7 Prometheus alert discovery is not configured")
    return {"status": "valid", "dashboards": len(dashboards), "alert_groups": len(rules["groups"])}


def _baseline_rows(path: Path = BASELINE_PATH) -> dict[str, dict[str, object]]:
    if not path.is_file():
        return {}
    rows: dict[str, dict[str, object]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        payload = json.loads(line)
        if not isinstance(payload, dict) or not isinstance(payload.get("date"), str):
            raise ValueError("Baseline row is invalid")
        rows[payload["date"]] = payload
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="MM-RAG Phase 7 observability operations")
    parser.add_argument(
        "command", choices=("status", "record-baseline", "baseline-status", "validate")
    )
    args = parser.parse_args()
    payload = {
        "status": status,
        "record-baseline": record_baseline,
        "baseline-status": baseline_status,
        "validate": validate_configuration,
    }[args.command]()
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
