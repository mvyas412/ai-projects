from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from backend.app.broker.messages import IngestionEventMessage
from backend.app.core.config import Settings
from backend.app.db.rls import DatabasePurpose, set_rls_context
from backend.app.db.session import SessionFactory
from backend.app.ingestion.pipeline import pipeline_manifest
from backend.app.models.document import Document, DocumentVersion
from backend.app.models.ingestion import IngestionAttempt, IngestionJob, IngestionProgressStage
from backend.app.rag.indexing import (
    DocumentIndexer,
    EmptyDocumentError,
    IndexingRequest,
    IndexingResult,
    IndexingUnavailableError,
)
from backend.app.repositories.documents import DocumentRepository
from backend.app.services.ingestion_jobs import (
    IngestionAttemptOwnershipError,
    IngestionInvalidTransitionError,
    IngestionJobNotFoundError,
    IngestionJobStateMachine,
    retry_delay,
)
from backend.app.storage.authorized import resolve_original_object
from backend.app.storage.base import (
    ObjectIntegrityError,
    ObjectNotFoundError,
    ObjectStorage,
    ObjectStorageUnavailableError,
)
from backend.app.storage.keys import attempt_artifact_key, generation_artifact_key


class DeliveryDisposition(StrEnum):
    ACK = "ack"
    REQUEUE = "requeue"


class WorkerShutdown(Exception):
    pass


class WorkerCancellation(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ClaimedWork:
    job: IngestionJob
    attempt: IngestionAttempt
    generation_id: UUID
    document: Document
    version: DocumentVersion


class IngestionWorkerService:
    """Execute one broker wake-up against PostgreSQL's fenced job authority."""

    def __init__(
        self,
        settings: Settings,
        session_factory: SessionFactory,
        original_storage: ObjectStorage,
        artifact_storage: ObjectStorage,
        indexer: DocumentIndexer,
        *,
        worker_id: str,
        shutdown_requested: threading.Event | None = None,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._original_storage = original_storage
        self._artifact_storage = artifact_storage
        self._indexer = indexer
        self._worker_id = worker_id
        self._shutdown = shutdown_requested or threading.Event()

    def process(self, message: IngestionEventMessage) -> DeliveryDisposition:
        try:
            work = self._claim(message.job_id)
        except (IngestionJobNotFoundError, IngestionInvalidTransitionError):
            return DeliveryDisposition.ACK
        except Exception:
            return DeliveryDisposition.REQUEUE

        heartbeat_stop = threading.Event()
        ownership_lost = threading.Event()
        cancellation = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(work, heartbeat_stop, ownership_lost, cancellation),
            name=f"heartbeat-{work.attempt.id}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            self._checkpoint(work, IngestionProgressStage.LOADING_ORIGINAL)
            if self._shutdown.is_set():
                raise WorkerShutdown
            stored = resolve_original_object(
                self._original_storage, work.document, work.version
            )
            content = self._original_storage.read(stored.key)
            if hashlib.sha256(content).hexdigest() != work.version.content_sha256:
                raise ObjectIntegrityError("Original identity mismatch")

            def progress(
                stage: str,
                completed: int | None,
                total: int | None,
                unit: str | None,
            ) -> None:
                if self._shutdown.is_set():
                    raise WorkerShutdown
                if ownership_lost.is_set():
                    raise IngestionAttemptOwnershipError("Worker lease was lost")
                if cancellation.is_set():
                    raise WorkerCancellation
                self._checkpoint(
                    work,
                    IngestionProgressStage(stage),
                    completed=completed,
                    total=total,
                    unit=unit,
                )

            result = self._indexer.index(
                IndexingRequest(
                    workspace_id=work.job.workspace_id,
                    document_id=work.job.document_id,
                    document_version_id=work.job.document_version_id,
                    document_title=work.document.title,
                    media_type=work.document.media_type,
                    content=content,
                    generation_id=work.generation_id,
                ),
                progress=progress,
            )
            if self._shutdown.is_set():
                raise WorkerShutdown
            if ownership_lost.is_set():
                raise IngestionAttemptOwnershipError("Worker lease was lost")
            if cancellation.is_set():
                raise WorkerCancellation
            return self._promote(work, result)
        except WorkerShutdown:
            return DeliveryDisposition.REQUEUE
        except WorkerCancellation:
            return self._finish_cancellation(work)
        except IngestionAttemptOwnershipError:
            return DeliveryDisposition.ACK
        except Exception as exc:
            return self._record_failure(work, exc)
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=2)

    def recover_expired(self) -> list[UUID]:
        with self._session_factory.begin() as session:
            set_rls_context(session, purpose=DatabasePurpose.OPERATIONS)
            return IngestionJobStateMachine(session).recover_expired_jobs(
                now=datetime.now(UTC),
                limit=25,
            )

    def _claim(self, job_id: UUID) -> ClaimedWork:
        now = datetime.now(UTC)
        with self._session_factory.begin() as session:
            workspace_id = set_rls_context(
                session, purpose=DatabasePurpose.WORKER, job_id=job_id
            )
            if workspace_id is None:
                raise IngestionJobNotFoundError
            state = IngestionJobStateMachine(session)
            job, attempt = state.claim_job(
                job_id=job_id,
                worker_id=self._worker_id,
                now=now,
                lease_duration=timedelta(seconds=self._settings.worker_lease_seconds),
            )
            generation = state.create_generation(
                job_id=job.id,
                attempt_id=attempt.id,
                fencing_token=attempt.fencing_token,
                now=now,
            )
            documents = DocumentRepository(session)
            document = documents.get_document(job.workspace_id, job.document_id)
            version = documents.get_version(
                job.workspace_id,
                job.document_id,
                job.document_version_id,
            )
            if document is None or version is None:
                raise IngestionJobNotFoundError
            return ClaimedWork(job, attempt, generation.id, document, version)

    def _heartbeat_loop(
        self,
        work: ClaimedWork,
        stop: threading.Event,
        ownership_lost: threading.Event,
        cancellation: threading.Event,
    ) -> None:
        while not stop.wait(self._settings.worker_heartbeat_seconds):
            if self._shutdown.is_set():
                return
            try:
                with self._session_factory.begin() as session:
                    set_rls_context(
                        session,
                        purpose=DatabasePurpose.WORKER,
                        workspace_id=work.job.workspace_id,
                        job_id=work.job.id,
                    )
                    cancel = IngestionJobStateMachine(session).heartbeat(
                        job_id=work.job.id,
                        attempt_id=work.attempt.id,
                        fencing_token=work.attempt.fencing_token,
                        now=datetime.now(UTC),
                        lease_duration=timedelta(
                            seconds=self._settings.worker_lease_seconds
                        ),
                    )
                if cancel:
                    cancellation.set()
            except IngestionAttemptOwnershipError:
                ownership_lost.set()
                return
            except Exception:
                ownership_lost.set()
                return

    def _checkpoint(
        self,
        work: ClaimedWork,
        stage: IngestionProgressStage,
        *,
        completed: int | None = None,
        total: int | None = None,
        unit: str | None = None,
    ) -> None:
        with self._session_factory.begin() as session:
            set_rls_context(
                session,
                purpose=DatabasePurpose.WORKER,
                workspace_id=work.job.workspace_id,
                job_id=work.job.id,
            )
            cancelled = IngestionJobStateMachine(session).heartbeat(
                job_id=work.job.id,
                attempt_id=work.attempt.id,
                fencing_token=work.attempt.fencing_token,
                now=datetime.now(UTC),
                lease_duration=timedelta(seconds=self._settings.worker_lease_seconds),
                stage=stage,
                completed_units=completed,
                total_units=total,
                unit=unit,
            )
        if cancelled:
            raise WorkerCancellation

    def _promote(
        self, work: ClaimedWork, result: IndexingResult
    ) -> DeliveryDisposition:
        self._checkpoint(work, IngestionProgressStage.PROMOTING)
        vector_count = result.vector_count or result.chunk_count
        manifest: dict[str, object] = {
            "schema_version": 1,
            "generation_id": str(work.generation_id),
            "job_id": str(work.job.id),
            "attempt_id": str(work.attempt.id),
            "document_version_id": str(work.version.id),
            "source_sha256": work.version.content_sha256,
            "pipeline_fingerprint": work.job.pipeline_fingerprint,
            "pipeline": pipeline_manifest(self._settings, work.document.media_type),
            "chunk_count": result.chunk_count,
            "vector_count": vector_count,
        }
        content = json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        checksum = hashlib.sha256(content).hexdigest()
        metadata = {
            "workspace-id": str(work.job.workspace_id),
            "job-id": str(work.job.id),
            "attempt-id": str(work.attempt.id),
            "generation-id": str(work.generation_id),
        }
        attempt_key = attempt_artifact_key(
            workspace_id=work.job.workspace_id,
            job_id=work.job.id,
            attempt_id=work.attempt.id,
            artifact_name="manifest.json",
        )
        final_key = generation_artifact_key(
            workspace_id=work.job.workspace_id,
            document_id=work.job.document_id,
            version_id=work.job.document_version_id,
            generation_id=work.generation_id,
            artifact_name="manifest.json",
        )
        self._artifact_storage.put(
            attempt_key,
            content,
            media_type="application/json",
            metadata=metadata,
        )
        stored = self._artifact_storage.put(
            final_key,
            content,
            media_type="application/json",
            metadata=metadata,
        )
        if stored.content_sha256 != checksum or stored.byte_size != len(content):
            raise ObjectIntegrityError("Generation manifest identity mismatch")
        with self._session_factory.begin() as session:
            set_rls_context(
                session,
                purpose=DatabasePurpose.WORKER,
                workspace_id=work.job.workspace_id,
                job_id=work.job.id,
            )
            IngestionJobStateMachine(session).complete_success(
                job_id=work.job.id,
                attempt_id=work.attempt.id,
                fencing_token=work.attempt.fencing_token,
                generation_id=work.generation_id,
                manifest=manifest,
                manifest_object_key=final_key,
                manifest_sha256=checksum,
                chunk_count=result.chunk_count,
                vector_count=vector_count,
                now=datetime.now(UTC),
            )
        return DeliveryDisposition.ACK

    def _finish_cancellation(self, work: ClaimedWork) -> DeliveryDisposition:
        try:
            with self._session_factory.begin() as session:
                set_rls_context(
                    session,
                    purpose=DatabasePurpose.WORKER,
                    workspace_id=work.job.workspace_id,
                    job_id=work.job.id,
                )
                IngestionJobStateMachine(session).finish_cancellation(
                    job_id=work.job.id,
                    attempt_id=work.attempt.id,
                    fencing_token=work.attempt.fencing_token,
                    now=datetime.now(UTC),
                )
            return DeliveryDisposition.ACK
        except IngestionAttemptOwnershipError:
            return DeliveryDisposition.ACK
        except Exception:
            return DeliveryDisposition.REQUEUE

    def _record_failure(
        self, work: ClaimedWork, exc: Exception
    ) -> DeliveryDisposition:
        retryable, code, summary = _classify_failure(exc)
        now = datetime.now(UTC)
        try:
            with self._session_factory.begin() as session:
                set_rls_context(
                    session,
                    purpose=DatabasePurpose.WORKER,
                    workspace_id=work.job.workspace_id,
                    job_id=work.job.id,
                )
                IngestionJobStateMachine(session).record_failure(
                    job_id=work.job.id,
                    attempt_id=work.attempt.id,
                    fencing_token=work.attempt.fencing_token,
                    now=now,
                    retryable=retryable,
                    error_code=code,
                    error_message=summary,
                    retry_at=(
                        now + retry_delay(work.attempt.attempt_number, work.job.id)
                        if retryable
                        else None
                    ),
                )
            return DeliveryDisposition.ACK
        except IngestionAttemptOwnershipError:
            return DeliveryDisposition.ACK
        except Exception:
            return DeliveryDisposition.REQUEUE


def _classify_failure(exc: Exception) -> tuple[bool, str, str]:
    if isinstance(exc, EmptyDocumentError):
        return False, "empty_document", "No readable content was found in the document."
    if isinstance(exc, (ObjectNotFoundError, ObjectIntegrityError)):
        return False, "original_invalid", "The stored original could not be verified."
    if isinstance(exc, (IndexingUnavailableError, ObjectStorageUnavailableError)):
        return True, "dependency_unavailable", "A processing dependency is unavailable."
    return True, "worker_execution_failed", "Document processing could not be completed."
