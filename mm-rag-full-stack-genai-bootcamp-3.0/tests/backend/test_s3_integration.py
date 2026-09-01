import hashlib
import os
from io import BytesIO
from uuid import uuid4

import pytest
from pydantic import SecretStr

from backend.app.core.config import Settings
from backend.app.models import Document, DocumentVersion
from backend.app.storage.authorized import resolve_original_object
from backend.app.storage.base import ObjectConflictError, ObjectIntegrityError
from backend.app.storage.factory import create_object_storage
from backend.app.storage.keys import original_object_key
from backend.app.storage.s3 import S3ObjectStorage


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("MM_RAG_RUN_S3_INTEGRATION_TESTS") != "1",
    reason="Set MM_RAG_RUN_S3_INTEGRATION_TESTS=1 with SeaweedFS running",
)
def test_seaweedfs_s3_provider_contract() -> None:
    configured = Settings()
    settings = Settings(
        object_storage_backend="s3",
        s3_endpoint_url=configured.s3_endpoint_url,
        s3_region=configured.s3_region,
        s3_access_key_id=configured.s3_access_key_id or SecretStr("mmrag-local-dev"),
        s3_secret_access_key=(configured.s3_secret_access_key or SecretStr("mmrag-local-dev-only")),
        s3_originals_bucket=configured.s3_originals_bucket,
        s3_artifacts_bucket=configured.s3_artifacts_bucket,
        s3_path_style=True,
    )
    storage = create_object_storage(settings)
    assert isinstance(storage, S3ObjectStorage)
    key = f"contract-tests/{uuid4()}/original"
    content = b"seaweedfs-provider-contract"
    checksum = hashlib.sha256(content).hexdigest()

    try:
        storage.probe()
        stored = storage.put_stream(
            key,
            BytesIO(content),
            byte_size=len(content),
            content_sha256=checksum,
            media_type="application/octet-stream",
            metadata={"contract-version": "1"},
        )

        assert storage.head(key) == stored
        assert storage.read(key) == content
        assert storage.put(key, content) == stored
        with pytest.raises(ObjectConflictError):
            storage.put(key, b"different")
    finally:
        storage.delete(key)

    assert not storage.exists(key)


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("MM_RAG_RUN_S3_INTEGRATION_TESTS") != "1",
    reason="Set MM_RAG_RUN_S3_INTEGRATION_TESTS=1 with SeaweedFS running",
)
def test_seaweedfs_authorized_original_resolution_is_tenant_bound() -> None:
    configured = Settings()
    settings = Settings(
        object_storage_backend="s3",
        s3_endpoint_url=configured.s3_endpoint_url,
        s3_region=configured.s3_region,
        s3_access_key_id=configured.s3_access_key_id or SecretStr("mmrag-local-dev"),
        s3_secret_access_key=(
            configured.s3_secret_access_key or SecretStr("mmrag-local-dev-only")
        ),
        s3_originals_bucket=configured.s3_originals_bucket,
        s3_artifacts_bucket=configured.s3_artifacts_bucket,
        s3_path_style=True,
    )
    storage = create_object_storage(settings)
    workspace_id, document_id, version_id = uuid4(), uuid4(), uuid4()
    key = original_object_key(
        workspace_id=workspace_id,
        document_id=document_id,
        version_id=version_id,
    )
    content = b"authorized-seaweedfs-object"
    document = Document(
        id=document_id,
        workspace_id=workspace_id,
        created_by_user_id=uuid4(),
        title="Authorized",
        original_filename="authorized.txt",
        media_type="text/plain",
    )
    version = DocumentVersion(
        id=version_id,
        document_id=document_id,
        workspace_id=workspace_id,
        created_by_user_id=document.created_by_user_id,
        version_number=1,
        content_sha256=hashlib.sha256(content).hexdigest(),
        ingestion_fingerprint="b" * 64,
        object_key=key,
        byte_size=len(content),
        status="uploaded",
    )
    try:
        storage.put(key, content, media_type="text/plain")
        assert resolve_original_object(storage, document, version).key == key
        version.object_key = f"workspaces/{uuid4()}/documents/{document_id}/private"
        with pytest.raises(ObjectIntegrityError):
            resolve_original_object(storage, document, version)
    finally:
        storage.delete(key)
