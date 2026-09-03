from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from backend.app.core.config import PROJECT_ROOT
from backend.app.retrieval.ranking import hybrid_v2_profile_fingerprint
from scripts.build_phase5_v2_fixture import TOPICS

DATASET_REVISION = "phase5-retrieval-v3"
OUTPUT_ROOT = PROJECT_ROOT / "evaluation/phase5/v3"


def _chunk_id(document_number: int, chunk_number: int) -> str:
    return f"p5v3-doc-{document_number:02}-chunk-{chunk_number:02}"


def document_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for document_number, topic in enumerate(TOPICS, start=1):
        document_id = f"p5v3-doc-{document_number:02}"
        for chunk_number, content in enumerate(topic.evidence + topic.confounders, start=1):
            rows.append(
                {
                    "dataset_revision": DATASET_REVISION,
                    "chunk_id": _chunk_id(document_number, chunk_number),
                    "document_id": document_id,
                    "document_version_id": f"{document_id}-v1",
                    "generation_id": f"{document_id}-g1",
                    "title": topic.title,
                    "page_number": chunk_number,
                    "fixture_role": "evidence" if chunk_number <= 2 else "confounder",
                    "content": content,
                }
            )
    return rows


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
        "query_id": f"p5v3-q{number:03}",
        "split": split,
        "query_class": query_class,
        "query": query,
        "allowed_document_ids": (
            ["@workspace"]
            if allowed is None
            else [f"p5v3-doc-{document:02}" for document in allowed]
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


def _answerable_specs() -> dict[str, dict[str, tuple[tuple[str, tuple[tuple[int, int, int], ...]], ...]]]:
    return {
        "tune": {
            "semantic_paraphrase": (
                ("On what date does the main Acme services term roll forward?", ((1, 1, 3),)),
                ("How long are Zephyr finance records preserved after year close?", ((2, 1, 3),)),
                (
                    "Why did the western Orion service interruption happen?",
                    ((3, 2, 3), (3, 1, 1)),
                ),
                ("What is the payment deadline for the principal Nimbus bill?", ((4, 1, 3),)),
                (
                    "What paid time away is offered after a new child joins a family?",
                    ((5, 1, 3), (5, 2, 1)),
                ),
                (
                    "Which control protects administrator sign-in from credential phishing?",
                    ((6, 1, 3),),
                ),
                (
                    "Which checks must Aurora clear before public launch?",
                    ((7, 2, 3), (7, 1, 1)),
                ),
                (
                    "How soon is the first response for the highest-priority Cedar outage?",
                    ((8, 2, 3),),
                ),
                ("Who receives Acme's written nonrenewal notice?", ((1, 2, 3),)),
                ("Who can release a hold on Zephyr records?", ((2, 2, 3),)),
                ("Which reference must accompany the Nimbus payment?", ((4, 2, 3),)),
                ("How early may an Atlas parental leave begin?", ((5, 2, 3),)),
            ),
            "exact_identifier": (
                ("ACME-774 January 15 2027", ((1, 1, 3),)),
                ("ZP-204 seven years fiscal close", ((2, 1, 3),)),
                ("INC-442 forty-seven minutes May 8", ((3, 1, 3),)),
                ("INV-908 128450 September 30", ((4, 1, 3),)),
                ("PO-7712 Nimbus payment", ((4, 2, 3),)),
                ("\"sixteen weeks\" paid parental leave", ((5, 1, 3),)),
                ("phishing-resistant registered hardware security keys", ((6, 1, 3),)),
                ("Aurora general availability November 2026", ((7, 1, 3),)),
                ("ZP-204 workspace-owner approval", ((2, 2, 3),)),
                ("INC-442 automated certificate rotation", ((3, 2, 3),)),
                ("PO-7712 INV-908", ((4, 2, 3),)),
                ("Harbor June 15 evidence certification", ((9, 2, 3),)),
            ),
            "multi_document": (
                (
                    "Compare the Acme nonrenewal notice with Harbor's certification deadline.",
                    ((1, 2, 3), (9, 2, 3)),
                ),
                (
                    "Give the Zephyr retention period and Polaris European storage location.",
                    ((2, 1, 3), (11, 1, 3)),
                ),
                (
                    "State the Orion outage duration and Cedar priority-one response target.",
                    ((3, 1, 3), (8, 2, 3)),
                ),
                (
                    "List the Nimbus invoice total and Luna fourth-quarter marketing allocation.",
                    ((4, 1, 3), (10, 1, 3)),
                ),
                (
                    "Contrast Atlas practical notice with Acme nonrenewal notice.",
                    ((5, 2, 3), (1, 2, 3)),
                ),
                (
                    "Which anti-phishing control and Aurora launch safeguards are mandatory?",
                    ((6, 1, 3), (7, 2, 3)),
                ),
                (
                    "Who releases a Zephyr legal hold and approves a large Luna transfer?",
                    ((2, 2, 3), (10, 2, 3)),
                ),
                (
                    "Combine Redwood recovery-code handling with the Polaris exception rule.",
                    ((6, 2, 3), (11, 2, 3)),
                ),
                (
                    "Pair Atlas early-leave timing with Aurora launch timing.",
                    ((5, 2, 3), (7, 1, 3)),
                ),
                (
                    "Give the Acme renewal date and the Nimbus invoice due date.",
                    ((1, 1, 3), (4, 1, 3)),
                ),
                (
                    "Combine Cedar incident response with Vega escalation fields.",
                    ((8, 2, 3), (12, 2, 3)),
                ),
                (
                    "State the Zephyr legal-hold approver and Luna transfer approvers.",
                    ((2, 2, 3), (10, 2, 3)),
                ),
            ),
        },
        "validation": {
            "semantic_paraphrase": (
                ("How much warning should Atlas staff give before planned leave?", ((5, 2, 3),)),
                ("Which periods do not count against Cedar availability?", ((8, 1, 3),)),
                ("By when must Harbor control owners confirm complete evidence?", ((9, 2, 3),)),
                ("What details belong in a Vega customer-impact escalation?", ((12, 2, 3),)),
            ),
            "exact_identifier": (
                ("ACME-774 sixty days contract owner", ((1, 2, 3),)),
                ("INC-442 expired service certificate", ((3, 2, 3),)),
                ("INV-908 PO-7712", ((4, 2, 3),)),
                ("Harbor June 15, 2026", ((9, 2, 3),)),
            ),
            "multi_document": (
                (
                    "Combine Redwood administrator MFA with Polaris storage safeguards.",
                    ((6, 1, 3), (11, 1, 3)),
                ),
                (
                    "Pair Aurora launch gates with Harbor evidence completeness.",
                    ((7, 2, 3), (9, 2, 3)),
                ),
                (
                    "Give the Nimbus total and Cedar priority-one response time.",
                    ((4, 1, 3), (8, 2, 3)),
                ),
                (
                    "Compare Atlas early-leave timing and Acme notice timing.",
                    ((5, 2, 3), (1, 2, 3)),
                ),
            ),
        },
        "holdout": {
            "semantic_paraphrase": (
                ("When is the Acme service agreement scheduled to renew?", ((1, 1, 3),)),
                (
                    "How long was the Orion disruption and what triggered it?",
                    ((3, 1, 3), (3, 2, 3)),
                ),
                ("What happens when a Redwood emergency recovery code is used?", ((6, 2, 3),)),
                ("Whose authorization is required for a sizable Luna reallocation?", ((10, 2, 3),)),
            ),
            "exact_identifier": (
                ("Cedar 99.95%", ((8, 1, 3),)),
                ("Aurora November 2026", ((7, 1, 3),)),
                ("Polaris Frankfurt EU", ((11, 1, 3),)),
                ("Vega tier 1 tier 2 tier 3", ((12, 1, 3),)),
            ),
            "multi_document": (
                (
                    "Combine Zephyr record retention with the Luna marketing budget.",
                    ((2, 1, 3), (10, 1, 3)),
                ),
                (
                    "Pair Orion corrective action with Redwood administrator MFA.",
                    ((3, 2, 3), (6, 1, 3)),
                ),
                (
                    "Give the Harbor review and fieldwork dates plus the Acme renewal date.",
                    ((9, 1, 3), (1, 1, 3)),
                ),
                (
                    "State Nimbus purchase-order handling and Vega engineering escalation.",
                    ((4, 2, 3), (12, 1, 3)),
                ),
            ),
        },
    }


def _negative_specs() -> dict[str, tuple[tuple[str, tuple[int, ...], str, tuple[tuple[int, int], ...]], ...]]:
    return {
        "tune": (
            ("Which court governs ACME-774 disputes?", (1,), "unanswerable", ()),
            ("Which cipher does ZP-204 mandate for archives?", (2,), "unanswerable", ()),
            ("How many customers opened tickets during INC-442?", (3,), "unanswerable", ()),
            ("Which bank routing number receives INV-908?", (4,), "unanswerable", ()),
            ("What share of salary is paid during Atlas leave?", (5,), "unanswerable", ()),
            ("Which manufacturer supplies Redwood hardware keys?", (6,), "unanswerable", ()),
            ("What month is Aurora generally available?", (6,), "unauthorized_scope", ((7, 1),)),
            ("Who owns the ACME-774 contract?", (2,), "unauthorized_scope", ((1, 2),)),
            ("What caused INC-442?", (4,), "unauthorized_scope", ((3, 2),)),
            ("Which PO must reference INV-908?", (5,), "unauthorized_scope", ((4, 2),)),
            ("Who releases the ZP-204 hold?", (6,), "unauthorized_scope", ((2, 2),)),
            ("What fields describe a Vega escalation?", (7,), "unauthorized_scope", ((12, 2),)),
        ),
        "validation": (
            ("Which encryption algorithm protects Redwood keys?", (6,), "unanswerable", ()),
            ("Which vendor hosts Luna budgeting?", (10,), "unanswerable", ()),
            ("When does Harbor fieldwork begin?", (7,), "unauthorized_scope", ((9, 1),)),
            ("What permits a Polaris residency exception?", (12,), "unauthorized_scope", ((11, 2),)),
        ),
        "holdout": (
            ("Which law controls the Acme agreement?", (1,), "unanswerable", ()),
            ("What is the Polaris office street address?", (11,), "unanswerable", ()),
            ("What is Cedar monthly availability?", (5,), "unauthorized_scope", ((8, 1),)),
            ("What amount is due on INV-908?", (8,), "unauthorized_scope", ((4, 1),)),
        ),
    }


def judgment_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    number = 1
    answerable = _answerable_specs()
    negatives = _negative_specs()
    for split in ("tune", "validation", "holdout"):
        for query_class in ("semantic_paraphrase", "exact_identifier", "multi_document"):
            for query, relevance in answerable[split][query_class]:
                rows.append(_query(number, split, query_class, query, relevance))
                number += 1
        for query, allowed, negative_kind, excluded in negatives[split]:
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


def dense_profile() -> dict[str, Any]:
    return {
        "dataset_revision": DATASET_REVISION,
        "baseline": "dense-v1",
        "candidate": "hybrid-v2",
        "candidate_profile_fingerprint": hybrid_v2_profile_fingerprint(),
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
        "predecessor_holdout_policy": "sealed-not-reused",
        "paid_run": "explicit-opt-in",
    }


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return "".join(
        json.dumps(row, sort_keys=False, separators=(",", ":")) + "\n" for row in rows
    ).encode()


def rendered_files() -> dict[str, bytes]:
    documents = document_rows()
    judgments = judgment_rows()
    files = {
        "dense-profile.json": (
            json.dumps(dense_profile(), sort_keys=True, indent=2) + "\n"
        ).encode(),
        "documents.jsonl": _jsonl(documents),
        "judgments.jsonl": _jsonl(judgments),
    }
    manifest = {
        "dataset_revision": DATASET_REVISION,
        "supersedes": "phase5-retrieval-v2",
        "chunk_count": len(documents),
        "query_count": len(judgments),
        "minimum_quality_candidate_pool": 50,
        "quality_contract_revision": "phase5-quality-v2",
        "candidate_profile": "hybrid-v2",
        "candidate_profile_fingerprint": hybrid_v2_profile_fingerprint(),
        "holdout_policy": "validation-before-holdout",
        "predecessor_holdout_policy": "sealed-not-reused",
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
        raise SystemExit(f"Phase 5 v3 fixture is stale: {', '.join(mismatches)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the synthetic Phase 5 v3 fixture")
    parser.add_argument("--output", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check_fixture(args.output)
        print("Phase 5 v3 fixture is reproducible")
        return
    write_fixture(args.output)
    print(f"Wrote Phase 5 v3 fixture to {args.output}")


if __name__ == "__main__":
    main()
