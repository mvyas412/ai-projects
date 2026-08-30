from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.models.document import DocumentVersion, DocumentVersionStatus
from backend.app.models.user import User
from backend.app.rag.indexing import (
    DocumentIndexer,
    EmptyDocumentError,
    IndexingRequest,
    IndexingResult,
    IndexingUnavailableError,
)
from backend.app.repositories.documents import DocumentRepository
from backend.app.repositories.workspaces import WorkspaceRepository
from backend.app.services.audit import record_audit_event
from backend.app.services.documents import WRITE_ROLES
from backend.app.storage.base import ObjectStorage


class IndexingNotFoundError(Exception):
    pass


class IndexingPermissionError(Exception):
    pass


class IndexingInProgressError(Exception):
    pass


class DocumentIndexingService:
    def __init__(
        self,
        session: Session,
        storage: ObjectStorage,
        indexer: DocumentIndexer,
    ) -> None:
        self._session = session
        self._storage = storage
        self._indexer = indexer
        self._documents = DocumentRepository(session)
        self._workspaces = WorkspaceRepository(session)

    def index_version(
        self,
        *,
        user: User,
        workspace_id: UUID,
        document_id: UUID,
        version_id: UUID,
    ) -> tuple[DocumentVersion, IndexingResult]:
        membership = self._workspaces.get_for_user(workspace_id, user.id)
        if membership is None:
            raise IndexingNotFoundError
        role = membership[1]
        if role not in WRITE_ROLES:
            raise IndexingPermissionError
        document = self._documents.get_document(workspace_id, document_id)
        version = self._documents.get_version(workspace_id, document_id, version_id)
        if document is None or version is None:
            raise IndexingNotFoundError
        if version.status == DocumentVersionStatus.PROCESSING.value:
            raise IndexingInProgressError("This document version is already being indexed")

        version.status = DocumentVersionStatus.PROCESSING.value
        version.failure_reason = None
        self._session.commit()
        try:
            result = self._indexer.index(
                IndexingRequest(
                    workspace_id=workspace_id,
                    document_id=document_id,
                    document_version_id=version_id,
                    document_title=document.title,
                    media_type=document.media_type,
                    content=self._storage.read(version.object_key),
                )
            )
        except IndexingUnavailableError:
            version.status = DocumentVersionStatus.UPLOADED.value
            version.failure_reason = None
            self._session.commit()
            raise
        except EmptyDocumentError as exc:
            version.status = DocumentVersionStatus.FAILED.value
            version.failure_reason = str(exc)[:500]
            self._session.commit()
            raise
        except Exception:
            version.status = DocumentVersionStatus.FAILED.value
            version.failure_reason = "Document indexing failed"
            self._session.commit()
            raise

        version.status = DocumentVersionStatus.READY.value
        version.failure_reason = None
        record_audit_event(
            self._session,
            workspace_id=workspace_id,
            actor_user_id=user.id,
            action="document.version_indexed",
            resource_type="document",
            resource_id=document_id,
            details={"version_id": str(version_id), "chunk_count": result.chunk_count},
        )
        self._session.commit()
        return version, result
