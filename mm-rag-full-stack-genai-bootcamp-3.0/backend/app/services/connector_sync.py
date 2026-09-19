from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.connectors.base import ChangeKind, ConnectorChange
from backend.app.models.enterprise import (
    ConnectorInstallation,
    ConnectorSourceObject,
    ConnectorSyncAttempt,
    ConnectorSyncRun,
)


class ConnectorSyncError(Exception):
    """Base class for non-disclosing durable connector-sync failures."""


class ConnectorSyncConflictError(ConnectorSyncError):
    pass


class ConnectorSyncStateMachine:
    """Own connector checkpoints and deny-first source visibility transactionally."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_run(
        self,
        *,
        workspace_id: UUID,
        connector_id: UUID,
        idempotency_key: str,
        trigger: str,
    ) -> ConnectorSyncRun:
        existing = self._session.scalar(
            select(ConnectorSyncRun).where(
                ConnectorSyncRun.workspace_id == workspace_id,
                ConnectorSyncRun.connector_id == connector_id,
                ConnectorSyncRun.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return existing
        connector = self._connector(workspace_id, connector_id, for_update=True)
        if connector.state != "active":
            raise ConnectorSyncConflictError("The connector is not active")
        run = ConnectorSyncRun(
            workspace_id=workspace_id,
            connector_id=connector_id,
            idempotency_key=idempotency_key,
            trigger=trigger,
            base_cursor=connector.checkpoint_cursor,
        )
        self._session.add(run)
        self._session.flush()
        return run

    def claim(
        self,
        *,
        workspace_id: UUID,
        run_id: UUID,
        worker_id: str,
        now: datetime,
        lease: timedelta,
    ) -> ConnectorSyncAttempt:
        run = self._run(workspace_id, run_id, for_update=True)
        if run.state not in {"pending", "retry_scheduled"}:
            raise ConnectorSyncConflictError("The sync run is not claimable")
        if run.attempt_count >= run.max_attempts or lease <= timedelta(0):
            raise ConnectorSyncConflictError("The sync run cannot be claimed")
        run.attempt_count += 1
        run.fencing_token += 1
        run.state = "running"
        attempt = ConnectorSyncAttempt(
            workspace_id=workspace_id,
            run_id=run.id,
            attempt_number=run.attempt_count,
            fencing_token=run.fencing_token,
            worker_id=worker_id,
            lease_expires_at=_utc(now) + lease,
            started_at=_utc(now),
        )
        self._session.add(attempt)
        self._session.flush()
        return attempt

    def apply_change(
        self,
        *,
        workspace_id: UUID,
        run_id: UUID,
        attempt_id: UUID,
        fencing_token: int,
        change: ConnectorChange,
        permission_fingerprint: str,
        permission_contracts: bool = False,
        now: datetime | None = None,
    ) -> ConnectorSourceObject:
        run, _ = self._active_attempt(workspace_id, run_id, attempt_id, fencing_token)
        source = self._session.scalar(
            select(ConnectorSourceObject)
            .where(
                ConnectorSourceObject.workspace_id == workspace_id,
                ConnectorSourceObject.connector_id == run.connector_id,
                ConnectorSourceObject.external_id == change.object_external_id,
            )
            .with_for_update()
        )
        if source is not None and source.last_sequence == change.sequence:
            return source
        if source is None:
            source = ConnectorSourceObject(
                workspace_id=workspace_id,
                connector_id=run.connector_id,
                external_id=change.object_external_id,
                permission_fingerprint=permission_fingerprint,
                last_sequence=change.sequence,
            )
            self._session.add(source)
        source.version_external_id = change.version_external_id
        source.permission_fingerprint = permission_fingerprint
        source.last_sequence = change.sequence
        if change.kind is ChangeKind.DELETE:
            source.visibility_state = "deleted"
            source.deleted_at = _utc(now or datetime.now(UTC))
        elif permission_contracts:
            source.visibility_state = "denied"
        else:
            # Expansion remains hidden until content and ACL evidence are promoted.
            source.visibility_state = "pending"
            source.deleted_at = None
        self._session.flush()
        return source

    def promote_source(
        self,
        *,
        workspace_id: UUID,
        run_id: UUID,
        attempt_id: UUID,
        fencing_token: int,
        source_id: UUID,
        document_id: UUID,
        document_version_id: UUID,
    ) -> ConnectorSourceObject:
        self._active_attempt(workspace_id, run_id, attempt_id, fencing_token)
        source = self._session.scalar(
            select(ConnectorSourceObject)
            .where(
                ConnectorSourceObject.id == source_id,
                ConnectorSourceObject.workspace_id == workspace_id,
            )
            .with_for_update()
        )
        if source is None or source.visibility_state != "pending":
            raise ConnectorSyncConflictError("The source object is not promotable")
        source.document_id = document_id
        source.document_version_id = document_version_id
        source.visibility_state = "visible"
        self._session.flush()
        return source

    def complete(
        self,
        *,
        workspace_id: UUID,
        run_id: UUID,
        attempt_id: UUID,
        fencing_token: int,
        checkpoint_cursor: str,
        now: datetime,
    ) -> ConnectorSyncRun:
        run, attempt = self._active_attempt(workspace_id, run_id, attempt_id, fencing_token)
        connector = self._connector(workspace_id, run.connector_id, for_update=True)
        if connector.checkpoint_cursor != run.base_cursor:
            raise ConnectorSyncConflictError("The connector checkpoint changed")
        connector.checkpoint_cursor = checkpoint_cursor
        connector.last_reconciled_at = _utc(now)
        connector.revision += 1
        run.proposed_cursor = checkpoint_cursor
        run.state = "succeeded"
        run.completed_at = _utc(now)
        attempt.state = "succeeded"
        attempt.finished_at = _utc(now)
        self._session.flush()
        return run

    def _active_attempt(
        self,
        workspace_id: UUID,
        run_id: UUID,
        attempt_id: UUID,
        fencing_token: int,
    ) -> tuple[ConnectorSyncRun, ConnectorSyncAttempt]:
        run = self._run(workspace_id, run_id, for_update=True)
        attempt = self._session.scalar(
            select(ConnectorSyncAttempt)
            .where(
                ConnectorSyncAttempt.id == attempt_id,
                ConnectorSyncAttempt.workspace_id == workspace_id,
                ConnectorSyncAttempt.run_id == run_id,
            )
            .with_for_update()
        )
        if (
            attempt is None
            or run.state != "running"
            or attempt.state != "running"
            or run.fencing_token != fencing_token
            or attempt.fencing_token != fencing_token
        ):
            raise ConnectorSyncConflictError("The sync attempt is no longer active")
        return run, attempt

    def _connector(
        self, workspace_id: UUID, connector_id: UUID, *, for_update: bool
    ) -> ConnectorInstallation:
        query = select(ConnectorInstallation).where(
            ConnectorInstallation.id == connector_id,
            ConnectorInstallation.workspace_id == workspace_id,
        )
        connector = self._session.scalar(query.with_for_update() if for_update else query)
        if connector is None:
            raise ConnectorSyncConflictError("The connector was not found")
        return connector

    def _run(self, workspace_id: UUID, run_id: UUID, *, for_update: bool) -> ConnectorSyncRun:
        query = select(ConnectorSyncRun).where(
            ConnectorSyncRun.id == run_id,
            ConnectorSyncRun.workspace_id == workspace_id,
        )
        run = self._session.scalar(query.with_for_update() if for_update else query)
        if run is None:
            raise ConnectorSyncConflictError("The sync run was not found")
        return run


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
