from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Iterator, Mapping

from opentelemetry import context as otel_context
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode

from backend.app.core.config import Settings

TELEMETRY_SCHEMA_REVISION = "phase7-telemetry-v1"
_SAFE_KEY = re.compile(
    r"^(?:app\.|service\.|deployment\.|http\.|job\.|attempt\.|event\.|"
    r"retrieval\.|model\.|storage\.|db\.|messaging\.|evaluation\.|feedback\.|"
    r"error\.|outcome$|duration_ms$|count$|profile$|revision$|request_id$)"
)
_FORBIDDEN_KEY_PARTS = (
    "authorization",
    "cookie",
    "credential",
    "document_content",
    "db.statement",
    "exception",
    "object_key",
    "passage",
    "password",
    "prompt",
    "response_content",
    "secret",
    "stack",
)


def safe_attributes(attributes: Mapping[str, object] | None) -> dict[str, str | int | float | bool]:
    """Keep only bounded metadata from the Phase 7 telemetry allowlist."""

    cleaned: dict[str, str | int | float | bool] = {}
    for raw_key, raw_value in (attributes or {}).items():
        key = str(raw_key).strip().lower()
        if not _SAFE_KEY.match(key) or any(part in key for part in _FORBIDDEN_KEY_PARTS):
            continue
        # Token usage is useful cost metadata; token-shaped strings remain forbidden.
        if "token" in key and not (
            key.endswith("_token_count") and isinstance(raw_value, int) and raw_value >= 0
        ):
            continue
        if isinstance(raw_value, bool):
            cleaned[key] = raw_value
        elif isinstance(raw_value, int | float):
            cleaned[key] = raw_value
        elif isinstance(raw_value, str):
            cleaned[key] = raw_value[:256]
    return cleaned


def _otlp_headers(settings: Settings) -> dict[str, str] | None:
    secret = settings.otel_exporter_otlp_headers
    if secret is None:
        return None
    parsed: dict[str, str] = {}
    for item in secret.get_secret_value().split(","):
        key, separator, value = item.partition("=")
        if separator and key.strip() and value.strip():
            parsed[key.strip()] = value.strip()
    return parsed or None


def current_trace_fields() -> dict[str, str]:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return {}
    return {
        "trace_id": f"{context.trace_id:032x}",
        "span_id": f"{context.span_id:016x}",
    }


def current_traceparent() -> str | None:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    flags = int(context.trace_flags) & 1
    return f"00-{context.trace_id:032x}-{context.span_id:016x}-{flags:02x}"


@contextmanager
def observed_span(
    name: str,
    *,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: Mapping[str, object] | None = None,
    context: otel_context.Context | None = None,
) -> Iterator[trace.Span]:
    """Create a metadata-only span and classify failures without recording messages."""

    tracer = trace.get_tracer("mm-rag", TELEMETRY_SCHEMA_REVISION)
    started = perf_counter()
    with tracer.start_as_current_span(name, kind=kind, context=context) as span:
        for key, value in safe_attributes(attributes).items():
            span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            span.set_attribute("error.type", type(exc).__name__[:128])
            span.set_status(Status(StatusCode.ERROR))
            raise
        finally:
            span.set_attribute("duration_ms", round((perf_counter() - started) * 1000, 2))


@dataclass(slots=True)
class TelemetryRuntime:
    tracer_provider: TracerProvider | None = None
    meter_provider: MeterProvider | None = None
    logger_provider: LoggerProvider | None = None
    logging_handler: LoggingHandler | None = None

    def shutdown(self) -> None:
        if self.logging_handler is not None:
            logging.getLogger().removeHandler(self.logging_handler)
        if self.logger_provider is not None:
            self.logger_provider.shutdown()
        if self.meter_provider is not None:
            self.meter_provider.shutdown()
        if self.tracer_provider is not None:
            self.tracer_provider.shutdown()


def configure_telemetry(settings: Settings, *, service_name: str) -> TelemetryRuntime:
    """Configure OTLP export only when explicitly enabled for this process."""

    if not settings.telemetry_enabled:
        return TelemetryRuntime()

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": settings.app_version,
            "deployment.environment.name": settings.app_env,
            "telemetry.schema.revision": TELEMETRY_SCHEMA_REVISION,
        }
    )
    endpoint = settings.otel_exporter_otlp_endpoint.rstrip("/")
    headers = _otlp_headers(settings)

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces", headers=headers),
            max_queue_size=settings.telemetry_max_queue_size,
        )
    )
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics", headers=headers),
        export_interval_millis=settings.telemetry_metric_interval_seconds * 1000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(endpoint=f"{endpoint}/v1/logs", headers=headers),
            max_queue_size=settings.telemetry_max_queue_size,
        )
    )
    set_logger_provider(logger_provider)
    handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    logging.getLogger().addHandler(handler)
    return TelemetryRuntime(tracer_provider, meter_provider, logger_provider, handler)


def record_operation(
    operation: str,
    *,
    outcome: str,
    duration_ms: float,
    attributes: Mapping[str, object] | None = None,
) -> None:
    """Record bounded operation count and latency through the configured meter."""

    values = safe_attributes({"outcome": outcome, **(attributes or {})})
    meter = metrics.get_meter("mm-rag", TELEMETRY_SCHEMA_REVISION)
    meter.create_counter(
        "mm_rag_operations_total",
        unit="1",
        description="Completed MM-RAG operations",
    ).add(1, {"operation": operation[:128], **values})
    meter.create_histogram(
        "mm_rag_operation_duration",
        unit="ms",
        description="MM-RAG operation duration",
    ).record(max(0.0, duration_ms), {"operation": operation[:128], **values})


def record_invariant_violation(invariant: str) -> None:
    """Record only a bounded invariant name; details remain in authoritative audit data."""

    metrics.get_meter("mm-rag", TELEMETRY_SCHEMA_REVISION).create_counter(
        "mm_rag_invariant_violations_total",
        unit="1",
        description="Zero-tolerance MM-RAG invariant violations",
    ).add(1, {"invariant": invariant[:80]})
