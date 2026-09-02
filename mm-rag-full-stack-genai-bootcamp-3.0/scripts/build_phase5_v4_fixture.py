from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from backend.app.core.config import PROJECT_ROOT
from backend.app.retrieval.ranking import hybrid_v3_profile_fingerprint
from scripts.build_phase5_v3_fixture import (
    document_rows as v3_document_rows,
)
from scripts.build_phase5_v3_fixture import (
    judgment_rows as v3_judgment_rows,
)

DATASET_REVISION = "phase5-retrieval-v4"
OUTPUT_ROOT = PROJECT_ROOT / "evaluation/phase5/v4"


def _chunk_id(document_number: int, chunk_number: int) -> str:
    return f"p5v4-doc-{document_number:02}-chunk-{chunk_number:02}"


def _replace_v3_identity(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("phase5-retrieval-v3", DATASET_REVISION).replace("p5v3-", "p5v4-")
    if isinstance(value, list):
        return [_replace_v3_identity(item) for item in value]
    if isinstance(value, dict):
        return {key: _replace_v3_identity(item) for key, item in value.items()}
    return value


def document_rows() -> list[dict[str, Any]]:
    return [_replace_v3_identity(row) for row in v3_document_rows()]


def _query(
    number: int,
    split: str,
    query_class: str,
    query: str,
    relevance: tuple[tuple[int, int, int], ...] = (),
    *,
    allowed: tuple[int, ...] | None = None,
    negative_kind: str | None = None,
    excluded: tuple[tuple[int, int], ...] = (),
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "dataset_revision": DATASET_REVISION,
        "query_id": f"p5v4-q{number:03}",
        "split": split,
        "query_class": query_class,
        "query": query,
        "allowed_document_ids": (
            ["@workspace"]
            if allowed is None
            else [f"p5v4-doc-{document:02}" for document in allowed]
        ),
        "answerable": bool(relevance),
        "relevance": [
            {"chunk_id": _chunk_id(document, chunk), "grade": grade}
            for document, chunk, grade in relevance
        ],
    }
    if negative_kind is not None:
        row["negative_kind"] = negative_kind
    if excluded:
        row["excluded_relevant_chunk_ids"] = [
            _chunk_id(document, chunk) for document, chunk in excluded
        ]
    return row


PROTECTED_ANSWERABLE = {
    "validation": {
        "semantic_paraphrase": (
            ("When does the Acme services term renew if no party opts out?", ((1, 1, 3),)),
            ("Who may authorize disposal after a Zephyr legal hold ends?", ((2, 2, 3),)),
            ("What permanent fix followed the Orion regional interruption?", ((3, 2, 3),)),
            ("How much paid family leave does Atlas provide?", ((5, 1, 3),)),
        ),
        "exact_identifier": (
            ("Cedar 99.95% planned maintenance", ((8, 1, 3),)),
            ("Harbor SOC 2 June 3 June 22", ((9, 1, 3),)),
            ('"$600,000" partner campaigns', ((10, 1, 3),)),
            ("Polaris Frankfurt European Union", ((11, 1, 3),)),
        ),
        "multi_document": (
            (
                "Compare the Acme opt-out period with the Atlas planned-leave notice.",
                ((1, 2, 3), (5, 2, 3)),
            ),
            (
                "Pair the Cedar priority-one response interval with Harbor's certification deadline.",
                ((8, 2, 3), (9, 2, 3)),
            ),
            (
                "Combine Zephyr hold-release authority with Luna large-transfer approval.",
                ((2, 2, 3), (10, 2, 3)),
            ),
            (
                "Which safeguards cover Redwood administrator access and Aurora launch readiness?",
                ((6, 1, 3), (7, 2, 3)),
            ),
        ),
    },
    "holdout": {
        "semantic_paraphrase": (
            (
                "What notice prevents the Acme agreement from automatically renewing?",
                ((1, 2, 3),),
            ),
            (
                "What step restores Redwood access after an emergency code is used?",
                ((6, 2, 3),),
            ),
            (
                "What condition must Aurora meet regarding critical launch blockers?",
                ((7, 2, 3),),
            ),
            (
                "How are Luna reallocations over the threshold governed?",
                ((10, 2, 3),),
            ),
        ),
        "exact_identifier": (
            ("INV-908 $128,450 September 30", ((4, 1, 3),)),
            ("Atlas sixteen weeks paid leave", ((5, 1, 3),)),
            ("Cedar priority-one thirty minutes", ((8, 2, 3),)),
            ("Vega tier-3 Account Manager Sales Engineer", ((12, 1, 3),)),
        ),
        "multi_document": (
            (
                "Contrast Zephyr's retention duration with Polaris's storage region.",
                ((2, 1, 3), (11, 1, 3)),
            ),
            (
                "Combine Orion's incident duration with Harbor's fieldwork dates.",
                ((3, 1, 3), (9, 1, 3)),
            ),
            (
                "Pair Nimbus remittance reference with Vega escalation details.",
                ((4, 2, 3), (12, 2, 3)),
            ),
            (
                "What controls protect Redwood administrators and Polaris residency exceptions?",
                ((6, 1, 3), (11, 2, 3)),
            ),
        ),
    },
}

PROTECTED_NEGATIVES = {
    "validation": (
        ("What arbitration venue applies to the Acme contract?", (1,), "unanswerable", ()),
        (
            "What is the name of Redwood's security-key manufacturer?",
            (6,),
            "unanswerable",
            (),
        ),
        (
            "What date must Harbor evidence be certified?",
            (7,),
            "unauthorized_scope",
            ((9, 2),),
        ),
        (
            "Which approvals permit a Luna transfer above one hundred thousand dollars?",
            (11,),
            "unauthorized_scope",
            ((10, 2),),
        ),
    ),
    "holdout": (
        (
            "What interest rate applies to overdue Nimbus invoices?",
            (4,),
            "unanswerable",
            (),
        ),
        ("Which insurer underwrites Atlas parental leave?", (5,), "unanswerable", ()),
        (
            "What is the approved Cedar availability target?",
            (12,),
            "unauthorized_scope",
            ((8, 1),),
        ),
        (
            "Where must Polaris customer records stay?",
            (2,),
            "unauthorized_scope",
            ((11, 1),),
        ),
    ),
}


def judgment_rows() -> list[dict[str, Any]]:
    rows = [_replace_v3_identity(row) for row in v3_judgment_rows() if row["split"] == "tune"]
    number = len(rows) + 1
    for split in ("validation", "holdout"):
        for query_class in ("semantic_paraphrase", "exact_identifier", "multi_document"):
            for query, relevance in PROTECTED_ANSWERABLE[split][query_class]:
                rows.append(_query(number, split, query_class, query, relevance))
                number += 1
        for query, allowed, negative_kind, excluded in PROTECTED_NEGATIVES[split]:
            rows.append(
                _query(
                    number,
                    split,
                    "negative",
                    query,
                    allowed=allowed,
                    negative_kind=negative_kind,
                    excluded=excluded,
                )
            )
            number += 1
    return rows


def _protected_hash(rows: list[dict[str, Any]]) -> str:
    protected = sorted(
        " ".join(str(row["query"]).casefold().split())
        for row in rows
        if row["split"] in {"validation", "holdout"}
    )
    return hashlib.sha256("\n".join(protected).encode()).hexdigest()


def _predecessor_protected_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for revision in ("v1", "v2", "v3"):
        path = PROJECT_ROOT / "evaluation/phase5" / revision / "judgments.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("split") in {"validation", "holdout"}:
                rows.append(row)
    return rows


def dense_profile() -> dict[str, Any]:
    return {
        "dataset_revision": DATASET_REVISION,
        "baseline": "dense-v1",
        "candidate": "hybrid-v3",
        "candidate_profile_fingerprint": hybrid_v3_profile_fingerprint(),
        "source_release": "mm-rag-v4.0.0",
        "pipeline_profile": "phase3-async-v1",
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "qdrant_collection_schema": "unnamed-dense-cosine-with-payload-schema-2",
        "authorization_scope_revision": "adr-0015-v1",
        "candidate_limits": {"per_leg": 30, "pre_rerank": 20, "final_evidence": 8},
        "evaluation_depth": 10,
        "minimum_quality_candidate_pool": 50,
        "metric_revision": "phase5-quality-v2",
        "holdout_policy": "validation-before-holdout",
        "predecessor_holdout_policy": "v1-v3-sealed-not-reused",
        "tuning_source_revision": "phase5-retrieval-v3:tune",
        "paid_run": "explicit-opt-in",
    }


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return "".join(
        json.dumps(row, sort_keys=False, separators=(",", ":")) + "\n" for row in rows
    ).encode()


def rendered_files() -> dict[str, bytes]:
    documents = document_rows()
    judgments = judgment_rows()
    predecessor_rows = _predecessor_protected_rows()
    files = {
        "dense-profile.json": (
            json.dumps(dense_profile(), sort_keys=True, indent=2) + "\n"
        ).encode(),
        "documents.jsonl": _jsonl(documents),
        "judgments.jsonl": _jsonl(judgments),
    }
    manifest = {
        "dataset_revision": DATASET_REVISION,
        "supersedes": "phase5-retrieval-v3",
        "chunk_count": len(documents),
        "query_count": len(judgments),
        "minimum_quality_candidate_pool": 50,
        "quality_contract_revision": "phase5-quality-v2",
        "candidate_profile": "hybrid-v3",
        "candidate_profile_fingerprint": hybrid_v3_profile_fingerprint(),
        "holdout_policy": "validation-before-holdout",
        "predecessor_holdout_policy": "v1-v3-sealed-not-reused",
        "tuning_source_revision": "phase5-retrieval-v3:tune",
        "protected_query_sha256": _protected_hash(judgments),
        "predecessor_protected_query_sha256": _protected_hash(predecessor_rows),
        "split": {"tune": 48, "validation": 16, "holdout": 16},
        "files": {
            name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())
        },
    }
    files["manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    return files


def write_fixture(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name, content in rendered_files().items():
        (output / name).write_bytes(content)


def check_fixture(output: Path) -> None:
    mismatches = [
        name
        for name, content in rendered_files().items()
        if not (output / name).exists() or (output / name).read_bytes() != content
    ]
    if mismatches:
        raise SystemExit(f"Phase 5 v4 fixture is stale: {', '.join(mismatches)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the synthetic Phase 5 v4 fixture")
    parser.add_argument("--output", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check_fixture(args.output)
        print("Phase 5 v4 fixture is reproducible")
        return
    write_fixture(args.output)
    print(f"Wrote Phase 5 v4 fixture to {args.output}")


if __name__ == "__main__":
    main()
