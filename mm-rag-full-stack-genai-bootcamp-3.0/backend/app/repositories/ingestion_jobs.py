from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.ingestion import (
    IngestionAttempt,
    IngestionAttemptState,
    IngestionJob,
)


class IngestionJobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_job(self, job: IngestionJob) -> None:
        self._session.add(job)
        self._session.flush()

    def get_job(
        self,
        workspace_id: UUID,
        job_id: UUID,
        *,
        for_update: bool = False,
    ) -> IngestionJob | None:
        statement = select(IngestionJob).where(
            IngestionJob.workspace_id == workspace_id,
            IngestionJob.id == job_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self._session.scalar(statement)

    def get_job_by_id(
        self, job_id: UUID, *, for_update: bool = False
    ) -> IngestionJob | None:
        statement = select(IngestionJob).where(IngestionJob.id == job_id)
        if for_update:
            statement = statement.with_for_update()
        return self._session.scalar(statement)

    def get_by_idempotency_key(
        self,
        workspace_id: UUID,
        operation: str,
        idempotency_key: str,
    ) -> IngestionJob | None:
        return self._session.scalar(
            select(IngestionJob).where(
                IngestionJob.workspace_id == workspace_id,
                IngestionJob.operation == operation,
                IngestionJob.idempotency_key == idempotency_key,
            )
        )

    def add_attempt(self, attempt: IngestionAttempt) -> None:
        self._session.add(attempt)
        self._session.flush()

    def get_attempt(
        self,
        job_id: UUID,
        attempt_id: UUID,
        *,
        for_update: bool = False,
    ) -> IngestionAttempt | None:
        statement = select(IngestionAttempt).where(
            IngestionAttempt.job_id == job_id,
            IngestionAttempt.id == attempt_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self._session.scalar(statement)

    def get_running_attempt(
        self, job_id: UUID, *, for_update: bool = False
    ) -> IngestionAttempt | None:
        statement = select(IngestionAttempt).where(
            IngestionAttempt.job_id == job_id,
            IngestionAttempt.state == IngestionAttemptState.RUNNING.value,
        )
        if for_update:
            statement = statement.with_for_update()
        return self._session.scalar(statement)

    def list_attempts(self, job_id: UUID) -> list[IngestionAttempt]:
        statement = (
            select(IngestionAttempt)
            .where(IngestionAttempt.job_id == job_id)
            .order_by(IngestionAttempt.attempt_number)
        )
        return list(self._session.scalars(statement))
