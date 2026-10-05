"""Report only retry configuration; never connect to a provider or start a worker."""

from __future__ import annotations

import json

from pydantic import ValidationError

from backend.app.core.config import Settings


def retry_report(settings: Settings) -> dict[str, str | int | bool | None]:
    return {
        "profile": settings.execution_retry_profile,
        "ingestion_max_attempts": settings.ingestion_max_attempts,
        "embedding_max_retries": settings.openai_embedding_max_retries,
        "chat_max_retries": settings.openai_chat_max_retries,
        "bounded_retry_configuration": settings.single_attempt_execution,
        "live_execution_authorized": False,
    }


def main() -> None:
    try:
        settings = Settings()
    except ValidationError:
        print(json.dumps({"status": "invalid_configuration", "live_execution_authorized": False}))
        raise SystemExit(2) from None
    print(json.dumps(retry_report(settings), sort_keys=True))
    raise SystemExit(0 if settings.single_attempt_execution else 1)


if __name__ == "__main__":
    main()
