from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import PurePath
from typing import BinaryIO
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.ingestion.pipeline import pipeline_fingerprint
from backend.app.models.document import Document, DocumentVersion
from backend.app.models.ingestion import (
    IngestionAttempt,
    IngestionJob,
    IngestionOperation,
)
from backend.app.models.user import User
from backend.app.repositories.documents import DocumentRepository
from backend.app.repositories.ingestion_jobs import IngestionJobRepository
from backend.app.services.documents import DocumentLibraryService
from backend.app.services.ingestion_jobs import (
    IngestionIdempotencyConflictError,
    IngestionJobNotFoundError,
    IngestionJobPermissionError,
    IngestionJobStateMachine,
    IngestionJobValidationError,
)
from backend.app.services.policy import (
    PolicyAction,
    PolicyDeniedError,
    PolicyNotFoundError,
    PolicyService,
    resource_context,
)
from backend.app.storage.base import ObjectStorage


@dataclass(frozen=True, slots=True)
class IngestionJobView:
    job: IngestionJob
    latest_attempt: IngestionAttempt | None


class IngestionAPIService:
    def __init__(
        self,
        session: Session,
        storage: ObjectStorage,
        settings: Settings,
    ) -> None:
        self._session = session
        self._storage = storage
        self._settings = settings
        self._jobs = IngestionJobRepository(session)
        self._documents = DocumentRepository(session)
        self._policy = PolicyService(session)

    def upload_and_enqueue(
        self,
        *,
        user: User,
        workspace_id: UUID,
        filename: str,
        media_type: str,
        content: bytes,
        title: str | None,
        idempotency_key: str,
    ) -> tuple[Document, DocumentVersion, IngestionJob, bool]:
        content_sha256 = hashlib.sha256(content).hexdigest()
        return self.upload_stream_and_enqueue(
            user=user,
            workspace_id=workspace_id,
            filename=filename,
            media_type=media_type,
            stream=BytesIO(content),
            byte_size=len(content),
            content_sha256=content_sha256,
            title=title,
            idempotency_key=idempotency_key,
        )

    def upload_stream_and_enqueue(
        self,
        *,
        user: User,
        workspace_id: UUID,
        filename: str,
        media_type: str,
        stream: BinaryIO,
        byte_size: int,
        content_sha256: str,
        title: str | None,
        idempotency_key: str,
    ) -> tuple[Document, DocumentVersion, IngestionJob, bool]:
        request_hash = _upload_request_hash(
            filename=filename,
            media_type=media_type,
            content_sha256=content_sha256,
            title=title,
        )
        existing = self._existing_replay(
            user=user,
            workspace_id=workspace_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        if existing is not None:
            return (*existing, False)

        library = DocumentLibraryService(self._session, self._storage, self._settings)

        def create_job(document: Document, version: DocumentVersion) -> IngestionJob:
            job, _ = IngestionJobStateMachine(self._session).create_job(
                user=user,
                workspace_id=workspace_id,
                document_id=document.id,
                document_version_id=version.id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                pipeline_fingerprint=version.ingestion_fingerprint,
                now=datetime.now(UTC),
            )
            return job

        try:
            document, version, job = library.create_document_stream_with_callback(
                user=user,
                workspace_id=workspace_id,
                filename=filename,
                media_type=media_type,
                stream=stream,
                byte_size=byte_size,
                content_sha256=content_sha256,
                title=title,
                max_upload_bytes=self._settings.max_upload_bytes,
                after_original=create_job,
            )
            return document, version, job, True
        except IngestionIdempotencyConflictError:
            replay = self._existing_replay(
                user=user,
                workspace_id=workspace_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            if replay is None:
                raise
            return (*replay, False)

    def enqueue_version(
        self,
        *,
        user: User,
        workspace_id: UUID,
        document_id: UUID,
        version_id: UUID,
        idempotency_key: str,
        predecessor_job_id: UUID | None = None,
    ) -> tuple[IngestionJob, bool]:
        with self._session.begin():
            return self._enqueue_version(
                user=user,
                workspace_id=workspace_id,
                document_id=document_id,
                version_id=version_id,
                idempotency_key=idempotency_key,
                predecessor_job_id=predecessor_job_id,
            )

    def get_job(
        self, *, user: User, workspace_id: UUID, job_id: UUID
    ) -> IngestionJobView:
        job = self._jobs.get_job(workspace_id, job_id)
        if job is None:
            raise IngestionJobNotFoundError
        self._require_job_read(user, job)
        return IngestionJobView(job, self._jobs.latest_attempt(job.id))

    def list_jobs(
        self,
        *,
        user: User,
        workspace_id: UUID,
        document_version_id: UUID | None = None,
        limit: int = 100,
    ) -> list[IngestionJobView]:
        self._require_workspace_job_read(user, workspace_id)
        views: list[IngestionJobView] = []
        for job in self._jobs.list_for_workspace(
            workspace_id,
            document_version_id=document_version_id,
            limit=limit,
        ):
            try:
                self._require_job_read(user, job)
            except (IngestionJobNotFoundError, IngestionJobPermissionError):
                continue
            views.append(IngestionJobView(job, self._jobs.latest_attempt(job.id)))
        return views

    def cancel_job(
        self, *, user: User, workspace_id: UUID, job_id: UUID
    ) -> IngestionJobView:
        with self._session.begin():
            job = IngestionJobStateMachine(self._session).request_cancellation(
                user=user,
                workspace_id=workspace_id,
                job_id=job_id,
                now=datetime.now(UTC),
            )
        return IngestionJobView(job, self._jobs.latest_attempt(job.id))

    def retry_job(
        self,
        *,
        user: User,
        workspace_id: UUID,
        job_id: UUID,
        idempotency_key: str,
    ) -> tuple[IngestionJob, bool]:
        with self._session.begin():
            predecessor = self._jobs.get_job(workspace_id, job_id)
            if predecessor is None:
                raise IngestionJobNotFoundError
            return self._enqueue_version(
                user=user,
                workspace_id=workspace_id,
                document_id=predecessor.document_id,
                version_id=predecessor.document_version_id,
                idempotency_key=idempotency_key,
                predecessor_job_id=predecessor.id,
            )

    def _enqueue_version(
        self,
        *,
        user: User,
        workspace_id: UUID,
        document_id: UUID,
        version_id: UUID,
        idempotency_key: str,
        predecessor_job_id: UUID | None,
    ) -> tuple[IngestionJob, bool]:
        document = self._documents.get_document(workspace_id, document_id)
        version = self._documents.get_version(workspace_id, document_id, version_id)
        if document is None or version is None:
            raise IngestionJobNotFoundError
        self._require_document_action(user, document, PolicyAction.DOCUMENT_INDEX)
        current_fingerprint = pipeline_fingerprint(self._settings, document.media_type)
        if (
            version.ingestion_fingerprint != current_fingerprint
            and predecessor_job_id is None
        ):
            raise IngestionJobValidationError(
                "Use an owner-approved successor job to upgrade this immutable version"
            )
        request_hash = _job_request_hash(
            document_id=document_id,
            version_id=version_id,
            pipeline_fingerprint=current_fingerprint,
            predecessor_job_id=predecessor_job_id,
        )
        return IngestionJobStateMachine(self._session).create_job(
            user=user,
            workspace_id=workspace_id,
            document_id=document_id,
            document_version_id=version_id,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            pipeline_fingerprint=current_fingerprint,
            predecessor_job_id=predecessor_job_id,
            now=datetime.now(UTC),
        )

    def _existing_replay(
        self,
        *,
        user: User,
        workspace_id: UUID,
        idempotency_key: str,
        request_hash: str,
    ) -> tuple[Document, DocumentVersion, IngestionJob] | None:
        with self._session.begin():
            existing = self._jobs.get_by_idempotency_key(
                workspace_id,
                IngestionOperation.INDEX_DOCUMENT_VERSION.value,
                idempotency_key.strip(),
            )
            if existing is None:
                return None
            if (
                existing.request_hash != request_hash
                or existing.requested_by_user_id != user.id
            ):
                raise IngestionIdempotencyConflictError(
                    "Idempotency key was already used for a different request"
                )
            document = self._documents.get_document(workspace_id, existing.document_id)
            version = self._documents.get_version(
                workspace_id,
                existing.document_id,
                existing.document_version_id,
            )
            if document is None or version is None:
                raise IngestionJobNotFoundError
            self._require_document_action(user, document, PolicyAction.DOCUMENT_INDEX)
            return document, version, existing

    def _require_workspace_job_read(self, user: User, workspace_id: UUID) -> None:
        try:
            self._policy.require(
                user=user,
                workspace_id=workspace_id,
                action=PolicyAction.JOB_READ,
            )
        except PolicyNotFoundError as exc:
            raise IngestionJobNotFoundError from exc
        except PolicyDeniedError as exc:
            raise IngestionJobPermissionError from exc

    def _require_job_read(self, user: User, job: IngestionJob) -> None:
        document = self._documents.get_document(job.workspace_id, job.document_id)
        if document is None:
            raise IngestionJobNotFoundError
        self._require_document_action(user, document, PolicyAction.JOB_READ)

    def _require_document_action(
        self, user: User, document: Document, action: PolicyAction
    ) -> None:
        try:
            self._policy.require(
                user=user,
                workspace_id=document.workspace_id,
                action=action,
                resource=resource_context(document),
            )
        except PolicyNotFoundError as exc:
            raise IngestionJobNotFoundError from exc
        except PolicyDeniedError as exc:
            raise IngestionJobPermissionError from exc


def _upload_request_hash(
    *, filename: str, media_type: str, content_sha256: str, title: str | None
) -> str:
    payload = {
        "operation": "upload_and_index",
        "filename": PurePath(filename).name,
        "media_type": media_type.split(";", 1)[0].strip().lower(),
        "title": " ".join((title or "").split()) or None,
        "content_sha256": content_sha256,
    }
    return _canonical_hash(payload)


def _job_request_hash(
    *,
    document_id: UUID,
    version_id: UUID,
    pipeline_fingerprint: str,
    predecessor_job_id: UUID | None,
) -> str:
    return _canonical_hash(
        {
            "operation": "index_document_version",
            "document_id": str(document_id),
            "document_version_id": str(version_id),
            "pipeline_fingerprint": pipeline_fingerprint,
            "predecessor_job_id": (
                str(predecessor_job_id) if predecessor_job_id is not None else None
            ),
        }
    )


def _canonical_hash(payload: Mapping[str, object]) -> str:
    content = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()
