from pathlib import Path

import pytest
from pydantic import SecretStr
from qdrant_client import QdrantClient, models

from backend.app.core.config import PROJECT_ROOT, Settings
from backend.app.retrieval import benchmark as benchmark_module
from backend.app.retrieval.benchmark import run_benchmark
from backend.app.retrieval.evaluation import load_dataset


class FakeEmbeddings:
    def __init__(self, **kwargs):
        pass

    def embed_documents(self, texts):
        return [[1.0, float(index % 3)] for index, _ in enumerate(texts)]


class FakeSparseEncoder:
    def __init__(self, cache_dir: Path):
        pass

    def embed_documents(self, texts):
        return tuple(
            models.SparseVector(indices=[index + 1], values=[1.0]) for index, _ in enumerate(texts)
        )

    def embed_query(self, query):
        return models.SparseVector(indices=[1], values=[1.0])


class FakeReranker:
    def __init__(self, cache_dir: Path, **kwargs):
        pass

    def scores(self, query, candidates):
        return tuple(float(-index) for index, _ in enumerate(candidates))


@pytest.mark.parametrize(
    ("validation_passes", "expected_lines"),
    ((False, 64), (True, 80)),
)
def test_benchmark_enforces_validation_before_holdout_without_persisting_content(
    monkeypatch, tmp_path: Path, validation_passes: bool, expected_lines: int
) -> None:
    monkeypatch.setattr(benchmark_module, "OpenAIEmbeddings", FakeEmbeddings)
    monkeypatch.setattr(benchmark_module, "FastEmbedBM25Encoder", FakeSparseEncoder)
    monkeypatch.setattr(benchmark_module, "FastEmbedCandidateReranker", FakeReranker)
    monkeypatch.setattr(
        benchmark_module,
        "phase5_gate",
        lambda dense, hybrid, **kwargs: (
            validation_passes,
            [] if validation_passes else ["failed"],
        ),
    )
    documents, queries = load_dataset(PROJECT_ROOT / "evaluation/phase5/v3")
    settings = Settings(
        app_env="test",
        database_url=SecretStr("sqlite+pysqlite:///:memory:"),
        openai_api_key=SecretStr("test-key"),
        phase5_model_cache_dir=tmp_path / "models",
    )
    qdrant = QdrantClient(path=str(tmp_path / "qdrant"))
    try:
        report = run_benchmark(
            settings=settings,
            qdrant=qdrant,
            documents=documents,
            queries=queries,
            output_dir=tmp_path / "results",
            embedding_cost_per_million_tokens=0.02,
        )
    finally:
        qdrant.close()

    assert set(report.profiles) == {
        "dense-v1",
        "hybrid-v1",
        "hybrid-v2",
        "hybrid-rerank-v1",
    }
    assert report.candidate_profile == "hybrid-v2"
    assert report.quality_contract_revision == "phase5-quality-v2"
    assert len(report.candidate_fingerprint) == 64
    assert set(report.class_metrics["hybrid-v2"]["validation"]) == {
        "semantic_paraphrase",
        "exact_identifier",
        "multi_document",
    }
    assert report.validation_passed is validation_passes
    assert report.holdout_evaluated is validation_passes
    assert ("holdout" in report.profiles["dense-v1"]) is validation_passes
    if validation_passes:
        assert report.profiles["dense-v1"]["holdout"].query_count == 16
    assert report.provider_calls == 1
    output = (tmp_path / "results/dense-v1.jsonl").read_text(encoding="utf-8")
    assert "When does" not in output
    assert len(output.splitlines()) == expected_lines
