from pathlib import Path

import pytest
from pydantic import SecretStr

from backend.app.core.config import Settings


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
        rag_retrieval_profile="dense-v1",
        rag_sparse_indexing_enabled=False,
    )
