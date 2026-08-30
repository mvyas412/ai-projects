from __future__ import annotations

from collections.abc import Callable, Mapping
from time import perf_counter
from typing import Literal, cast

import structlog
from fastapi import Request
from qdrant_client import QdrantClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from backend.app.schemas.health import DependencyReadiness, ReadinessResponse

Probe = Callable[[], None]


def probe_postgres(engine: Engine) -> None:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1")).scalar_one()
        if result != 1:
            raise RuntimeError("PostgreSQL readiness query returned an unexpected result")


def probe_qdrant(client: QdrantClient) -> None:
    client.get_collections()


class ReadinessService:
    """Run dependency probes while keeping raw failure details out of responses."""

    def __init__(
        self,
        *,
        service_name: str,
        version: str,
        probes: Mapping[str, Probe],
    ) -> None:
        if not probes:
            raise ValueError("At least one readiness probe is required")
        self._service_name = service_name
        self._version = version
        self._probes = dict(probes)
        self._logger = structlog.get_logger(__name__)

    def check(self) -> ReadinessResponse:
        checks: dict[str, DependencyReadiness] = {}

        for dependency, probe in self._probes.items():
            started_at = perf_counter()
            try:
                probe()
            except Exception as exc:
                latency_ms = round((perf_counter() - started_at) * 1000, 2)
                checks[dependency] = DependencyReadiness(
                    status="unavailable",
                    latency_ms=latency_ms,
                )
                self._logger.warning(
                    "readiness_probe_failed",
                    dependency=dependency,
                    error_type=type(exc).__name__,
                )
            else:
                latency_ms = round((perf_counter() - started_at) * 1000, 2)
                checks[dependency] = DependencyReadiness(
                    status="ready",
                    latency_ms=latency_ms,
                )

        overall_status: Literal["ready", "not_ready"] = (
            "ready" if all(item.status == "ready" for item in checks.values()) else "not_ready"
        )
        return ReadinessResponse(
            status=overall_status,
            service=self._service_name,
            version=self._version,
            checks=checks,
        )


def get_readiness_service(request: Request) -> ReadinessService:
    return cast(ReadinessService, request.app.state.readiness_service)
