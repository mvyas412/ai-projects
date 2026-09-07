from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError

from backend.app.core.config import get_settings
from backend.app.db.rls import DatabasePurpose, set_rls_context
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.models import (
    ArtifactKind,
    ArtifactValidationState,
    CalculationOperator,
    CalculationTrace,
    ContentArtifact,
    ContentRegion,
    ContentRegionKind,
    Document,
    DocumentVersion,
    IngestionAttempt,
    IngestionGeneration,
    IngestionJob,
    IngestionOperation,
    TableCell,
    TableLogicalType,
    TableRegion,
    TableValidationState,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspaceRole,
)


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("MM_RAG_RUN_INTEGRATION_TESTS") != "1",
    reason="Set MM_RAG_RUN_INTEGRATION_TESTS=1 with PostgreSQL running",
)
def test_table_evidence_is_tenant_scoped_and_immutable() -> None:
    engine = create_database_engine(get_settings())
    factory = create_session_factory(engine)
    user_id, workspace_id = uuid4(), uuid4()
    other_user_id, other_workspace_id = uuid4(), uuid4()
    document_id, version_id = uuid4(), uuid4()
    job_id, attempt_id, generation_id = uuid4(), uuid4(), uuid4()
    region_id, crop_id, normalized_id, table_id, trace_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    now = datetime.now(UTC)

    try:
        with factory.begin() as session:
            session.add_all(
                [
                    User(id=user_id, external_subject=f"test|table-rls-{user_id}"),
                    User(
                        id=other_user_id,
                        external_subject=f"test|table-rls-{other_user_id}",
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    Workspace(
                        id=workspace_id,
                        name="Table RLS",
                        created_by_user_id=user_id,
                    ),
                    Workspace(
                        id=other_workspace_id,
                        name="Other table RLS",
                        created_by_user_id=other_user_id,
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    WorkspaceMembership(
                        workspace_id=workspace_id,
                        user_id=user_id,
                        role=WorkspaceRole.MEMBER.value,
                    ),
                    WorkspaceMembership(
                        workspace_id=other_workspace_id,
                        user_id=other_user_id,
                        role=WorkspaceRole.MEMBER.value,
                    ),
                ]
            )
            session.flush()
            session.add(
                Document(
                    id=document_id,
                    workspace_id=workspace_id,
                    created_by_user_id=user_id,
                    title="Table evidence",
                    original_filename="table.pdf",
                    media_type="application/pdf",
                )
            )
            session.flush()
            session.add(
                DocumentVersion(
                    id=version_id,
                    document_id=document_id,
                    workspace_id=workspace_id,
                    created_by_user_id=user_id,
                    version_number=1,
                    content_sha256="a" * 64,
                    ingestion_fingerprint="b" * 64,
                    object_key=f"tests/{version_id}/original.pdf",
                    byte_size=1,
                    status="processing",
                )
            )
            session.flush()
            session.add(
                IngestionJob(
                    id=job_id,
                    workspace_id=workspace_id,
                    document_id=document_id,
                    document_version_id=version_id,
                    requested_by_user_id=user_id,
                    operation=IngestionOperation.INDEX_DOCUMENT_VERSION.value,
                    pipeline_fingerprint="c" * 64,
                    idempotency_key=f"table-rls-{job_id}",
                    request_hash="d" * 64,
                )
            )
            session.flush()
            session.add(
                IngestionAttempt(
                    id=attempt_id,
                    job_id=job_id,
                    workspace_id=workspace_id,
                    attempt_number=1,
                    fencing_token=1,
                    worker_id="phase6-rls-test",
                    lease_expires_at=now + timedelta(minutes=5),
                    last_heartbeat_at=now,
                )
            )
            session.flush()
            session.add(
                IngestionGeneration(
                    id=generation_id,
                    workspace_id=workspace_id,
                    document_id=document_id,
                    document_version_id=version_id,
                    job_id=job_id,
                    attempt_id=attempt_id,
                    pipeline_fingerprint="c" * 64,
                )
            )
            session.flush()
            session.add(
                ContentRegion(
                    id=region_id,
                    workspace_id=workspace_id,
                    document_id=document_id,
                    document_version_id=version_id,
                    generation_id=generation_id,
                    creation_attempt_id=attempt_id,
                    page_number=1,
                    kind=ContentRegionKind.TABLE.value,
                    ordinal=0,
                    bbox_x=0.1,
                    bbox_y=0.1,
                    bbox_width=0.8,
                    bbox_height=0.4,
                    page_width=612,
                    page_height=792,
                    rotation=0,
                    locator_schema_revision="visual-locator-v1",
                    locator_sha256="e" * 64,
                    page_render_sha256="f" * 64,
                    extractor_name="fixture",
                    extractor_revision="1",
                    extractor_config_sha256="1" * 64,
                    confidence=1.0,
                )
            )
            session.flush()
            session.add_all(
                [
                    ContentArtifact(
                        id=crop_id,
                        workspace_id=workspace_id,
                        document_id=document_id,
                        document_version_id=version_id,
                        generation_id=generation_id,
                        region_id=region_id,
                        creation_attempt_id=attempt_id,
                        kind=ArtifactKind.REGION_CROP.value,
                        object_key=f"tests/{generation_id}/crop.png",
                        media_type="image/png",
                        byte_size=1,
                        content_sha256="2" * 64,
                        producer_name="fixture",
                        producer_revision="1",
                        schema_revision="visual-artifact-v1",
                        validation_state=ArtifactValidationState.VALIDATED.value,
                    ),
                    ContentArtifact(
                        id=normalized_id,
                        workspace_id=workspace_id,
                        document_id=document_id,
                        document_version_id=version_id,
                        generation_id=generation_id,
                        region_id=region_id,
                        creation_attempt_id=attempt_id,
                        kind=ArtifactKind.NORMALIZED_JSON.value,
                        object_key=f"tests/{generation_id}/table.json",
                        media_type="application/json",
                        byte_size=1,
                        content_sha256="3" * 64,
                        producer_name="fixture",
                        producer_revision="1",
                        schema_revision="structured-table-v1",
                        validation_state=ArtifactValidationState.VALIDATED.value,
                    ),
                ]
            )
            session.flush()
            session.add(
                TableRegion(
                    id=table_id,
                    workspace_id=workspace_id,
                    document_id=document_id,
                    document_version_id=version_id,
                    generation_id=generation_id,
                    region_id=region_id,
                    creation_attempt_id=attempt_id,
                    source_crop_artifact_id=crop_id,
                    normalized_artifact_id=normalized_id,
                    page_number=1,
                    header_row_count=1,
                    row_count=2,
                    column_count=1,
                    structure_schema_revision="structured-table-v1",
                    structure_sha256="4" * 64,
                    extractor_name="fixture",
                    extractor_revision="1",
                    validation_state=TableValidationState.VALIDATED.value,
                    validation_codes=[],
                    confidence=1.0,
                )
            )
            session.flush()
            session.add(
                CalculationTrace(
                    id=trace_id,
                    workspace_id=workspace_id,
                    document_id=document_id,
                    document_version_id=version_id,
                    generation_id=generation_id,
                    table_id=table_id,
                    region_id=region_id,
                    table_creation_attempt_id=attempt_id,
                    operator=CalculationOperator.SUM.value,
                    operator_revision="table-calculation-v1",
                    cell_ids=[],
                    operand_types=[],
                    operand_values=[],
                    currency="USD",
                    rounding_rule="decimal-normalize-v1",
                    result_type="currency",
                    result_value="42",
                    query_fingerprint="5" * 64,
                )
            )

        with factory.begin() as session:
            set_rls_context(
                session,
                purpose=DatabasePurpose.API,
                workspace_id=workspace_id,
                principal_id=user_id,
            )
            assert session.scalar(select(TableRegion.id)) == table_id
            assert session.scalar(select(CalculationTrace.id)) == trace_id

        with factory.begin() as session:
            set_rls_context(
                session,
                purpose=DatabasePurpose.API,
                workspace_id=other_workspace_id,
                principal_id=other_user_id,
            )
            assert session.scalar(select(TableRegion.id)) is None
            assert session.scalar(select(CalculationTrace.id)) is None

        with pytest.raises(DBAPIError):
            with factory.begin() as session:
                set_rls_context(
                    session,
                    purpose=DatabasePurpose.OPERATIONS,
                    workspace_id=workspace_id,
                    principal_id=user_id,
                )
                session.add(
                    TableCell(
                        workspace_id=workspace_id,
                        document_id=uuid4(),
                        document_version_id=version_id,
                        generation_id=generation_id,
                        creation_attempt_id=attempt_id,
                        table_id=table_id,
                        row_index=1,
                        column_index=0,
                        row_span=1,
                        column_span=1,
                        is_header=False,
                        header_associations=[],
                        raw_text="42",
                        normalized_text="42",
                        logical_type=TableLogicalType.INTEGER.value,
                        normalized_value="42",
                        confidence=1.0,
                    )
                )
                session.flush()

        with pytest.raises(DBAPIError):
            with factory.begin() as session:
                set_rls_context(
                    session,
                    purpose=DatabasePurpose.API,
                    workspace_id=workspace_id,
                    principal_id=user_id,
                )
                table = session.get(TableRegion, table_id)
                assert table is not None
                table.validation_state = TableValidationState.REJECTED.value
                session.flush()
    finally:
        with factory.begin() as session:
            set_rls_context(
                session,
                purpose=DatabasePurpose.OPERATIONS,
                workspace_id=workspace_id,
                principal_id=user_id,
            )
            session.execute(delete(Document).where(Document.id == document_id))
            session.execute(
                delete(Workspace).where(
                    Workspace.id.in_([workspace_id, other_workspace_id])
                )
            )
            session.execute(
                delete(User).where(User.id.in_([user_id, other_user_id]))
            )
        engine.dispose()
