from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import TracerProvider

from backend.app.broker.messages import IngestionEventMessage
from backend.app.core.logging import redact_log_event
from backend.app.core.telemetry import current_traceparent, safe_attributes
from backend.app.main import create_app


def test_safe_attributes_reject_content_credentials_and_unbounded_keys() -> None:
    assert safe_attributes(
        {
            "retrieval.profile": "hybrid-v1",
            "model.token": "must-not-export",
            "model.input_token_count": 42,
            "prompt": "must-not-export",
            "db.statement": "select private_content",
            "unknown": "must-not-export",
            "count": 4,
        }
    ) == {
        "retrieval.profile": "hybrid-v1",
        "model.input_token_count": 42,
        "count": 4,
    }


def test_log_redaction_removes_sensitive_values_and_collapses_lists() -> None:
    result = redact_log_event(
        object(),
        "info",
        {
            "event": "retrieval_ranked",
            "prompt_token": "must-not-export",
            "model_input_token_count": 10,
            "object_key": "private/path",
            "ranked_point_ids": ["one", "two"],
        },
    )

    assert result["event"] == "retrieval_ranked"
    assert result["ranked_point_ids_count"] == 2
    assert "prompt_token" not in result
    assert result["model_input_token_count"] == 10
    assert "object_key" not in result


def test_current_traceparent_uses_w3c_shape() -> None:
    provider = TracerProvider()
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("root"):
        traceparent = current_traceparent()

    assert traceparent is not None
    assert len(traceparent) == 55
    assert traceparent.startswith("00-")


def test_http_response_returns_safe_request_and_trace_correlation(test_settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        response = client.get(
            "/api/v1/health/live",
            headers={
                "x-request-id": "invalid request id with spaces",
                "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            },
        )

    assert response.status_code == 200
    assert response.headers["x-request-id"] != "invalid request id with spaces"
    assert response.headers["traceparent"].startswith(
        "00-4bf92f3577b34da6a3ce929d0e0e4736-"
    )


def test_broker_message_accepts_only_metadata_trace_context() -> None:
    message = IngestionEventMessage(
        event_id=uuid4(),
        event_type="ingestion.job.available",
        schema_version=1,
        job_id=uuid4(),
        occurred_at=datetime.now(UTC),
        traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
    )

    restored = IngestionEventMessage.from_body(message.broker_body())
    assert restored.traceparent == message.traceparent
