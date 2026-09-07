from __future__ import annotations

import logging
import re
import sys
from collections.abc import Mapping, MutableMapping
from time import perf_counter
from typing import Any
from uuid import uuid4

import structlog
from opentelemetry.propagate import extract
from opentelemetry.trace import SpanKind
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars

from backend.app.core.telemetry import (
    current_trace_fields,
    current_traceparent,
    observed_span,
    record_operation,
)

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_PATH_ID = re.compile(
    r"/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?=/|$)"
)
_DROP_LOG_KEYS = {
    "authorization",
    "cookie",
    "credentials",
    "document_content",
    "exception",
    "exc_info",
    "object_key",
    "password",
    "prompt",
    "retrieved_passages",
    "secret",
    "stack",
}


def redact_log_event(
    _logger: object, _method_name: str, event_dict: MutableMapping[str, Any]
) -> Mapping[str, Any]:
    """Apply the telemetry privacy boundary before rendering or OTLP export."""

    redacted: dict[str, object] = {}
    for key, value in event_dict.items():
        normalized = key.lower()
        if normalized in _DROP_LOG_KEYS or any(item in normalized for item in _DROP_LOG_KEYS):
            continue
        if "token" in normalized and not (
            normalized.endswith("_token_count") and isinstance(value, int) and value >= 0
        ):
            continue
        if isinstance(value, str):
            redacted[key] = value[:512]
        elif isinstance(value, list | tuple):
            redacted[f"{key}_count"] = len(value)
        elif value is None or isinstance(value, bool | int | float):
            redacted[key] = value
    redacted.update(current_trace_fields())
    return redacted


def configure_logging(log_level: str) -> None:
    """Configure structured JSON logs for standard logging and structlog."""

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(message)s",
        stream=sys.stdout,
        force=True,
    )
    structlog.configure(
        processors=[
            merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            redact_log_event,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


class RequestContextMiddleware:
    """Attach a correlation ID and emit one structured completion log per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.logger = structlog.get_logger("http")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        provided_request_id = (headers.get("x-request-id") or "").strip()[:128]
        if provided_request_id and not _SAFE_REQUEST_ID.fullmatch(provided_request_id):
            provided_request_id = ""
        request_id = provided_request_id or str(uuid4())
        method = str(scope.get("method", ""))
        path = _PATH_ID.sub("/{id}", str(scope.get("path", "")))
        status_code = 500
        started_at = perf_counter()

        clear_contextvars()
        parent_context = extract(dict(headers.items()))
        with observed_span(
            f"HTTP {method}",
            kind=SpanKind.SERVER,
            context=parent_context,
            attributes={"http.request.method": method, "http.route": path},
        ) as span:
            trace_fields = current_trace_fields()
            bind_contextvars(request_id=request_id, **trace_fields)

            async def send_with_request_id(message: Message) -> None:
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = int(message["status"])
                    span.set_attribute("http.response.status_code", status_code)
                    response_headers = MutableHeaders(scope=message)
                    response_headers["x-request-id"] = request_id
                    traceparent = current_traceparent()
                    if traceparent is not None:
                        response_headers["traceparent"] = traceparent
                await send(message)

            try:
                await self.app(scope, receive, send_with_request_id)
            except Exception as exc:
                duration_ms = round((perf_counter() - started_at) * 1000, 2)
                self.logger.error(
                    "http_request_failed",
                    method=method,
                    path=path,
                    duration_ms=duration_ms,
                    error_type=type(exc).__name__,
                )
                raise
            else:
                duration_ms = round((perf_counter() - started_at) * 1000, 2)
                self.logger.info(
                    "http_request_completed",
                    method=method,
                    path=path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                )
            finally:
                record_operation(
                    "http.request",
                    outcome="success" if status_code < 500 else "failure",
                    duration_ms=round((perf_counter() - started_at) * 1000, 2),
                    attributes={
                        "http.request.method": method,
                        "http.route": path,
                        "http.response.status_code": status_code,
                    },
                )
                clear_contextvars()
