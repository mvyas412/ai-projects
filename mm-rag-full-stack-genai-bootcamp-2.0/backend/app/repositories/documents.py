from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.document import (
    Collection,
    CollectionDocument,
    Document,
    DocumentVersion,
)


class DocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_document(self, document: Document, version: DocumentVersion) -> None:
        self._session.add(document)
        self._session.flush()
        self._session.add(version)
        self._session.flush()

    def add_version(self, version: DocumentVersion) -> None:
        self._session.add(version)
        self._session.flush()

    def list_documents(
        self, workspace_id: UUID, *, include_archived: bool = False
    ) -> list[Document]:
        statement = select(Document).where(Document.workspace_id == workspace_id)
        if not include_archived:
            statement = statement.where(Document.archived_at.is_(None))
        return list(self._session.scalars(statement.order_by(Document.created_at, Document.id)))

    def get_document(
        self, workspace_id: UUID, document_id: UUID, *, include_archived: bool = False
    ) -> Document | None:
        statement = select(Document).where(
            Document.workspace_id == workspace_id,
            Document.id == document_id,
        )
        if not include_archived:
            statement = statement.where(Document.archived_at.is_(None))
        return self._session.scalar(statement)

    def list_versions(self, workspace_id: UUID, document_id: UUID) -> list[DocumentVersion]:
        statement = (
            select(DocumentVersion)
            .where(
                DocumentVersion.workspace_id == workspace_id,
                DocumentVersion.document_id == document_id,
            )
            .order_by(DocumentVersion.version_number.desc(), DocumentVersion.id)
        )
        return list(self._session.scalars(statement))

    def latest_version(self, workspace_id: UUID, document_id: UUID) -> DocumentVersion:
        version = self._session.scalar(
            select(DocumentVersion)
            .where(
                DocumentVersion.workspace_id == workspace_id,
                DocumentVersion.document_id == document_id,
            )
            .order_by(DocumentVersion.version_number.desc())
            .limit(1)
        )
        if version is None:  # Database invariants require every document to have a version.
            raise RuntimeError("Document has no version")
        return version

    def next_version_number(self, workspace_id: UUID, document_id: UUID) -> int:
        current = self._session.scalar(
            select(func.max(DocumentVersion.version_number)).where(
                DocumentVersion.workspace_id == workspace_id,
                DocumentVersion.document_id == document_id,
            )
        )
        return (current or 0) + 1

    def version_with_fingerprint(
        self,
        workspace_id: UUID,
        document_id: UUID,
        content_sha256: str,
        ingestion_fingerprint: str,
    ) -> DocumentVersion | None:
        return self._session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.workspace_id == workspace_id,
                DocumentVersion.document_id == document_id,
                DocumentVersion.content_sha256 == content_sha256,
                DocumentVersion.ingestion_fingerprint == ingestion_fingerprint,
            )
        )


class CollectionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, collection: Collection) -> None:
        self._session.add(collection)
        self._session.flush()

    def list_collections(
        self, workspace_id: UUID, *, include_archived: bool = False
    ) -> list[tuple[Collection, int]]:
        statement = (
            select(Collection, func.count(CollectionDocument.document_id))
            .outerjoin(
                CollectionDocument,
                (CollectionDocument.collection_id == Collection.id)
                & (CollectionDocument.workspace_id == Collection.workspace_id),
            )
            .where(Collection.workspace_id == workspace_id)
            .group_by(Collection.id)
            .order_by(Collection.created_at, Collection.id)
        )
        if not include_archived:
            statement = statement.where(Collection.archived_at.is_(None))
        return [(row[0], row[1]) for row in self._session.execute(statement).all()]

    def get_collection(
        self, workspace_id: UUID, collection_id: UUID, *, include_archived: bool = False
    ) -> Collection | None:
        statement = select(Collection).where(
            Collection.workspace_id == workspace_id,
            Collection.id == collection_id,
        )
        if not include_archived:
            statement = statement.where(Collection.archived_at.is_(None))
        return self._session.scalar(statement)

    def count_documents(self, workspace_id: UUID, collection_id: UUID) -> int:
        count = self._session.scalar(
            select(func.count())
            .select_from(CollectionDocument)
            .where(
                CollectionDocument.workspace_id == workspace_id,
                CollectionDocument.collection_id == collection_id,
            )
        )
        return count or 0

    def list_documents(self, workspace_id: UUID, collection_id: UUID) -> list[Document]:
        statement = (
            select(Document)
            .join(
                CollectionDocument,
                (CollectionDocument.document_id == Document.id)
                & (CollectionDocument.workspace_id == Document.workspace_id),
            )
            .where(
                CollectionDocument.workspace_id == workspace_id,
                CollectionDocument.collection_id == collection_id,
                Document.archived_at.is_(None),
            )
            .order_by(Document.created_at, Document.id)
        )
        return list(self._session.scalars(statement))

    def add_document(
        self,
        *,
        workspace_id: UUID,
        collection_id: UUID,
        document_id: UUID,
        user_id: UUID,
    ) -> None:
        existing = self._session.get(CollectionDocument, (collection_id, document_id))
        if existing is None:
            self._session.add(
                CollectionDocument(
                    collection_id=collection_id,
                    document_id=document_id,
                    workspace_id=workspace_id,
                    added_by_user_id=user_id,
                )
            )

    def remove_document(self, collection_id: UUID, document_id: UUID) -> bool:
        membership = self._session.get(CollectionDocument, (collection_id, document_id))
        if membership is None:
            return False
        self._session.delete(membership)
        return True
