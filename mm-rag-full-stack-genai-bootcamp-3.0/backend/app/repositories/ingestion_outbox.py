from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import exists, or_, select, update
from sqlalchemy.orm import Session, aliased

from backend.app.models.outbox import IngestionOutboxEvent


class IngestionOutboxRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, event: IngestionOutboxEvent) -> None:
        self._session.add(event)
        self._session.flush()

    def get(
        self,
        event_id: UUID,
        *,
        for_update: bool = False,
    ) -> IngestionOutboxEvent | None:
        statement = select(IngestionOutboxEvent).where(
            IngestionOutboxEvent.id == event_id
        )
        if for_update:
            statement = statement.with_for_update()
        return self._session.scalar(statement)

    def list_for_job(self, job_id: UUID) -> list[IngestionOutboxEvent]:
        statement = (
            select(IngestionOutboxEvent)
            .where(IngestionOutboxEvent.job_id == job_id)
            .order_by(IngestionOutboxEvent.dispatch_sequence)
        )
        return list(self._session.scalars(statement))

    def claim_due(
        self,
        *,
        lease_owner: str,
        now: datetime,
        lease_duration: timedelta,
        batch_size: int,
    ) -> list[IngestionOutboxEvent]:
        prior = aliased(IngestionOutboxEvent)
        outstanding_prior = exists(
            select(prior.id).where(
                prior.job_id == IngestionOutboxEvent.job_id,
                prior.dispatch_sequence < IngestionOutboxEvent.dispatch_sequence,
                prior.published_at.is_(None),
                prior.discarded_at.is_(None),
            )
        )
        statement = (
            select(IngestionOutboxEvent)
            .where(
                IngestionOutboxEvent.published_at.is_(None),
                IngestionOutboxEvent.discarded_at.is_(None),
                IngestionOutboxEvent.available_at <= now,
                or_(
                    IngestionOutboxEvent.lease_owner.is_(None),
                    IngestionOutboxEvent.lease_expires_at <= now,
                ),
                ~outstanding_prior,
            )
            .order_by(
                IngestionOutboxEvent.available_at,
                IngestionOutboxEvent.created_at,
                IngestionOutboxEvent.id,
            )
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        events = list(self._session.scalars(statement))
        lease_expires_at = now + lease_duration
        for event in events:
            event.lease_owner = lease_owner
            event.lease_expires_at = lease_expires_at
            event.publication_started_at = None
        self._session.flush()
        return events

    def discard_unpublished_for_job(
        self,
        *,
        job_id: UUID,
        now: datetime,
        reason: str,
    ) -> None:
        self._session.execute(
            update(IngestionOutboxEvent)
            .where(
                IngestionOutboxEvent.job_id == job_id,
                IngestionOutboxEvent.published_at.is_(None),
                IngestionOutboxEvent.discarded_at.is_(None),
            )
            .values(
                discarded_at=now,
                discard_reason=reason,
                lease_owner=None,
                lease_expires_at=None,
                publication_started_at=None,
            )
        )
        self._session.flush()
