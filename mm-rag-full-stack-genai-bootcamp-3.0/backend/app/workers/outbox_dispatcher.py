from __future__ import annotations

import argparse
import asyncio
import os
import signal
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from uuid import UUID

import structlog

from backend.app.broker.messages import IngestionEventMessage
from backend.app.broker.rabbitmq import BrokerPublishError, RabbitMQPublisher
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import configure_logging
from backend.app.db.rls import DatabasePurpose, set_rls_context
from backend.app.db.session import (
    SessionFactory,
    create_database_engine,
    create_session_factory,
)
from backend.app.services.ingestion_outbox import (
    IngestionOutboxLeaseError,
    IngestionOutboxStateMachine,
)
from backend.app.workers.health import ProcessHealth, health_is_ready


class ConfirmedPublisher(Protocol):
    async def publish(self, message: IngestionEventMessage) -> None: ...

    async def close(self) -> None: ...


class OutboxDispatcher:
    def __init__(
        self,
        settings: Settings,
        session_factory: SessionFactory,
        publisher: ConfirmedPublisher,
        *,
        dispatcher_id: str,
        health: ProcessHealth,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._publisher = publisher
        self._dispatcher_id = dispatcher_id
        self._health = health
        self._logger = structlog.get_logger(__name__)

    async def run_once(self) -> int:
        now = datetime.now(UTC)
        with self._session_factory.begin() as session:
            set_rls_context(session, purpose=DatabasePurpose.DISPATCHER)
            events = IngestionOutboxStateMachine(session).claim_due_events(
                lease_owner=self._dispatcher_id,
                now=now,
                lease_duration=timedelta(seconds=self._settings.dispatcher_lease_seconds),
                batch_size=self._settings.dispatcher_batch_size,
            )
        if events:
            self._health.increment("claimed")
        for event_hint in events:
            await self._publish_event(event_hint.id)
        return len(events)

    async def _publish_event(self, event_id: UUID) -> None:
        try:
            with self._session_factory.begin() as session:
                set_rls_context(session, purpose=DatabasePurpose.DISPATCHER)
                event = IngestionOutboxStateMachine(session).start_publication(
                    event_id=event_id,
                    lease_owner=self._dispatcher_id,
                    now=datetime.now(UTC),
                )
                message = IngestionEventMessage.model_validate(event.payload)
                attempt_count = event.publication_attempt_count
            await self._publisher.publish(message)
            with self._session_factory.begin() as session:
                set_rls_context(session, purpose=DatabasePurpose.DISPATCHER)
                IngestionOutboxStateMachine(session).mark_published(
                    event_id=event_id,
                    lease_owner=self._dispatcher_id,
                    now=datetime.now(UTC),
                )
            self._health.increment("confirmed")
            self._logger.info("outbox_event_confirmed", event_id=str(event_id))
        except IngestionOutboxLeaseError:
            self._health.increment("lease_lost")
            self._logger.warning("outbox_lease_lost", event_id=str(event_id))
        except (BrokerPublishError, ValueError) as exc:
            error_code = (
                "outbox_payload_invalid"
                if isinstance(exc, ValueError)
                else "broker_publish_unconfirmed"
            )
            delay = _publication_backoff(attempt_count if "attempt_count" in locals() else 1, event_id)
            try:
                with self._session_factory.begin() as session:
                    set_rls_context(session, purpose=DatabasePurpose.DISPATCHER)
                    IngestionOutboxStateMachine(session).record_publication_failure(
                        event_id=event_id,
                        lease_owner=self._dispatcher_id,
                        now=datetime.now(UTC),
                        next_available_at=datetime.now(UTC) + delay,
                        error_code=error_code,
                    )
            except IngestionOutboxLeaseError:
                self._health.increment("lease_lost")
            self._health.increment("publish_failed")
            self._logger.warning(
                "outbox_publication_deferred",
                event_id=str(event_id),
                error_code=error_code,
            )

    async def run(self, stop: asyncio.Event) -> None:
        self._health.update(state="running", ready=True)
        try:
            while not stop.is_set():
                try:
                    claimed = await self.run_once()
                    self._health.update(state="running", ready=True)
                except Exception:
                    claimed = 0
                    self._health.increment("loop_failed")
                    self._health.update(state="degraded", ready=False)
                    self._logger.exception("outbox_dispatch_loop_failed")
                delay = 0.05 if claimed else self._settings.dispatcher_poll_seconds
                try:
                    await asyncio.wait_for(stop.wait(), timeout=delay)
                except TimeoutError:
                    pass
        finally:
            self._health.update(state="stopping", ready=False)
            await self._publisher.close()
            self._health.update(state="stopped", ready=False)


def _publication_backoff(attempt_count: int, event_id: UUID) -> timedelta:
    schedule = (1, 5, 30, 120, 300)
    base = schedule[min(max(attempt_count, 1) - 1, len(schedule) - 1)]
    jitter = 0.8 + ((event_id.int % 401) / 1000)
    return timedelta(seconds=max(1.0, base * jitter))


async def _run(settings: Settings) -> None:
    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    identity = f"dispatcher-{socket.gethostname()}-{os.getpid()}"[:200]
    health = ProcessHealth(settings.runtime_health_directory, "dispatcher")
    publisher = RabbitMQPublisher(settings, process_name=identity)
    dispatcher = OutboxDispatcher(
        settings,
        factory,
        publisher,
        dispatcher_id=identity,
        health=health,
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for item in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(item, stop.set)
    try:
        await dispatcher.run(stop)
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="MM-RAG transactional outbox dispatcher")
    parser.add_argument("--health-check", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if args.health_check:
        path = Path(settings.runtime_health_directory) / "dispatcher.json"
        raise SystemExit(0 if health_is_ready(path, max_age=timedelta(seconds=90)) else 1)
    configure_logging(settings.log_level)
    asyncio.run(_run(settings))


if __name__ == "__main__":
    main()
