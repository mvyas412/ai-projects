from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from typing import Any, cast

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import Settings

SessionFactory = sessionmaker[Session]


def create_database_engine(settings: Settings) -> Engine:
    """Build the process-wide SQLAlchemy engine without opening a connection."""

    database_url = settings.require_database_url()
    engine_options: dict[str, Any] = {
        "echo": settings.database_echo,
        "pool_pre_ping": True,
    }

    if database_url.startswith("postgresql"):
        engine_options.update(
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout_seconds,
            pool_recycle=settings.database_pool_recycle_seconds,
            connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
        )

    return create_engine(database_url, **engine_options)


def create_session_factory(engine: Engine) -> SessionFactory:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db_session(request: Request) -> Generator[Session, None, None]:
    """Provide a request-scoped session without implicit transaction commits."""

    factory = cast(SessionFactory, request.app.state.session_factory)
    with factory() as session:
        yield session


@contextmanager
def transactional_session(factory: SessionFactory) -> Iterator[Session]:
    """Provide an explicit commit-on-success, rollback-on-error transaction."""

    with factory.begin() as session:
        yield session
