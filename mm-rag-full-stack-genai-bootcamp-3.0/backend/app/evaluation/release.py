from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,79}$")
    split: Literal["tune", "validation", "holdout"]
    capability: Literal[
        "parsing", "retrieval", "answer", "citation", "authorization", "calculation"
    ]
    expected_outcome: Literal["pass", "abstain", "deny"]
    expected_evidence_ids: list[str] = Field(default_factory=list, max_length=20)


class EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    outcome: Literal["pass", "abstain", "deny", "fail"]
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    duration_ms: float = Field(ge=0, le=300_000)
    provider_calls: int = Field(ge=0, le=100)


@dataclass(frozen=True, slots=True)
class ReleaseMetrics:
    schema_revision: str
    split: str
    case_count: int
    passed_count: int
    outcome_accuracy: float
    evidence_identity_accuracy: float
    authorization_escape_count: int
    invalid_citation_count: int
    provider_calls: int
    estimated_cost_usd: float
    p95_latency_ms: float
    passed: bool
    failures: tuple[str, ...]


def load_cases(path: Path) -> list[EvaluationCase]:
    return [EvaluationCase.model_validate(item) for item in _load_jsonl(path)]


def load_results(path: Path) -> list[EvaluationResult]:
    return [EvaluationResult.model_validate(item) for item in _load_jsonl(path)]


def evaluate_release(
    cases: list[EvaluationCase],
    results: list[EvaluationResult],
    *,
    split: Literal["tune", "validation", "holdout"],
    provider_call_budget: int = 0,
    p95_latency_budget_ms: float = 100.0,
) -> ReleaseMetrics:
    selected = [case for case in cases if case.split == split]
    by_id = {result.case_id: result for result in results}
    if len(by_id) != len(results):
        raise ValueError("Evaluation result identities must be unique")
    if set(by_id) - {case.case_id for case in cases}:
        raise ValueError("Evaluation results contain unknown case identities")
    missing = [case.case_id for case in selected if case.case_id not in by_id]
    if missing:
        raise ValueError("Evaluation results do not cover the selected split")

    outcomes = 0
    evidence = 0
    authorization_escapes = 0
    invalid_citations = 0
    provider_calls = 0
    durations: list[float] = []
    for case in selected:
        result = by_id[case.case_id]
        outcomes += int(result.outcome == case.expected_outcome)
        evidence_match = result.evidence_ids == case.expected_evidence_ids
        evidence += int(evidence_match)
        if case.capability == "authorization" and result.outcome != "deny":
            authorization_escapes += 1
        if case.capability == "citation" and not evidence_match:
            invalid_citations += 1
        provider_calls += result.provider_calls
        durations.append(result.duration_ms)

    count = len(selected)
    if count == 0:
        raise ValueError("Evaluation split is empty")
    ordered = sorted(durations)
    p95_index = max(0, min(len(ordered) - 1, int(0.95 * len(ordered) + 0.999) - 1))
    p95 = ordered[p95_index]
    failures: list[str] = []
    if outcomes != count:
        failures.append("outcome_accuracy")
    if evidence != count:
        failures.append("evidence_identity")
    if authorization_escapes:
        failures.append("authorization_escape")
    if invalid_citations:
        failures.append("citation_identity")
    if provider_calls > provider_call_budget:
        failures.append("provider_call_budget")
    if p95 > p95_latency_budget_ms:
        failures.append("latency_budget")
    return ReleaseMetrics(
        schema_revision="phase7-release-evaluation-v1",
        split=split,
        case_count=count,
        passed_count=outcomes,
        outcome_accuracy=outcomes / count,
        evidence_identity_accuracy=evidence / count,
        authorization_escape_count=authorization_escapes,
        invalid_citation_count=invalid_citations,
        provider_calls=provider_calls,
        estimated_cost_usd=0.0,
        p95_latency_ms=p95,
        passed=not failures,
        failures=tuple(failures),
    )


def verify_manifest(root: Path) -> dict[str, object]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("dataset_revision") != "phase7-unified-evaluation-v1":
        raise ValueError("Phase 7 evaluation revision is invalid")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("Phase 7 evaluation hashes are missing")
    for relative, expected in files.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValueError("Phase 7 evaluation hash entry is invalid")
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("Phase 7 evaluation file is unavailable")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Phase 7 evaluation file hash mismatch")
    return manifest


def metrics_dict(metrics: ReleaseMetrics) -> dict[str, object]:
    return asdict(metrics)


def _load_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("Evaluation JSONL rows must be objects")
            rows.append(payload)
    return rows
