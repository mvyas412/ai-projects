from typing import Annotated

from fastapi import Depends, Request
from qdrant_client import QdrantClient
from sqlalchemy.orm import Session

from backend.app.core.security import AuthenticatedIdentity, get_current_identity
from backend.app.db.session import get_db_session
from backend.app.models.user import User
from backend.app.rag.engine import RAGEngine
from backend.app.rag.indexing import DocumentIndexer
from backend.app.services.identity import IdentityProvisioningService
from backend.app.storage.base import ObjectStorage


def get_current_user(
    identity: Annotated[AuthenticatedIdentity, Depends(get_current_identity)],
    session: Annotated[Session, Depends(get_db_session)],
) -> User:
    return IdentityProvisioningService(session).provision(identity)


def get_object_storage(request: Request) -> ObjectStorage:
    return request.app.state.object_storage


def get_artifact_storage(request: Request) -> ObjectStorage:
    return request.app.state.artifact_storage


def get_rag_engine(request: Request) -> RAGEngine:
    return request.app.state.rag_engine


def get_document_indexer(request: Request) -> DocumentIndexer:
    return request.app.state.document_indexer


def get_qdrant_client(request: Request) -> QdrantClient:
    return request.app.state.qdrant_client
