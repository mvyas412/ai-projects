from __future__ import annotations

import hashlib
import json
from importlib.metadata import version

from backend.app.core.config import Settings
from backend.app.retrieval.artifacts import SPARSE_MODEL
from backend.app.retrieval.sparse import SPARSE_VECTOR_NAME

PIPELINE_PROFILE = "phase5-hybrid-v1"


def pipeline_manifest(settings: Settings, media_type: str) -> dict[str, object]:
    """Return the canonical output-affecting ingestion contract from ADR 0008."""

    extractor = {
        "application/pdf": "pypdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "python-docx",
    }.get(media_type, "utf8-or-vision")
    manifest: dict[str, object] = {
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
        "sparse_embedding": {
            "enabled": settings.rag_sparse_indexing_enabled,
            "provider": "fastembed",
            "library_version": version("fastembed"),
            "model": SPARSE_MODEL.name,
            "model_revision": SPARSE_MODEL.revision,
            "model_tree_sha256": SPARSE_MODEL.tree_sha256,
            "license": SPARSE_MODEL.license,
            "language": "english",
            "vector_name": SPARSE_VECTOR_NAME,
            "qdrant_modifier": "idf",
        },
        "index": {
            "provider": "qdrant",
            "payload_schema_revision": 3,
            "generation_filter_required": True,
        },
        "citation_schema_revision": 1,
    }
    if settings.phase6_visual_enabled and media_type in {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/tiff",
        "image/webp",
    }:
        manifest["visual_extraction"] = {
            "profile": settings.phase6_extraction_profile,
            "implementation": "docling-or-pillow",
            "library_version": version("docling"),
            "artifacts_manifest_revision": "docling-structural-v1",
            "remote_services": False,
            "picture_description": False,
            "ocr": "tesseract-cli-eng",
            "table_structure": "tableformer-accurate",
            "image_scale": settings.phase6_image_scale,
            "locator_schema_revision": "region-locator-v1",
        }
    return manifest


def pipeline_fingerprint(settings: Settings, media_type: str) -> str:
    canonical = json.dumps(
        pipeline_manifest(settings, media_type),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def manifest_supports_sparse(manifest: dict[str, object] | None) -> bool:
    if not manifest:
        return False
    pipeline = manifest.get("pipeline")
    if not isinstance(pipeline, dict):
        return False
    sparse = pipeline.get("sparse_embedding")
    return bool(
        pipeline.get("profile") == PIPELINE_PROFILE
        and isinstance(sparse, dict)
        and sparse.get("enabled") is True
        and sparse.get("vector_name") == SPARSE_VECTOR_NAME
        and sparse.get("model_revision") == SPARSE_MODEL.revision
        and sparse.get("model_tree_sha256") == SPARSE_MODEL.tree_sha256
        and sparse.get("qdrant_modifier") == "idf"
        and manifest.get("sparse_vector_count") == manifest.get("chunk_count")
    )
