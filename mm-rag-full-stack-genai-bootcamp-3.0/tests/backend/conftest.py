from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy.engine import Engine

from backend.app.core.config import Settings, get_settings
from scripts.isolated_postgres_test_database import isolated_postgres_test_database


@pytest.fixture
def isolated_postgres_engine() -> Iterator[Engine]:
    with isolated_postgres_test_database(get_settings()) as engine:
        yield engine


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    database_path = tmp_path / "backend-tests.sqlite3"
    return Settings(
        app_name="MM-RAG Test API",
        app_version="test",
        app_env="test",
        database_url=SecretStr(f"sqlite+pysqlite:///{database_path}"),
        qdrant_url="http://127.0.0.1:1",
        local_storage_root=tmp_path / "storage",
        object_storage_backend="local",
        rag_retrieval_profile="dense-v1",
        rag_sparse_indexing_enabled=False,
    )
