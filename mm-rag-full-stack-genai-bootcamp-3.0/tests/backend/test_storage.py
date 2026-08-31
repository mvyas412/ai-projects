import hashlib
from io import BytesIO

import pytest

from backend.app.storage.base import (
    ObjectConflictError,
    ObjectIntegrityError,
    ObjectNotFoundError,
)
from backend.app.storage.local import LocalFileStorage


def test_local_storage_round_trip_and_delete(tmp_path) -> None:
    storage = LocalFileStorage(tmp_path / "objects")

    stored = storage.put(
        "workspace/document/original",
        b"pdf-content",
        media_type="application/pdf",
    )

    assert stored.content_sha256 == hashlib.sha256(b"pdf-content").hexdigest()
    assert storage.head(stored.key) == stored
    assert storage.exists(stored.key)
    assert storage.read(stored.key) == b"pdf-content"
    with storage.open_stream(stored.key) as stream:
        assert stream.read() == b"pdf-content"
    storage.delete(stored.key)
    assert not storage.exists(stored.key)
    with pytest.raises(ObjectNotFoundError):
        storage.head(stored.key)


def test_local_storage_stream_verifies_identity_and_is_idempotent(tmp_path) -> None:
    storage = LocalFileStorage(tmp_path / "objects")
    content = b"streamed-content"
    checksum = hashlib.sha256(content).hexdigest()

    first = storage.put_stream(
        "workspace/document/original",
        BytesIO(content),
        byte_size=len(content),
        content_sha256=checksum,
        media_type="text/plain",
    )
    replay = storage.put_stream(
        "workspace/document/original",
        BytesIO(content),
        byte_size=len(content),
        content_sha256=checksum,
        media_type="text/plain",
    )

    assert replay == first
    with pytest.raises(ObjectConflictError):
        storage.put("workspace/document/original", b"different", media_type="text/plain")
    with pytest.raises(ObjectIntegrityError):
        storage.put_stream(
            "workspace/document/corrupt",
            BytesIO(content),
            byte_size=len(content) + 1,
            content_sha256=checksum,
        )
    assert not storage.exists("workspace/document/corrupt")


def test_local_storage_detects_content_corruption(tmp_path) -> None:
    root = tmp_path / "objects"
    storage = LocalFileStorage(root)
    key = "workspace/document/original"
    storage.put(key, b"verified")
    (root / key).write_bytes(b"tampered")

    with pytest.raises(ObjectIntegrityError):
        storage.read(key)


@pytest.mark.parametrize("key", ["", "/absolute.pdf", "../escape.pdf", "a/../../escape", "a\\b"])
def test_local_storage_rejects_unsafe_keys(tmp_path, key: str) -> None:
    storage = LocalFileStorage(tmp_path / "objects")

    with pytest.raises(ValueError):
        storage.put(key, b"unsafe")
