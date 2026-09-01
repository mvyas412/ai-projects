from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest
from botocore.exceptions import ClientError

from backend.app.storage.base import ObjectConflictError, ObjectIntegrityError
from backend.app.storage.s3 import S3ObjectStorage


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, Any]] = {}
        self.last_put_request: dict[str, Any] | None = None

    def put_object(self, **request: Any) -> dict[str, str]:
        self.last_put_request = request
        identity = (request["Bucket"], request["Key"])
        if request.get("IfNoneMatch") == "*" and identity in self.objects:
            raise ClientError(
                {
                    "Error": {"Code": "PreconditionFailed"},
                    "ResponseMetadata": {"HTTPStatusCode": 412},
                },
                "PutObject",
            )
        content = request["Body"].read()
        self.objects[identity] = {
            "content": content,
            "ContentLength": len(content),
            "ContentType": request["ContentType"],
            "Metadata": request["Metadata"],
            "ETag": '"test-etag"',
        }
        return {"ETag": '"test-etag"'}

    def head_object(self, **request: Any) -> dict[str, Any]:
        return dict(self.objects[(request["Bucket"], request["Key"])])

    def get_object(self, **request: Any) -> dict[str, BytesIO]:
        stored = self.objects[(request["Bucket"], request["Key"])]
        return {"Body": BytesIO(stored["content"])}

    def delete_object(self, **request: Any) -> None:
        self.objects.pop((request["Bucket"], request["Key"]), None)

    def head_bucket(self, **request: Any) -> None:
        return None

    def list_objects_v2(self, **request: Any) -> dict[str, Any]:
        prefix = request.get("Prefix", "")
        contents = [
            {"Key": key}
            for bucket, key in self.objects
            if bucket == request["Bucket"] and key.startswith(prefix)
        ]
        return {"Contents": contents, "IsTruncated": False}


def test_s3_storage_round_trip_and_idempotent_replay() -> None:
    client = FakeS3Client()
    storage = S3ObjectStorage(client, "mm-rag-phase3-originals")

    first = storage.put(
        "workspaces/one/documents/two/versions/three/original",
        b"content",
        media_type="text/plain",
        metadata={"version-id": "three"},
    )
    replay = storage.put(
        first.key,
        b"content",
        media_type="text/plain",
        metadata={"version-id": "three"},
    )

    assert replay == first
    assert storage.read(first.key) == b"content"
    with storage.open_stream(first.key) as stream:
        assert stream.read() == b"content"
    storage.probe()


def test_s3_storage_rejects_same_key_with_different_content() -> None:
    storage = S3ObjectStorage(FakeS3Client(), "mm-rag-phase3-originals")
    key = "workspaces/one/documents/two/versions/three/original"
    storage.put(key, b"first", media_type="text/plain")

    with pytest.raises(ObjectConflictError):
        storage.put(key, b"second", media_type="text/plain")


def test_s3_storage_rejects_missing_integrity_metadata() -> None:
    client = FakeS3Client()
    key = "workspaces/one/documents/two/versions/three/original"
    client.objects[("mm-rag-phase3-originals", key)] = {
        "content": b"content",
        "ContentLength": 7,
        "ContentType": "text/plain",
        "Metadata": {},
        "ETag": '"test-etag"',
    }
    storage = S3ObjectStorage(client, "mm-rag-phase3-originals")

    with pytest.raises(ObjectIntegrityError):
        storage.head(key)


def test_s3_storage_lists_bounded_objects_and_sends_encryption_headers() -> None:
    client = FakeS3Client()
    storage = S3ObjectStorage(
        client,
        "mm-rag-phase3-originals",
        server_side_encryption="aws:kms",
        kms_key_id="test-key",
    )
    stored = storage.put(
        "workspaces/one/documents/two/versions/three/original",
        b"content",
        media_type="text/plain",
    )

    assert storage.list_objects("workspaces/one") == [stored]
    assert client.last_put_request is not None
    assert client.last_put_request["ServerSideEncryption"] == "aws:kms"
    assert client.last_put_request["SSEKMSKeyId"] == "test-key"
