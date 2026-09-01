from __future__ import annotations

from backend.app.models.document import Document, DocumentVersion
from backend.app.storage.base import ObjectIntegrityError, ObjectStorage, StoredObject
from backend.app.storage.keys import original_object_key


def resolve_original_object(
    storage: ObjectStorage, document: Document, version: DocumentVersion
) -> StoredObject:
    """Resolve a server-generated original only after trusted resource authorization."""

    expected_key = original_object_key(
        workspace_id=document.workspace_id,
        document_id=document.id,
        version_id=version.id,
    )
    if (
        version.workspace_id != document.workspace_id
        or version.document_id != document.id
        or version.object_key != expected_key
    ):
        raise ObjectIntegrityError("Stored original identity is inconsistent")
    stored = storage.head(expected_key)
    if (
        stored.byte_size != version.byte_size
        or stored.content_sha256 != version.content_sha256
        or stored.media_type != document.media_type
    ):
        raise ObjectIntegrityError("Stored original identity is inconsistent")
    return stored
