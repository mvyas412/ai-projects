from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from backend.app.api.dependencies import (
    get_current_user,
    get_document_indexer,
    get_object_storage,
)
from backend.app.db.session import get_db_session
from backend.app.models.document import Collection, Document, DocumentVersion
from backend.app.models.user import User
from backend.app.rag.indexing import (
    DocumentIndexer,
    EmptyDocumentError,
    IndexingUnavailableError,
)
from backend.app.repositories.documents import DocumentRepository
from backend.app.schemas.documents import (
    CollectionCreate,
    CollectionDetail,
    CollectionSummary,
    DocumentDetail,
    DocumentIndexingResponse,
    DocumentSummary,
    DocumentVersionSummary,
)
from backend.app.services.documents import (
    DocumentLibraryError,
    DocumentLibraryService,
    DuplicateCollectionError,
    DuplicateVersionError,
    InvalidUploadError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from backend.app.services.indexing import (
    DocumentIndexingService,
    IndexingInProgressError,
    IndexingNotFoundError,
    IndexingPermissionError,
)
from backend.app.storage.base import ObjectStorage

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["documents"])


def _version_summary(version: DocumentVersion) -> DocumentVersionSummary:
    return DocumentVersionSummary.model_validate(version)


def _document_summary(
    document: Document, latest_version: DocumentVersion
) -> DocumentSummary:
    return DocumentSummary(
        id=document.id,
        workspace_id=document.workspace_id,
        title=document.title,
        original_filename=document.original_filename,
        media_type=document.media_type,
        archived_at=document.archived_at,
        latest_version=_version_summary(latest_version),
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def _collection_summary(collection: Collection, document_count: int) -> CollectionSummary:
    return CollectionSummary(
        id=collection.id,
        workspace_id=collection.workspace_id,
        name=collection.name,
        description=collection.description,
        document_count=document_count,
        archived_at=collection.archived_at,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


def _translate_error(exc: DocumentLibraryError) -> HTTPException:
    if isinstance(exc, ResourceNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
    if isinstance(exc, PermissionDeniedError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient access")
    if isinstance(exc, (DuplicateVersionError, DuplicateCollectionError)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, InvalidUploadError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="The document operation could not be completed",
    )


@router.get("/documents", response_model=list[DocumentSummary], summary="List documents")
def list_documents(
    workspace_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> list[DocumentSummary]:
    service = DocumentLibraryService(session, storage)
    try:
        documents = service.list_documents(user=user, workspace_id=workspace_id)
    except DocumentLibraryError as exc:
        raise _translate_error(exc) from exc
    repository = DocumentRepository(session)
    return [
        _document_summary(document, repository.latest_version(workspace_id, document.id))
        for document in documents
    ]


@router.post(
    "/documents",
    response_model=DocumentDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
)
def upload_document(
    workspace_id: UUID,
    request: Request,
    file: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    title: Annotated[str | None, Form()] = None,
) -> DocumentDetail:
    content = file.file.read(request.app.state.settings.max_upload_bytes + 1)
    service = DocumentLibraryService(session, storage, request.app.state.settings)
    try:
        document, version = service.create_document(
            user=user,
            workspace_id=workspace_id,
            filename=file.filename or "",
            media_type=file.content_type or "application/octet-stream",
            content=content,
            title=title,
            max_upload_bytes=request.app.state.settings.max_upload_bytes,
        )
    except DocumentLibraryError as exc:
        raise _translate_error(exc) from exc
    summary = _document_summary(document, version)
    return DocumentDetail(**summary.model_dump(), versions=[_version_summary(version)])


@router.get(
    "/documents/{document_id}", response_model=DocumentDetail, summary="Get a document"
)
def get_document(
    workspace_id: UUID,
    document_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> DocumentDetail:
    try:
        document, versions = DocumentLibraryService(session, storage).get_document(
            user=user, workspace_id=workspace_id, document_id=document_id
        )
    except DocumentLibraryError as exc:
        raise _translate_error(exc) from exc
    summary = _document_summary(document, versions[0])
    return DocumentDetail(
        **summary.model_dump(), versions=[_version_summary(version) for version in versions]
    )


@router.post(
    "/documents/{document_id}/versions",
    response_model=DocumentVersionSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document version",
)
def upload_document_version(
    workspace_id: UUID,
    document_id: UUID,
    request: Request,
    file: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> DocumentVersionSummary:
    content = file.file.read(request.app.state.settings.max_upload_bytes + 1)
    try:
        version = DocumentLibraryService(
            session, storage, request.app.state.settings
        ).add_version(
            user=user,
            workspace_id=workspace_id,
            document_id=document_id,
            filename=file.filename or "",
            media_type=file.content_type or "application/octet-stream",
            content=content,
            max_upload_bytes=request.app.state.settings.max_upload_bytes,
        )
    except DocumentLibraryError as exc:
        raise _translate_error(exc) from exc
    return _version_summary(version)


@router.post(
    "/documents/{document_id}/versions/{version_id}/index",
    response_model=DocumentIndexingResponse,
    summary="Index a document version",
)
def index_document_version(
    workspace_id: UUID,
    document_id: UUID,
    version_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    indexer: Annotated[DocumentIndexer, Depends(get_document_indexer)],
) -> DocumentIndexingResponse:
    try:
        version, result = DocumentIndexingService(session, storage, indexer).index_version(
            user=user,
            workspace_id=workspace_id,
            document_id=document_id,
            version_id=version_id,
        )
    except IndexingNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Resource not found") from exc
    except IndexingPermissionError as exc:
        raise HTTPException(status_code=403, detail="Insufficient access") from exc
    except IndexingInProgressError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EmptyDocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IndexingUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail="Document indexing is temporarily unavailable"
        ) from exc
    return DocumentIndexingResponse(
        version=_version_summary(version), chunk_count=result.chunk_count
    )


@router.get(
    "/documents/{document_id}/versions/{version_id}/content",
    summary="Download authorized document content",
)
def download_document_version(
    workspace_id: UUID,
    document_id: UUID,
    version_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> Response:
    try:
        document, _, content = DocumentLibraryService(
            session, storage
        ).read_version_content(
            user=user,
            workspace_id=workspace_id,
            document_id=document_id,
            version_id=version_id,
        )
    except DocumentLibraryError as exc:
        raise _translate_error(exc) from exc
    safe_name = document.original_filename.replace('"', "")
    return Response(
        content=content,
        media_type=document.media_type,
        headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
    )


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive a document",
)
def archive_document(
    workspace_id: UUID,
    document_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> None:
    try:
        DocumentLibraryService(session, storage).archive_document(
            user=user, workspace_id=workspace_id, document_id=document_id
        )
    except DocumentLibraryError as exc:
        raise _translate_error(exc) from exc


@router.get(
    "/collections", response_model=list[CollectionSummary], summary="List collections"
)
def list_collections(
    workspace_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> list[CollectionSummary]:
    try:
        rows = DocumentLibraryService(session, storage).list_collections(
            user=user, workspace_id=workspace_id
        )
    except DocumentLibraryError as exc:
        raise _translate_error(exc) from exc
    return [_collection_summary(collection, count) for collection, count in rows]


@router.post(
    "/collections",
    response_model=CollectionSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Create a collection",
)
def create_collection(
    workspace_id: UUID,
    payload: CollectionCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> CollectionSummary:
    try:
        collection = DocumentLibraryService(session, storage).create_collection(
            user=user,
            workspace_id=workspace_id,
            name=payload.name,
            description=payload.description,
        )
    except DocumentLibraryError as exc:
        raise _translate_error(exc) from exc
    return _collection_summary(collection, 0)


@router.get(
    "/collections/{collection_id}",
    response_model=CollectionDetail,
    summary="Get a collection",
)
def get_collection(
    workspace_id: UUID,
    collection_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> CollectionDetail:
    service = DocumentLibraryService(session, storage)
    try:
        collection, documents = service.get_collection(
            user=user, workspace_id=workspace_id, collection_id=collection_id
        )
    except DocumentLibraryError as exc:
        raise _translate_error(exc) from exc
    repository = DocumentRepository(session)
    document_summaries = [
        _document_summary(document, repository.latest_version(workspace_id, document.id))
        for document in documents
    ]
    summary = _collection_summary(collection, len(document_summaries))
    return CollectionDetail(**summary.model_dump(), documents=document_summaries)


@router.put(
    "/collections/{collection_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Add a document to a collection",
)
def add_document_to_collection(
    workspace_id: UUID,
    collection_id: UUID,
    document_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> None:
    try:
        DocumentLibraryService(session, storage).add_document_to_collection(
            user=user,
            workspace_id=workspace_id,
            collection_id=collection_id,
            document_id=document_id,
        )
    except DocumentLibraryError as exc:
        raise _translate_error(exc) from exc


@router.delete(
    "/collections/{collection_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a document from a collection",
)
def remove_document_from_collection(
    workspace_id: UUID,
    collection_id: UUID,
    document_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> None:
    try:
        DocumentLibraryService(session, storage).remove_document_from_collection(
            user=user,
            workspace_id=workspace_id,
            collection_id=collection_id,
            document_id=document_id,
        )
    except DocumentLibraryError as exc:
        raise _translate_error(exc) from exc
