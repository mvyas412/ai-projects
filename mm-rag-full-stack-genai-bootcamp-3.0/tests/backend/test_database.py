import pytest
from pydantic import SecretStr
from sqlalchemy import Column, Integer, MetaData, String, Table, func, select

from backend.app.core.config import Settings
from backend.app.db.session import (
    create_database_engine,
    create_session_factory,
    transactional_session,
)


def database_settings(database_url: str) -> Settings:
    return Settings(
        app_env="test",
        database_url=SecretStr(database_url),
    )


def test_engine_and_transactional_session_commit_and_rollback(tmp_path) -> None:
    database_path = tmp_path / "transactions.sqlite3"
    engine = create_database_engine(database_settings(f"sqlite+pysqlite:///{database_path}"))
    metadata = MetaData()
    records = Table(
        "records",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(50), nullable=False),
    )
    metadata.create_all(engine)
    factory = create_session_factory(engine)

    try:
        with transactional_session(factory) as session:
            session.execute(records.insert().values(name="committed"))

        with pytest.raises(RuntimeError, match="rollback"):
            with transactional_session(factory) as session:
                session.execute(records.insert().values(name="rolled-back"))
                raise RuntimeError("force rollback")

        with engine.connect() as connection:
            names = connection.execute(select(records.c.name).order_by(records.c.id)).scalars()
            count = connection.execute(select(func.count()).select_from(records)).scalar_one()

        assert list(names) == ["committed"]
        assert count == 1
    finally:
        engine.dispose()


def test_database_url_is_required_without_exposing_a_value() -> None:
    settings = Settings(app_env="test", database_url=None)

    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        create_database_engine(settings)
