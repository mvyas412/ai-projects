from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, BinaryIO, ContextManager
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_artifact_storage, get_current_user
from backend.app.db.session import get_db_session
from backend.app.models.audit import AuditActorKind, AuditResult
from backend.app.models.user import User
from backend.app.schemas.audit import (
    AuditEventResponse,
    ComplianceExportCreate,
    ComplianceExportResponse,
    SecurityAuditEventResponse,
)
from backend.app.services.audit import (
    AuditNotFoundError,
    AuditPermissionError,
    AuditService,
    AuditValidationError,
    ComplianceExportError,
    ComplianceExportNotFoundError,
    ComplianceExportPermissionError,
    ComplianceExportService,
    ComplianceExportUnavailableError,
    ComplianceExportValidationError,
    SecurityAuditFilter,
)
from backend.app.storage.base import ObjectStorage

router = APIRouter(prefix="/workspaces/{workspace_id}/activity", tags=["activity"])
security_router = APIRouter(
    prefix="/workspaces/{workspace_id}/security", tags=["security-audit"]
)


@router.get("", response_model=list[AuditEventResponse], summary="List workspace activity")
def list_activity(
    workspace_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[AuditEventResponse]:
    try:
        rows = AuditService(session).list_events(
            user=user, workspace_id=workspace_id, limit=limit
        )
    except AuditNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Resource not found") from exc
    return [
        AuditEventResponse(
            id=event.id,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            actor_kind=AuditActorKind(event.actor_kind),
            actor_user_id=event.actor_user_id,
            service_actor=event.service_actor,
            actor_display_name=(
                actor.display_name or actor.email or "User"
                if actor is not None
                else event.service_actor or "Service"
            ),
            result=AuditResult(event.result),
            details=event.details,
            created_at=event.created_at,
        )
        for event, actor in rows
    ]


@security_router.get(
    "/audit-events",
    response_model=list[SecurityAuditEventResponse],
    summary="Review bounded security audit events",
)
def list_security_events(
    workspace_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    range_start: datetime | None = None,
    range_end: datetime | None = None,
    action: str | None = None,
    result: AuditResult | None = None,
    actor_kind: AuditActorKind | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[SecurityAuditEventResponse]:
    try:
        events = AuditService(session).list_security_events(
            user=user,
            workspace_id=workspace_id,
            filters=SecurityAuditFilter(
                range_start=range_start,
                range_end=range_end,
                action=action,
                result=result,
                actor_kind=actor_kind,
            ),
            limit=limit,
        )
    except AuditNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Resource not found") from exc
    except AuditPermissionError as exc:
        raise HTTPException(status_code=403, detail="Insufficient access") from exc
    except AuditValidationError as exc:
        raise HTTPException(status_code=422, detail="Invalid audit filter") from exc
    return [SecurityAuditEventResponse.model_validate(event) for event in events]


@security_router.post(
    "/compliance-exports",
    response_model=ComplianceExportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a bounded compliance export",
)
def create_compliance_export(
    workspace_id: UUID,
    payload: ComplianceExportCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_artifact_storage)],
) -> ComplianceExportResponse:
    try:
        export = ComplianceExportService(session, storage).create(
            user=user,
            workspace_id=workspace_id,
            range_start=payload.range_start,
            range_end=payload.range_end,
        )
    except ComplianceExportError as exc:
        raise _export_error(exc) from exc
    return ComplianceExportResponse.model_validate(export)


@security_router.get(
    "/compliance-exports/{export_id}",
    response_model=ComplianceExportResponse,
    summary="Get compliance export metadata",
)
def get_compliance_export(
    workspace_id: UUID,
    export_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_artifact_storage)],
) -> ComplianceExportResponse:
    try:
        export = ComplianceExportService(session, storage).get(
            user=user, workspace_id=workspace_id, export_id=export_id
        )
    except ComplianceExportError as exc:
        raise _export_error(exc) from exc
    return ComplianceExportResponse.model_validate(export)


@security_router.get(
    "/compliance-exports/{export_id}/content",
    summary="Download an authorized compliance export",
)
def download_compliance_export(
    workspace_id: UUID,
    export_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_artifact_storage)],
) -> StreamingResponse:
    try:
        export, stream = ComplianceExportService(session, storage).open_content(
            user=user, workspace_id=workspace_id, export_id=export_id
        )
    except ComplianceExportError as exc:
        raise _export_error(exc) from exc
    return StreamingResponse(
        _stream_chunks(stream),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="audit-export-{export.id}.json"',
            "Content-Length": str(export.byte_size),
            "X-Content-Type-Options": "nosniff",
        },
    )


def _export_error(exc: ComplianceExportError) -> HTTPException:
    if isinstance(exc, ComplianceExportNotFoundError):
        return HTTPException(status_code=404, detail="Resource not found")
    if isinstance(exc, ComplianceExportPermissionError):
        return HTTPException(status_code=403, detail="Insufficient access")
    if isinstance(exc, ComplianceExportValidationError):
        return HTTPException(status_code=422, detail="Invalid export range")
    if isinstance(exc, ComplianceExportUnavailableError):
        return HTTPException(status_code=503, detail="Export is temporarily unavailable")
    return HTTPException(status_code=500, detail="The export could not be completed")


def _stream_chunks(
    stream: ContextManager[BinaryIO], chunk_size: int = 1024 * 1024
) -> Iterator[bytes]:
    with stream as file:
        while chunk := file.read(chunk_size):
            yield chunk
