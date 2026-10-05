from __future__ import annotations

import os
import subprocess
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from pydantic import SecretStr
from sqlalchemy.engine import Engine, make_url

from backend.app.core.config import Settings
from scripts import isolated_postgres_test_database as isolation

_NAME = "mm_rag_test_00000000000000000000000000000001"
_URL = "postgresql+psycopg://test:synthetic-password@127.0.0.1:5434/application"


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, app_env="test", database_url=SecretStr(_URL))


@pytest.fixture
def database_mocks(monkeypatch):
    admin = MagicMock(spec=Engine)
    connection = admin.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalar_one.return_value = 42
    connection.execute.return_value.scalar_one_or_none.return_value = 42
    target = MagicMock(spec=Engine)
    target_connection = target.connect.return_value.__enter__.return_value
    target_connection.execute.side_effect = [
        MagicMock(scalar_one=MagicMock(return_value=_NAME)),
        MagicMock(scalar_one=MagicMock(return_value="20260919_0019")),
    ]
    monkeypatch.setattr(isolation, "uuid4", lambda: UUID(int=1))
    monkeypatch.setattr(isolation, "create_engine", MagicMock(return_value=admin))
    monkeypatch.setattr(isolation, "create_database_engine", MagicMock(return_value=target))
    migrate = MagicMock()
    monkeypatch.setattr(isolation, "_migrate", migrate)
    return admin, connection, target, target_connection, migrate


def _commands(connection: MagicMock) -> list[str]:
    return [str(call.args[0]) for call in connection.execute.call_args_list]


def test_isolated_database_migrates_verifies_and_drops_only_its_creation(
    settings, database_mocks,
) -> None:
    admin, connection, target, _, migrate = database_mocks
    original_url = settings.require_database_url()
    with isolation.isolated_postgres_test_database(settings) as engine:
        assert engine is target
        assert not any(sql.startswith("DROP") for sql in _commands(connection))
    assert _commands(connection) == [
        f'CREATE DATABASE "{_NAME}" TEMPLATE template0',
        "SELECT oid FROM pg_database WHERE datname = :name "
        "AND datdba = (SELECT oid FROM pg_roles WHERE rolname = current_user)",
        "SELECT oid FROM pg_database WHERE datname = :name "
        "AND datdba = (SELECT oid FROM pg_roles WHERE rolname = current_user)",
        f'DROP DATABASE "{_NAME}"',
    ]
    assert migrate.call_args.args[0].database == _NAME
    assert settings.require_database_url() == original_url
    target.dispose.assert_called_once()
    admin.dispose.assert_called_once()


@pytest.mark.parametrize("phase", ["migration", "test", "target", "head"])
def test_isolated_database_cleans_up_after_failures(settings, database_mocks, phase) -> None:
    admin, connection, target, target_connection, migrate = database_mocks
    if phase == "migration":
        migrate.side_effect = RuntimeError("diagnostic failure")
    elif phase == "target":
        target_connection.execute.side_effect = [
            MagicMock(scalar_one=MagicMock(return_value="application")),
            MagicMock(scalar_one=MagicMock(return_value="20260919_0019")),
        ]
    elif phase == "head":
        target_connection.execute.side_effect = [
            MagicMock(scalar_one=MagicMock(return_value=_NAME)),
            MagicMock(scalar_one=MagicMock(return_value="old-head")),
        ]
    with pytest.raises(RuntimeError):
        with isolation.isolated_postgres_test_database(settings):
            if phase != "test":
                pytest.fail("Setup failure must prevent access to the test database")
            raise RuntimeError("diagnostic failure")
    assert _commands(connection)[-1] == f'DROP DATABASE "{_NAME}"'
    admin.dispose.assert_called_once()
    assert target.dispose.call_count == int(phase != "migration")


def test_failed_creation_never_drops_a_preexisting_database(settings, database_mocks) -> None:
    admin, connection, _, _, migrate = database_mocks
    connection.execute.side_effect = RuntimeError("database already exists")
    with pytest.raises(RuntimeError, match="already exists"):
        with isolation.isolated_postgres_test_database(settings):
            pytest.fail("Creation should have failed")
    assert len(_commands(connection)) == 1
    migrate.assert_not_called()
    admin.dispose.assert_called_once()


@pytest.mark.parametrize("actual_oid", [None, 43])
def test_cleanup_refuses_replaced_or_no_longer_owned_database(
    settings, database_mocks, actual_oid,
) -> None:
    admin, connection, target, _, _ = database_mocks
    connection.execute.return_value.scalar_one_or_none.return_value = actual_oid
    with pytest.raises(RuntimeError, match="Refusing cleanup"):
        with isolation.isolated_postgres_test_database(settings):
            pass
    assert not any(sql.startswith("DROP") for sql in _commands(connection))
    target.dispose.assert_called_once()
    admin.dispose.assert_called_once()


@pytest.mark.parametrize("url, environment", [
    (_URL, "production"),
    (_URL.replace("127.0.0.1", "remote.invalid"), "test"),
    (_URL + "?host=remote.invalid", "test"),
    ("sqlite+pysqlite:///:memory:", "test"),
])
def test_invalid_targets_fail_before_connecting(settings, database_mocks, url, environment) -> None:
    admin, _, _, _, migrate = database_mocks
    candidate = settings.model_copy(update={
        "database_url": SecretStr(url), "app_env": environment,
    })
    with pytest.raises(RuntimeError, match="require a local"):
        with isolation.isolated_postgres_test_database(candidate):
            pytest.fail("Target must be rejected")
    admin.connect.assert_not_called()
    migrate.assert_not_called()


def test_migration_url_is_child_only_and_errors_are_non_disclosing(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", _URL)
    target = make_url(_URL).set(database=_NAME)
    run = MagicMock(return_value=subprocess.CompletedProcess([], 1, stderr="private failure"))
    monkeypatch.setattr(isolation.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="^Isolated PostgreSQL migration failed$"):
        isolation._migrate(target)
    assert os.environ["DATABASE_URL"] == _URL
    assert make_url(run.call_args.kwargs["env"]["DATABASE_URL"]).database == _NAME
    assert run.call_args.args[0][-2:] == ["upgrade", "head"]
    assert all("postgresql" not in argument for argument in run.call_args.args[0])
    run.assert_called_once()


def test_migration_timeout_is_not_retried(monkeypatch) -> None:
    run = MagicMock(side_effect=subprocess.TimeoutExpired("alembic", 120))
    monkeypatch.setattr(isolation.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="^Isolated PostgreSQL migration timed out$"):
        isolation._migrate(make_url(_URL).set(database=_NAME))
    run.assert_called_once()
