from collections.abc import Mapping
from dataclasses import dataclass
from typing import BinaryIO, ContextManager, Protocol


class ObjectStorageError(Exception):
    """Base class for provider-neutral, non-disclosing storage failures."""


class ObjectNotFoundError(ObjectStorageError):
    pass


class ObjectConflictError(ObjectStorageError):
    pass


class ObjectIntegrityError(ObjectStorageError):
    pass


class ObjectStorageUnavailableError(ObjectStorageError):
    pass


class ObjectStorageConfigurationError(ObjectStorageError):
    pass


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    byte_size: int
    content_sha256: str
    media_type: str
    etag: str | None = None


class ObjectStorage(Protocol):
    def put(
        self,
        key: str,
        content: bytes,
        *,
        media_type: str = "application/octet-stream",
        metadata: Mapping[str, str] | None = None,
        if_absent: bool = True,
    ) -> StoredObject: ...

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
    ) -> StoredObject: ...

    def open_stream(self, key: str) -> ContextManager[BinaryIO]: ...

    def head(self, key: str) -> StoredObject: ...

    def read(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...
