from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from typing import BinaryIO

from backend.app.storage.base import (
    ObjectConflictError,
    ObjectIntegrityError,
    ObjectNotFoundError,
    StoredObject,
)

_CHUNK_SIZE = 1024 * 1024
_METADATA_DIRECTORY = ".mm-rag-metadata"


class LocalFileStorage:
    """Path-safe development fallback implementing the object-storage contract."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()
        self._metadata_root = self._root / _METADATA_DIRECTORY
        self._root.mkdir(parents=True, exist_ok=True)
        self._metadata_root.mkdir(parents=True, exist_ok=True)

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
        _validate_expected_object(byte_size, content_sha256, media_type)
        destination = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        promoted = False
        try:
            digest = hashlib.sha256()
            written = 0
            with NamedTemporaryFile(
                dir=destination.parent, prefix=".upload-", delete=False
            ) as file:
                temporary = Path(file.name)
                while chunk := stream.read(_CHUNK_SIZE):
                    file.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)

            if written != byte_size or digest.hexdigest() != content_sha256:
                raise ObjectIntegrityError("Object content did not match its declared identity")

            record = StoredObject(
                key=key,
                byte_size=written,
                content_sha256=content_sha256,
                media_type=media_type,
                etag=content_sha256,
            )
            if if_absent:
                try:
                    os.link(temporary, destination)
                except FileExistsError:
                    existing = self.head(key)
                    if _same_identity(existing, record):
                        return existing
                    raise ObjectConflictError(
                        "Object key already contains different content"
                    ) from None
                promoted = True
            else:
                temporary.replace(destination)
                promoted = True

            self._write_metadata(record, metadata)
            return record
        except Exception:
            if promoted:
                destination.unlink(missing_ok=True)
                self._metadata_path(key).unlink(missing_ok=True)
            raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @contextmanager
    def open_stream(self, key: str) -> Iterator[BinaryIO]:
        try:
            with self._resolve(key).open("rb") as file:
                yield file
        except FileNotFoundError:
            raise ObjectNotFoundError("Object not found") from None

    def head(self, key: str) -> StoredObject:
        path = self._resolve(key)
        if not path.is_file():
            raise ObjectNotFoundError("Object not found")
        try:
            payload = json.loads(self._metadata_path(key).read_text(encoding="utf-8"))
            record = StoredObject(
                key=key,
                byte_size=int(payload["byte_size"]),
                content_sha256=str(payload["content_sha256"]),
                media_type=str(payload["media_type"]),
                etag=str(payload["etag"]),
            )
            _validate_expected_object(record.byte_size, record.content_sha256, record.media_type)
            if path.stat().st_size != record.byte_size:
                raise ObjectIntegrityError("Stored object size metadata is inconsistent")
            return record
        except FileNotFoundError:
            digest = hashlib.sha256()
            with path.open("rb") as file:
                while chunk := file.read(_CHUNK_SIZE):
                    digest.update(chunk)
            checksum = digest.hexdigest()
            return StoredObject(
                key=key,
                byte_size=path.stat().st_size,
                content_sha256=checksum,
                media_type="application/octet-stream",
                etag=checksum,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ObjectIntegrityError("Stored object metadata is invalid") from exc

    def read(self, key: str) -> bytes:
        expected = self.head(key)
        with self.open_stream(key) as stream:
            content = stream.read()
        if (
            len(content) != expected.byte_size
            or hashlib.sha256(content).hexdigest() != expected.content_sha256
        ):
            raise ObjectIntegrityError("Stored object content failed integrity verification")
        return content

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def list_objects(self, prefix: str = "") -> list[StoredObject]:
        normalized = prefix.strip("/")
        if normalized:
            self._resolve(f"{normalized}/inventory-probe")
        records: list[StoredObject] = []
        for path in self._root.rglob("*"):
            if not path.is_file() or path.is_relative_to(self._metadata_root):
                continue
            key = path.relative_to(self._root).as_posix()
            if normalized and not key.startswith(f"{normalized}/"):
                continue
            records.append(self.head(key))
        return sorted(records, key=lambda item: item.key)

    def delete(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)
        self._metadata_path(key).unlink(missing_ok=True)

    def _write_metadata(self, record: StoredObject, metadata: Mapping[str, str] | None) -> None:
        destination = self._metadata_path(record.key)
        temporary: Path | None = None
        payload = {
            "byte_size": record.byte_size,
            "content_sha256": record.content_sha256,
            "media_type": record.media_type,
            "etag": record.etag,
            "metadata": dict(metadata or {}),
        }
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._metadata_root,
                prefix=".metadata-",
                delete=False,
            ) as file:
                json.dump(payload, file, sort_keys=True)
                temporary = Path(file.name)
            temporary.replace(destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _metadata_path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._metadata_root / f"{digest}.json"

    def _resolve(self, key: str) -> Path:
        if not key or "\\" in key:
            raise ValueError("Storage key must be a non-empty POSIX-style relative path")
        relative = PurePosixPath(key)
        if (
            relative.is_absolute()
            or any(part in {"", ".", ".."} for part in relative.parts)
            or relative.parts[0] == _METADATA_DIRECTORY
        ):
            raise ValueError("Storage key must not escape the configured root")
        destination = self._root.joinpath(*relative.parts).resolve()
        if not destination.is_relative_to(self._root):
            raise ValueError("Storage key must not escape the configured root")
        return destination


def _validate_expected_object(byte_size: int, content_sha256: str, media_type: str) -> None:
    if byte_size < 0:
        raise ValueError("Object byte size must not be negative")
    if len(content_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in content_sha256
    ):
        raise ValueError("Object SHA-256 must be lowercase hexadecimal")
    if not media_type.strip():
        raise ValueError("Object media type must not be blank")


def _same_identity(left: StoredObject, right: StoredObject) -> bool:
    return (
        left.byte_size == right.byte_size
        and left.content_sha256 == right.content_sha256
        and left.media_type == right.media_type
    )
