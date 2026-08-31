import hashlib
import os
from io import BytesIO
from uuid import uuid4

import pytest
from pydantic import SecretStr

from backend.app.core.config import Settings
from backend.app.storage.base import ObjectConflictError
from backend.app.storage.factory import create_object_storage
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
