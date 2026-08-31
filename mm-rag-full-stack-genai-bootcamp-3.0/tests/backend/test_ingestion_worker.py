from __future__ import annotations

import hashlib
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from backend.app.broker.messages import IngestionEventMessage
from backend.app.broker.rabbitmq import BrokerPublishError
from backend.app.db.base import Base
from backend.app.db.session import SessionFactory, create_database_engine, create_session_factory
from backend.app.models import (
    AuditEvent,
    Document,
    DocumentVersion,
    DocumentVersionStatus,
    IngestionAttempt,
    IngestionGeneration,
    IngestionGenerationState,
    IngestionJob,
    IngestionJobState,
    IngestionOutboxEvent,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
)
from backend.app.rag.indexing import IndexingRequest, IndexingResult, IndexingUnavailableError
from backend.app.services.ingestion_api import IngestionAPIService
from backend.app.services.ingestion_jobs import (
    IngestionJobNotFoundError,
    IngestionJobStateMachine,
)
from backend.app.services.ingestion_operations import IngestionOperationsService
from backend.app.services.ingestion_worker import DeliveryDisposition, IngestionWorkerService
from backend.app.storage.keys import original_object_key
from backend.app.storage.local import LocalFileStorage
from backend.app.workers.health import ProcessHealth
from backend.app.workers.outbox_dispatcher import OutboxDispatcher


@dataclass(frozen=True, slots=True)
class WorkerContext:
    factory: SessionFactory
    storage: LocalFileStorage
    user: User
    workspace_id: UUID
    document_id: UUID
    version_id: UUID
    job_id: UUID
    message: IngestionEventMessage


class SuccessfulIndexer:
    def index(self, request: IndexingRequest, *, progress=None) -> IndexingResult:
        assert request.generation_id is not None
        if progress is not None:
            progress("extracting", None, None, None)
            progress("chunking", 1, 1, "pages")
            progress("embedding", 2, 2, "chunks")
            progress("writing_outputs", 2, 2, "vectors")
            progress("validating", 2, 2, "vectors")
        return IndexingResult(chunk_count=2, vector_count=2)


class UnavailableIndexer:
    def index(self, request: IndexingRequest, *, progress=None) -> IndexingResult:
        raise IndexingUnavailableError("do not disclose dependency details")


class RecordingPublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[IngestionEventMessage] = []

    async def publish(self, message: IngestionEventMessage) -> None:
        if self.fail:
            raise BrokerPublishError("unconfirmed")
        self.messages.append(message)

    async def close(self) -> None:
        return None


@pytest.fixture
def worker_context(test_settings) -> Iterator[WorkerContext]:
    engine = create_database_engine(test_settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    storage = LocalFileStorage(test_settings.local_storage_root)
    user = User(id=uuid4(), external_subject="auth0|worker-owner")
    workspace_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    content = b"durable asynchronous ingestion"
    checksum = hashlib.sha256(content).hexdigest()
    fingerprint = "b" * 64
    object_key = original_object_key(
        workspace_id=workspace_id,
        document_id=document_id,
        version_id=version_id,
    )
    storage.put(object_key, content, media_type="text/plain")
    with factory.begin() as session:
        session.add(user)
        session.add(
            Workspace(
                id=workspace_id,
                name="Worker tests",
                created_by_user_id=user.id,
            )
        )
        session.add(
            WorkspaceMembership(
                workspace_id=workspace_id,
                user_id=user.id,
                role=WorkspaceRole.OWNER.value,
            )
        )
        session.add(
            Document(
                id=document_id,
                workspace_id=workspace_id,
                created_by_user_id=user.id,
                title="Report",
                original_filename="report.txt",
                media_type="text/plain",
            )
        )
        session.add(
            DocumentVersion(
                id=version_id,
                document_id=document_id,
                workspace_id=workspace_id,
                created_by_user_id=user.id,
                version_number=1,
                content_sha256=checksum,
                ingestion_fingerprint=fingerprint,
                object_key=object_key,
                byte_size=len(content),
                status=DocumentVersionStatus.UPLOADED.value,
            )
        )
        session.flush()
        job, _ = IngestionJobStateMachine(session).create_job(
            user=user,
            workspace_id=workspace_id,
            document_id=document_id,
            document_version_id=version_id,
            idempotency_key="worker-job-1",
            request_hash="a" * 64,
            pipeline_fingerprint=fingerprint,
            now=datetime.now(UTC),
        )
        event = session.scalar(
            select(IngestionOutboxEvent).where(IngestionOutboxEvent.job_id == job.id)
        )
        assert event is not None
        job_id = job.id
        message = IngestionEventMessage.model_validate(event.payload)
    try:
        yield WorkerContext(
            factory,
            storage,
            user,
            workspace_id,
            document_id,
            version_id,
            job_id,
            message,
        )
    finally:
        engine.dispose()


def _worker(test_settings, context: WorkerContext, indexer) -> IngestionWorkerService:
    return IngestionWorkerService(
        test_settings,
        context.factory,
        context.storage,
        context.storage,
        indexer,
        worker_id="worker-test-1",
    )


def test_worker_promotes_one_immutable_generation(test_settings, worker_context) -> None:
    worker = _worker(test_settings, worker_context, SuccessfulIndexer())
    assert worker.process(worker_context.message) == DeliveryDisposition.ACK

    with worker_context.factory() as session:
        job = session.get(IngestionJob, worker_context.job_id)
        version = session.get(DocumentVersion, worker_context.version_id)
        attempts = list(
            session.scalars(
                select(IngestionAttempt).where(
                    IngestionAttempt.job_id == worker_context.job_id
                )
            )
        )
        generation = session.scalar(
            select(IngestionGeneration).where(
                IngestionGeneration.job_id == worker_context.job_id
            )
        )
        assert job is not None and job.state == IngestionJobState.SUCCEEDED.value
        assert version is not None and version.status == DocumentVersionStatus.READY.value
        assert generation is not None
        assert generation.state == IngestionGenerationState.PROMOTED.value
        assert version.active_generation_id == generation.id
        assert generation.manifest_object_key is not None
        assert worker_context.storage.exists(generation.manifest_object_key)
        assert len(attempts) == 1
        succeeded_event = session.scalar(
            select(AuditEvent).where(AuditEvent.action == "ingestion.job_succeeded")
        )
        assert succeeded_event is not None
        assert succeeded_event.actor_kind == "service"
        assert succeeded_event.actor_user_id is None
        assert succeeded_event.service_actor == "ingestion-worker"


def test_membership_removal_blocks_job_read_but_not_workspace_owned_processing(
    test_settings, worker_context
) -> None:
    with worker_context.factory.begin() as session:
        membership = session.get(
            WorkspaceMembership,
            (worker_context.workspace_id, worker_context.user.id),
        )
        assert membership is not None
        session.delete(membership)

    with worker_context.factory() as session:
        with pytest.raises(IngestionJobNotFoundError):
            IngestionAPIService(session, worker_context.storage, test_settings).get_job(
                user=worker_context.user,
                workspace_id=worker_context.workspace_id,
                job_id=worker_context.job_id,
            )

    worker = _worker(test_settings, worker_context, SuccessfulIndexer())
    assert worker.process(worker_context.message) == DeliveryDisposition.ACK
    with worker_context.factory() as session:
        job = session.get(IngestionJob, worker_context.job_id)
        assert job is not None and job.state == IngestionJobState.SUCCEEDED.value
        terminal_revision = job.revision

    assert worker.process(worker_context.message) == DeliveryDisposition.ACK
    with worker_context.factory() as session:
        job = session.get(IngestionJob, worker_context.job_id)
        attempts = list(
            session.scalars(
                select(IngestionAttempt).where(
                    IngestionAttempt.job_id == worker_context.job_id
                )
            )
        )
        assert job is not None and job.revision == terminal_revision
        assert len(attempts) == 1


def test_worker_schedules_retry_and_hides_dependency_detail(
    test_settings, worker_context
) -> None:
    worker = _worker(test_settings, worker_context, UnavailableIndexer())
    assert worker.process(worker_context.message) == DeliveryDisposition.ACK

    with worker_context.factory() as session:
        job = session.get(IngestionJob, worker_context.job_id)
        version = session.get(DocumentVersion, worker_context.version_id)
        attempt = session.scalar(
            select(IngestionAttempt).where(
                IngestionAttempt.job_id == worker_context.job_id
            )
        )
        generation = session.scalar(
            select(IngestionGeneration).where(
                IngestionGeneration.job_id == worker_context.job_id
            )
        )
        events = list(
            session.scalars(
                select(IngestionOutboxEvent)
                .where(IngestionOutboxEvent.job_id == worker_context.job_id)
                .order_by(IngestionOutboxEvent.dispatch_sequence)
            )
        )
        assert job is not None and job.state == IngestionJobState.RETRY_SCHEDULED.value
        assert job.last_error_code == "dependency_unavailable"
        assert "disclose" not in (job.last_error_message or "")
        assert version is not None and version.status == DocumentVersionStatus.PROCESSING.value
        assert attempt is not None and attempt.state == "retryable_failure"
        assert generation is not None
        assert generation.state == IngestionGenerationState.ABANDONED.value
        assert [event.dispatch_sequence for event in events] == [1, 2]


def test_worker_observes_cancellation_before_promotion(
    test_settings, worker_context
) -> None:
    class CancellingIndexer:
        def index(self, request: IndexingRequest, *, progress=None) -> IndexingResult:
            with worker_context.factory.begin() as session:
                IngestionJobStateMachine(session).request_cancellation(
                    user=worker_context.user,
                    workspace_id=worker_context.workspace_id,
                    job_id=worker_context.job_id,
                    now=datetime.now(UTC),
                )
            assert progress is not None
            progress("validating", 1, 1, "vectors")
            return IndexingResult(1, 1)

    worker = _worker(test_settings, worker_context, CancellingIndexer())
    assert worker.process(worker_context.message) == DeliveryDisposition.ACK
    with worker_context.factory() as session:
        job = session.get(IngestionJob, worker_context.job_id)
        version = session.get(DocumentVersion, worker_context.version_id)
        generation = session.scalar(
            select(IngestionGeneration).where(
                IngestionGeneration.job_id == worker_context.job_id
            )
        )
        assert job is not None and job.state == IngestionJobState.CANCELLED.value
        assert version is not None and version.active_generation_id is None
        assert version.status == DocumentVersionStatus.UPLOADED.value
        assert generation is not None
        assert generation.state == IngestionGenerationState.ABANDONED.value


def test_document_tombstone_wins_the_final_worker_promotion_race(
    test_settings, worker_context
) -> None:
    class TombstoningIndexer:
        def index(self, request: IndexingRequest, *, progress=None) -> IndexingResult:
            now = datetime.now(UTC)
            with worker_context.factory.begin() as session:
                document = session.get(Document, worker_context.document_id)
                assert document is not None
                document.tombstoned_at = now
                document.tombstone_expires_at = now + timedelta(days=30)
                document.tombstoned_by_user_id = worker_context.user.id
            return IndexingResult(1, 1)

    worker = _worker(test_settings, worker_context, TombstoningIndexer())
    assert worker.process(worker_context.message) == DeliveryDisposition.ACK
    with worker_context.factory() as session:
        job = session.get(IngestionJob, worker_context.job_id)
        version = session.get(DocumentVersion, worker_context.version_id)
        generation = session.scalar(
            select(IngestionGeneration).where(
                IngestionGeneration.job_id == worker_context.job_id
            )
        )
        assert job is not None and job.state == IngestionJobState.CANCELLED.value
        assert version is not None and version.active_generation_id is None
        assert generation is not None
        assert generation.state == IngestionGenerationState.ABANDONED.value


@pytest.mark.asyncio
async def test_dispatcher_marks_job_queued_only_after_confirmed_publish(
    test_settings, worker_context
) -> None:
    publisher = RecordingPublisher()
    dispatcher = OutboxDispatcher(
        test_settings,
        worker_context.factory,
        publisher,
        dispatcher_id="dispatcher-test-1",
        health=ProcessHealth(test_settings.runtime_health_directory, "dispatcher"),
    )
    assert await dispatcher.run_once() == 1
    assert [message.job_id for message in publisher.messages] == [worker_context.job_id]
    with worker_context.factory() as session:
        job = session.get(IngestionJob, worker_context.job_id)
        event = session.scalar(
            select(IngestionOutboxEvent).where(
                IngestionOutboxEvent.job_id == worker_context.job_id
            )
        )
        assert job is not None and job.state == IngestionJobState.QUEUED.value
        assert event is not None and event.published_at is not None
        assert event.publication_attempt_count == 1
        assert event.last_error_code is None


@pytest.mark.asyncio
async def test_dispatcher_releases_failed_publication_for_safe_retry(
    test_settings, worker_context
) -> None:
    dispatcher = OutboxDispatcher(
        test_settings,
        worker_context.factory,
        RecordingPublisher(fail=True),
        dispatcher_id="dispatcher-test-2",
        health=ProcessHealth(test_settings.runtime_health_directory, "dispatcher"),
    )
    assert await dispatcher.run_once() == 1
    with worker_context.factory() as session:
        job = session.get(IngestionJob, worker_context.job_id)
        event = session.scalar(
            select(IngestionOutboxEvent).where(
                IngestionOutboxEvent.job_id == worker_context.job_id
            )
        )
        assert job is not None and job.state == IngestionJobState.PENDING.value
        assert event is not None and event.published_at is None
        assert event.lease_owner is None
        assert event.publication_started_at is None
        assert event.publication_attempt_count == 1
        assert event.last_error_code == "broker_publish_unconfirmed"
        available_at = event.available_at
        if available_at.tzinfo is None:
            available_at = available_at.replace(tzinfo=UTC)
        assert available_at > datetime.now(UTC)


def test_operations_alert_and_retention_never_delete_pending_events(
    test_settings, worker_context
) -> None:
    old = datetime.now(UTC) - timedelta(days=40)
    with worker_context.factory.begin() as session:
        event = session.scalar(
            select(IngestionOutboxEvent).where(
                IngestionOutboxEvent.job_id == worker_context.job_id
            )
        )
        assert event is not None
        event.created_at = old
        event.available_at = old
        event.publication_attempt_count = 10

    settings = test_settings.model_copy(
        update={"outbox_alert_age_seconds": 60, "outbox_alert_attempts": 10}
    )
    with worker_context.factory() as session:
        operations = IngestionOperationsService(session, settings)
        report = operations.report()
        assert report.alert
        assert report.due_unpublished_events == 1
        assert report.repeated_publication_failures == 1
        assert operations.terminal_outbox_retention_candidates() == 0

    with worker_context.factory.begin() as session:
        IngestionJobStateMachine(session).request_cancellation(
            user=worker_context.user,
            workspace_id=worker_context.workspace_id,
            job_id=worker_context.job_id,
            now=datetime.now(UTC),
        )
    with worker_context.factory.begin() as session:
        operations = IngestionOperationsService(session, settings)
        assert operations.terminal_outbox_retention_candidates() == 1
        assert operations.apply_terminal_outbox_retention() == 1
    with worker_context.factory() as session:
        assert session.get(IngestionJob, worker_context.job_id) is not None
        assert session.scalar(
            select(IngestionOutboxEvent).where(
                IngestionOutboxEvent.job_id == worker_context.job_id
            )
        ) is None
