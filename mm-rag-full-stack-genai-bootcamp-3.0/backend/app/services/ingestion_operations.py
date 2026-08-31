from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.models.generation import IngestionGeneration, IngestionGenerationState
from backend.app.models.ingestion import IngestionAttempt, IngestionAttemptState, IngestionJob
from backend.app.models.outbox import IngestionOutboxEvent
from backend.app.repositories.ingestion_outbox import IngestionOutboxRepository


@dataclass(frozen=True, slots=True)
class IngestionOperationsReport:
    generated_at: str
    jobs_by_state: dict[str, int]
    due_unpublished_events: int
    oldest_due_event_age_seconds: int | None
    repeated_publication_failures: int
    expired_running_attempts: int
    inactive_generations: int
    alert: bool

    def safe_dict(self) -> dict[str, object]:
        return asdict(self)


class IngestionOperationsService:
    """Internal, identifier-free backlog and recovery inspection."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def report(self, *, now: datetime | None = None) -> IngestionOperationsReport:
        now = _utc(now or datetime.now(UTC))
        states = {
            state: count
            for state, count in self._session.execute(
                select(IngestionJob.state, func.count(IngestionJob.id)).group_by(
                    IngestionJob.state
                )
            )
        }
        due_filter = (
            IngestionOutboxEvent.published_at.is_(None),
            IngestionOutboxEvent.discarded_at.is_(None),
            IngestionOutboxEvent.available_at <= now,
        )
        due_count = int(
            self._session.scalar(
                select(func.count(IngestionOutboxEvent.id)).where(*due_filter)
            )
            or 0
        )
        oldest = self._session.scalar(
            select(func.min(IngestionOutboxEvent.available_at)).where(*due_filter)
        )
        oldest_age = int((now - _utc(oldest)).total_seconds()) if oldest else None
        failed_publications = int(
            self._session.scalar(
                select(func.count(IngestionOutboxEvent.id)).where(
                    IngestionOutboxEvent.published_at.is_(None),
                    IngestionOutboxEvent.discarded_at.is_(None),
                    IngestionOutboxEvent.publication_attempt_count
                    >= self._settings.outbox_alert_attempts,
                )
            )
            or 0
        )
        expired_attempts = int(
            self._session.scalar(
                select(func.count(IngestionAttempt.id)).where(
                    IngestionAttempt.state == IngestionAttemptState.RUNNING.value,
                    IngestionAttempt.lease_expires_at <= now,
                )
            )
            or 0
        )
        inactive_generations = int(
            self._session.scalar(
                select(func.count(IngestionGeneration.id)).where(
                    IngestionGeneration.state.in_(
                        (
                            IngestionGenerationState.BUILDING.value,
                            IngestionGenerationState.ABANDONED.value,
                        )
                    )
                )
            )
            or 0
        )
        age_alert = (
            oldest_age is not None
            and oldest_age >= self._settings.outbox_alert_age_seconds
        )
        return IngestionOperationsReport(
            generated_at=now.isoformat(),
            jobs_by_state=states,
            due_unpublished_events=due_count,
            oldest_due_event_age_seconds=oldest_age,
            repeated_publication_failures=failed_publications,
            expired_running_attempts=expired_attempts,
            inactive_generations=inactive_generations,
            alert=age_alert or failed_publications > 0 or expired_attempts > 0,
        )

    def terminal_outbox_retention_candidates(
        self, *, now: datetime | None = None
    ) -> int:
        cutoff = _utc(now or datetime.now(UTC)) - timedelta(
            days=self._settings.outbox_terminal_retention_days
        )
        terminal_jobs = select(IngestionJob.id).where(
            IngestionJob.state.in_(("succeeded", "failed", "cancelled"))
        )
        return int(
            self._session.scalar(
                select(func.count(IngestionOutboxEvent.id)).where(
                    IngestionOutboxEvent.created_at < cutoff,
                    or_(
                        IngestionOutboxEvent.published_at.is_not(None),
                        IngestionOutboxEvent.discarded_at.is_not(None),
                    ),
                    IngestionOutboxEvent.job_id.in_(terminal_jobs),
                )
            )
            or 0
        )

    def apply_terminal_outbox_retention(
        self, *, now: datetime | None = None
    ) -> int:
        cutoff = _utc(now or datetime.now(UTC)) - timedelta(
            days=self._settings.outbox_terminal_retention_days
        )
        return IngestionOutboxRepository(self._session).delete_terminal_before(
            cutoff=cutoff
        )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
