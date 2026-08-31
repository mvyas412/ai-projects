from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any, BinaryIO

from botocore.exceptions import BotoCoreError, ClientError

from backend.app.storage.base import (
    ObjectConflictError,
    ObjectIntegrityError,
    ObjectNotFoundError,
    ObjectStorageConfigurationError,
    ObjectStorageUnavailableError,
    StoredObject,
)

_SHA256_METADATA = "mm-rag-sha256"
_BYTE_SIZE_METADATA = "mm-rag-byte-size"
_METADATA_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_BUCKET_NAME = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")


class S3ObjectStorage:
    """S3-compatible immutable object adapter with provider-neutral failures."""

    def __init__(self, client: Any, bucket: str) -> None:
        if not _BUCKET_NAME.fullmatch(bucket):
            raise ObjectStorageConfigurationError("Object-storage bucket name is invalid")
        self._client = client
        self._bucket = bucket

    def put(
        self,
        key: str,
        content: bytes,
        *,
        media_type: str = "application/octet-stream",
        metadata: Mapping[str, str] | None = None,
        if_absent: bool = True,
    ) -> StoredObject:
        content_sha256 = hashlib.sha256(content).hexdigest()
        return self.put_stream(
            key,
            BytesIO(content),
            byte_size=len(content),
            content_sha256=content_sha256,
            media_type=media_type,
            metadata=metadata,
            if_absent=if_absent,
        )

    def put_stream(
        self,
        key: str,
        stream: BinaryIO,
        *,
        byte_size: int,
        content_sha256: str,
        media_type: str = "application/octet-stream",
        metadata: Mapping[str, str] | None = None,
        if_absent: bool = True,
    ) -> StoredObject:
        _validate_key(key)
        _validate_expected_object(byte_size, content_sha256, media_type)
        hashing_stream = _HashingReader(stream)
        request: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": hashing_stream,
            "ContentLength": byte_size,
            "ContentType": media_type,
            "Metadata": _object_metadata(content_sha256, byte_size, metadata),
        }
        if if_absent:
            request["IfNoneMatch"] = "*"

        try:
            response = self._client.put_object(**request)
        except ClientError as exc:
            if if_absent and _is_conflict(exc):
                return self._resolve_idempotent_conflict(
                    key=key,
                    byte_size=byte_size,
                    content_sha256=content_sha256,
                    media_type=media_type,
                )
            raise _storage_error(exc) from None
        except BotoCoreError:
            raise ObjectStorageUnavailableError("Object storage request failed") from None

        if hashing_stream.byte_size != byte_size or hashing_stream.hexdigest != content_sha256:
            self.delete(key)
            raise ObjectIntegrityError("Object content did not match its declared identity")

        stored = self.head(key)
        expected = StoredObject(
            key=key,
            byte_size=byte_size,
            content_sha256=content_sha256,
            media_type=media_type,
            etag=_clean_etag(response.get("ETag")),
        )
        if not _same_identity(stored, expected):
            self.delete(key)
            raise ObjectIntegrityError("Stored object did not match its declared identity")
        return stored

    @contextmanager
    def open_stream(self, key: str) -> Iterator[BinaryIO]:
        _validate_key(key)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            raise _storage_error(exc) from None
        except BotoCoreError:
            raise ObjectStorageUnavailableError("Object storage request failed") from None

        body = response["Body"]
        try:
            yield body
        finally:
            body.close()

    def head(self, key: str) -> StoredObject:
        _validate_key(key)
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            raise _storage_error(exc) from None
        except BotoCoreError:
            raise ObjectStorageUnavailableError("Object storage request failed") from None

        metadata = response.get("Metadata") or {}
        try:
            byte_size = int(response["ContentLength"])
            declared_size = int(metadata[_BYTE_SIZE_METADATA])
            content_sha256 = str(metadata[_SHA256_METADATA])
            media_type = str(response.get("ContentType") or "application/octet-stream")
        except (KeyError, TypeError, ValueError) as exc:
            raise ObjectIntegrityError("Stored object metadata is invalid") from exc
        _validate_expected_object(declared_size, content_sha256, media_type)
        if declared_size != byte_size:
            raise ObjectIntegrityError("Stored object size metadata is inconsistent")
        return StoredObject(
            key=key,
            byte_size=byte_size,
            content_sha256=content_sha256,
            media_type=media_type,
            etag=_clean_etag(response.get("ETag")),
        )

    def read(self, key: str) -> bytes:
        expected = self.head(key)
        digest = hashlib.sha256()
        content = bytearray()
        with self.open_stream(key) as stream:
            while chunk := stream.read(1024 * 1024):
                content.extend(chunk)
                digest.update(chunk)
        if len(content) != expected.byte_size or digest.hexdigest() != expected.content_sha256:
            raise ObjectIntegrityError("Stored object content failed integrity verification")
        return bytes(content)

    def exists(self, key: str) -> bool:
        try:
            self.head(key)
        except ObjectNotFoundError:
            return False
        return True

    def delete(self, key: str) -> None:
        _validate_key(key)
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            raise _storage_error(exc) from None
        except BotoCoreError:
            raise ObjectStorageUnavailableError("Object storage request failed") from None

    def probe(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError as exc:
            raise _storage_error(exc) from None
        except BotoCoreError:
            raise ObjectStorageUnavailableError("Object storage request failed") from None

    def close(self) -> None:
        self._client.close()

    def _resolve_idempotent_conflict(
        self,
        *,
        key: str,
        byte_size: int,
        content_sha256: str,
        media_type: str,
    ) -> StoredObject:
        try:
            existing = self.head(key)
        except (ObjectNotFoundError, ObjectIntegrityError):
            raise ObjectConflictError("Object key already exists") from None
        expected = StoredObject(
            key=key,
            byte_size=byte_size,
            content_sha256=content_sha256,
            media_type=media_type,
        )
        if not _same_identity(existing, expected):
            raise ObjectConflictError("Object key already contains different content")
        return existing


class _HashingReader:
    def __init__(self, source: BinaryIO) -> None:
        self._source = source
        self._digest = hashlib.sha256()
        self.byte_size = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._source.read(size)
        self._digest.update(chunk)
        self.byte_size += len(chunk)
        return chunk

    def tell(self) -> int:
        return self._source.tell()

    def seek(self, offset: int, whence: int = 0) -> int:
        position = self._source.seek(offset, whence)
        if position == 0:
            self._digest = hashlib.sha256()
            self.byte_size = 0
        return position

    @property
    def hexdigest(self) -> str:
        return self._digest.hexdigest()


def _validate_key(key: str) -> None:
    if not key or "\\" in key:
        raise ValueError("Storage key must be a non-empty POSIX-style relative path")
    relative = PurePosixPath(key)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("Storage key must be a safe relative path")


def _validate_expected_object(byte_size: int, content_sha256: str, media_type: str) -> None:
    if byte_size < 0:
        raise ValueError("Object byte size must not be negative")
    if len(content_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in content_sha256
    ):
        raise ValueError("Object SHA-256 must be lowercase hexadecimal")
    if not media_type.strip():
        raise ValueError("Object media type must not be blank")


def _object_metadata(
    content_sha256: str, byte_size: int, metadata: Mapping[str, str] | None
) -> dict[str, str]:
    result = {_SHA256_METADATA: content_sha256, _BYTE_SIZE_METADATA: str(byte_size)}
    for key, value in (metadata or {}).items():
        normalized_key = key.strip().lower()
        if (
            not _METADATA_KEY.fullmatch(normalized_key)
            or normalized_key in result
            or len(value) > 512
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError("Object metadata contains an invalid field")
        result[normalized_key] = value
    return result


def _same_identity(left: StoredObject, right: StoredObject) -> bool:
    return (
        left.byte_size == right.byte_size
        and left.content_sha256 == right.content_sha256
        and left.media_type == right.media_type
    )


def _is_conflict(exc: ClientError) -> bool:
    response = exc.response
    code = str(response.get("Error", {}).get("Code", ""))
    status = int(response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
    return code in {"ConditionalRequestConflict", "PreconditionFailed"} or status in {409, 412}


def _storage_error(exc: ClientError) -> Exception:
    response = exc.response
    code = str(response.get("Error", {}).get("Code", ""))
    status = int(response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
    if code in {"NoSuchKey", "NotFound"} or status == 404:
        return ObjectNotFoundError("Object not found")
    if _is_conflict(exc):
        return ObjectConflictError("Object key already exists")
    if code in {"NoSuchBucket", "InvalidAccessKeyId", "SignatureDoesNotMatch", "AccessDenied"}:
        return ObjectStorageConfigurationError("Object storage is not correctly configured")
    return ObjectStorageUnavailableError("Object storage request failed")


def _clean_etag(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip('"') or None
