from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.app.broker.messages import IngestionEventMessage
from backend.app.broker.rabbitmq import BrokerPublishError
from backend.app.core.security import AuthenticatedIdentity, get_current_identity
from backend.app.db.base import Base
from backend.app.db.session import SessionFactory, create_database_engine, create_session_factory
from backend.app.main import create_app
from backend.app.models import (
    AuditEvent,
    CalculationTrace,
    ContentArtifact,
    ContentRegion,
    Conversation,
    ConversationMessage,
    ConversationTargetType,
    Document,
    DocumentVersion,
    DocumentVersionStatus,
    IngestionAttempt,
    IngestionGeneration,
    IngestionGenerationState,
    IngestionJob,
    IngestionJobState,
    IngestionOutboxEvent,
    MessageRole,
    TableCell,
    TableColumn,
    TableRegion,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
)
from backend.app.models.visual import ContentRegionKind
from backend.app.rag.indexing import IndexingRequest, IndexingResult, IndexingUnavailableError
from backend.app.schemas.conversations import Citation
from backend.app.services.ingestion_api import IngestionAPIService
from backend.app.services.ingestion_jobs import (
    IngestionJobNotFoundError,
    IngestionJobStateMachine,
)
from backend.app.services.ingestion_operations import IngestionOperationsService
from backend.app.services.ingestion_worker import DeliveryDisposition, IngestionWorkerService
from backend.app.services.lifecycle import LifecycleService
from backend.app.services.visual_ingestion import LocalVisualIngestionProcessor
from backend.app.storage.keys import attempt_artifact_key, original_object_key
from backend.app.storage.local import LocalFileStorage
from backend.app.tables.calculation import (
    PostgresTableCalculationEngine,
    TableCalculationRequest,
    TableCalculationScope,
)
from backend.app.visual.extraction import ExtractedRegion, ExtractedTable, ExtractionResult
from backend.app.visual.provenance import NormalizedBoundingBox
from backend.app.workers.health import ProcessHealth
from backend.app.workers.ingestion_worker import _recover_expired_and_heartbeat
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


def _worker(
    test_settings, context: WorkerContext, indexer, *, visual_processor=None
) -> IngestionWorkerService:
    return IngestionWorkerService(
        test_settings,
        context.factory,
        context.storage,
        context.storage,
        indexer,
        worker_id="worker-test-1",
        visual_processor=visual_processor,
    )


class FixtureVisualExtractor:
    def __init__(self, png: bytes) -> None:
        self._png = png

    def extract(self, content: bytes, media_type: str) -> ExtractionResult:
        return ExtractionResult(
            extractor_name="fixture",
            extractor_revision="1.0.0",
            regions=(
                ExtractedRegion(
                    page_number=1,
                    kind=ContentRegionKind.CHART,
                    ordinal=0,
                    bbox=NormalizedBoundingBox(0.1, 0.2, 0.6, 0.5),
                    page_width=100.0,
                    page_height=80.0,
                    rotation=0,
                    page_render=self._png,
                    crop=self._png,
                    source_caption="Revenue chart",
                    ocr_text="2025 revenue 42",
                    confidence=0.99,
                ),
            ),
        )


class FixtureTableExtractor(FixtureVisualExtractor):
    def extract(self, content: bytes, media_type: str) -> ExtractionResult:
        return ExtractionResult(
            extractor_name="fixture",
            extractor_revision="1.0.0",
            regions=(
                ExtractedRegion(
                    page_number=1,
                    kind=ContentRegionKind.TABLE,
                    ordinal=0,
                    bbox=NormalizedBoundingBox(0.1, 0.2, 0.6, 0.5),
                    page_width=100.0,
                    page_height=80.0,
                    rotation=0,
                    page_render=self._png,
                    crop=self._png,
                    source_caption="Revenue table",
                    ocr_text="Year | Revenue\n2025 | $42",
                    confidence=0.99,
                    table=ExtractedTable(
                        columns=("Year", "Revenue"),
                        rows=(("2025", "$42"),),
                    ),
                ),
            ),
        )


class FixtureMalformedTableExtractor(FixtureVisualExtractor):
    def extract(self, content: bytes, media_type: str) -> ExtractionResult:
        result = super().extract(content, media_type)
        region = result.regions[0]
        return ExtractionResult(
            extractor_name=result.extractor_name,
            extractor_revision=result.extractor_revision,
            regions=(
                ExtractedRegion(
                    page_number=region.page_number,
                    kind=ContentRegionKind.TABLE,
                    ordinal=region.ordinal,
                    bbox=region.bbox,
                    page_width=region.page_width,
                    page_height=region.page_height,
                    rotation=region.rotation,
                    page_render=region.page_render,
                    crop=region.crop,
                    source_caption="Unstructured table image",
                    ocr_text=None,
                    confidence=region.confidence,
                    table=ExtractedTable(columns=(), rows=()),
                ),
            ),
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


def test_worker_promotes_immutable_visual_region_artifacts(
    test_settings, worker_context
) -> None:
    from io import BytesIO

    from PIL import Image

    output = BytesIO()
    Image.new("RGB", (20, 10), "navy").save(output, format="PNG")
    processor = LocalVisualIngestionProcessor(
        worker_context.factory,
        worker_context.storage,
        FixtureVisualExtractor(output.getvalue()),
        extractor_config={"profile": "fixture-v1"},
    )
    worker = _worker(
        test_settings,
        worker_context,
        SuccessfulIndexer(),
        visual_processor=processor,
    )

    assert worker.process(worker_context.message) == DeliveryDisposition.ACK

    with worker_context.factory() as session:
        generation = session.scalar(
            select(IngestionGeneration).where(
                IngestionGeneration.job_id == worker_context.job_id
            )
        )
        regions = list(session.scalars(select(ContentRegion)))
        artifacts = list(session.scalars(select(ContentArtifact)))
        assert generation is not None
        assert generation.state == IngestionGenerationState.PROMOTED.value
        assert generation.manifest is not None
        visual = generation.manifest["visual_outputs"]
        assert isinstance(visual, dict)
        assert visual["region_count"] == 1
        assert visual["artifact_count"] == 5
        assert len(regions) == 1
        assert len(artifacts) == 5
        assert all(row.generation_id == generation.id for row in artifacts)
        assert all(worker_context.storage.exists(row.object_key) for row in artifacts)


def test_worker_promotes_normalized_table_structure(test_settings, worker_context) -> None:
    from io import BytesIO

    from PIL import Image

    output = BytesIO()
    Image.new("RGB", (20, 10), "white").save(output, format="PNG")
    processor = LocalVisualIngestionProcessor(
        worker_context.factory,
        worker_context.storage,
        FixtureTableExtractor(output.getvalue()),
        extractor_config={"profile": "fixture-v1"},
    )
    worker = _worker(
        test_settings,
        worker_context,
        SuccessfulIndexer(),
        visual_processor=processor,
    )

    assert worker.process(worker_context.message) == DeliveryDisposition.ACK

    with worker_context.factory() as session:
        generation = session.scalar(
            select(IngestionGeneration).where(
                IngestionGeneration.job_id == worker_context.job_id
            )
        )
        tables = list(session.scalars(select(TableRegion)))
        columns = list(session.scalars(select(TableColumn)))
        cells = list(session.scalars(select(TableCell)))
        assert generation is not None and generation.manifest is not None
        visual = generation.manifest["visual_outputs"]
        assert isinstance(visual, dict)
        assert visual["table_count"] == 1
        assert visual["exact_table_count"] == 1
        assert visual["table_cell_count"] == 4
        assert len(tables) == 1
        assert len(columns) == 2
        assert len(cells) == 4
        assert tables[0].validation_state == "validated"
        assert {cell.normalized_value for cell in cells if not cell.is_header} == {
            "2025",
            "42",
        }

    with worker_context.factory.begin() as session:
        decision = PostgresTableCalculationEngine(session).calculate(
            TableCalculationRequest(
                workspace_id=worker_context.workspace_id,
                documents=(
                    TableCalculationScope(
                        worker_context.document_id,
                        worker_context.version_id,
                        generation.id,
                        "Fixture report",
                    ),
                ),
                query="What is the total Revenue?",
            )
        )
        assert decision.evidence is not None
        assert decision.evidence.result_value == "42"
        assert decision.evidence.currency == "USD"
        trace = session.get(CalculationTrace, decision.evidence.trace_id)
        assert trace is not None
        assert trace.operator == "sum"
        assert trace.query_fingerprint != "What is the total Revenue?"


def test_malformed_table_keeps_visual_evidence_but_skips_exact_structure(
    test_settings, worker_context
) -> None:
    from io import BytesIO

    from PIL import Image

    output = BytesIO()
    Image.new("RGB", (20, 10), "white").save(output, format="PNG")
    processor = LocalVisualIngestionProcessor(
        worker_context.factory,
        worker_context.storage,
        FixtureMalformedTableExtractor(output.getvalue()),
        extractor_config={"profile": "fixture-v1"},
    )
    worker = _worker(
        test_settings,
        worker_context,
        SuccessfulIndexer(),
        visual_processor=processor,
    )

    assert worker.process(worker_context.message) == DeliveryDisposition.ACK

    with worker_context.factory() as session:
        generation = session.scalar(
            select(IngestionGeneration).where(
                IngestionGeneration.job_id == worker_context.job_id
            )
        )
        assert generation is not None and generation.manifest is not None
        visual = generation.manifest["visual_outputs"]
        assert visual["region_count"] == 1
        assert visual["table_count"] == 0
        assert session.scalar(select(TableRegion)) is None
        artifact_kinds = set(session.scalars(select(ContentArtifact.kind)))
        assert {"region_crop", "structured_table"} <= artifact_kinds


def test_evidence_api_rechecks_scope_generation_and_artifact_integrity(
    test_settings, worker_context
) -> None:
    from io import BytesIO

    from PIL import Image

    output = BytesIO()
    Image.new("RGB", (20, 10), "white").save(output, format="PNG")
    processor = LocalVisualIngestionProcessor(
        worker_context.factory,
        worker_context.storage,
        FixtureTableExtractor(output.getvalue()),
        extractor_config={"profile": "fixture-v1"},
    )
    worker = _worker(
        test_settings,
        worker_context,
        SuccessfulIndexer(),
        visual_processor=processor,
    )
    assert worker.process(worker_context.message) == DeliveryDisposition.ACK

    conversation_id, message_id, legacy_message_id = uuid4(), uuid4(), uuid4()
    with worker_context.factory.begin() as session:
        generation = session.scalar(
            select(IngestionGeneration).where(
                IngestionGeneration.job_id == worker_context.job_id
            )
        )
        table = session.scalar(select(TableRegion))
        assert generation is not None and table is not None
        decision = PostgresTableCalculationEngine(session).calculate(
            TableCalculationRequest(
                workspace_id=worker_context.workspace_id,
                documents=(
                    TableCalculationScope(
                        worker_context.document_id,
                        worker_context.version_id,
                        generation.id,
                        "Fixture report",
                    ),
                ),
                query="What is the total Revenue?",
            )
        )
        evidence = decision.evidence
        assert evidence is not None
        citation = Citation(
            document_id=evidence.document_id,
            document_version_id=evidence.document_version_id,
            generation_id=evidence.generation_id,
            document_title=evidence.document_title,
            page_number=evidence.page_number,
            content_type="application/vnd.mm-rag.table-calculation+json",
            excerpt="Exact sum from one validated table cell.",
            evidence_kind="calculation",
            region_id=evidence.region_id,
            table_id=evidence.table_id,
            cell_ids=list(evidence.cell_ids),
            calculation_trace_id=evidence.trace_id,
        )
        session.add(
            Conversation(
                id=conversation_id,
                workspace_id=worker_context.workspace_id,
                created_by_user_id=worker_context.user.id,
                title="Evidence verification",
                target_type=ConversationTargetType.WORKSPACE.value,
            )
        )
        session.flush()
        session.add(
            ConversationMessage(
                id=message_id,
                conversation_id=conversation_id,
                workspace_id=worker_context.workspace_id,
                sequence_number=1,
                role=MessageRole.ASSISTANT.value,
                content="The exact sum is USD 42.",
                citations=[citation.model_dump(mode="json")],
                model_name="deterministic-table-v1",
            )
        )
        session.add(
            ConversationMessage(
                id=legacy_message_id,
                conversation_id=conversation_id,
                workspace_id=worker_context.workspace_id,
                sequence_number=2,
                role=MessageRole.ASSISTANT.value,
                content="A compatible historical text answer.",
                citations=[
                    {
                        "document_id": str(worker_context.document_id),
                        "document_version_id": str(worker_context.version_id),
                        "document_title": "Fixture report",
                        "page_number": 1,
                        "content_type": "text/plain",
                        "excerpt": "Historical text evidence",
                    }
                ],
                model_name="historical-model",
            )
        )

    with worker_context.factory() as session:
        stored_artifacts = tuple(session.scalars(select(ContentArtifact)))
        referenced = LifecycleService(
            session,
            test_settings,
            worker_context.storage,
            worker_context.storage,
            None,
        )._referenced_object_keys(worker_context.workspace_id)["artifacts"]
        for artifact in stored_artifacts:
            assert artifact.object_key in referenced
            assert attempt_artifact_key(
                workspace_id=worker_context.workspace_id,
                job_id=worker_context.job_id,
                attempt_id=artifact.creation_attempt_id,
                artifact_name=PurePosixPath(artifact.object_key).name,
            ) in referenced

    app = create_app(test_settings)
    with TestClient(app) as client:
        app.state.session_factory = worker_context.factory
        app.state.artifact_storage = worker_context.storage
        app.dependency_overrides[get_current_identity] = lambda: AuthenticatedIdentity(
            subject=worker_context.user.external_subject,
            email="owner@example.com",
            display_name="Owner",
        )
        evidence_url = (
            f"/api/v1/workspaces/{worker_context.workspace_id}/conversations/"
            f"{conversation_id}/messages/{message_id}/evidence/0"
        )
        described = client.get(evidence_url)
        assert described.status_code == 200, described.text
        descriptor = described.json()
        assert descriptor["schema_revision"] == "evidence-v1"
        assert descriptor["calculation"]["result_value"] == "42"
        assert descriptor["table"]["validation_state"] == "validated"
        assert sum(cell["cited"] for cell in descriptor["table"]["cells"]) == 1
        assert "object_key" not in described.text

        legacy_url = (
            f"/api/v1/workspaces/{worker_context.workspace_id}/conversations/"
            f"{conversation_id}/messages/{legacy_message_id}/evidence/0"
        )
        legacy = client.get(legacy_url)
        assert legacy.status_code == 200
        assert legacy.json()["generation_id"] == str(generation.id)
        assert legacy.json()["region"] is None
        assert legacy.json()["artifacts"] == []

        crop = next(
            artifact
            for artifact in descriptor["artifacts"]
            if artifact["kind"] == "region_crop"
        )
        artifact_url = f"{evidence_url}/artifacts/{crop['id']}"
        streamed = client.get(artifact_url)
        assert streamed.status_code == 200
        assert streamed.headers["cache-control"] == "private, no-store"
        assert streamed.content == output.getvalue()
        assert client.get(f"{evidence_url}/artifacts/{uuid4()}").status_code == 404

        app.dependency_overrides[get_current_identity] = lambda: AuthenticatedIdentity(
            subject="auth0|other-evidence-user",
            email="other@example.com",
            display_name="Other",
        )
        denied = client.get(artifact_url)
        assert denied.status_code == 404
        assert output.getvalue() not in denied.content

        app.dependency_overrides[get_current_identity] = lambda: AuthenticatedIdentity(
            subject=worker_context.user.external_subject,
            email="owner@example.com",
            display_name="Owner",
        )
        artifact = None
        with worker_context.factory() as session:
            artifact = session.get(ContentArtifact, UUID(crop["id"]))
        assert artifact is not None
        worker_context.storage.put(
            artifact.object_key,
            b"changed artifact bytes",
            media_type=artifact.media_type,
            if_absent=False,
        )
        integrity_failure = client.get(artifact_url)
        assert integrity_failure.status_code == 503
        assert b"changed artifact bytes" not in integrity_failure.content

        with worker_context.factory.begin() as session:
            version = session.get(DocumentVersion, worker_context.version_id)
            assert version is not None
            version.active_generation_id = None
            version.active_generation_promoted_at = None
        assert client.get(evidence_url).status_code == 404

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


@pytest.mark.asyncio
async def test_idle_recovery_refreshes_worker_readiness(
    test_settings, worker_context
) -> None:
    worker = _worker(test_settings, worker_context, SuccessfulIndexer())
    health = ProcessHealth(test_settings.runtime_health_directory, "worker")
    health.update(state="degraded", ready=False, in_flight=4)

    await _recover_expired_and_heartbeat(worker, health, in_flight=0)

    payload = json.loads(health.path.read_text(encoding="utf-8"))
    assert payload["state"] == "running"
    assert payload["ready"] is True
    assert payload["in_flight"] == 0


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
