from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select

from backend.app.core.config import get_settings
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.models import (
    AuditEvent,
    Document,
    DocumentVersion,
    DocumentVersionStatus,
    IngestionAttempt,
    IngestionJob,
    IngestionOutboxEvent,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
)
from backend.app.services.ingestion_jobs import IngestionJobStateMachine
from backend.app.services.ingestion_outbox import IngestionOutboxStateMachine


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("MM_RAG_RUN_INTEGRATION_TESTS") != "1",
    reason="Set MM_RAG_RUN_INTEGRATION_TESTS=1 with Compose services running",
)
def test_postgres_skip_locked_prevents_overlapping_outbox_leases() -> None:
    engine = create_database_engine(get_settings())
    factory = create_session_factory(engine)
    user_id = uuid4()
    workspace_id = uuid4()
    document_id = uuid4()
    version_id = uuid4()
    now = datetime.now(UTC)
    pipeline_fingerprint = "b" * 64

    try:
        with factory.begin() as session:
            user = User(id=user_id, external_subject=f"test|outbox-{user_id}")
            session.add(user)
            session.flush()
            session.add(
                Workspace(
                    id=workspace_id,
                    name="Outbox integration",
                    created_by_user_id=user_id,
                )
            )
            session.flush()
            session.add(
                WorkspaceMembership(
                    workspace_id=workspace_id,
                    user_id=user_id,
                    role=WorkspaceRole.OWNER.value,
                )
            )
            session.flush()
            session.add(
                Document(
                    id=document_id,
                    workspace_id=workspace_id,
                    created_by_user_id=user_id,
                    title="Outbox integration document",
                    original_filename="integration.pdf",
                    media_type="application/pdf",
                )
            )
            session.flush()
            session.add(
                DocumentVersion(
                    id=version_id,
                    document_id=document_id,
                    workspace_id=workspace_id,
                    created_by_user_id=user_id,
                    version_number=1,
                    content_sha256="c" * 64,
                    ingestion_fingerprint=pipeline_fingerprint,
                    object_key=f"workspaces/{workspace_id}/documents/{document_id}/original",
                    byte_size=100,
                    status=DocumentVersionStatus.UPLOADED.value,
                )
            )
            session.flush()
            job, created = IngestionJobStateMachine(session).create_job(
                user=user,
                workspace_id=workspace_id,
                document_id=document_id,
                document_version_id=version_id,
                idempotency_key=f"outbox-integration-{uuid4()}",
                request_hash="a" * 64,
                pipeline_fingerprint=pipeline_fingerprint,
                now=now,
            )
            assert created
            job_id = job.id

        barrier = Barrier(2)

        def create_same_request() -> tuple[UUID, bool]:
            with factory.begin() as session:
                user = session.get(User, user_id)
                assert user is not None
                barrier.wait(timeout=5)
                concurrent_job, created = IngestionJobStateMachine(session).create_job(
                    user=user,
                    workspace_id=workspace_id,
                    document_id=document_id,
                    document_version_id=version_id,
                    idempotency_key="outbox-concurrent-replay",
                    request_hash="d" * 64,
                    pipeline_fingerprint=pipeline_fingerprint,
                    now=now,
                )
                return concurrent_job.id, created

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: create_same_request(), range(2)))
        concurrent_job_ids = {result[0] for result in results}
        assert len(concurrent_job_ids) == 1
        assert sorted(result[1] for result in results) == [False, True]
        concurrent_job_id = next(iter(concurrent_job_ids))
        with factory() as session:
            assert session.scalar(
                select(func.count())
                .select_from(IngestionOutboxEvent)
                .where(IngestionOutboxEvent.job_id == concurrent_job_id)
            ) == 1
        with factory.begin() as session:
            IngestionOutboxStateMachine(session).discard_unpublished_for_job(
                job_id=concurrent_job_id,
                now=now,
                reason="integration_complete",
            )

        first_session = factory()
        second_session = factory()
        first_transaction = first_session.begin()
        try:
            first_claim = IngestionOutboxStateMachine(first_session).claim_due_events(
                lease_owner="dispatcher-a:integration-claim",
                now=now,
                lease_duration=timedelta(seconds=30),
            )
            assert len(first_claim) == 1
            event_id = first_claim[0].id

            with second_session.begin():
                second_claim = IngestionOutboxStateMachine(
                    second_session
                ).claim_due_events(
                    lease_owner="dispatcher-b:integration-claim",
                    now=now,
                    lease_duration=timedelta(seconds=30),
                )
                assert second_claim == []
            first_transaction.commit()
        finally:
            if first_transaction.is_active:
                first_transaction.rollback()
            first_session.close()
            second_session.close()

        with factory.begin() as session:
            assert IngestionOutboxStateMachine(session).claim_due_events(
                lease_owner="dispatcher-b:before-expiry",
                now=now + timedelta(seconds=29),
                lease_duration=timedelta(seconds=30),
            ) == []

        with factory.begin() as session:
            reclaimed = IngestionOutboxStateMachine(session).claim_due_events(
                lease_owner="dispatcher-b:after-expiry",
                now=now + timedelta(seconds=31),
                lease_duration=timedelta(seconds=30),
            )
            assert [event.id for event in reclaimed] == [event_id]
            outbox = IngestionOutboxStateMachine(session)
            started = outbox.start_publication(
                event_id=event_id,
                lease_owner="dispatcher-b:after-expiry",
                now=now + timedelta(seconds=31),
            )
            assert started.publication_attempt_count == 1
            event, queued_job, changed = outbox.mark_published(
                event_id=event_id,
                lease_owner="dispatcher-b:after-expiry",
                now=now + timedelta(seconds=32),
            )
            assert changed
            assert event.publication_attempt_count == 1
            assert queued_job.id == job_id
    finally:
        with factory.begin() as session:
            session.execute(delete(AuditEvent).where(AuditEvent.workspace_id == workspace_id))
            session.execute(
                delete(IngestionOutboxEvent).where(
                    IngestionOutboxEvent.workspace_id == workspace_id
                )
            )
            session.execute(
                delete(IngestionAttempt).where(IngestionAttempt.workspace_id == workspace_id)
            )
            session.execute(
                delete(IngestionJob).where(IngestionJob.workspace_id == workspace_id)
            )
            session.execute(
                delete(DocumentVersion).where(DocumentVersion.workspace_id == workspace_id)
            )
            session.execute(delete(Document).where(Document.workspace_id == workspace_id))
            session.execute(
                delete(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == workspace_id
                )
            )
            session.execute(delete(Workspace).where(Workspace.id == workspace_id))
            session.execute(delete(User).where(User.id == user_id))
        engine.dispose()
