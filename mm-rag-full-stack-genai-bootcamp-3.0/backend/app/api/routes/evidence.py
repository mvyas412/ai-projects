from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_artifact_storage, get_current_user
from backend.app.db.session import get_db_session
from backend.app.models import User
from backend.app.schemas.evidence import EvidenceDescriptor
from backend.app.services.evidence import (
    EvidenceError,
    EvidenceIntegrityError,
    EvidenceNotFoundError,
    EvidenceService,
)
from backend.app.storage.base import ObjectStorage

router = APIRouter(
    prefix=(
        "/workspaces/{workspace_id}/conversations/{conversation_id}/messages/"
        "{message_id}/evidence/{citation_index}"
    ),
    tags=["evidence"],
)


def _translate(exc: EvidenceError) -> HTTPException:
    if isinstance(exc, EvidenceNotFoundError):
        return HTTPException(status_code=404, detail="Evidence is unavailable")
    if isinstance(exc, EvidenceIntegrityError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Evidence is temporarily unavailable",
        )
    return HTTPException(status_code=500, detail="Evidence could not be resolved")


@router.get("", response_model=EvidenceDescriptor, summary="Resolve cited evidence")
def get_evidence(
    workspace_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    citation_index: int,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_artifact_storage)],
) -> EvidenceDescriptor:
    try:
        return EvidenceService(session, storage).describe(
            user=user,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            citation_index=citation_index,
        )
    except EvidenceError as exc:
        raise _translate(exc) from exc


@router.get(
    "/artifacts/{artifact_id}",
    summary="Stream an authorized cited artifact",
)
def get_evidence_artifact(
    workspace_id: UUID,
    conversation_id: UUID,
    message_id: UUID,
    citation_index: int,
    artifact_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_artifact_storage)],
) -> StreamingResponse:
    try:
        artifact = EvidenceService(session, storage).artifact_content(
            user=user,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            message_id=message_id,
            citation_index=citation_index,
            artifact_id=artifact_id,
        )
    except EvidenceError as exc:
        raise _translate(exc) from exc
    return StreamingResponse(
        _one_chunk(artifact.content),
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": f'inline; filename="{artifact.filename}"',
            "Content-Length": str(len(artifact.content)),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _one_chunk(content: bytes) -> Iterator[bytes]:
    yield content
