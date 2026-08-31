from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from backend.app.db.base import Base
from backend.app.db.session import SessionFactory, create_database_engine, create_session_factory
from backend.app.models import (
    AuditEvent,
    Document,
    DocumentVersion,
    DocumentVersionStatus,
    IngestionAttempt,
    IngestionAttemptState,
    IngestionJob,
    IngestionJobState,
    IngestionOutboxEvent,
    IngestionProgressStage,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
)
from backend.app.services.ingestion_jobs import (
    IngestionAttemptOwnershipError,
    IngestionIdempotencyConflictError,
    IngestionInvalidTransitionError,
    IngestionJobNotFoundError,
    IngestionJobPermissionError,
    IngestionJobStateMachine,
    IngestionJobValidationError,
)
from backend.app.services.ingestion_outbox import (
    IngestionOutboxLeaseError,
    IngestionOutboxStateMachine,
)

REQUEST_HASH = "a" * 64
PIPELINE_FINGERPRINT = "b" * 64


@dataclass(frozen=True)
class JobContext:
    factory: SessionFactory
    workspace_id: UUID
    document_id: UUID
    version_id: UUID
    owner: User
    member: User
    other_member: User
    viewer: User
    outsider: User


@pytest.fixture
def job_context(test_settings) -> Iterator[JobContext]:
    engine = create_database_engine(test_settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    owner = User(id=uuid4(), external_subject="auth0|owner")
    member = User(id=uuid4(), external_subject="auth0|member")
    other_member = User(id=uuid4(), external_subject="auth0|other-member")
    viewer = User(id=uuid4(), external_subject="auth0|viewer")
    outsider = User(id=uuid4(), external_subject="auth0|outsider")
    workspace_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    with factory.begin() as session:
        session.add_all([owner, member, other_member, viewer, outsider])
        session.add(
            Workspace(
                id=workspace_id,
                name="Durable ingestion",
                created_by_user_id=owner.id,
            )
        )
        session.add_all(
            [
                WorkspaceMembership(
                    workspace_id=workspace_id,
                    user_id=owner.id,
                    role=WorkspaceRole.OWNER.value,
                ),
                WorkspaceMembership(
                    workspace_id=workspace_id,
                    user_id=member.id,
                    role=WorkspaceRole.MEMBER.value,
                ),
                WorkspaceMembership(
                    workspace_id=workspace_id,
                    user_id=other_member.id,
                    role=WorkspaceRole.MEMBER.value,
                ),
                WorkspaceMembership(
                    workspace_id=workspace_id,
                    user_id=viewer.id,
                    role=WorkspaceRole.VIEWER.value,
                ),
            ]
        )
        session.add(
            Document(
                id=document_id,
                workspace_id=workspace_id,
                created_by_user_id=owner.id,
                title="Quarterly report",
                original_filename="report.pdf",
                media_type="application/pdf",
            )
        )
        session.add(
            DocumentVersion(
                id=version_id,
                document_id=document_id,
                workspace_id=workspace_id,
                created_by_user_id=owner.id,
                version_number=1,
                content_sha256="c" * 64,
                ingestion_fingerprint=PIPELINE_FINGERPRINT,
                object_key=f"workspaces/{workspace_id}/documents/{document_id}/report.pdf",
                byte_size=100,
                status=DocumentVersionStatus.UPLOADED.value,
            )
        )
    try:
        yield JobContext(
            factory=factory,
            workspace_id=workspace_id,
            document_id=document_id,
            version_id=version_id,
            owner=owner,
            member=member,
            other_member=other_member,
            viewer=viewer,
            outsider=outsider,
        )
    finally:
        engine.dispose()


def _create_job(
    context: JobContext,
    *,
    user: User,
    key: str,
    predecessor_job_id: UUID | None = None,
    now: datetime | None = None,
) -> UUID:
    with context.factory.begin() as session:
        job, created = IngestionJobStateMachine(session).create_job(
            user=user,
            workspace_id=context.workspace_id,
            document_id=context.document_id,
            document_version_id=context.version_id,
            idempotency_key=key,
            request_hash=REQUEST_HASH,
            pipeline_fingerprint=PIPELINE_FINGERPRINT,
            predecessor_job_id=predecessor_job_id,
            now=now,
        )
        assert created
        return job.id


def test_job_creation_is_idempotent_and_authorized(job_context: JobContext) -> None:
    with job_context.factory.begin() as session:
        state_machine = IngestionJobStateMachine(session)
        first, created = state_machine.create_job(
            user=job_context.member,
            workspace_id=job_context.workspace_id,
            document_id=job_context.document_id,
            document_version_id=job_context.version_id,
            idempotency_key="upload-request-1",
            request_hash=REQUEST_HASH,
            pipeline_fingerprint=PIPELINE_FINGERPRINT,
        )
        replay, replay_created = state_machine.create_job(
            user=job_context.member,
            workspace_id=job_context.workspace_id,
            document_id=job_context.document_id,
            document_version_id=job_context.version_id,
            idempotency_key="upload-request-1",
            request_hash=REQUEST_HASH,
            pipeline_fingerprint=PIPELINE_FINGERPRINT,
        )
        assert created
        assert not replay_created
        assert replay.id == first.id
        assert first.state == IngestionJobState.PENDING.value
        assert first.max_attempts == 3
        assert first.attempt_count == 0
        session.flush()
        outbox_events = list(
            session.scalars(
                select(IngestionOutboxEvent).where(
                    IngestionOutboxEvent.job_id == first.id
                )
            )
        )
        assert len(outbox_events) == 1
        assert outbox_events[0].dispatch_sequence == 1
        assert outbox_events[0].payload == {
            "event_id": str(outbox_events[0].id),
            "event_type": "ingestion.job.available",
            "schema_version": 1,
            "job_id": str(first.id),
            "occurred_at": outbox_events[0].payload["occurred_at"],
        }
        assert "workspace_id" not in outbox_events[0].payload
        creation_events = list(
            session.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == "ingestion.job_created",
                    AuditEvent.resource_id == job_context.document_id,
                )
            )
        )
        assert len(creation_events) == 1

        with pytest.raises(IngestionIdempotencyConflictError):
            state_machine.create_job(
                user=job_context.member,
                workspace_id=job_context.workspace_id,
                document_id=job_context.document_id,
                document_version_id=job_context.version_id,
                idempotency_key="upload-request-1",
                request_hash="d" * 64,
                pipeline_fingerprint=PIPELINE_FINGERPRINT,
            )

        with pytest.raises(IngestionIdempotencyConflictError):
            state_machine.create_job(
                user=job_context.other_member,
                workspace_id=job_context.workspace_id,
                document_id=job_context.document_id,
                document_version_id=job_context.version_id,
                idempotency_key="upload-request-1",
                request_hash=REQUEST_HASH,
                pipeline_fingerprint=PIPELINE_FINGERPRINT,
            )

        with pytest.raises(IngestionJobValidationError):
            state_machine.create_job(
                user=job_context.member,
                workspace_id=job_context.workspace_id,
                document_id=job_context.document_id,
                document_version_id=job_context.version_id,
                idempotency_key="fingerprint-mismatch",
                request_hash=REQUEST_HASH,
                pipeline_fingerprint="e" * 64,
            )

    with job_context.factory.begin() as session:
        with pytest.raises(IngestionJobPermissionError):
            IngestionJobStateMachine(session).create_job(
                user=job_context.viewer,
                workspace_id=job_context.workspace_id,
                document_id=job_context.document_id,
                document_version_id=job_context.version_id,
                idempotency_key="viewer-request",
                request_hash=REQUEST_HASH,
                pipeline_fingerprint=PIPELINE_FINGERPRINT,
            )

    with job_context.factory.begin() as session:
        with pytest.raises(IngestionJobNotFoundError):
            IngestionJobStateMachine(session).create_job(
                user=job_context.outsider,
                workspace_id=job_context.workspace_id,
                document_id=job_context.document_id,
                document_version_id=job_context.version_id,
                idempotency_key="outsider-request",
                request_hash=REQUEST_HASH,
                pipeline_fingerprint=PIPELINE_FINGERPRINT,
            )


def test_queued_claim_and_heartbeat_use_fenced_attempt(job_context: JobContext) -> None:
    job_id = _create_job(job_context, user=job_context.member, key="claim-request")
    now = datetime(2026, 8, 30, 20, 0, tzinfo=UTC)
    with job_context.factory.begin() as session:
        state_machine = IngestionJobStateMachine(session)
        queued = state_machine.mark_queued(
            workspace_id=job_context.workspace_id, job_id=job_id
        )
        job, attempt = state_machine.claim_job(
            job_id=job_id,
            worker_id="worker-a",
            now=now,
            lease_duration=timedelta(minutes=5),
        )
        assert queued.state == IngestionJobState.RUNNING.value
        assert job.attempt_count == 1
        assert job.fencing_token == 1
        assert attempt.attempt_number == 1
        assert attempt.fencing_token == 1
        with pytest.raises(IngestionInvalidTransitionError):
            state_machine.claim_job(
                job_id=job_id,
                worker_id="worker-b",
                now=now,
                lease_duration=timedelta(minutes=5),
            )
        attempt_id = attempt.id

    with job_context.factory.begin() as session:
        state_machine = IngestionJobStateMachine(session)
        cancellation_requested = state_machine.heartbeat(
            job_id=job_id,
            attempt_id=attempt_id,
            fencing_token=1,
            now=now + timedelta(minutes=1),
            lease_duration=timedelta(minutes=5),
            stage=IngestionProgressStage.EMBEDDING,
            completed_units=4,
            total_units=10,
            unit="chunks",
        )
        assert not cancellation_requested
        state_machine.heartbeat(
            job_id=job_id,
            attempt_id=attempt_id,
            fencing_token=1,
            now=now + timedelta(minutes=2),
            lease_duration=timedelta(minutes=5),
        )

    with job_context.factory() as session:
        stored_attempt = session.get(IngestionAttempt, attempt_id)
        assert stored_attempt is not None
        assert stored_attempt.progress_stage == IngestionProgressStage.EMBEDDING.value
        assert stored_attempt.progress_completed == 4
        assert stored_attempt.progress_total == 10
        assert stored_attempt.progress_unit == "chunks"


def test_retry_budget_creates_three_append_only_attempts(job_context: JobContext) -> None:
    job_id = _create_job(job_context, user=job_context.member, key="retry-request")
    now = datetime(2026, 8, 30, 21, 0, tzinfo=UTC)
    attempt_ids: list[UUID] = []

    for attempt_number, retry_delay in ((1, 30), (2, 120), (3, None)):
        with job_context.factory.begin() as session:
            state_machine = IngestionJobStateMachine(session)
            job, attempt = state_machine.claim_job(
                job_id=job_id,
                worker_id=f"worker-{attempt_number}",
                now=now,
                lease_duration=timedelta(minutes=5),
            )
            assert job.attempt_count == attempt_number
            assert attempt.fencing_token == attempt_number
            attempt_ids.append(attempt.id)
            retry_at = (
                now + timedelta(seconds=retry_delay) if retry_delay is not None else None
            )
            if attempt_number == 1:
                with pytest.raises(IngestionJobValidationError):
                    state_machine.record_failure(
                        job_id=job_id,
                        attempt_id=attempt.id,
                        fencing_token=attempt.fencing_token,
                        now=now + timedelta(seconds=1),
                        retryable=True,
                        error_code="dependency_unavailable",
                        error_message="Dependency is temporarily unavailable.",
                        retry_at=now + timedelta(seconds=1),
                    )
                assert job.state == IngestionJobState.RUNNING.value
                assert attempt.state == IngestionAttemptState.RUNNING.value
            failed_job, failed_attempt = state_machine.record_failure(
                job_id=job_id,
                attempt_id=attempt.id,
                fencing_token=attempt.fencing_token,
                now=now + timedelta(seconds=1),
                retryable=True,
                error_code="dependency_unavailable",
                error_message="Dependency is temporarily unavailable.",
                retry_at=retry_at,
            )
            assert failed_attempt.state == IngestionAttemptState.RETRYABLE_FAILURE.value
            if retry_delay is None:
                assert failed_job.state == IngestionJobState.FAILED.value
                assert failed_job.last_error_code == "attempts_exhausted"
            else:
                assert failed_job.state == IngestionJobState.RETRY_SCHEDULED.value
                assert retry_at is not None
                with pytest.raises(IngestionInvalidTransitionError):
                    state_machine.claim_job(
                        job_id=job_id,
                        worker_id="too-early",
                        now=now + timedelta(seconds=2),
                        lease_duration=timedelta(minutes=5),
                    )
                now = retry_at

    with job_context.factory() as session:
        stored_job = session.get(IngestionJob, job_id)
        assert stored_job is not None
        assert stored_job.attempt_count == 3
        assert stored_job.completed_at is not None
        attempts = list(
            session.scalars(
                select(IngestionAttempt)
                .where(IngestionAttempt.job_id == job_id)
                .order_by(IngestionAttempt.attempt_number)
            )
        )
        assert [attempt.id for attempt in attempts] == attempt_ids
        assert [attempt.fencing_token for attempt in attempts] == [1, 2, 3]
        outbox_events = list(
            session.scalars(
                select(IngestionOutboxEvent)
                .where(IngestionOutboxEvent.job_id == job_id)
                .order_by(IngestionOutboxEvent.dispatch_sequence)
            )
        )
        assert [event.dispatch_sequence for event in outbox_events] == [1, 2, 3]
        assert all(event.discard_reason == "job_terminal" for event in outbox_events)


def test_member_cancellation_is_self_scoped_and_fenced(job_context: JobContext) -> None:
    job_id = _create_job(job_context, user=job_context.member, key="cancel-request")
    now = datetime(2026, 8, 30, 22, 0, tzinfo=UTC)
    with job_context.factory.begin() as session:
        with pytest.raises(IngestionJobPermissionError):
            IngestionJobStateMachine(session).request_cancellation(
                user=job_context.other_member,
                workspace_id=job_context.workspace_id,
                job_id=job_id,
                now=now,
            )

    with job_context.factory.begin() as session:
        cancelled = IngestionJobStateMachine(session).request_cancellation(
            user=job_context.member,
            workspace_id=job_context.workspace_id,
            job_id=job_id,
            now=now,
        )
        assert cancelled.state == IngestionJobState.CANCELLED.value
        repeated = IngestionJobStateMachine(session).request_cancellation(
            user=job_context.member,
            workspace_id=job_context.workspace_id,
            job_id=job_id,
            now=now + timedelta(seconds=1),
        )
        assert repeated.id == cancelled.id
        session.flush()
        cancellation_events = list(
            session.scalars(
                select(AuditEvent).where(
                    AuditEvent.action == "ingestion.job_cancel_requested",
                    AuditEvent.resource_id == job_context.document_id,
                )
            )
        )
        assert len(cancellation_events) == 1
        outbox_event = session.scalar(
            select(IngestionOutboxEvent).where(IngestionOutboxEvent.job_id == job_id)
        )
        assert outbox_event is not None
        assert outbox_event.discard_reason == "job_cancelled"

    running_job_id = _create_job(
        job_context, user=job_context.member, key="running-cancel-request"
    )
    with job_context.factory.begin() as session:
        state_machine = IngestionJobStateMachine(session)
        _, attempt = state_machine.claim_job(
            job_id=running_job_id,
            worker_id="worker-cancel",
            now=now,
            lease_duration=timedelta(minutes=5),
        )
        requested = state_machine.request_cancellation(
            user=job_context.owner,
            workspace_id=job_context.workspace_id,
            job_id=running_job_id,
            now=now + timedelta(seconds=10),
        )
        assert requested.state == IngestionJobState.RUNNING.value
        assert state_machine.heartbeat(
            job_id=running_job_id,
            attempt_id=attempt.id,
            fencing_token=attempt.fencing_token,
            now=now + timedelta(seconds=20),
            lease_duration=timedelta(minutes=5),
        )
        finished_job, finished_attempt = state_machine.finish_cancellation(
            job_id=running_job_id,
            attempt_id=attempt.id,
            fencing_token=attempt.fencing_token,
            now=now + timedelta(seconds=30),
        )
        assert finished_job.state == IngestionJobState.CANCELLED.value
        assert finished_attempt.state == IngestionAttemptState.CANCELLED.value

    with job_context.factory() as session:
        version = session.get(DocumentVersion, job_context.version_id)
        assert version is not None
        assert version.status == DocumentVersionStatus.UPLOADED.value


def test_job_and_initial_dispatch_intent_roll_back_together(
    job_context: JobContext,
) -> None:
    now = datetime(2026, 8, 31, 1, 0, tzinfo=UTC)
    with pytest.raises(RuntimeError, match="force rollback"):
        with job_context.factory.begin() as session:
            IngestionJobStateMachine(session).create_job(
                user=job_context.member,
                workspace_id=job_context.workspace_id,
                document_id=job_context.document_id,
                document_version_id=job_context.version_id,
                idempotency_key="rolled-back-request",
                request_hash=REQUEST_HASH,
                pipeline_fingerprint=PIPELINE_FINGERPRINT,
                now=now,
            )
            raise RuntimeError("force rollback")

    with job_context.factory() as session:
        assert session.scalar(
            select(IngestionJob).where(
                IngestionJob.idempotency_key == "rolled-back-request"
            )
        ) is None
        assert session.scalar(select(IngestionOutboxEvent)) is None


def test_outbox_claim_failure_backoff_and_ack_are_lease_safe(
    job_context: JobContext,
) -> None:
    now = datetime(2026, 8, 31, 2, 0, tzinfo=UTC)
    _create_job(
        job_context,
        user=job_context.member,
        key="outbox-publish-request",
        now=now,
    )

    with job_context.factory.begin() as session:
        outbox = IngestionOutboxStateMachine(session)
        claimed = outbox.claim_due_events(
            lease_owner="dispatcher-a:claim-1",
            now=now,
            lease_duration=timedelta(seconds=30),
        )
        assert len(claimed) == 1
        event_id = claimed[0].id
        assert claimed[0].publication_attempt_count == 0
        started = outbox.start_publication(
            event_id=event_id,
            lease_owner="dispatcher-a:claim-1",
            now=now,
        )
        assert started.publication_attempt_count == 1
        with pytest.raises(IngestionOutboxLeaseError):
            outbox.mark_published(
                event_id=event_id,
                lease_owner="dispatcher-b:claim-1",
                now=now + timedelta(seconds=1),
            )
        failed = outbox.record_publication_failure(
            event_id=event_id,
            lease_owner="dispatcher-a:claim-1",
            now=now + timedelta(seconds=1),
            next_available_at=now + timedelta(seconds=6),
            error_code="broker_unavailable",
        )
        assert failed.lease_owner is None
        assert failed.last_error_code == "broker_unavailable"

    with job_context.factory.begin() as session:
        outbox = IngestionOutboxStateMachine(session)
        assert outbox.claim_due_events(
            lease_owner="dispatcher-a:too-early",
            now=now + timedelta(seconds=5),
            lease_duration=timedelta(seconds=30),
        ) == []
        claimed = outbox.claim_due_events(
            lease_owner="dispatcher-b:claim-2",
            now=now + timedelta(seconds=6),
            lease_duration=timedelta(seconds=30),
        )
        assert [event.id for event in claimed] == [event_id]
        assert claimed[0].publication_attempt_count == 1
        started = outbox.start_publication(
            event_id=event_id,
            lease_owner="dispatcher-b:claim-2",
            now=now + timedelta(seconds=6),
        )
        assert started.publication_attempt_count == 2
        event, job, changed = outbox.mark_published(
            event_id=event_id,
            lease_owner="dispatcher-b:claim-2",
            now=now + timedelta(seconds=7),
        )
        assert changed
        assert event.published_at is not None
        assert job.state == IngestionJobState.QUEUED.value
        _, replayed_job, replayed = outbox.mark_published(
            event_id=event_id,
            lease_owner="stale-owner",
            now=now + timedelta(seconds=8),
        )
        assert not replayed
        assert replayed_job.state == IngestionJobState.QUEUED.value


def test_retry_dispatch_intents_publish_in_per_job_sequence(
    job_context: JobContext,
) -> None:
    now = datetime(2026, 8, 31, 3, 0, tzinfo=UTC)
    retry_at = now + timedelta(seconds=30)
    job_id = _create_job(
        job_context,
        user=job_context.member,
        key="ordered-retry-request",
        now=now,
    )
    with job_context.factory.begin() as session:
        state_machine = IngestionJobStateMachine(session)
        _, attempt = state_machine.claim_job(
            job_id=job_id,
            worker_id="worker-before-publish-ack",
            now=now,
            lease_duration=timedelta(minutes=1),
        )
        job, _ = state_machine.record_failure(
            job_id=job_id,
            attempt_id=attempt.id,
            fencing_token=attempt.fencing_token,
            now=now + timedelta(seconds=1),
            retryable=True,
            error_code="dependency_unavailable",
            error_message="Dependency is temporarily unavailable.",
            retry_at=retry_at,
        )
        assert job.state == IngestionJobState.RETRY_SCHEDULED.value

    with job_context.factory.begin() as session:
        outbox = IngestionOutboxStateMachine(session)
        first_claim = outbox.claim_due_events(
            lease_owner="dispatcher:sequence-1",
            now=retry_at,
            lease_duration=timedelta(seconds=30),
        )
        assert [event.dispatch_sequence for event in first_claim] == [1]
        outbox.start_publication(
            event_id=first_claim[0].id,
            lease_owner="dispatcher:sequence-1",
            now=retry_at,
        )
        _, job, _ = outbox.mark_published(
            event_id=first_claim[0].id,
            lease_owner="dispatcher:sequence-1",
            now=retry_at,
        )
        assert job.state == IngestionJobState.RETRY_SCHEDULED.value
        second_claim = outbox.claim_due_events(
            lease_owner="dispatcher:sequence-2",
            now=retry_at,
            lease_duration=timedelta(seconds=30),
        )
        assert [event.dispatch_sequence for event in second_claim] == [2]
        outbox.start_publication(
            event_id=second_claim[0].id,
            lease_owner="dispatcher:sequence-2",
            now=retry_at,
        )
        _, job, _ = outbox.mark_published(
            event_id=second_claim[0].id,
            lease_owner="dispatcher:sequence-2",
            now=retry_at,
        )
        assert job.state == IngestionJobState.QUEUED.value
        assert job.next_attempt_at is None


def test_expired_lease_is_recovered_and_stale_worker_is_rejected(
    job_context: JobContext,
) -> None:
    job_id = _create_job(job_context, user=job_context.member, key="expired-request")
    now = datetime(2026, 8, 30, 23, 0, tzinfo=UTC)
    with job_context.factory.begin() as session:
        _, attempt = IngestionJobStateMachine(session).claim_job(
            job_id=job_id,
            worker_id="worker-expiring",
            now=now,
            lease_duration=timedelta(minutes=1),
        )
        attempt_id = attempt.id

    with job_context.factory.begin() as session:
        state_machine = IngestionJobStateMachine(session)
        with pytest.raises(IngestionJobValidationError):
            state_machine.recover_expired_lease(
                job_id=job_id,
                now=now + timedelta(minutes=2),
                retry_at=now + timedelta(minutes=2),
            )
        running_attempt = session.get(IngestionAttempt, attempt_id)
        assert running_attempt is not None
        assert running_attempt.state == IngestionAttemptState.RUNNING.value
        recovered_job, recovered_attempt = state_machine.recover_expired_lease(
            job_id=job_id,
            now=now + timedelta(minutes=2),
            retry_at=now + timedelta(minutes=3),
        )
        assert recovered_job.state == IngestionJobState.RETRY_SCHEDULED.value
        assert recovered_attempt.state == IngestionAttemptState.LEASE_EXPIRED.value

    with job_context.factory.begin() as session:
        with pytest.raises(IngestionAttemptOwnershipError):
            IngestionJobStateMachine(session).heartbeat(
                job_id=job_id,
                attempt_id=attempt_id,
                fencing_token=1,
                now=now + timedelta(minutes=2),
                lease_duration=timedelta(minutes=1),
            )

    with job_context.factory.begin() as session:
        job, second_attempt = IngestionJobStateMachine(session).claim_job(
            job_id=job_id,
            worker_id="worker-recovery",
            now=now + timedelta(minutes=3),
            lease_duration=timedelta(minutes=5),
        )
        assert job.attempt_count == 2
        assert second_attempt.fencing_token == 2


def test_cancellation_wins_over_a_late_retryable_failure(
    job_context: JobContext,
) -> None:
    job_id = _create_job(job_context, user=job_context.member, key="cancel-failure-race")
    now = datetime(2026, 8, 31, 0, 0, tzinfo=UTC)
    with job_context.factory.begin() as session:
        state_machine = IngestionJobStateMachine(session)
        _, attempt = state_machine.claim_job(
            job_id=job_id,
            worker_id="worker-racing-cancel",
            now=now,
            lease_duration=timedelta(minutes=5),
        )
        state_machine.request_cancellation(
            user=job_context.member,
            workspace_id=job_context.workspace_id,
            job_id=job_id,
            now=now + timedelta(seconds=10),
        )
        job, finished_attempt = state_machine.record_failure(
            job_id=job_id,
            attempt_id=attempt.id,
            fencing_token=attempt.fencing_token,
            now=now + timedelta(seconds=20),
            retryable=True,
            error_code="dependency_unavailable",
            error_message="Dependency is temporarily unavailable.",
            retry_at=now + timedelta(seconds=50),
        )
        assert job.state == IngestionJobState.CANCELLED.value
        assert job.next_attempt_at is None
        assert finished_attempt.state == IngestionAttemptState.CANCELLED.value
