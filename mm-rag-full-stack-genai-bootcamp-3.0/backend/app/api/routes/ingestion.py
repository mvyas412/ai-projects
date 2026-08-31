from __future__ import annotations

import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_current_user, get_object_storage
from backend.app.db.session import get_db_session
from backend.app.models.document import Document, DocumentVersion
from backend.app.models.ingestion import IngestionJobState, IngestionProgressStage
from backend.app.models.user import User
from backend.app.schemas.documents import (
    DocumentDetail,
    DocumentSummary,
    DocumentVersionSummary,
)
from backend.app.schemas.ingestion import (
    AsyncUploadResponse,
    IngestionJobSummary,
    IngestionProgress,
    IngestionPublicError,
)
from backend.app.services.documents import DocumentLibraryError
from backend.app.services.ingestion_api import IngestionAPIService, IngestionJobView
from backend.app.services.ingestion_jobs import (
    IngestionIdempotencyConflictError,
    IngestionInvalidTransitionError,
    IngestionJobError,
    IngestionJobNotFoundError,
    IngestionJobPermissionError,
    IngestionJobValidationError,
)
from backend.app.storage.base import ObjectStorage

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["ingestion"])
IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=255),
]


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, IngestionJobNotFoundError):
        return HTTPException(status_code=404, detail="Resource not found")
    if isinstance(exc, IngestionJobPermissionError):
        return HTTPException(status_code=403, detail="Insufficient access")
    if isinstance(exc, (IngestionIdempotencyConflictError, IngestionInvalidTransitionError)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, IngestionJobValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, DocumentLibraryError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="The ingestion request could not be completed")


def _job_summary(view: IngestionJobView) -> IngestionJobSummary:
    job, attempt = view.job, view.latest_attempt
    completed = attempt.progress_completed if attempt is not None else None
    total = attempt.progress_total if attempt is not None else None
    percentage = (
        min(100, int((completed / total) * 100))
        if completed is not None and total is not None
        else None
    )
    progress = IngestionProgress(
        stage=(
            IngestionProgressStage(attempt.progress_stage)
            if attempt is not None and attempt.progress_stage is not None
            else None
        ),
        attempt_number=(attempt.attempt_number if attempt is not None else job.attempt_count),
        completed_units=completed,
        total_units=total,
        unit=(attempt.progress_unit if attempt is not None else None),
        percentage=percentage,
        updated_at=(attempt.updated_at if attempt is not None else job.updated_at),
    )
    error = None
    if job.last_error_code and job.last_error_message:
        error = IngestionPublicError(
            code=job.last_error_code,
            retryable=(
                job.state == IngestionJobState.RETRY_SCHEDULED.value
                or job.last_error_code == "attempts_exhausted"
            ),
            summary=job.last_error_message,
            correlation_id=str(job.id),
        )
    return IngestionJobSummary(
        id=job.id,
        document_id=job.document_id,
        document_version_id=job.document_version_id,
        predecessor_job_id=job.predecessor_job_id,
        state=IngestionJobState(job.state),
        revision=job.revision,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
        cancel_requested=job.cancel_requested_at is not None,
        next_attempt_at=job.next_attempt_at,
        progress=progress,
        error=error,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
    )


def _document_detail(document: Document, version: DocumentVersion) -> DocumentDetail:
    version_summary = DocumentVersionSummary.model_validate(version)
    summary = DocumentSummary(
        id=document.id,
        workspace_id=document.workspace_id,
        title=document.title,
        original_filename=document.original_filename,
        media_type=document.media_type,
        archived_at=document.archived_at,
        latest_version=version_summary,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )
    return DocumentDetail(**summary.model_dump(), versions=[version_summary])


def _service(
    request: Request, session: Session, storage: ObjectStorage
) -> IngestionAPIService:
    return IngestionAPIService(session, storage, request.app.state.settings)


@router.post(
    "/ingestion/uploads",
    response_model=AsyncUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Durably upload and enqueue a document",
)
def upload_and_enqueue(
    workspace_id: UUID,
    request: Request,
    idempotency_key: IdempotencyHeader,
    file: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    title: Annotated[str | None, Form()] = None,
) -> AsyncUploadResponse:
    digest = hashlib.sha256()
    byte_size = 0
    while chunk := file.file.read(1024 * 1024):
        byte_size += len(chunk)
        if byte_size > request.app.state.settings.max_upload_bytes:
            break
        digest.update(chunk)
    file.file.seek(0)
    service = _service(request, session, storage)
    try:
        document, version, job, created = service.upload_stream_and_enqueue(
            user=user,
            workspace_id=workspace_id,
            filename=file.filename or "",
            media_type=file.content_type or "application/octet-stream",
            stream=file.file,
            byte_size=byte_size,
            content_sha256=digest.hexdigest(),
            title=title,
            idempotency_key=idempotency_key,
        )
        view = service.get_job(user=user, workspace_id=workspace_id, job_id=job.id)
    except (IngestionJobError, DocumentLibraryError) as exc:
        raise _translate(exc) from exc
    return AsyncUploadResponse(
        document=_document_detail(document, version),
        job=_job_summary(view),
        replayed=not created,
    )


@router.post(
    "/documents/{document_id}/versions/{version_id}/ingestion-jobs",
    response_model=IngestionJobSummary,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue an immutable document version",
)
def enqueue_version(
    workspace_id: UUID,
    document_id: UUID,
    version_id: UUID,
    request: Request,
    idempotency_key: IdempotencyHeader,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> IngestionJobSummary:
    service = _service(request, session, storage)
    try:
        job, _ = service.enqueue_version(
            user=user,
            workspace_id=workspace_id,
            document_id=document_id,
            version_id=version_id,
            idempotency_key=idempotency_key,
        )
        return _job_summary(
            service.get_job(user=user, workspace_id=workspace_id, job_id=job.id)
        )
    except IngestionJobError as exc:
        raise _translate(exc) from exc


@router.get("/ingestion/jobs", response_model=list[IngestionJobSummary])
def list_jobs(
    workspace_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    document_version_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> list[IngestionJobSummary]:
    try:
        views = _service(request, session, storage).list_jobs(
            user=user,
            workspace_id=workspace_id,
            document_version_id=document_version_id,
            limit=limit,
        )
    except IngestionJobError as exc:
        raise _translate(exc) from exc
    return [_job_summary(view) for view in views]


@router.get("/ingestion/jobs/{job_id}", response_model=IngestionJobSummary)
def get_job(
    workspace_id: UUID,
    job_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> IngestionJobSummary:
    try:
        view = _service(request, session, storage).get_job(
            user=user, workspace_id=workspace_id, job_id=job_id
        )
    except IngestionJobError as exc:
        raise _translate(exc) from exc
    return _job_summary(view)


@router.post("/ingestion/jobs/{job_id}/cancel", response_model=IngestionJobSummary)
def cancel_job(
    workspace_id: UUID,
    job_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> IngestionJobSummary:
    try:
        view = _service(request, session, storage).cancel_job(
            user=user, workspace_id=workspace_id, job_id=job_id
        )
    except IngestionJobError as exc:
        raise _translate(exc) from exc
    return _job_summary(view)


@router.post(
    "/ingestion/jobs/{job_id}/retry",
    response_model=IngestionJobSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_job(
    workspace_id: UUID,
    job_id: UUID,
    request: Request,
    idempotency_key: IdempotencyHeader,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> IngestionJobSummary:
    service = _service(request, session, storage)
    try:
        job, _ = service.retry_job(
            user=user,
            workspace_id=workspace_id,
            job_id=job_id,
            idempotency_key=idempotency_key,
        )
        return _job_summary(
            service.get_job(user=user, workspace_id=workspace_id, job_id=job.id)
        )
    except IngestionJobError as exc:
        raise _translate(exc) from exc
