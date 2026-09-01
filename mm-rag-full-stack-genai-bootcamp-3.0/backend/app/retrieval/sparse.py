from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence

from fastembed import SparseTextEmbedding
from qdrant_client import models

from backend.app.retrieval.artifacts import SPARSE_MODEL, resolve_local_model

SPARSE_VECTOR_NAME = "sparse-bm25-v1"


class SparseEncoder(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> tuple[models.SparseVector, ...]: ...

    def embed_query(self, query: str) -> models.SparseVector: ...


class FastEmbedBM25Encoder:
    def __init__(self, cache_dir: Path) -> None:
        model_dir = resolve_local_model(SPARSE_MODEL, cache_dir)
        self._model = SparseTextEmbedding(
            model_name=SPARSE_MODEL.name,
            specific_model_path=str(model_dir),
            local_files_only=True,
            language="english",
        )

    def embed_documents(self, texts: Sequence[str]) -> tuple[models.SparseVector, ...]:
        return tuple(_qdrant_vector(item) for item in self._model.passage_embed(texts))

    def embed_query(self, query: str) -> models.SparseVector:
        vectors = tuple(self._model.query_embed(query))
        if len(vectors) != 1:
            raise RuntimeError("Sparse query encoder returned an invalid result count")
        return _qdrant_vector(vectors[0])


def _qdrant_vector(item: object) -> models.SparseVector:
    indices = getattr(item, "indices", None)
    values = getattr(item, "values", None)
    if indices is None or values is None or len(indices) != len(values):
        raise RuntimeError("Sparse encoder returned malformed output")
    return models.SparseVector(
        indices=[int(value) for value in indices],
        values=[float(value) for value in values],
    )
