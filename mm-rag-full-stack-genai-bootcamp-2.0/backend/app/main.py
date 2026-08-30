from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

import structlog
from fastapi import FastAPI
from qdrant_client import QdrantClient

from backend.app.api.router import api_router
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import RequestContextMiddleware, configure_logging
from backend.app.core.security import build_access_token_verifier
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.services.readiness import ReadinessService, probe_postgres, probe_qdrant
from backend.app.storage.local import LocalFileStorage


def _lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        logger = structlog.get_logger(__name__)

        engine = create_database_engine(settings)
        session_factory = create_session_factory(engine)
        qdrant_client = QdrantClient(
            url=settings.qdrant_url,
            api_key=(
                settings.qdrant_api_key.get_secret_value()
                if settings.qdrant_api_key is not None
                else None
            ),
            timeout=settings.qdrant_timeout_seconds,
            check_compatibility=False,
        )

        app.state.settings = settings
        app.state.database_engine = engine
        app.state.session_factory = session_factory
        app.state.qdrant_client = qdrant_client
        app.state.access_token_verifier = build_access_token_verifier(settings)
        app.state.object_storage = LocalFileStorage(settings.local_storage_root)
        app.state.readiness_service = ReadinessService(
            service_name=settings.app_name,
            version=settings.app_version,
            probes={
                "postgres": partial(probe_postgres, engine),
                "qdrant": partial(probe_qdrant, qdrant_client),
            },
        )

        logger.info(
            "application_started",
            app_name=settings.app_name,
            app_version=settings.app_version,
            environment=settings.app_env,
            authentication_configured=settings.auth0_is_configured,
        )
        try:
            yield
        finally:
            qdrant_client.close()
            engine.dispose()
            logger.info("application_stopped", app_name=settings.app_name)

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        docs_url="/docs",
        redoc_url=None,
        openapi_url=f"{resolved_settings.api_v1_prefix}/openapi.json",
        lifespan=_lifespan(resolved_settings),
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(api_router, prefix=resolved_settings.api_v1_prefix)
    return app


app = create_app()
