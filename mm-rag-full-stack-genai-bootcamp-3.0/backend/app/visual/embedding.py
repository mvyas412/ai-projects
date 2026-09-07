from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from typing import Protocol

from fastembed import ImageEmbedding, TextEmbedding
from PIL import Image

from backend.app.retrieval.artifacts import resolve_local_model
from backend.app.visual.artifacts import VISUAL_IMAGE_MODEL, VISUAL_TEXT_MODEL

VISUAL_EMBEDDING_PROFILE = "visual-clip-v1"
VISUAL_VECTOR_SIZE = 512
VISUAL_VECTOR_DISTANCE = "cosine"
VISUAL_IMAGE_PREPROCESSING = "fastembed-preprocessor-config-rgb-v1"
VISUAL_VECTOR_NORMALIZATION = "application-l2-v1"


class VisualEmbeddingError(RuntimeError):
    """Raised when the pinned visual embedding contract cannot be satisfied."""


class VisualEmbeddingEncoder(Protocol):
    def embed_images(self, images: Sequence[bytes]) -> tuple[tuple[float, ...], ...]: ...

    def embed_query(self, query: str) -> tuple[float, ...]: ...


class FastEmbedCLIPEncoder:
    """Load the reviewed CLIP pair only from checksum-verified local snapshots."""

    def __init__(self, cache_dir: Path, *, threads: int = 2, batch_size: int = 8) -> None:
        image_path = resolve_local_model(VISUAL_IMAGE_MODEL, cache_dir)
        text_path = resolve_local_model(VISUAL_TEXT_MODEL, cache_dir)
        self._batch_size = batch_size
        self._image_model = ImageEmbedding(
            model_name=VISUAL_IMAGE_MODEL.name,
            cache_dir=str(cache_dir),
            threads=threads,
            local_files_only=True,
            specific_model_path=str(image_path),
        )
        self._text_model = TextEmbedding(
            model_name=VISUAL_TEXT_MODEL.name,
            cache_dir=str(cache_dir),
            threads=threads,
            local_files_only=True,
            specific_model_path=str(text_path),
        )

    def embed_images(self, images: Sequence[bytes]) -> tuple[tuple[float, ...], ...]:
        decoded: list[Image.Image] = []
        try:
            for content in images:
                with Image.open(BytesIO(content)) as source:
                    decoded.append(source.convert("RGB"))
            vectors = self._image_model.embed(decoded, batch_size=self._batch_size)
            return tuple(_validated_vector(vector) for vector in vectors)
        except VisualEmbeddingError:
            raise
        except Exception as exc:
            raise VisualEmbeddingError("Local visual image embedding failed") from exc

    def embed_query(self, query: str) -> tuple[float, ...]:
        normalized = " ".join(query.split())
        if not normalized:
            raise VisualEmbeddingError("Visual query is empty")
        try:
            vectors = tuple(self._text_model.embed([normalized], batch_size=1))
            if len(vectors) != 1:
                raise VisualEmbeddingError("Visual text encoder returned an invalid result count")
            return _validated_vector(vectors[0])
        except VisualEmbeddingError:
            raise
        except Exception as exc:
            raise VisualEmbeddingError("Local visual text embedding failed") from exc


def visual_embedding_manifest(*, batch_size: int) -> dict[str, object]:
    return {
        "profile": VISUAL_EMBEDDING_PROFILE,
        "provider": "fastembed",
        "image_model": {
            "name": VISUAL_IMAGE_MODEL.name,
            "revision": VISUAL_IMAGE_MODEL.revision,
            "tree_sha256": VISUAL_IMAGE_MODEL.tree_sha256,
            "license": VISUAL_IMAGE_MODEL.license,
        },
        "text_model": {
            "name": VISUAL_TEXT_MODEL.name,
            "revision": VISUAL_TEXT_MODEL.revision,
            "tree_sha256": VISUAL_TEXT_MODEL.tree_sha256,
            "license": VISUAL_TEXT_MODEL.license,
        },
        "preprocessing": VISUAL_IMAGE_PREPROCESSING,
        "normalization": VISUAL_VECTOR_NORMALIZATION,
        "dimensions": VISUAL_VECTOR_SIZE,
        "distance": VISUAL_VECTOR_DISTANCE,
        "batch_size": batch_size,
    }


def visual_embedding_fingerprint(*, batch_size: int) -> str:
    encoded = json.dumps(
        visual_embedding_manifest(batch_size=batch_size),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validated_vector(values) -> tuple[float, ...]:
    vector = tuple(float(value) for value in values)
    if len(vector) != VISUAL_VECTOR_SIZE or any(not math.isfinite(value) for value in vector):
        raise VisualEmbeddingError("Visual encoder returned a malformed vector")
    norm = math.sqrt(sum(value * value for value in vector))
    if not math.isfinite(norm) or norm <= 0:
        raise VisualEmbeddingError("Visual encoder returned a zero vector")
    return tuple(value / norm for value in vector)
