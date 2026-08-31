from __future__ import annotations

import hashlib
import json
from importlib.metadata import version

from backend.app.core.config import Settings

PIPELINE_PROFILE = "phase3-async-v1"


def pipeline_manifest(settings: Settings, media_type: str) -> dict[str, object]:
    """Return the canonical output-affecting ingestion contract from ADR 0008."""

    extractor = {
        "application/pdf": "pypdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "python-docx",
    }.get(media_type, "utf8-or-vision")
    return {
        "schema_version": 1,
        "profile": PIPELINE_PROFILE,
        "media_type": media_type,
        "extraction": {
            "implementation": extractor,
            "pypdf_version": version("pypdf"),
            "python_docx_version": version("python-docx"),
            "image_prompt_revision": "image-transcription-v1",
            "chat_model": settings.openai_chat_model,
            "normalization_revision": "text-v1",
        },
        "chunking": {
            "implementation": "recursive-character",
            "chunk_size": 1200,
            "chunk_overlap": 180,
            "locator_schema_revision": 1,
        },
        "embedding": {
            "provider": "openai",
            "model": settings.openai_embedding_model,
            "normalization": "provider-default",
            "vector_kind": "dense-text",
        },
        "index": {
            "provider": "qdrant",
            "payload_schema_revision": 2,
            "generation_filter_required": True,
        },
        "citation_schema_revision": 1,
    }


def pipeline_fingerprint(settings: Settings, media_type: str) -> str:
    canonical = json.dumps(
        pipeline_manifest(settings, media_type),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
