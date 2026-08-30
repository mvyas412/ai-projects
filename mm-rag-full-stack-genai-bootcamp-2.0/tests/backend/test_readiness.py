import pytest
from sqlalchemy import create_engine

from backend.app.services.readiness import ReadinessService, probe_postgres


def test_readiness_checks_every_dependency_after_a_failure() -> None:
    calls: list[str] = []

    def first_probe() -> None:
        calls.append("first")
        raise ConnectionError("not exposed")

    def second_probe() -> None:
        calls.append("second")

    service = ReadinessService(
        service_name="test",
        version="test",
        probes={"first": first_probe, "second": second_probe},
    )

    report = service.check()

    assert calls == ["first", "second"]
    assert report.status == "not_ready"
    assert report.checks["first"].status == "unavailable"
    assert report.checks["second"].status == "ready"


def test_postgres_probe_executes_a_scalar_query() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        probe_postgres(engine)
    finally:
        engine.dispose()


def test_readiness_requires_at_least_one_probe() -> None:
    with pytest.raises(ValueError, match="At least one readiness probe"):
        ReadinessService(service_name="test", version="test", probes={})
