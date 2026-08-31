from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from backend.app.core.config import get_settings
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.services.ingestion_jobs import IngestionJobStateMachine
from backend.app.services.ingestion_operations import IngestionOperationsService


def main() -> None:
    parser = argparse.ArgumentParser(description="MM-RAG ingestion operations")
    parser.add_argument(
        "command",
        choices=("status", "recover-expired", "retention-preview", "retention-apply"),
    )
    args = parser.parse_args()
    settings = get_settings()
    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    try:
        if args.command == "status":
            with factory() as session:
                payload = IngestionOperationsService(session, settings).report().safe_dict()
        elif args.command == "recover-expired":
            with factory.begin() as session:
                recovered = IngestionJobStateMachine(session).recover_expired_jobs(
                    now=datetime.now(UTC),
                    limit=25,
                )
            payload = {"recovered_expired_jobs": len(recovered)}
        elif args.command == "retention-preview":
            with factory() as session:
                count = IngestionOperationsService(
                    session, settings
                ).terminal_outbox_retention_candidates()
            payload = {"retention_candidates": count, "applied": False}
        else:
            with factory.begin() as session:
                count = IngestionOperationsService(
                    session, settings
                ).apply_terminal_outbox_retention()
            payload = {"deleted_terminal_outbox_events": count, "applied": True}
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
