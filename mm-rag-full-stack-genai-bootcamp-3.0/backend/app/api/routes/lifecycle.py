from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from qdrant_client import QdrantClient
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    get_artifact_storage,
    get_current_user,
    get_object_storage,
    get_qdrant_client,
)
from backend.app.db.session import get_db_session
from backend.app.models.lifecycle import LifecycleResourceType
from backend.app.models.user import User
from backend.app.schemas.lifecycle import (
    LifecyclePlanResponse,
    OrphanInventoryResponse,
    RetentionApplyRequest,
    RetentionApplyResponse,
    RetentionHoldRequest,
    RetentionHoldResponse,
    RetentionPreviewResponse,
)
from backend.app.services.lifecycle import (
    LifecycleConflictError,
    LifecycleDependencyError,
    LifecycleError,
    LifecycleNotFoundError,
    LifecyclePermissionError,
    LifecyclePreviewChangedError,
    LifecycleService,
)
from backend.app.storage.base import ObjectStorage

router = APIRouter(prefix="/workspaces/{workspace_id}/governance", tags=["governance"])


def _service(
    request: Request,
    session: Session,
    originals: ObjectStorage,
    artifacts: ObjectStorage,
    qdrant: QdrantClient,
) -> LifecycleService:
    return LifecycleService(
        session,
        request.app.state.settings,
        originals,
        artifacts,
        qdrant,
    )


def _translate(exc: LifecycleError) -> HTTPException:
    if isinstance(exc, LifecycleNotFoundError):
        return HTTPException(status_code=404, detail="Resource not found")
    if isinstance(exc, LifecyclePermissionError):
        return HTTPException(status_code=403, detail="Insufficient access")
    if isinstance(exc, (LifecyclePreviewChangedError, LifecycleConflictError)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, LifecycleDependencyError):
        return HTTPException(status_code=503, detail="A governed store is unavailable")
    return HTTPException(status_code=500, detail="The lifecycle operation failed")


@router.post(
    "/documents/{document_id}/deletion",
    response_model=LifecyclePlanResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_document_deletion(
    workspace_id: UUID,
    document_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    originals: Annotated[ObjectStorage, Depends(get_object_storage)],
    artifacts: Annotated[ObjectStorage, Depends(get_artifact_storage)],
    qdrant: Annotated[QdrantClient, Depends(get_qdrant_client)],
) -> LifecyclePlanResponse:
    try:
        plan = _service(request, session, originals, artifacts, qdrant).request_document_deletion(
            user=user, workspace_id=workspace_id, document_id=document_id
        )
    except LifecycleError as exc:
        raise _translate(exc) from exc
    return LifecyclePlanResponse.model_validate(plan)


@router.post(
    "/documents/{document_id}/restore",
    status_code=status.HTTP_204_NO_CONTENT,
)
def restore_document(
    workspace_id: UUID,
    document_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    originals: Annotated[ObjectStorage, Depends(get_object_storage)],
    artifacts: Annotated[ObjectStorage, Depends(get_artifact_storage)],
    qdrant: Annotated[QdrantClient, Depends(get_qdrant_client)],
) -> None:
    try:
        _service(request, session, originals, artifacts, qdrant).restore_document(
            user=user, workspace_id=workspace_id, document_id=document_id
        )
    except LifecycleError as exc:
        raise _translate(exc) from exc


@router.post(
    "/conversations/{conversation_id}/deletion",
    response_model=LifecyclePlanResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_conversation_deletion(
    workspace_id: UUID,
    conversation_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    originals: Annotated[ObjectStorage, Depends(get_object_storage)],
    artifacts: Annotated[ObjectStorage, Depends(get_artifact_storage)],
    qdrant: Annotated[QdrantClient, Depends(get_qdrant_client)],
) -> LifecyclePlanResponse:
    try:
        plan = _service(
            request, session, originals, artifacts, qdrant
        ).request_conversation_deletion(
            user=user, workspace_id=workspace_id, conversation_id=conversation_id
        )
    except LifecycleError as exc:
        raise _translate(exc) from exc
    return LifecyclePlanResponse.model_validate(plan)


@router.post(
    "/conversations/{conversation_id}/restore",
    status_code=status.HTTP_204_NO_CONTENT,
)
def restore_conversation(
    workspace_id: UUID,
    conversation_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    originals: Annotated[ObjectStorage, Depends(get_object_storage)],
    artifacts: Annotated[ObjectStorage, Depends(get_artifact_storage)],
    qdrant: Annotated[QdrantClient, Depends(get_qdrant_client)],
) -> None:
    try:
        _service(request, session, originals, artifacts, qdrant).restore_conversation(
            user=user, workspace_id=workspace_id, conversation_id=conversation_id
        )
    except LifecycleError as exc:
        raise _translate(exc) from exc


@router.put(
    "/holds/{resource_type}/{resource_id}",
    response_model=RetentionHoldResponse,
)
def place_retention_hold(
    workspace_id: UUID,
    resource_type: LifecycleResourceType,
    resource_id: UUID,
    payload: RetentionHoldRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    originals: Annotated[ObjectStorage, Depends(get_object_storage)],
    artifacts: Annotated[ObjectStorage, Depends(get_artifact_storage)],
    qdrant: Annotated[QdrantClient, Depends(get_qdrant_client)],
) -> RetentionHoldResponse:
    try:
        hold = _service(request, session, originals, artifacts, qdrant).place_hold(
            user=user,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
            reason_code=payload.reason_code,
        )
    except LifecycleError as exc:
        raise _translate(exc) from exc
    return RetentionHoldResponse.model_validate(hold)


@router.delete(
    "/holds/{resource_type}/{resource_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_retention_hold(
    workspace_id: UUID,
    resource_type: LifecycleResourceType,
    resource_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    originals: Annotated[ObjectStorage, Depends(get_object_storage)],
    artifacts: Annotated[ObjectStorage, Depends(get_artifact_storage)],
    qdrant: Annotated[QdrantClient, Depends(get_qdrant_client)],
) -> None:
    try:
        _service(request, session, originals, artifacts, qdrant).remove_hold(
            user=user,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
    except LifecycleError as exc:
        raise _translate(exc) from exc


@router.get("/retention/preview", response_model=RetentionPreviewResponse)
def preview_retention(
    workspace_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    originals: Annotated[ObjectStorage, Depends(get_object_storage)],
    artifacts: Annotated[ObjectStorage, Depends(get_artifact_storage)],
    qdrant: Annotated[QdrantClient, Depends(get_qdrant_client)],
) -> RetentionPreviewResponse:
    try:
        preview = _service(request, session, originals, artifacts, qdrant).preview_retention(
            user=user, workspace_id=workspace_id
        )
    except LifecycleError as exc:
        raise _translate(exc) from exc
    return RetentionPreviewResponse(
        policy_revision=preview.policy_revision,
        generated_at=preview.generated_at,
        preview_token=preview.scope.token,
        due_document_deletions=preview.due_document_deletions,
        due_conversation_deletions=preview.due_conversation_deletions,
        inactive_generations=len(preview.scope.generations),
        terminal_jobs=len(preview.scope.jobs),
        security_audit_events=len(preview.scope.audits),
        orphan_objects=len(preview.scope.orphans),
    )


@router.post("/retention/orphan-inventory", response_model=OrphanInventoryResponse)
def inventory_orphan_objects(
    workspace_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    originals: Annotated[ObjectStorage, Depends(get_object_storage)],
    artifacts: Annotated[ObjectStorage, Depends(get_artifact_storage)],
    qdrant: Annotated[QdrantClient, Depends(get_qdrant_client)],
) -> OrphanInventoryResponse:
    try:
        result = _service(request, session, originals, artifacts, qdrant).inventory_orphans(
            user=user, workspace_id=workspace_id
        )
    except LifecycleError as exc:
        raise _translate(exc) from exc
    return OrphanInventoryResponse(
        observed_objects=result.observed_objects,
        orphan_objects=result.orphan_objects,
        new_evidence=result.new_evidence,
        cleared_evidence=result.cleared_evidence,
    )


@router.post("/retention/apply", response_model=RetentionApplyResponse)
def apply_retention(
    workspace_id: UUID,
    payload: RetentionApplyRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    originals: Annotated[ObjectStorage, Depends(get_object_storage)],
    artifacts: Annotated[ObjectStorage, Depends(get_artifact_storage)],
    qdrant: Annotated[QdrantClient, Depends(get_qdrant_client)],
) -> RetentionApplyResponse:
    try:
        result = _service(request, session, originals, artifacts, qdrant).apply_retention(
            user=user,
            workspace_id=workspace_id,
            preview_token=payload.preview_token,
        )
    except LifecycleError as exc:
        raise _translate(exc) from exc
    return RetentionApplyResponse(
        policy_revision=result.policy_revision,
        completed_plans=result.completed_plans,
        blocked_plans=result.blocked_plans,
        deleted_inactive_generations=result.deleted_inactive_generations,
        deleted_terminal_jobs=result.deleted_terminal_jobs,
        deleted_security_audit_events=result.deleted_security_audit_events,
        deleted_orphan_objects=result.deleted_orphan_objects,
    )
