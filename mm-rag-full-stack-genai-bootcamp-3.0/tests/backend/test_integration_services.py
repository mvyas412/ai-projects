import os

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("MM_RAG_RUN_INTEGRATION_TESTS") != "1",
    reason="Set MM_RAG_RUN_INTEGRATION_TESTS=1 with Compose services running",
)
def test_real_postgres_and_qdrant_are_ready() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
