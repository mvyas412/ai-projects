from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.generation import IngestionGeneration
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

    def list_for_workspace(
        self,
        workspace_id: UUID,
        *,
        document_version_id: UUID | None = None,
        limit: int = 100,
    ) -> list[IngestionJob]:
        statement = select(IngestionJob).where(
            IngestionJob.workspace_id == workspace_id
        )
        if document_version_id is not None:
            statement = statement.where(
                IngestionJob.document_version_id == document_version_id
            )
        statement = statement.order_by(
            IngestionJob.created_at.desc(), IngestionJob.id.desc()
        ).limit(limit)
        return list(self._session.scalars(statement))

    def add_attempt(self, attempt: IngestionAttempt) -> None:
        self._session.add(attempt)
        self._session.flush()

    def add_generation(self, generation: IngestionGeneration) -> None:
        self._session.add(generation)
        self._session.flush()

    def get_generation(
        self, generation_id: UUID, *, for_update: bool = False
    ) -> IngestionGeneration | None:
        statement = select(IngestionGeneration).where(
            IngestionGeneration.id == generation_id
        )
        if for_update:
            statement = statement.with_for_update()
        return self._session.scalar(statement)

    def get_generation_for_attempt(
        self, attempt_id: UUID, *, for_update: bool = False
    ) -> IngestionGeneration | None:
        statement = select(IngestionGeneration).where(
            IngestionGeneration.attempt_id == attempt_id
        )
        if for_update:
            statement = statement.with_for_update()
        return self._session.scalar(statement)

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

    def latest_attempt(self, job_id: UUID) -> IngestionAttempt | None:
        return self._session.scalar(
            select(IngestionAttempt)
            .where(IngestionAttempt.job_id == job_id)
            .order_by(IngestionAttempt.attempt_number.desc())
            .limit(1)
        )

    def claim_expired_running_job_ids(
        self, *, now: datetime, limit: int
    ) -> list[UUID]:
        statement = (
            select(IngestionJob.id)
            .join(IngestionAttempt, IngestionAttempt.job_id == IngestionJob.id)
            .where(
                IngestionJob.state == "running",
                IngestionAttempt.state == IngestionAttemptState.RUNNING.value,
                IngestionAttempt.lease_expires_at <= now,
            )
            .order_by(IngestionAttempt.lease_expires_at, IngestionJob.id)
            .limit(limit)
            .with_for_update(skip_locked=True, of=IngestionJob)
        )
        return list(self._session.scalars(statement))
