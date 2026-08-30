from __future__ import annotations

import logging
import sys
from time import perf_counter
from uuid import uuid4

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars


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
        request_id = provided_request_id or str(uuid4())
        method = str(scope.get("method", ""))
        path = str(scope.get("path", ""))
        status_code = 500
        started_at = perf_counter()

        clear_contextvars()
        bind_contextvars(request_id=request_id)

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                response_headers = MutableHeaders(scope=message)
                response_headers["x-request-id"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            duration_ms = round((perf_counter() - started_at) * 1000, 2)
            self.logger.exception(
                "http_request_failed",
                method=method,
                path=path,
                duration_ms=duration_ms,
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
            clear_contextvars()
