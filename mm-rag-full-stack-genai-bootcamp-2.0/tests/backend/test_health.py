from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.services.readiness import ReadinessService, get_readiness_service


@pytest.fixture
def client(test_settings: Settings) -> Iterator[TestClient]:
    app = create_app(test_settings)
    with TestClient(app) as test_client:
        yield test_client


def test_liveness_is_independent_of_external_services(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "MM-RAG Test API",
        "version": "test",
    }
    assert response.headers["x-request-id"]


def test_request_id_is_preserved(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health/live",
        headers={"x-request-id": "presentation-check-123"},
    )

    assert response.headers["x-request-id"] == "presentation-check-123"


def test_blank_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/api/v1/health/live", headers={"x-request-id": "   "})

    assert response.headers["x-request-id"]
    assert response.headers["x-request-id"] != "   "


def test_liveness_starts_when_postgres_and_qdrant_are_unreachable() -> None:
    settings = Settings(
        app_env="test",
        database_url=SecretStr(
            "postgresql+psycopg://unavailable:unavailable@127.0.0.1:1/unavailable"
        ),
        database_connect_timeout_seconds=1,
        qdrant_url="http://127.0.0.1:1",
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200


def test_readiness_returns_200_when_all_dependencies_are_ready(
    test_settings: Settings,
) -> None:
    app = create_app(test_settings)
    service = ReadinessService(
        service_name=test_settings.app_name,
        version=test_settings.app_version,
        probes={"postgres": lambda: None, "qdrant": lambda: None},
    )
    app.dependency_overrides[get_readiness_service] = lambda: service

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["postgres"]["status"] == "ready"
    assert body["checks"]["qdrant"]["status"] == "ready"


def test_readiness_returns_safe_503_when_a_dependency_is_unavailable(
    test_settings: Settings,
) -> None:
    def unavailable_postgres() -> None:
        raise RuntimeError("private connection details must never reach the response")

    app = create_app(test_settings)
    service = ReadinessService(
        service_name=test_settings.app_name,
        version=test_settings.app_version,
        probes={"postgres": unavailable_postgres, "qdrant": lambda: None},
    )
    app.dependency_overrides[get_readiness_service] = lambda: service

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["postgres"]["status"] == "unavailable"
    assert body["checks"]["qdrant"]["status"] == "ready"
    assert "private connection details" not in response.text
