from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models.document import DocumentVersion, DocumentVersionStatus
from backend.app.models.generation import IngestionGeneration, IngestionGenerationState
from backend.app.models.ingestion import (
    IngestionAttempt,
    IngestionAttemptState,
    IngestionJob,
    IngestionJobState,
    IngestionOperation,
    IngestionProgressStage,
)
from backend.app.models.user import User
from backend.app.models.workspace import WorkspaceRole
from backend.app.repositories.documents import DocumentRepository
from backend.app.repositories.ingestion_jobs import IngestionJobRepository
from backend.app.services.audit import record_audit_event
from backend.app.services.ingestion_outbox import IngestionOutboxStateMachine
from backend.app.services.policy import (
    PolicyAction,
    PolicyDeniedError,
    PolicyNotFoundError,
    PolicyService,
    resource_context,
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ERROR_CODE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,79}$")
_RUNNABLE_STATES = frozenset(
    {
        IngestionJobState.PENDING.value,
        IngestionJobState.QUEUED.value,
        IngestionJobState.RETRY_SCHEDULED.value,
    }
)
_TERMINAL_STATES = frozenset(
    {
        IngestionJobState.SUCCEEDED.value,
        IngestionJobState.FAILED.value,
        IngestionJobState.CANCELLED.value,
    }
)


class IngestionJobError(Exception):
    """Base class for safe durable-job failures."""


class IngestionJobNotFoundError(IngestionJobError):
    pass


class IngestionJobPermissionError(IngestionJobError):
    pass


class IngestionIdempotencyConflictError(IngestionJobError):
    pass


class IngestionInvalidTransitionError(IngestionJobError):
    pass


class IngestionAttemptOwnershipError(IngestionJobError):
    pass


class IngestionJobValidationError(IngestionJobError):
    pass


class IngestionJobStateMachine:
    """Mutate durable job state inside a caller-owned database transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._documents = DocumentRepository(session)
        self._jobs = IngestionJobRepository(session)
        self._outbox = IngestionOutboxStateMachine(session)
        self._policy = PolicyService(session)

    def create_job(
        self,
        *,
        user: User,
        workspace_id: UUID,
        document_id: UUID,
        document_version_id: UUID,
        idempotency_key: str,
        request_hash: str,
        pipeline_fingerprint: str,
        predecessor_job_id: UUID | None = None,
        now: datetime | None = None,
    ) -> tuple[IngestionJob, bool]:
        self._require_transaction()
        occurred_at = self._utc(now or datetime.now(UTC))
        normalized_key = self._validate_idempotency_key(idempotency_key)
        self._validate_hash("request_hash", request_hash)
        self._validate_hash("pipeline_fingerprint", pipeline_fingerprint)
        document = self._documents.get_document(workspace_id, document_id)
        version = self._documents.get_version(
            workspace_id, document_id, document_version_id
        )
        if document is None or version is None:
            raise IngestionJobNotFoundError
        role = self._require_document_action(
            user, document, PolicyAction.DOCUMENT_INDEX
        )
        if version.ingestion_fingerprint != pipeline_fingerprint:
            raise IngestionJobValidationError(
                "pipeline_fingerprint does not match the document version"
            )

        operation = IngestionOperation.INDEX_DOCUMENT_VERSION.value
        existing = self._jobs.get_by_idempotency_key(
            workspace_id, operation, normalized_key
        )
        if existing is not None:
            return self._resolve_replay(
                existing,
                document_id=document_id,
                document_version_id=document_version_id,
                request_hash=request_hash,
                pipeline_fingerprint=pipeline_fingerprint,
                requested_by_user_id=user.id,
            )

        predecessor = self._validate_predecessor(
            user=user,
            role=role,
            workspace_id=workspace_id,
            version=version,
            predecessor_job_id=predecessor_job_id,
            pipeline_fingerprint=pipeline_fingerprint,
        )
        job = IngestionJob(
            workspace_id=workspace_id,
            document_id=document_id,
            document_version_id=document_version_id,
            requested_by_user_id=user.id,
            predecessor_job_id=predecessor.id if predecessor is not None else None,
            operation=operation,
            pipeline_fingerprint=pipeline_fingerprint,
            idempotency_key=normalized_key,
            request_hash=request_hash,
            max_attempts=3,
        )
        try:
            with self._session.begin_nested():
                self._jobs.add_job(job)
        except IntegrityError:
            existing = self._jobs.get_by_idempotency_key(
                workspace_id, operation, normalized_key
            )
            if existing is None:
                raise
            return self._resolve_replay(
                existing,
                document_id=document_id,
                document_version_id=document_version_id,
                request_hash=request_hash,
                pipeline_fingerprint=pipeline_fingerprint,
                requested_by_user_id=user.id,
            )
        self._outbox.enqueue_job_available(
            job=job,
            dispatch_sequence=1,
            available_at=occurred_at,
            occurred_at=occurred_at,
        )
        record_audit_event(
            self._session,
            workspace_id=workspace_id,
            actor_user_id=user.id,
            action="ingestion.job_created",
            resource_type="document",
            resource_id=document_id,
            details={
                "job_id": str(job.id),
                "version_id": str(document_version_id),
                "predecessor_job_id": (
                    str(predecessor.id) if predecessor is not None else None
                ),
            },
        )
        return job, True

    def mark_queued(
        self,
        *,
        workspace_id: UUID,
        job_id: UUID,
    ) -> IngestionJob:
        self._require_transaction()
        job = self._get_workspace_job(workspace_id, job_id, for_update=True)
        if job.state == IngestionJobState.PENDING.value:
            job.state = IngestionJobState.QUEUED.value
            self._advance_revision(job)
        return job

    def claim_job(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        now: datetime,
        lease_duration: timedelta,
    ) -> tuple[IngestionJob, IngestionAttempt]:
        self._require_transaction()
        normalized_worker = " ".join(worker_id.split())
        if not normalized_worker or len(normalized_worker) > 200:
            raise IngestionJobValidationError("worker_id must contain 1-200 characters")
        if lease_duration <= timedelta(0):
            raise IngestionJobValidationError("lease_duration must be positive")
        now = self._utc(now)
        job = self._jobs.get_job_by_id(job_id, for_update=True)
        if job is None:
            raise IngestionJobNotFoundError
        if job.state not in _RUNNABLE_STATES:
            raise IngestionInvalidTransitionError("Job is not runnable")
        document = self._documents.get_document(
            job.workspace_id,
            job.document_id,
            include_archived=True,
            include_tombstoned=True,
        )
        if document is None:
            raise IngestionJobNotFoundError
        if document.tombstoned_at is not None and job.cancel_requested_at is None:
            job.cancel_requested_at = now
            job.cancel_requested_by_user_id = document.tombstoned_by_user_id

        if job.cancel_requested_at is not None:
            raise IngestionInvalidTransitionError("Job cancellation was requested")
        if (
            job.state == IngestionJobState.RETRY_SCHEDULED.value
            and job.next_attempt_at is not None
            and self._utc(job.next_attempt_at) > now
        ):
            raise IngestionInvalidTransitionError("Retry is not due")
        if self._jobs.get_running_attempt(job.id, for_update=True) is not None:
            raise IngestionInvalidTransitionError("Job already has an active attempt")
        if job.attempt_count >= job.max_attempts:
            raise IngestionInvalidTransitionError("Retry budget is exhausted")

        job.attempt_count += 1
        job.fencing_token += 1
        job.state = IngestionJobState.RUNNING.value
        job.next_attempt_at = None
        if job.first_started_at is None:
            job.first_started_at = now
        self._advance_revision(job)
        attempt = IngestionAttempt(
            job_id=job.id,
            workspace_id=job.workspace_id,
            attempt_number=job.attempt_count,
            fencing_token=job.fencing_token,
            worker_id=normalized_worker,
            lease_expires_at=now + lease_duration,
            last_heartbeat_at=now,
        )
        self._jobs.add_attempt(attempt)
        version = self._documents.get_version(
            job.workspace_id,
            job.document_id,
            job.document_version_id,
            for_update=True,
        )
        if version is None:
            raise IngestionJobNotFoundError
        if version.active_generation_id is None:
            version.status = DocumentVersionStatus.PROCESSING.value
            version.failure_reason = None
        return job, attempt

    def create_generation(
        self,
        *,
        job_id: UUID,
        attempt_id: UUID,
        fencing_token: int,
        now: datetime,
    ) -> IngestionGeneration:
        self._require_transaction()
        now = self._utc(now)
        job, attempt = self._active_attempt(
            job_id=job_id,
            attempt_id=attempt_id,
            fencing_token=fencing_token,
            now=now,
        )
        existing = self._jobs.get_generation_for_attempt(attempt.id, for_update=True)
        if existing is not None:
            return existing
        generation = IngestionGeneration(
            workspace_id=job.workspace_id,
            document_id=job.document_id,
            document_version_id=job.document_version_id,
            job_id=job.id,
            attempt_id=attempt.id,
            pipeline_fingerprint=job.pipeline_fingerprint,
        )
        self._jobs.add_generation(generation)
        return generation

    def heartbeat(
        self,
        *,
        job_id: UUID,
        attempt_id: UUID,
        fencing_token: int,
        now: datetime,
        lease_duration: timedelta,
        stage: IngestionProgressStage | None = None,
        completed_units: int | None = None,
        total_units: int | None = None,
        unit: str | None = None,
    ) -> bool:
        self._require_transaction()
        if lease_duration <= timedelta(0):
            raise IngestionJobValidationError("lease_duration must be positive")
        now = self._utc(now)
        job, attempt = self._active_attempt(
            job_id=job_id,
            attempt_id=attempt_id,
            fencing_token=fencing_token,
            now=now,
        )
        attempt.last_heartbeat_at = now
        attempt.lease_expires_at = now + lease_duration
        stage_changed = stage is not None and attempt.progress_stage != stage.value
        next_completed = (
            completed_units
            if completed_units is not None
            else (None if stage_changed else attempt.progress_completed)
        )
        next_total = (
            total_units
            if total_units is not None
            else (None if stage_changed else attempt.progress_total)
        )
        next_unit = (
            self._normalize_unit(unit)
            if unit is not None
            else (None if stage_changed else attempt.progress_unit)
        )
        self._validate_progress(next_completed, next_total, next_unit)
        if stage is not None:
            attempt.progress_stage = stage.value
        if completed_units is not None or stage_changed:
            attempt.progress_completed = next_completed
        if total_units is not None or stage_changed:
            attempt.progress_total = next_total
        if unit is not None or stage_changed:
            attempt.progress_unit = next_unit
        self._advance_revision(job)
        return job.cancel_requested_at is not None

    def request_cancellation(
        self,
        *,
        user: User,
        workspace_id: UUID,
        job_id: UUID,
        now: datetime,
    ) -> IngestionJob:
        self._require_transaction()
        now = self._utc(now)
        job = self._get_workspace_job(workspace_id, job_id, for_update=True)
        self._require_job_action(user, job, PolicyAction.JOB_CANCEL)
        if job.state == IngestionJobState.CANCELLED.value:
            return job
        if job.state in {IngestionJobState.SUCCEEDED.value, IngestionJobState.FAILED.value}:
            raise IngestionInvalidTransitionError("Terminal job cannot be cancelled")
        if job.cancel_requested_at is not None:
            return job
        job.cancel_requested_at = now
        job.cancel_requested_by_user_id = user.id
        if job.state != IngestionJobState.RUNNING.value:
            job.state = IngestionJobState.CANCELLED.value
            job.next_attempt_at = None
            job.completed_at = now
            self._project_version(job, cancelled=True)
        self._outbox.discard_unpublished_for_job(
            job_id=job.id,
            now=now,
            reason="job_cancelled",
        )
        record_audit_event(
            self._session,
            workspace_id=workspace_id,
            actor_user_id=user.id,
            action="ingestion.job_cancel_requested",
            resource_type="document",
            resource_id=job.document_id,
            details={"job_id": str(job.id), "version_id": str(job.document_version_id)},
        )
        self._advance_revision(job)
        return job

    def finish_cancellation(
        self,
        *,
        job_id: UUID,
        attempt_id: UUID,
        fencing_token: int,
        now: datetime,
    ) -> tuple[IngestionJob, IngestionAttempt]:
        self._require_transaction()
        now = self._utc(now)
        job, attempt = self._active_attempt(
            job_id=job_id,
            attempt_id=attempt_id,
            fencing_token=fencing_token,
            now=now,
        )
        if job.cancel_requested_at is None:
            raise IngestionInvalidTransitionError("Cancellation was not requested")
        self._finish_attempt(attempt, IngestionAttemptState.CANCELLED, now)
        job.state = IngestionJobState.CANCELLED.value
        job.completed_at = now
        job.next_attempt_at = None
        self._outbox.discard_unpublished_for_job(
            job_id=job.id,
            now=now,
            reason="job_cancelled",
        )
        self._abandon_generation(attempt.id, now)
        self._project_version(job, cancelled=True)
        self._advance_revision(job)
        return job, attempt

    def complete_success(
        self,
        *,
        job_id: UUID,
        attempt_id: UUID,
        fencing_token: int,
        generation_id: UUID,
        manifest: dict[str, object],
        manifest_object_key: str,
        manifest_sha256: str,
        chunk_count: int,
        vector_count: int,
        now: datetime,
    ) -> tuple[IngestionJob, IngestionAttempt, IngestionGeneration, bool]:
        self._require_transaction()
        now = self._utc(now)
        job, attempt = self._active_attempt(
            job_id=job_id,
            attempt_id=attempt_id,
            fencing_token=fencing_token,
            now=now,
        )
        generation = self._jobs.get_generation(generation_id, for_update=True)
        if (
            generation is None
            or generation.job_id != job.id
            or generation.attempt_id != attempt.id
            or generation.workspace_id != job.workspace_id
            or generation.document_version_id != job.document_version_id
        ):
            raise IngestionAttemptOwnershipError("Generation ownership is invalid")
        if generation.state != IngestionGenerationState.BUILDING.value:
            raise IngestionInvalidTransitionError("Generation is not buildable")
        if _HEX64.fullmatch(manifest_sha256) is None:
            raise IngestionJobValidationError("manifest_sha256 is invalid")
        if not manifest_object_key or len(manifest_object_key) > 1024:
            raise IngestionJobValidationError("manifest_object_key is invalid")
        if chunk_count <= 0 or vector_count <= 0:
            raise IngestionJobValidationError("A promoted generation must contain vectors")

        document = self._documents.get_document(
            job.workspace_id,
            job.document_id,
            include_archived=True,
            include_tombstoned=True,
        )
        if document is None:
            raise IngestionJobNotFoundError
        if document.tombstoned_at is not None and job.cancel_requested_at is None:
            job.cancel_requested_at = now
            job.cancel_requested_by_user_id = document.tombstoned_by_user_id

        if job.cancel_requested_at is not None:
            self._finish_attempt(attempt, IngestionAttemptState.CANCELLED, now)
            generation.state = IngestionGenerationState.ABANDONED.value
            generation.abandoned_at = now
            job.state = IngestionJobState.CANCELLED.value
            job.completed_at = now
            job.next_attempt_at = None
            self._project_version(job, cancelled=True)
            self._advance_revision(job)
            return job, attempt, generation, False

        version = self._documents.get_version(
            job.workspace_id,
            job.document_id,
            job.document_version_id,
            for_update=True,
        )
        if version is None:
            raise IngestionJobNotFoundError
        generation.manifest = manifest
        generation.manifest_object_key = manifest_object_key
        generation.manifest_sha256 = manifest_sha256
        generation.chunk_count = chunk_count
        generation.vector_count = vector_count
        generation.validated_at = now
        generation.promoted_at = now
        generation.state = IngestionGenerationState.PROMOTED.value
        version.active_generation_id = generation.id
        version.active_generation_promoted_at = now
        version.status = DocumentVersionStatus.READY.value
        version.failure_reason = None
        self._finish_attempt(attempt, IngestionAttemptState.SUCCEEDED, now)
        job.state = IngestionJobState.SUCCEEDED.value
        job.completed_at = now
        job.next_attempt_at = None
        job.last_error_code = None
        job.last_error_message = None
        record_audit_event(
            self._session,
            workspace_id=job.workspace_id,
            service_actor="ingestion-worker",
            action="ingestion.job_succeeded",
            resource_type="document",
            resource_id=job.document_id,
            correlation_id=str(job.id),
            details={
                "job_id": str(job.id),
                "version_id": str(job.document_version_id),
                "chunk_count": chunk_count,
            },
        )
        self._advance_revision(job)
        return job, attempt, generation, True

    def record_failure(
        self,
        *,
        job_id: UUID,
        attempt_id: UUID,
        fencing_token: int,
        now: datetime,
        retryable: bool,
        error_code: str,
        error_message: str,
        retry_at: datetime | None = None,
    ) -> tuple[IngestionJob, IngestionAttempt]:
        self._require_transaction()
        now = self._utc(now)
        job, attempt = self._active_attempt(
            job_id=job_id,
            attempt_id=attempt_id,
            fencing_token=fencing_token,
            now=now,
        )
        if job.cancel_requested_at is not None:
            self._finish_attempt(attempt, IngestionAttemptState.CANCELLED, now)
            job.state = IngestionJobState.CANCELLED.value
            job.completed_at = now
            job.next_attempt_at = None
            self._outbox.discard_unpublished_for_job(
                job_id=job.id,
                now=now,
                reason="job_cancelled",
            )
            self._abandon_generation(attempt.id, now)
            self._project_version(job, cancelled=True)
            self._advance_revision(job)
            return job, attempt

        code, message = self._safe_error(error_code, error_message)
        scheduled_retry_at: datetime | None = None
        if retryable and job.attempt_count < job.max_attempts:
            if retry_at is None or self._utc(retry_at) <= now:
                raise IngestionJobValidationError("retry_at must be in the future")
            scheduled_retry_at = self._utc(retry_at)

        attempt.error_code = code
        attempt.error_message = message
        if retryable:
            self._finish_attempt(attempt, IngestionAttemptState.RETRYABLE_FAILURE, now)
        else:
            self._finish_attempt(attempt, IngestionAttemptState.PERMANENT_FAILURE, now)

        if scheduled_retry_at is not None:
            job.state = IngestionJobState.RETRY_SCHEDULED.value
            job.next_attempt_at = scheduled_retry_at
            job.last_error_code = code
            job.last_error_message = message
            self._outbox.enqueue_job_available(
                job=job,
                dispatch_sequence=job.attempt_count + 1,
                available_at=scheduled_retry_at,
                occurred_at=now,
            )
        else:
            job.state = IngestionJobState.FAILED.value
            job.completed_at = now
            job.next_attempt_at = None
            if retryable:
                job.last_error_code = "attempts_exhausted"
                job.last_error_message = "Ingestion failed after the retry limit."
            else:
                job.last_error_code = code
                job.last_error_message = message
            self._outbox.discard_unpublished_for_job(
                job_id=job.id,
                now=now,
                reason="job_terminal",
            )
        self._abandon_generation(attempt.id, now)
        self._project_version(job, terminal_failure=scheduled_retry_at is None)
        self._advance_revision(job)
        return job, attempt

    def recover_expired_lease(
        self,
        *,
        job_id: UUID,
        now: datetime,
        retry_at: datetime | None,
    ) -> tuple[IngestionJob, IngestionAttempt]:
        self._require_transaction()
        now = self._utc(now)
        job = self._jobs.get_job_by_id(job_id, for_update=True)
        if job is None:
            raise IngestionJobNotFoundError
        if job.state != IngestionJobState.RUNNING.value:
            raise IngestionInvalidTransitionError("Job is not running")
        attempt = self._jobs.get_running_attempt(job.id, for_update=True)
        if attempt is None:
            raise IngestionAttemptOwnershipError("Running attempt is missing")
        if self._utc(attempt.lease_expires_at) > now:
            raise IngestionInvalidTransitionError("Lease has not expired")

        scheduled_retry_at: datetime | None = None
        if job.cancel_requested_at is None and job.attempt_count < job.max_attempts:
            if retry_at is None or self._utc(retry_at) <= now:
                raise IngestionJobValidationError("retry_at must be in the future")
            scheduled_retry_at = self._utc(retry_at)

        attempt.error_code = "lease_expired"
        attempt.error_message = "The worker lease expired before completion."
        self._finish_attempt(attempt, IngestionAttemptState.LEASE_EXPIRED, now)
        if job.cancel_requested_at is not None:
            job.state = IngestionJobState.CANCELLED.value
            job.completed_at = now
            job.next_attempt_at = None
            self._outbox.discard_unpublished_for_job(
                job_id=job.id,
                now=now,
                reason="job_cancelled",
            )
        elif scheduled_retry_at is not None:
            job.state = IngestionJobState.RETRY_SCHEDULED.value
            job.next_attempt_at = scheduled_retry_at
            job.last_error_code = attempt.error_code
            job.last_error_message = attempt.error_message
            self._outbox.enqueue_job_available(
                job=job,
                dispatch_sequence=job.attempt_count + 1,
                available_at=scheduled_retry_at,
                occurred_at=now,
            )
        else:
            job.state = IngestionJobState.FAILED.value
            job.completed_at = now
            job.next_attempt_at = None
            job.last_error_code = "attempts_exhausted"
            job.last_error_message = "Ingestion failed after the retry limit."
            self._outbox.discard_unpublished_for_job(
                job_id=job.id,
                now=now,
                reason="job_terminal",
            )
        self._abandon_generation(attempt.id, now)
        self._project_version(
            job,
            cancelled=job.state == IngestionJobState.CANCELLED.value,
            terminal_failure=job.state == IngestionJobState.FAILED.value,
        )
        self._advance_revision(job)
        return job, attempt

    def recover_expired_jobs(
        self, *, now: datetime, limit: int = 25
    ) -> list[UUID]:
        self._require_transaction()
        if not 1 <= limit <= 100:
            raise IngestionJobValidationError("Recovery limit must be between 1 and 100")
        now = self._utc(now)
        recovered: list[UUID] = []
        for job_id in self._jobs.claim_expired_running_job_ids(now=now, limit=limit):
            job = self._jobs.get_job_by_id(job_id, for_update=True)
            if job is None:
                continue
            self.recover_expired_lease(
                job_id=job.id,
                now=now,
                retry_at=now + retry_delay(job.attempt_count, job.id),
            )
            recovered.append(job.id)
        return recovered

    def _resolve_replay(
        self,
        existing: IngestionJob,
        *,
        document_id: UUID,
        document_version_id: UUID,
        request_hash: str,
        pipeline_fingerprint: str,
        requested_by_user_id: UUID,
    ) -> tuple[IngestionJob, bool]:
        if (
            existing.document_id != document_id
            or existing.document_version_id != document_version_id
            or existing.request_hash != request_hash
            or existing.pipeline_fingerprint != pipeline_fingerprint
            or existing.requested_by_user_id != requested_by_user_id
        ):
            raise IngestionIdempotencyConflictError(
                "Idempotency key was already used for a different request"
            )
        return existing, False

    def _validate_predecessor(
        self,
        *,
        user: User,
        role: WorkspaceRole,
        workspace_id: UUID,
        version: DocumentVersion,
        predecessor_job_id: UUID | None,
        pipeline_fingerprint: str,
    ) -> IngestionJob | None:
        if predecessor_job_id is None:
            return None
        predecessor = self._jobs.get_job(workspace_id, predecessor_job_id, for_update=True)
        if predecessor is None:
            raise IngestionJobNotFoundError
        if predecessor.state not in _TERMINAL_STATES:
            raise IngestionInvalidTransitionError("Predecessor job is not terminal")
        if (
            predecessor.document_id != version.document_id
            or predecessor.document_version_id != version.id
            or predecessor.pipeline_fingerprint != pipeline_fingerprint
        ):
            raise IngestionJobValidationError("Predecessor does not match the document version")
        document = self._documents.get_document(workspace_id, predecessor.document_id)
        if document is None:
            raise IngestionJobNotFoundError
        self._require_job_action(user, predecessor, PolicyAction.JOB_RETRY)
        if (
            predecessor.state == IngestionJobState.SUCCEEDED.value
            and role not in {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}
        ):
            raise IngestionJobPermissionError
        return predecessor

    def _require_document_action(
        self, user: User, document, action: PolicyAction
    ) -> WorkspaceRole:
        try:
            decision = self._policy.require(
                user=user,
                workspace_id=document.workspace_id,
                action=action,
                resource=resource_context(document),
            )
        except PolicyNotFoundError as exc:
            raise IngestionJobNotFoundError from exc
        except PolicyDeniedError as exc:
            raise IngestionJobPermissionError from exc
        if decision.role is None:
            raise IngestionJobPermissionError
        return decision.role

    def _require_job_action(
        self, user: User, job: IngestionJob, action: PolicyAction
    ) -> None:
        document = self._documents.get_document(job.workspace_id, job.document_id)
        if document is None:
            raise IngestionJobNotFoundError
        try:
            self._policy.require(
                user=user,
                workspace_id=job.workspace_id,
                action=action,
                resource=resource_context(document),
                requester_user_id=job.requested_by_user_id,
            )
        except PolicyNotFoundError as exc:
            raise IngestionJobNotFoundError from exc
        except PolicyDeniedError as exc:
            raise IngestionJobPermissionError from exc

    def _get_workspace_job(
        self, workspace_id: UUID, job_id: UUID, *, for_update: bool
    ) -> IngestionJob:
        job = self._jobs.get_job(workspace_id, job_id, for_update=for_update)
        if job is None:
            raise IngestionJobNotFoundError
        return job

    def _active_attempt(
        self,
        *,
        job_id: UUID,
        attempt_id: UUID,
        fencing_token: int,
        now: datetime,
    ) -> tuple[IngestionJob, IngestionAttempt]:
        job = self._jobs.get_job_by_id(job_id, for_update=True)
        attempt = self._jobs.get_attempt(job_id, attempt_id, for_update=True)
        if job is None or attempt is None:
            raise IngestionAttemptOwnershipError("Attempt ownership is invalid")
        if (
            job.state != IngestionJobState.RUNNING.value
            or attempt.state != IngestionAttemptState.RUNNING.value
            or job.fencing_token != fencing_token
            or attempt.fencing_token != fencing_token
        ):
            raise IngestionAttemptOwnershipError("Attempt ownership is stale")
        if self._utc(attempt.lease_expires_at) <= now:
            raise IngestionAttemptOwnershipError("Attempt lease has expired")
        return job, attempt

    def _abandon_generation(self, attempt_id: UUID, now: datetime) -> None:
        generation = self._jobs.get_generation_for_attempt(attempt_id, for_update=True)
        if generation is not None and generation.state in {
            IngestionGenerationState.BUILDING.value,
            IngestionGenerationState.VALIDATED.value,
        }:
            generation.state = IngestionGenerationState.ABANDONED.value
            generation.abandoned_at = now

    def _project_version(
        self,
        job: IngestionJob,
        *,
        cancelled: bool = False,
        terminal_failure: bool = False,
    ) -> None:
        version = self._documents.get_version(
            job.workspace_id,
            job.document_id,
            job.document_version_id,
            for_update=True,
        )
        if version is None:
            raise IngestionJobNotFoundError
        if version.active_generation_id is not None:
            version.status = DocumentVersionStatus.READY.value
            version.failure_reason = None
        elif cancelled:
            version.status = DocumentVersionStatus.UPLOADED.value
            version.failure_reason = None
        elif terminal_failure:
            version.status = DocumentVersionStatus.FAILED.value
            version.failure_reason = job.last_error_message
        else:
            version.status = DocumentVersionStatus.PROCESSING.value

    @staticmethod
    def _finish_attempt(
        attempt: IngestionAttempt,
        state: IngestionAttemptState,
        now: datetime,
    ) -> None:
        attempt.state = state.value
        attempt.finished_at = now

    @staticmethod
    def _advance_revision(job: IngestionJob) -> None:
        job.revision += 1

    def _require_transaction(self) -> None:
        if not self._session.in_transaction():
            raise RuntimeError("Ingestion job mutation requires an active transaction")

    @staticmethod
    def _validate_idempotency_key(value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 255:
            raise IngestionJobValidationError(
                "idempotency_key must contain 1-255 characters"
            )
        return normalized

    @staticmethod
    def _validate_hash(field: str, value: str) -> None:
        if _HEX64.fullmatch(value) is None:
            raise IngestionJobValidationError(f"{field} must be a lowercase SHA-256 value")

    @staticmethod
    def _safe_error(code: str, message: str) -> tuple[str, str]:
        if _ERROR_CODE.fullmatch(code) is None:
            raise IngestionJobValidationError("error_code is invalid")
        safe_message = " ".join(message.split())
        if not safe_message:
            raise IngestionJobValidationError("error_message must not be empty")
        return code, safe_message[:500]

    @staticmethod
    def _validate_progress(
        completed_units: int | None,
        total_units: int | None,
        unit: str | None,
    ) -> None:
        if completed_units is not None and completed_units < 0:
            raise IngestionJobValidationError("completed_units must not be negative")
        if total_units is not None and total_units <= 0:
            raise IngestionJobValidationError("total_units must be positive")
        if (
            completed_units is not None
            and total_units is not None
            and completed_units > total_units
        ):
            raise IngestionJobValidationError("completed_units exceeds total_units")
        if unit is not None and not (1 <= len(" ".join(unit.split())) <= 24):
            raise IngestionJobValidationError("unit must contain 1-24 characters")

    @staticmethod
    def _normalize_unit(unit: str | None) -> str | None:
        return " ".join(unit.split()) if unit is not None else None

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def retry_delay(attempt_number: int, job_id: UUID) -> timedelta:
    """Return the accepted two-step execution retry policy with stable bounded jitter."""

    base = 30 if attempt_number <= 1 else 120
    jitter = 0.8 + ((job_id.int % 401) / 1000)
    return timedelta(seconds=base * jitter)
