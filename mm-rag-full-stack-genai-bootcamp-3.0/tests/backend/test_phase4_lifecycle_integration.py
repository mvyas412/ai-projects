from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from qdrant_client import QdrantClient, models
from sqlalchemy import delete, select

from backend.app.core.config import get_settings
from backend.app.db.rls import DatabasePurpose, set_rls_context
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.models import (
    AuditEvent,
    Document,
    DocumentVersion,
    LifecycleDeletionPlan,
    LifecyclePlanState,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
)
from backend.app.retrieval.scope import VectorScope
from backend.app.services.lifecycle import LifecycleService
from backend.app.storage.factory import create_artifact_storage, create_object_storage
from backend.app.storage.keys import original_object_key
from backend.app.storage.s3 import S3ObjectStorage


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("MM_RAG_RUN_INTEGRATION_TESTS") != "1"
    or os.getenv("MM_RAG_RUN_S3_INTEGRATION_TESTS") != "1",
    reason="Set the integration flags with PostgreSQL, Qdrant, and SeaweedFS running",
)
def test_live_document_purge_reconciles_postgres_qdrant_and_seaweedfs() -> None:
    base_settings = get_settings()
    collection = f"phase4_lifecycle_{uuid4().hex}"
    settings = base_settings.model_copy(update={"qdrant_collection_name": collection})
    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    qdrant = QdrantClient(
        url=settings.qdrant_url,
        api_key=(
            settings.qdrant_api_key.get_secret_value()
            if settings.qdrant_api_key is not None
            else None
        ),
        check_compatibility=False,
    )
    originals = create_object_storage(settings)
    artifacts = create_artifact_storage(settings)
    user = User(id=uuid4(), external_subject=f"test|lifecycle-{uuid4()}")
    workspace_id, document_id, version_id = uuid4(), uuid4(), uuid4()
    content = b"phase 4 governed live lifecycle"
    object_key = original_object_key(
        workspace_id=workspace_id,
        document_id=document_id,
        version_id=version_id,
    )
    point_id = str(uuid4())
    audit_id = uuid4()
    plan_id: UUID | None = None
    try:
        qdrant.create_collection(
            collection_name=collection,
            vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE),
        )
        qdrant.upsert(
            collection_name=collection,
            wait=True,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=[1.0, 0.0],
                    payload={**VectorScope(workspace_id, document_id, version_id).payload()},
                )
            ],
        )
        originals.put(object_key, content, media_type="text/plain")
        with factory.begin() as session:
            session.add(user)
            session.flush()
            session.add(
                Workspace(
                    id=workspace_id,
                    name="Lifecycle integration",
                    created_by_user_id=user.id,
                )
            )
            session.flush()
            session.add(
                WorkspaceMembership(
                    workspace_id=workspace_id,
                    user_id=user.id,
                    role=WorkspaceRole.OWNER.value,
                )
            )
            session.flush()
            session.add(
                Document(
                    id=document_id,
                    workspace_id=workspace_id,
                    created_by_user_id=user.id,
                    title="Governed",
                    original_filename="governed.txt",
                    media_type="text/plain",
                )
            )
            session.flush()
            session.add(
                DocumentVersion(
                    id=version_id,
                    document_id=document_id,
                    workspace_id=workspace_id,
                    created_by_user_id=user.id,
                    version_number=1,
                    content_sha256=hashlib.sha256(content).hexdigest(),
                    ingestion_fingerprint="b" * 64,
                    object_key=object_key,
                    byte_size=len(content),
                    status="ready",
                )
            )
            session.add(
                AuditEvent(
                    id=audit_id,
                    workspace_id=workspace_id,
                    actor_kind="user",
                    actor_user_id=user.id,
                    action="test.retention_seed",
                    resource_type="workspace",
                    resource_id=workspace_id,
                    result="succeeded",
                    policy_revision="phase4-v1",
                    correlation_id=str(audit_id),
                    schema_version=1,
                    details={},
                    created_at=datetime.now(UTC) - timedelta(days=366),
                )
            )

        with factory() as session:
            plan = LifecycleService(
                session, settings, originals, artifacts, qdrant
            ).request_document_deletion(
                user=user,
                workspace_id=workspace_id,
                document_id=document_id,
            )
            plan_id = plan.id
        with factory.begin() as session:
            loaded_plan = session.get(LifecycleDeletionPlan, plan_id)
            assert loaded_plan is not None
            loaded_plan.execute_after = datetime.now(UTC) - timedelta(seconds=1)
        with factory() as session:
            service = LifecycleService(session, settings, originals, artifacts, qdrant)
            preview = service.preview_retention(user=user, workspace_id=workspace_id)
            result = service.apply_retention(
                user=user,
                workspace_id=workspace_id,
                preview_token=preview.scope.token,
            )
            if result.completed_plans != 1:
                with factory() as diagnostic_session:
                    blocked_plan = diagnostic_session.get(
                        LifecycleDeletionPlan, plan_id
                    )
                    pytest.fail(
                        "lifecycle purge blocked: "
                        f"{blocked_plan.last_error_code if blocked_plan else 'missing'} / "
                        f"{blocked_plan.last_error_message if blocked_plan else 'missing'} / "
                        f"checkpoints="
                        f"{bool(blocked_plan and blocked_plan.vectors_deleted_at)},"
                        f"{bool(blocked_plan and blocked_plan.artifacts_deleted_at)},"
                        f"{bool(blocked_plan and blocked_plan.originals_deleted_at)},"
                        f"{bool(blocked_plan and blocked_plan.metadata_deleted_at)}"
                    )
            assert result.blocked_plans == 0
            assert result.deleted_security_audit_events == 1

        assert not originals.exists(object_key)
        count = qdrant.count(
            collection_name=collection,
            count_filter=VectorScope(workspace_id, document_id, version_id).filter(),
            exact=True,
        )
        assert count.count == 0
        with factory() as session:
            assert session.get(Document, document_id) is None
            loaded_plan = session.get(LifecycleDeletionPlan, plan_id)
            assert (
                loaded_plan is not None
                and loaded_plan.state == LifecyclePlanState.COMPLETED.value
            )
            assert session.get(AuditEvent, audit_id) is None
        with factory.begin() as session:
            set_rls_context(
                session,
                purpose=DatabasePurpose.API,
                workspace_id=workspace_id,
                principal_id=uuid4(),
            )
            assert session.scalar(
                select(LifecycleDeletionPlan.id).where(
                    LifecycleDeletionPlan.id == plan_id
                )
            ) is None
    finally:
        originals.delete(object_key)
        if qdrant.collection_exists(collection):
            qdrant.delete_collection(collection)
        with factory.begin() as session:
            session.execute(delete(Workspace).where(Workspace.id == workspace_id))
            session.execute(delete(User).where(User.id == user.id))
        if isinstance(originals, S3ObjectStorage):
            originals.close()
        if isinstance(artifacts, S3ObjectStorage):
            artifacts.close()
        qdrant.close()
        engine.dispose()
