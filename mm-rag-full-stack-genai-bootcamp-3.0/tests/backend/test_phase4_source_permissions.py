from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete

from backend.app.core.config import get_settings
from backend.app.db.base import Base
from backend.app.db.rls import DatabasePurpose, set_rls_context
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.models import (
    Document,
    DocumentVersion,
    SourcePermissionSnapshot,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
)
from backend.app.services.source_permissions import (
    SourcePermissionEnvelope,
    SourcePermissionRejectedError,
    SourcePermissionService,
)
from backend.app.storage.keys import original_object_key


def test_permission_snapshot_is_append_only_current_and_fail_closed(test_settings) -> None:
    engine = create_database_engine(test_settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    owner_id, member_id = uuid4(), uuid4()
    workspace_id, document_id, version_id = uuid4(), uuid4(), uuid4()
    now = datetime.now(UTC)
    envelope = SourcePermissionEnvelope(
        workspace_id=workspace_id,
        document_id=document_id,
        document_version_id=version_id,
        source_namespace="future.enterprise-repository",
        source_item_ref_hash=hashlib.sha256(b"opaque-source-item").hexdigest(),
        sync_revision="sync:17",
        permission_revision="acl:9",
        principal_user_ids=(member_id,),
        verified_at=now - timedelta(minutes=1),
        valid_until=now + timedelta(hours=1),
    )
    try:
        with factory.begin() as session:
            session.add_all(
                [
                    User(id=owner_id, external_subject=f"test|{owner_id}"),
                    User(id=member_id, external_subject=f"test|{member_id}"),
                ]
            )
            session.flush()
            session.add(Workspace(id=workspace_id, name="Envelope", created_by_user_id=owner_id))
            session.flush()
            session.add_all(
                [
                    WorkspaceMembership(
                        workspace_id=workspace_id,
                        user_id=owner_id,
                        role=WorkspaceRole.OWNER.value,
                    ),
                    WorkspaceMembership(
                        workspace_id=workspace_id,
                        user_id=member_id,
                        role=WorkspaceRole.MEMBER.value,
                    ),
                ]
            )
            session.flush()
            session.add(
                Document(
                    id=document_id,
                    workspace_id=workspace_id,
                    created_by_user_id=owner_id,
                    title="Imported",
                    original_filename="imported.txt",
                    media_type="text/plain",
                )
            )
            session.flush()
            session.add(
                DocumentVersion(
                    id=version_id,
                    document_id=document_id,
                    workspace_id=workspace_id,
                    created_by_user_id=owner_id,
                    version_number=1,
                    content_sha256="a" * 64,
                    ingestion_fingerprint="b" * 64,
                    object_key=original_object_key(
                        workspace_id=workspace_id,
                        document_id=document_id,
                        version_id=version_id,
                    ),
                    byte_size=1,
                    status="uploaded",
                )
            )

        with factory.begin() as session:
            service = SourcePermissionService(session)
            snapshot, created = service.record(envelope)
            assert created
            snapshot_id = snapshot.id
            assert service.require_current(
                workspace_id=workspace_id,
                document_id=document_id,
                document_version_id=version_id,
                snapshot_id=snapshot_id,
                now=now,
            ) == frozenset({member_id})
            replay, created = service.record(envelope)
            assert not created and replay.id == snapshot_id

        with factory.begin() as session:
            service = SourcePermissionService(session)
            with pytest.raises(SourcePermissionRejectedError):
                service.require_current(
                    workspace_id=workspace_id,
                    document_id=document_id,
                    document_version_id=version_id,
                    snapshot_id=snapshot_id,
                    now=envelope.valid_until + timedelta(seconds=1),
                )
            persisted = session.get(SourcePermissionSnapshot, snapshot_id)
            assert persisted is not None
            fingerprint = persisted.permission_fingerprint
            persisted.permission_fingerprint = "f" * 64
            session.flush()
            with pytest.raises(SourcePermissionRejectedError):
                service.require_current(
                    workspace_id=workspace_id,
                    document_id=document_id,
                    document_version_id=version_id,
                    snapshot_id=snapshot_id,
                    now=now,
                )
            persisted.permission_fingerprint = fingerprint
            membership = session.get(WorkspaceMembership, (workspace_id, member_id))
            assert membership is not None
            session.delete(membership)

        with factory.begin() as session:
            with pytest.raises(SourcePermissionRejectedError):
                SourcePermissionService(session).require_current(
                    workspace_id=workspace_id,
                    document_id=document_id,
                    document_version_id=version_id,
                    snapshot_id=snapshot_id,
                    now=now,
                )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda item: replace(item, schema_version=2),
        lambda item: replace(item, unresolved_principal_count=1),
        lambda item: replace(item, semantics_supported=False),
        lambda item: replace(item, valid_until=datetime(2020, 1, 1, tzinfo=UTC)),
    ],
)
def test_permission_snapshot_rejects_unsupported_or_stale_contract(
    mutate: Callable[[SourcePermissionEnvelope], SourcePermissionEnvelope],
) -> None:
    now = datetime.now(UTC)
    baseline = SourcePermissionEnvelope(
        workspace_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        source_namespace="future.source",
        source_item_ref_hash="a" * 64,
        sync_revision="sync-1",
        permission_revision="acl-1",
        principal_user_ids=(),
        verified_at=now - timedelta(minutes=1),
        valid_until=now + timedelta(minutes=5),
    )
    envelope = mutate(baseline)
    with pytest.raises(SourcePermissionRejectedError):
        SourcePermissionService._validate(envelope, now=now)


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("MM_RAG_RUN_INTEGRATION_TESTS") != "1",
    reason="Set MM_RAG_RUN_INTEGRATION_TESTS=1 with PostgreSQL running",
)
def test_permission_snapshot_rls_hides_another_workspace() -> None:
    engine = create_database_engine(get_settings())
    factory = create_session_factory(engine)
    first_user_id, second_user_id = uuid4(), uuid4()
    first_workspace_id, second_workspace_id = uuid4(), uuid4()
    document_id, version_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    envelope = SourcePermissionEnvelope(
        workspace_id=first_workspace_id,
        document_id=document_id,
        document_version_id=version_id,
        source_namespace="future.integration",
        source_item_ref_hash=hashlib.sha256(b"integration-item").hexdigest(),
        sync_revision=f"sync-{uuid4()}",
        permission_revision="acl-1",
        principal_user_ids=(first_user_id,),
        verified_at=now - timedelta(minutes=1),
        valid_until=now + timedelta(hours=1),
    )
    try:
        with factory.begin() as session:
            session.add_all(
                [
                    User(id=first_user_id, external_subject=f"test|{first_user_id}"),
                    User(id=second_user_id, external_subject=f"test|{second_user_id}"),
                ]
            )
            session.flush()
            session.add_all(
                [
                    Workspace(
                        id=first_workspace_id,
                        name="Permission first",
                        created_by_user_id=first_user_id,
                    ),
                    Workspace(
                        id=second_workspace_id,
                        name="Permission second",
                        created_by_user_id=second_user_id,
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    WorkspaceMembership(
                        workspace_id=first_workspace_id,
                        user_id=first_user_id,
                        role=WorkspaceRole.OWNER.value,
                    ),
                    WorkspaceMembership(
                        workspace_id=second_workspace_id,
                        user_id=second_user_id,
                        role=WorkspaceRole.OWNER.value,
                    ),
                ]
            )
            session.flush()
            session.add(
                Document(
                    id=document_id,
                    workspace_id=first_workspace_id,
                    created_by_user_id=first_user_id,
                    title="Permission integration",
                    original_filename="permission.txt",
                    media_type="text/plain",
                )
            )
            session.flush()
            session.add(
                DocumentVersion(
                    id=version_id,
                    document_id=document_id,
                    workspace_id=first_workspace_id,
                    created_by_user_id=first_user_id,
                    version_number=1,
                    content_sha256="a" * 64,
                    ingestion_fingerprint="b" * 64,
                    object_key=original_object_key(
                        workspace_id=first_workspace_id,
                        document_id=document_id,
                        version_id=version_id,
                    ),
                    byte_size=1,
                    status="uploaded",
                )
            )

        with factory.begin() as session:
            set_rls_context(
                session,
                purpose=DatabasePurpose.API,
                workspace_id=first_workspace_id,
                principal_id=first_user_id,
            )
            snapshot, created = SourcePermissionService(session).record(envelope)
            assert created
            snapshot_id = snapshot.id

        with factory.begin() as session:
            set_rls_context(
                session,
                purpose=DatabasePurpose.API,
                workspace_id=second_workspace_id,
                principal_id=second_user_id,
            )
            with pytest.raises(SourcePermissionRejectedError):
                SourcePermissionService(session).require_current(
                    workspace_id=first_workspace_id,
                    document_id=document_id,
                    document_version_id=version_id,
                    snapshot_id=snapshot_id,
                    now=now,
                )
    finally:
        with factory.begin() as session:
            session.execute(delete(Document).where(Document.id == document_id))
            session.execute(
                delete(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id.in_(
                        [first_workspace_id, second_workspace_id]
                    )
                )
            )
            session.execute(
                delete(Workspace).where(
                    Workspace.id.in_([first_workspace_id, second_workspace_id])
                )
            )
            session.execute(
                delete(User).where(User.id.in_([first_user_id, second_user_id]))
            )
        engine.dispose()
