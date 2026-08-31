from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import PurePath
from typing import BinaryIO, TypeVar
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import Settings
from backend.app.ingestion.pipeline import pipeline_fingerprint
from backend.app.models.document import Collection, Document, DocumentVersion
from backend.app.models.user import User
from backend.app.models.workspace import WorkspaceRole
from backend.app.repositories.documents import CollectionRepository, DocumentRepository
from backend.app.repositories.workspaces import WorkspaceRepository
from backend.app.services.audit import record_audit_event
from backend.app.storage.base import ObjectStorage
from backend.app.storage.keys import original_object_key

ALLOWED_MEDIA_TYPES = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/jpeg",
        "image/png",
        "text/markdown",
        "text/plain",
    }
)
WRITE_ROLES = frozenset({WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.MEMBER})
ADMIN_ROLES = frozenset({WorkspaceRole.OWNER, WorkspaceRole.ADMIN})
T = TypeVar("T")


class DocumentLibraryError(Exception):
    """Base class for safe document-library failures."""


class ResourceNotFoundError(DocumentLibraryError):
    pass


class PermissionDeniedError(DocumentLibraryError):
    pass


class InvalidUploadError(DocumentLibraryError):
    pass


class DuplicateVersionError(DocumentLibraryError):
    pass


class DuplicateCollectionError(DocumentLibraryError):
    pass


class DocumentLibraryService:
    def __init__(
        self,
        session: Session,
        storage: ObjectStorage,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._storage = storage
        self._documents = DocumentRepository(session)
        self._collections = CollectionRepository(session)
        self._workspaces = WorkspaceRepository(session)
        self._settings = settings or Settings.model_construct()

    def list_documents(self, *, user: User, workspace_id: UUID) -> list[Document]:
        self._require_workspace(user, workspace_id)
        return self._documents.list_documents(workspace_id)

    def get_document(
        self, *, user: User, workspace_id: UUID, document_id: UUID
    ) -> tuple[Document, list[DocumentVersion]]:
        self._require_workspace(user, workspace_id)
        document = self._documents.get_document(workspace_id, document_id)
        if document is None:
            raise ResourceNotFoundError
        return document, self._documents.list_versions(workspace_id, document_id)

    def read_version_content(
        self,
        *,
        user: User,
        workspace_id: UUID,
        document_id: UUID,
        version_id: UUID,
    ) -> tuple[Document, DocumentVersion, bytes]:
        self._require_workspace(user, workspace_id)
        document = self._documents.get_document(workspace_id, document_id)
        version = self._documents.get_version(workspace_id, document_id, version_id)
        if document is None or version is None:
            raise ResourceNotFoundError
        return document, version, self._storage.read(version.object_key)

    def create_document(
        self,
        *,
        user: User,
        workspace_id: UUID,
        filename: str,
        media_type: str,
        content: bytes,
        title: str | None,
        max_upload_bytes: int,
    ) -> tuple[Document, DocumentVersion]:
        document, version, _ = self.create_document_with_callback(
            user=user,
            workspace_id=workspace_id,
            filename=filename,
            media_type=media_type,
            content=content,
            title=title,
            max_upload_bytes=max_upload_bytes,
            after_original=lambda _document, _version: None,
        )
        return document, version

    def create_document_with_callback(
        self,
        *,
        user: User,
        workspace_id: UUID,
        filename: str,
        media_type: str,
        content: bytes,
        title: str | None,
        max_upload_bytes: int,
        after_original: Callable[[Document, DocumentVersion], T],
    ) -> tuple[Document, DocumentVersion, T]:
        safe_filename, normalized_media_type = self._validate_upload(
            filename=filename,
            media_type=media_type,
            content=content,
            max_upload_bytes=max_upload_bytes,
        )
        document_id = uuid4()
        version_id = uuid4()
        document = Document(
            id=document_id,
            workspace_id=workspace_id,
            created_by_user_id=user.id,
            title=self._normalize_title(title, safe_filename),
            original_filename=safe_filename,
            media_type=normalized_media_type,
        )
        version = self._new_version(
            version_id=version_id,
            document=document,
            user=user,
            version_number=1,
            content=content,
        )
        result = self._write_with_storage(
            version.object_key,
            content,
            document.media_type,
            document,
            version,
            lambda: self._add_initial_document(user, workspace_id, document, version),
            lambda: after_original(document, version),
        )
        return document, version, result

    def create_document_stream_with_callback(
        self,
        *,
        user: User,
        workspace_id: UUID,
        filename: str,
        media_type: str,
        stream: BinaryIO,
        byte_size: int,
        content_sha256: str,
        title: str | None,
        max_upload_bytes: int,
        after_original: Callable[[Document, DocumentVersion], T],
    ) -> tuple[Document, DocumentVersion, T]:
        safe_filename, normalized_media_type = self._validate_upload_identity(
            filename=filename,
            media_type=media_type,
            byte_size=byte_size,
            content_sha256=content_sha256,
            max_upload_bytes=max_upload_bytes,
        )
        document = Document(
            id=uuid4(),
            workspace_id=workspace_id,
            created_by_user_id=user.id,
            title=self._normalize_title(title, safe_filename),
            original_filename=safe_filename,
            media_type=normalized_media_type,
        )
        version = self._new_version_from_identity(
            version_id=uuid4(),
            document=document,
            user=user,
            version_number=1,
            byte_size=byte_size,
            content_sha256=content_sha256,
        )
        stored = False
        try:
            with self._session.begin():
                self._add_initial_document(user, workspace_id, document, version)
                stream.seek(0)
                self._storage.put_stream(
                    version.object_key,
                    stream,
                    byte_size=byte_size,
                    content_sha256=content_sha256,
                    media_type=document.media_type,
                    metadata=self._object_metadata(document, version),
                )
                stored = True
                result = after_original(document, version)
            return document, version, result
        except Exception:
            if stored:
                self._storage.delete(version.object_key)
            raise

    def add_version(
        self,
        *,
        user: User,
        workspace_id: UUID,
        document_id: UUID,
        filename: str,
        media_type: str,
        content: bytes,
        max_upload_bytes: int,
    ) -> DocumentVersion:
        safe_filename, normalized_media_type = self._validate_upload(
            filename=filename,
            media_type=media_type,
            content=content,
            max_upload_bytes=max_upload_bytes,
        )
        stored_key: str | None = None
        try:
            with self._session.begin():
                self._require_role(user, workspace_id, WRITE_ROLES)
                document = self._documents.get_document(workspace_id, document_id)
                if document is None:
                    raise ResourceNotFoundError
                if normalized_media_type != document.media_type:
                    raise InvalidUploadError("A new version must keep the document media type")
                content_hash = hashlib.sha256(content).hexdigest()
                fingerprint = self._ingestion_fingerprint(normalized_media_type)
                if self._documents.version_with_fingerprint(
                    workspace_id,
                    document_id,
                    content_hash,
                    fingerprint,
                ) is not None:
                    raise DuplicateVersionError("This document version already exists")
                version = self._new_version(
                    version_id=uuid4(),
                    document=document,
                    user=user,
                    version_number=self._documents.next_version_number(
                        workspace_id, document_id
                    ),
                    content=content,
                )
                self._documents.add_version(version)
                record_audit_event(
                    self._session,
                    workspace_id=workspace_id,
                    actor_user_id=user.id,
                    action="document.version_created",
                    resource_type="document",
                    resource_id=document_id,
                    details={"version_id": str(version.id), "version_number": version.version_number},
                )
                self._storage.put(
                    version.object_key,
                    content,
                    media_type=document.media_type,
                    metadata=self._object_metadata(document, version),
                )
                stored_key = version.object_key
            return version
        except Exception:
            if stored_key is not None:
                self._storage.delete(stored_key)
            raise

    def archive_document(self, *, user: User, workspace_id: UUID, document_id: UUID) -> None:
        with self._session.begin():
            self._require_role(user, workspace_id, ADMIN_ROLES)
            document = self._documents.get_document(workspace_id, document_id)
            if document is None:
                raise ResourceNotFoundError
            document.archived_at = datetime.now(UTC)
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="document.archived",
                resource_type="document",
                resource_id=document_id,
            )

    def list_collections(self, *, user: User, workspace_id: UUID) -> list[tuple[Collection, int]]:
        self._require_workspace(user, workspace_id)
        return self._collections.list_collections(workspace_id)

    def get_collection(
        self, *, user: User, workspace_id: UUID, collection_id: UUID
    ) -> tuple[Collection, list[Document]]:
        self._require_workspace(user, workspace_id)
        collection = self._collections.get_collection(workspace_id, collection_id)
        if collection is None:
            raise ResourceNotFoundError
        return collection, self._collections.list_documents(workspace_id, collection_id)

    def create_collection(
        self,
        *,
        user: User,
        workspace_id: UUID,
        name: str,
        description: str | None,
    ) -> Collection:
        try:
            with self._session.begin():
                self._require_role(user, workspace_id, WRITE_ROLES)
                collection = Collection(
                    workspace_id=workspace_id,
                    created_by_user_id=user.id,
                    name=name,
                    description=description,
                )
                self._collections.add(collection)
                record_audit_event(
                    self._session,
                    workspace_id=workspace_id,
                    actor_user_id=user.id,
                    action="collection.created",
                    resource_type="collection",
                    resource_id=collection.id,
                    details={"name": collection.name},
                )
            return collection
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateCollectionError("A collection with this name already exists") from exc

    def add_document_to_collection(
        self,
        *,
        user: User,
        workspace_id: UUID,
        collection_id: UUID,
        document_id: UUID,
    ) -> None:
        with self._session.begin():
            self._require_role(user, workspace_id, WRITE_ROLES)
            if self._collections.get_collection(workspace_id, collection_id) is None:
                raise ResourceNotFoundError
            if self._documents.get_document(workspace_id, document_id) is None:
                raise ResourceNotFoundError
            self._collections.add_document(
                workspace_id=workspace_id,
                collection_id=collection_id,
                document_id=document_id,
                user_id=user.id,
            )
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="collection.document_added",
                resource_type="collection",
                resource_id=collection_id,
                details={"document_id": str(document_id)},
            )

    def remove_document_from_collection(
        self,
        *,
        user: User,
        workspace_id: UUID,
        collection_id: UUID,
        document_id: UUID,
    ) -> None:
        with self._session.begin():
            self._require_role(user, workspace_id, WRITE_ROLES)
            if self._collections.get_collection(workspace_id, collection_id) is None:
                raise ResourceNotFoundError
            if not self._collections.remove_document(collection_id, document_id):
                raise ResourceNotFoundError
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="collection.document_removed",
                resource_type="collection",
                resource_id=collection_id,
                details={"document_id": str(document_id)},
            )

    def _add_initial_document(
        self,
        user: User,
        workspace_id: UUID,
        document: Document,
        version: DocumentVersion,
    ) -> None:
        self._require_role(user, workspace_id, WRITE_ROLES)
        self._documents.add_document(document, version)
        record_audit_event(
            self._session,
            workspace_id=workspace_id,
            actor_user_id=user.id,
            action="document.created",
            resource_type="document",
            resource_id=document.id,
            details={
                "title": document.title,
                "version_id": str(version.id),
                "media_type": document.media_type,
            },
        )

    def _write_with_storage(
        self,
        object_key: str,
        content: bytes,
        media_type: str,
        document: Document,
        version: DocumentVersion,
        database_write: Callable[[], None],
        after_original: Callable[[], T],
    ) -> T:
        stored = False
        try:
            with self._session.begin():
                database_write()
                self._storage.put(
                    object_key,
                    content,
                    media_type=media_type,
                    metadata=self._object_metadata(document, version),
                )
                stored = True
                result = after_original()
            return result
        except Exception:
            if stored:
                self._storage.delete(object_key)
            raise

    @staticmethod
    def _object_metadata(document: Document, version: DocumentVersion) -> dict[str, str]:
        return {
            "workspace-id": str(document.workspace_id),
            "document-id": str(document.id),
            "version-id": str(version.id),
        }

    def _require_workspace(self, user: User, workspace_id: UUID) -> WorkspaceRole:
        result = self._workspaces.get_for_user(workspace_id, user.id)
        if result is None:
            raise ResourceNotFoundError
        return result[1]

    def _require_role(
        self, user: User, workspace_id: UUID, allowed: frozenset[WorkspaceRole]
    ) -> WorkspaceRole:
        role = self._require_workspace(user, workspace_id)
        if role not in allowed:
            raise PermissionDeniedError
        return role

    @staticmethod
    def _normalize_title(title: str | None, filename: str) -> str:
        candidate = title if title is not None else PurePath(filename).stem
        normalized = " ".join(candidate.split())
        if not normalized:
            raise InvalidUploadError("Document title cannot be blank")
        if len(normalized) > 240:
            raise InvalidUploadError("Document title is too long")
        return normalized

    @staticmethod
    def _validate_upload(
        *, filename: str, media_type: str, content: bytes, max_upload_bytes: int
    ) -> tuple[str, str]:
        safe_filename = _safe_filename(filename)
        normalized_media_type = media_type.split(";", 1)[0].strip().lower()
        if normalized_media_type not in ALLOWED_MEDIA_TYPES:
            raise InvalidUploadError("Unsupported document type")
        if not content:
            raise InvalidUploadError("The uploaded document is empty")
        if len(content) > max_upload_bytes:
            raise InvalidUploadError("The uploaded document exceeds the size limit")
        return safe_filename, normalized_media_type

    @staticmethod
    def _validate_upload_identity(
        *,
        filename: str,
        media_type: str,
        byte_size: int,
        content_sha256: str,
        max_upload_bytes: int,
    ) -> tuple[str, str]:
        safe_filename = _safe_filename(filename)
        normalized_media_type = media_type.split(";", 1)[0].strip().lower()
        if normalized_media_type not in ALLOWED_MEDIA_TYPES:
            raise InvalidUploadError("Unsupported document type")
        if byte_size <= 0:
            raise InvalidUploadError("The uploaded document is empty")
        if byte_size > max_upload_bytes:
            raise InvalidUploadError("The uploaded document exceeds the size limit")
        if len(content_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in content_sha256
        ):
            raise InvalidUploadError("The uploaded document identity is invalid")
        return safe_filename, normalized_media_type

    def _ingestion_fingerprint(self, media_type: str) -> str:
        return pipeline_fingerprint(self._settings, media_type)

    def _new_version(
        self,
        *,
        version_id: UUID,
        document: Document,
        user: User,
        version_number: int,
        content: bytes,
    ) -> DocumentVersion:
        return self._new_version_from_identity(
            version_id=version_id,
            document=document,
            user=user,
            version_number=version_number,
            byte_size=len(content),
            content_sha256=hashlib.sha256(content).hexdigest(),
        )

    def _new_version_from_identity(
        self,
        *,
        version_id: UUID,
        document: Document,
        user: User,
        version_number: int,
        byte_size: int,
        content_sha256: str,
    ) -> DocumentVersion:
        return DocumentVersion(
            id=version_id,
            document_id=document.id,
            workspace_id=document.workspace_id,
            created_by_user_id=user.id,
            version_number=version_number,
            content_sha256=content_sha256,
            ingestion_fingerprint=self._ingestion_fingerprint(document.media_type),
            object_key=original_object_key(
                workspace_id=document.workspace_id,
                document_id=document.id,
                version_id=version_id,
            ),
            byte_size=byte_size,
        )


def _safe_filename(filename: str) -> str:
    leaf = PurePath(filename).name
    normalized = unicodedata.normalize("NFKC", leaf).strip()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", normalized).strip("._")
    if not safe:
        raise InvalidUploadError("The uploaded document needs a valid filename")
    return safe[:255]
