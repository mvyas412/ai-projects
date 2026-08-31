from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from backend.app.models.ingestion import IngestionJob, IngestionJobState
from backend.app.models.outbox import IngestionOutboxEvent, IngestionOutboxEventType
from backend.app.repositories.ingestion_jobs import IngestionJobRepository
from backend.app.repositories.ingestion_outbox import IngestionOutboxRepository

_SAFE_CODE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,79}$")


class IngestionOutboxError(Exception):
    """Base class for safe transactional-outbox failures."""


class IngestionOutboxNotFoundError(IngestionOutboxError):
    pass


class IngestionOutboxLeaseError(IngestionOutboxError):
    pass


class IngestionOutboxValidationError(IngestionOutboxError):
    pass


class IngestionOutboxStateMachine:
    """Mutate outbox delivery state inside a caller-owned transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._events = IngestionOutboxRepository(session)
        self._jobs = IngestionJobRepository(session)

    def enqueue_job_available(
        self,
        *,
        job: IngestionJob,
        dispatch_sequence: int,
        available_at: datetime,
        occurred_at: datetime,
    ) -> IngestionOutboxEvent:
        self._require_transaction()
        if dispatch_sequence <= 0:
            raise IngestionOutboxValidationError(
                "dispatch_sequence must be positive"
            )
        available_at = self._utc(available_at)
        occurred_at = self._utc(occurred_at)
        event_id = uuid4()
        event = IngestionOutboxEvent(
            id=event_id,
            workspace_id=job.workspace_id,
            job_id=job.id,
            dispatch_sequence=dispatch_sequence,
            event_type=IngestionOutboxEventType.JOB_AVAILABLE.value,
            schema_version=1,
            payload={
                "event_id": str(event_id),
                "event_type": IngestionOutboxEventType.JOB_AVAILABLE.value,
                "schema_version": 1,
                "job_id": str(job.id),
                "occurred_at": self._timestamp(occurred_at),
            },
            available_at=available_at,
        )
        self._events.add(event)
        return event

    def claim_due_events(
        self,
        *,
        lease_owner: str,
        now: datetime,
        lease_duration: timedelta,
        batch_size: int = 50,
    ) -> list[IngestionOutboxEvent]:
        self._require_transaction()
        normalized_owner = " ".join(lease_owner.split())
        if not normalized_owner or len(normalized_owner) > 200:
            raise IngestionOutboxValidationError(
                "lease_owner must contain 1-200 characters"
            )
        if lease_duration <= timedelta(0):
            raise IngestionOutboxValidationError("lease_duration must be positive")
        if not 1 <= batch_size <= 50:
            raise IngestionOutboxValidationError("batch_size must be between 1 and 50")
        return self._events.claim_due(
            lease_owner=normalized_owner,
            now=self._utc(now),
            lease_duration=lease_duration,
            batch_size=batch_size,
        )

    def mark_published(
        self,
        *,
        event_id: UUID,
        lease_owner: str,
        now: datetime,
    ) -> tuple[IngestionOutboxEvent, IngestionJob, bool]:
        self._require_transaction()
        now = self._utc(now)
        event_hint = self._events.get(event_id)
        if event_hint is None:
            raise IngestionOutboxNotFoundError
        job = self._jobs.get_job_by_id(event_hint.job_id, for_update=True)
        event = self._events.get(event_id, for_update=True)
        if job is None or event is None or event.job_id != job.id:
            raise IngestionOutboxNotFoundError
        if event.published_at is not None:
            return event, job, False
        self._require_active_publication(event, lease_owner=lease_owner, now=now)
        event.published_at = now
        event.lease_owner = None
        event.lease_expires_at = None
        event.publication_started_at = None

        current_sequence = job.attempt_count + 1
        if (
            event.dispatch_sequence == current_sequence
            and job.state == IngestionJobState.PENDING.value
        ):
            job.state = IngestionJobState.QUEUED.value
            job.revision += 1
        elif (
            event.dispatch_sequence == current_sequence
            and job.state == IngestionJobState.RETRY_SCHEDULED.value
            and job.next_attempt_at is not None
            and self._utc(job.next_attempt_at) <= now
        ):
            job.state = IngestionJobState.QUEUED.value
            job.next_attempt_at = None
            job.revision += 1
        self._session.flush()
        return event, job, True

    def start_publication(
        self,
        *,
        event_id: UUID,
        lease_owner: str,
        now: datetime,
    ) -> IngestionOutboxEvent:
        self._require_transaction()
        now = self._utc(now)
        event = self._events.get(event_id, for_update=True)
        if event is None:
            raise IngestionOutboxNotFoundError
        self._require_active_lease(event, lease_owner=lease_owner, now=now)
        if event.publication_started_at is None:
            event.publication_started_at = now
            event.publication_attempt_count += 1
            self._session.flush()
        return event

    def record_publication_failure(
        self,
        *,
        event_id: UUID,
        lease_owner: str,
        now: datetime,
        next_available_at: datetime,
        error_code: str,
    ) -> IngestionOutboxEvent:
        self._require_transaction()
        now = self._utc(now)
        next_available_at = self._utc(next_available_at)
        if next_available_at <= now:
            raise IngestionOutboxValidationError(
                "next_available_at must be in the future"
            )
        if _SAFE_CODE.fullmatch(error_code) is None:
            raise IngestionOutboxValidationError("error_code is invalid")
        event = self._events.get(event_id, for_update=True)
        if event is None:
            raise IngestionOutboxNotFoundError
        self._require_active_publication(event, lease_owner=lease_owner, now=now)
        event.available_at = next_available_at
        event.last_error_code = error_code
        event.last_error_at = now
        event.lease_owner = None
        event.lease_expires_at = None
        event.publication_started_at = None
        self._session.flush()
        return event

    def discard_unpublished_for_job(
        self,
        *,
        job_id: UUID,
        now: datetime,
        reason: str,
    ) -> None:
        self._require_transaction()
        if _SAFE_CODE.fullmatch(reason) is None:
            raise IngestionOutboxValidationError("discard reason is invalid")
        self._events.discard_unpublished_for_job(
            job_id=job_id,
            now=self._utc(now),
            reason=reason,
        )

    @staticmethod
    def _require_active_lease(
        event: IngestionOutboxEvent,
        *,
        lease_owner: str,
        now: datetime,
    ) -> None:
        if event.discarded_at is not None:
            raise IngestionOutboxLeaseError("Outbox event was discarded")
        if (
            event.lease_owner != " ".join(lease_owner.split())
            or event.lease_expires_at is None
            or IngestionOutboxStateMachine._utc(event.lease_expires_at) <= now
        ):
            raise IngestionOutboxLeaseError("Outbox lease ownership is stale")

    @staticmethod
    def _require_active_publication(
        event: IngestionOutboxEvent,
        *,
        lease_owner: str,
        now: datetime,
    ) -> None:
        IngestionOutboxStateMachine._require_active_lease(
            event,
            lease_owner=lease_owner,
            now=now,
        )
        if event.publication_started_at is None:
            raise IngestionOutboxLeaseError("Publication attempt was not started")

    def _require_transaction(self) -> None:
        if not self._session.in_transaction():
            raise RuntimeError("Outbox mutation requires an active transaction")

    @staticmethod
    def _timestamp(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
