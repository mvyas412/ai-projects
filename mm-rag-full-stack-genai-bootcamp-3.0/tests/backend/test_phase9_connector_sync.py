from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.connectors.base import ChangeKind, ConnectorChange
from backend.app.db.base import Base
from backend.app.models import ConnectorInstallation, User, Workspace
from backend.app.services.connector_sync import (
    ConnectorSyncConflictError,
    ConnectorSyncStateMachine,
)


@pytest.fixture
def sync_session() -> Iterator[tuple[Session, Workspace, ConnectorInstallation]]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    user = User(external_subject=f"test|{uuid4()}")
    session.add(user)
    session.flush()
    workspace = Workspace(name="Enterprise", created_by_user_id=user.id)
    session.add(workspace)
    session.flush()
    connector = ConnectorInstallation(
        workspace_id=workspace.id,
        kind="google_drive",
        name="Learning Drive",
        credential_reference="vault://opaque/reference",
        checkpoint_cursor="base-token",
    )
    session.add(connector)
    session.commit()
    yield session, workspace, connector
    session.close()


def test_sync_checkpoint_promotes_only_with_active_fence(sync_session) -> None:
    session, workspace, connector = sync_session
    machine = ConnectorSyncStateMachine(session)
    now = datetime(2026, 9, 19, 20, 0, tzinfo=UTC)

    run = machine.create_run(
        workspace_id=workspace.id,
        connector_id=connector.id,
        idempotency_key="daily:2026-09-19",
        trigger="reconciliation",
    )
    attempt = machine.claim(
        workspace_id=workspace.id,
        run_id=run.id,
        worker_id="sync-worker-1",
        now=now,
        lease=timedelta(minutes=5),
    )
    machine.complete(
        workspace_id=workspace.id,
        run_id=run.id,
        attempt_id=attempt.id,
        fencing_token=attempt.fencing_token,
        checkpoint_cursor="next-token",
        now=now,
    )
    session.commit()

    session.refresh(connector)
    assert connector.checkpoint_cursor == "next-token"
    assert connector.revision == 2
    assert run.state == "succeeded"
    assert attempt.state == "succeeded"


def test_sync_run_replay_is_idempotent(sync_session) -> None:
    session, workspace, connector = sync_session
    machine = ConnectorSyncStateMachine(session)
    arguments = {
        "workspace_id": workspace.id,
        "connector_id": connector.id,
        "idempotency_key": "webhook:event-42",
        "trigger": "webhook_hint",
    }

    first = machine.create_run(**arguments)
    second = machine.create_run(**arguments)

    assert first.id == second.id


def test_deletion_and_permission_contraction_fail_closed(sync_session) -> None:
    session, workspace, connector = sync_session
    machine = ConnectorSyncStateMachine(session)
    now = datetime(2026, 9, 19, 20, 0, tzinfo=UTC)
    run = machine.create_run(
        workspace_id=workspace.id,
        connector_id=connector.id,
        idempotency_key="manual:1",
        trigger="manual",
    )
    attempt = machine.claim(
        workspace_id=workspace.id,
        run_id=run.id,
        worker_id="worker",
        now=now,
        lease=timedelta(minutes=5),
    )
    denied = machine.apply_change(
        workspace_id=workspace.id,
        run_id=run.id,
        attempt_id=attempt.id,
        fencing_token=attempt.fencing_token,
        change=ConnectorChange("seq-1", ChangeKind.PERMISSIONS, "file-1", "1"),
        permission_fingerprint="a" * 64,
        permission_contracts=True,
        now=now,
    )
    deleted = machine.apply_change(
        workspace_id=workspace.id,
        run_id=run.id,
        attempt_id=attempt.id,
        fencing_token=attempt.fencing_token,
        change=ConnectorChange("seq-2", ChangeKind.DELETE, "file-2"),
        permission_fingerprint="b" * 64,
        now=now,
    )

    assert denied.visibility_state == "denied"
    assert deleted.visibility_state == "deleted"
    assert deleted.deleted_at == now


def test_stale_attempt_cannot_mutate_sync(sync_session) -> None:
    session, workspace, connector = sync_session
    machine = ConnectorSyncStateMachine(session)
    now = datetime(2026, 9, 19, 20, 0, tzinfo=UTC)
    run = machine.create_run(
        workspace_id=workspace.id,
        connector_id=connector.id,
        idempotency_key="manual:2",
        trigger="manual",
    )
    attempt = machine.claim(
        workspace_id=workspace.id,
        run_id=run.id,
        worker_id="worker",
        now=now,
        lease=timedelta(minutes=5),
    )

    with pytest.raises(ConnectorSyncConflictError, match="no longer active"):
        machine.apply_change(
            workspace_id=workspace.id,
            run_id=run.id,
            attempt_id=attempt.id,
            fencing_token=attempt.fencing_token + 1,
            change=ConnectorChange("seq", ChangeKind.UPSERT, "file", "1"),
            permission_fingerprint="c" * 64,
        )
