"""Disposable local PostgreSQL storage for tests with competing connections."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.pool import NullPool

from backend.app.core.config import Settings
from backend.app.db.session import create_database_engine

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DATABASE_NAME = re.compile(r"mm_rag_test_[0-9a-f]{32}\Z")


def _local_url(settings: Settings) -> URL:
    url = make_url(settings.require_database_url())
    if (
        settings.app_env not in {"development", "test"}
        or url.drivername != "postgresql+psycopg"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.query
        or not url.database
    ):
        raise RuntimeError("Isolated PostgreSQL tests require a local development/test URL")
    return url


def _migrate(url: URL) -> None:
    # Only the child gets this URL; shared settings and the application stay unchanged.
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(_PROJECT_ROOT / "alembic.ini"),
             "upgrade", "head"],
            cwd=_PROJECT_ROOT,
            env={**os.environ, "APP_ENV": "test",
                 "DATABASE_URL": url.render_as_string(hide_password=False)},
            capture_output=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Isolated PostgreSQL migration timed out") from None
    if result.returncode:
        raise RuntimeError("Isolated PostgreSQL migration failed")


@contextmanager
def isolated_postgres_test_database(settings: Settings) -> Iterator[Engine]:
    url = _local_url(settings)
    database_name = f"mm_rag_test_{uuid4().hex}"
    if not _DATABASE_NAME.fullmatch(database_name) or database_name == url.database:
        raise RuntimeError("Unsafe isolated PostgreSQL database name")
    target_url = url.set(database=database_name)
    admin = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={
            "connect_timeout": settings.database_connect_timeout_seconds,
            "options": "-c statement_timeout=15000 -c lock_timeout=5000",
        },
    )
    engine: Engine | None = None
    created = False
    database_oid: int | None = None
    identity_query = text(
        "SELECT oid FROM pg_database WHERE datname = :name "
        "AND datdba = (SELECT oid FROM pg_roles WHERE rolname = current_user)"
    )
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{database_name}" TEMPLATE template0'))
            created = True
            database_oid = connection.execute(
                identity_query, {"name": database_name}
            ).scalar_one()
        _migrate(target_url)
        isolated_settings = settings.model_copy(update={
            "app_env": "test", "database_echo": False,
            "database_url": SecretStr(target_url.render_as_string(hide_password=False)),
        })
        engine = create_database_engine(isolated_settings)
        config = Config(str(_PROJECT_ROOT / "alembic.ini"))
        expected_head = ScriptDirectory.from_config(config).get_current_head()
        with engine.connect() as connection:
            actual_database = connection.execute(text("SELECT current_database()")).scalar_one()
            actual_head = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            if actual_database != database_name or actual_head != expected_head:
                raise RuntimeError("Isolated PostgreSQL migration/target verification failed")
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        try:
            if created:
                with admin.connect() as connection:
                    current_oid = connection.execute(
                        identity_query, {"name": database_name}
                    ).scalar_one_or_none()
                    if database_oid is None or current_oid != database_oid:
                        raise RuntimeError("Refusing cleanup of an unverified test database")
                    # No FORCE, broad matching or session termination: only our exact creation.
                    connection.execute(text(f'DROP DATABASE "{database_name}"'))
        finally:
            admin.dispose()
