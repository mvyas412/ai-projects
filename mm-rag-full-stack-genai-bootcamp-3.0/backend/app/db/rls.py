from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session


class DatabasePurpose(StrEnum):
    API = "api"
    WORKER = "worker"
    DISPATCHER = "dispatcher"
    OPERATIONS = "operations"


_ROLE_BY_PURPOSE = {
    DatabasePurpose.API: "mm_rag_api",
    DatabasePurpose.WORKER: "mm_rag_worker",
    DatabasePurpose.DISPATCHER: "mm_rag_dispatcher",
    DatabasePurpose.OPERATIONS: "mm_rag_operations",
}


def set_rls_context(
    session: Session,
    *,
    purpose: DatabasePurpose,
    workspace_id: UUID | None = None,
    principal_id: UUID | None = None,
    job_id: UUID | None = None,
) -> UUID | None:
    """Apply transaction-local effective role and trusted tenant context."""

    if session.get_bind().dialect.name != "postgresql":
        if workspace_id is None and job_id is not None:
            return _job_workspace(session, job_id)
        return workspace_id
    if not session.in_transaction():
        raise RuntimeError("RLS context requires an active transaction")

    role = _ROLE_BY_PURPOSE[purpose]
    session.execute(text(f"SET LOCAL ROLE {role}"))
    _set_local(session, "mm_rag.purpose", purpose.value)
    _set_local(session, "mm_rag.principal_id", str(principal_id) if principal_id else "")
    _set_local(session, "mm_rag.job_id", str(job_id) if job_id else "")
    _set_local(session, "mm_rag.workspace_id", str(workspace_id) if workspace_id else "")

    if workspace_id is None and job_id is not None:
        workspace_id = _job_workspace(session, job_id)
        if workspace_id is not None:
            _set_local(session, "mm_rag.workspace_id", str(workspace_id))
    return workspace_id


def _set_local(session: Session, name: str, value: str) -> None:
    session.execute(
        text("SELECT set_config(:name, :value, true)"),
        {"name": name, "value": value},
    )


def _job_workspace(session: Session, job_id: UUID) -> UUID | None:
    from backend.app.models.ingestion import IngestionJob

    return session.scalar(
        select(IngestionJob.workspace_id).where(IngestionJob.id == job_id)
    )
