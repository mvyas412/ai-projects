"""Run an isolated, real-OpenAI acceptance check for the Phase 3 RAG path."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from PIL import Image, ImageDraw
from pydantic import SecretStr
from qdrant_client import QdrantClient
from sqlalchemy import select

from backend.app.broker.messages import IngestionEventMessage
from backend.app.core.config import Settings
from backend.app.core.security import AuthenticatedIdentity
from backend.app.db.base import Base
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.ingestion.pipeline import manifest_supports_sparse
from backend.app.models import (
    ConversationTargetType,
    DocumentVersion,
    DocumentVersionStatus,
    IngestionOutboxEvent,
)
from backend.app.rag.engine import QdrantOpenAIRAGEngine
from backend.app.rag.indexing import QdrantOpenAIDocumentIndexer
from backend.app.repositories.documents import DocumentRepository
from backend.app.repositories.workspaces import WorkspaceRepository
from backend.app.retrieval.sparse import FastEmbedBM25Encoder
from backend.app.schemas.conversations import ConversationCreate
from backend.app.services.audit import AuditService
from backend.app.services.conversations import (
    ConversationNotFoundError,
    ConversationService,
)
from backend.app.services.identity import IdentityProvisioningService
from backend.app.services.ingestion_api import IngestionAPIService
from backend.app.services.ingestion_worker import (
    DeliveryDisposition,
    IngestionWorkerService,
)
from backend.app.storage.local import LocalFileStorage

TEXT_EVIDENCE = (
    b"Project Aurora has an approved budget of $4.2 million and a launch date "
    b"of November 14, 2026."
)


def _risk_card() -> bytes:
    """Create deterministic image evidence without checking in a test artifact."""

    image = Image.new("RGB", (1200, 600), "white")
    draw = ImageDraw.Draw(image)
    draw.text(
        (80, 120),
        "PROJECT AURORA\n\nRISK OWNER: DANA PATEL\n\nSTATUS: GREEN",
        fill="black",
        font_size=48,
    )
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _settings(root: Path) -> Settings:
    """Reuse local providers while isolating SQL, files, and vector collection."""

    settings = Settings(
        database_url=SecretStr(f"sqlite+pysqlite:///{root / 'acceptance.sqlite3'}"),
        local_storage_root=root / "storage",
        qdrant_collection_name=f"mm_rag_acceptance_{uuid4().hex}",
    )
    if settings.openai_api_key is None:
        raise RuntimeError("OPENAI_API_KEY is not configured in the local .env file")
    return settings


def run() -> None:
    """Exercise multimodal indexing, scoped retrieval, generation, and persistence."""

    with TemporaryDirectory(prefix="mm-rag-acceptance-") as temporary_directory:
        settings = _settings(Path(temporary_directory))
        database_engine = create_database_engine(settings)
        session_factory = create_session_factory(database_engine)
        qdrant = QdrantClient(
            url=settings.qdrant_url,
            api_key=(
                settings.qdrant_api_key.get_secret_value()
                if settings.qdrant_api_key is not None
                else None
            ),
            timeout=max(settings.qdrant_timeout_seconds, 30),
            check_compatibility=False,
        )
        try:
            Base.metadata.create_all(database_engine)
            storage = LocalFileStorage(settings.local_storage_root)
            sparse_encoder = FastEmbedBM25Encoder(settings.phase5_model_cache_dir)
            indexer = QdrantOpenAIDocumentIndexer(
                settings, qdrant, sparse_encoder=sparse_encoder
            )
            rag_engine = QdrantOpenAIRAGEngine(
                settings, qdrant, sparse_encoder=sparse_encoder
            )
            worker = IngestionWorkerService(
                settings,
                session_factory,
                storage,
                storage,
                indexer,
                worker_id="acceptance-worker",
            )

            with session_factory() as session:
                user = IdentityProvisioningService(session).provision(
                    AuthenticatedIdentity(
                        subject="acceptance|owner",
                        email="acceptance@example.invalid",
                        display_name="Acceptance owner",
                    )
                )
                workspace, _ = WorkspaceRepository(session).list_for_user(user.id)[0]
                # End the repository read transaction before services open their
                # explicit write transactions on the same acceptance session.
                session.commit()
                ingestion = IngestionAPIService(session, storage, settings)
                text_document, text_version, text_job, _ = ingestion.upload_and_enqueue(
                    user=user,
                    workspace_id=workspace.id,
                    filename="aurora-summary.txt",
                    media_type="text/plain",
                    content=TEXT_EVIDENCE,
                    title="Aurora summary",
                    idempotency_key=f"acceptance-text-{uuid4()}",
                )
                image_document, image_version, image_job, _ = ingestion.upload_and_enqueue(
                    user=user,
                    workspace_id=workspace.id,
                    filename="aurora-risk-card.png",
                    media_type="image/png",
                    content=_risk_card(),
                    title="Aurora risk card",
                    idempotency_key=f"acceptance-image-{uuid4()}",
                )

                ingestion_messages: list[IngestionEventMessage] = []
                for job in (text_job, image_job):
                    event = session.scalar(
                        select(IngestionOutboxEvent).where(
                            IngestionOutboxEvent.job_id == job.id
                        )
                    )
                    assert event is not None
                    ingestion_messages.append(
                        IngestionEventMessage.model_validate(event.payload)
                    )
                session.commit()
                for message in ingestion_messages:
                    assert worker.process(message) == DeliveryDisposition.ACK

                session.expire_all()
                indexed_text = session.get(DocumentVersion, text_version.id)
                indexed_image = session.get(DocumentVersion, image_version.id)
                assert indexed_text is not None and indexed_image is not None
                assert indexed_text.status == DocumentVersionStatus.READY.value
                assert indexed_image.status == DocumentVersionStatus.READY.value
                documents = DocumentRepository(session)
                assert manifest_supports_sparse(
                    documents.generation_manifest(workspace.id, indexed_text)
                )
                assert manifest_supports_sparse(
                    documents.generation_manifest(workspace.id, indexed_image)
                )

                conversations = ConversationService(session, rag_engine)
                conversation, _ = conversations.create_conversation(
                    user=user,
                    workspace_id=workspace.id,
                    payload=ConversationCreate(
                        title="Aurora acceptance",
                        target_type=ConversationTargetType.DOCUMENTS,
                        document_ids=[text_document.id, image_document.id],
                    ),
                )
                _, answer = conversations.ask(
                    user=user,
                    workspace_id=workspace.id,
                    conversation_id=conversation.id,
                    content=(
                        "What is Project Aurora's approved budget and who owns the risk? "
                        "Cite the supporting sources."
                    ),
                )
                normalized_answer = answer.content.casefold()
                assert "4.2" in normalized_answer
                assert "dana patel" in normalized_answer
                assert answer.model_name == settings.openai_chat_model
                assert answer.prompt_tokens and answer.prompt_tokens > 0
                assert answer.completion_tokens and answer.completion_tokens > 0
                cited_documents = {
                    item["document_id"] for item in answer.citations
                }
                assert cited_documents == {str(text_document.id), str(image_document.id)}

                _, _, messages = conversations.get_conversation(
                    user=user,
                    workspace_id=workspace.id,
                    conversation_id=conversation.id,
                )
                assert [message.role for message in messages] == ["user", "assistant"]
                session.commit()

                outsider = IdentityProvisioningService(session).provision(
                    AuthenticatedIdentity(subject="acceptance|outsider")
                )
                try:
                    conversations.get_conversation(
                        user=outsider,
                        workspace_id=workspace.id,
                        conversation_id=conversation.id,
                    )
                except ConversationNotFoundError:
                    pass
                else:
                    raise AssertionError("Cross-workspace conversation access was not hidden")

                events = AuditService(session).list_events(
                    user=user, workspace_id=workspace.id, limit=100
                )
                actions = {event.action for event, _ in events}
                assert {
                    "document.created",
                    "ingestion.job_succeeded",
                    "conversation.created",
                    "conversation.message_created",
                }.issubset(actions)
        finally:
            if qdrant.collection_exists(settings.qdrant_collection_name):
                qdrant.delete_collection(settings.qdrant_collection_name)
            qdrant.close()
            database_engine.dispose()

    print(
        "OpenAI acceptance passed: async text + image hybrid indexing, scoped retrieval, "
        "grounded citations, persistence, audit, and tenant isolation."
    )


if __name__ == "__main__":
    run()
