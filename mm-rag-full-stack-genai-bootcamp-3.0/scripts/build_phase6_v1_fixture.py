from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from backend.app.core.config import PROJECT_ROOT
from backend.app.visual.evaluation import (
    DATASET_REVISION,
    QUALITY_CONTRACT_REVISION,
    SPLIT_CLASS_COUNTS,
)

OUTPUT = PROJECT_ROOT / "evaluation/phase6/v1"
REGION_KINDS = ("figure", "chart", "diagram", "table", "photo")


def rendered_files() -> dict[str, bytes]:
    regions = _regions()
    questions = _questions(regions)
    region_bytes = _jsonl(regions)
    question_bytes = _jsonl(questions)
    profile = {
        "dataset_revision": DATASET_REVISION,
        "profile": "ocr-markdown-baseline-v1",
        "representation": "baseline_text",
        "retrieval": "authorized lexical token overlap",
        "calculation": "unsupported",
        "provider_calls": 0,
    }
    profile_bytes = _json_bytes(profile)
    files = {
        "baseline-profile.json": _sha256(profile_bytes),
        "judgments.jsonl": _sha256(question_bytes),
        "regions.jsonl": _sha256(region_bytes),
    }
    protected = [
        row["query"].casefold().strip() for row in questions if row["split"] != "tune"
    ]
    manifest = {
        "dataset_revision": DATASET_REVISION,
        "quality_contract_revision": QUALITY_CONTRACT_REVISION,
        "region_count": len(regions),
        "query_count": len(questions),
        "split": {
            split: sum(counts.values()) for split, counts in SPLIT_CLASS_COUNTS.items()
        },
        "classes": list(SPLIT_CLASS_COUNTS["tune"]),
        "holdout_policy": "validation-before-holdout",
        "private_representative_tier": "ignored",
        "protected_query_sha256": _canonical_sha256(protected),
        "files": files,
    }
    return {
        "baseline-profile.json": profile_bytes,
        "judgments.jsonl": question_bytes,
        "manifest.json": _json_bytes(manifest),
        "regions.jsonl": region_bytes,
    }


def _regions() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(40):
        ordinal = index + 1
        split = "tune" if index < 24 else "validation" if index < 32 else "holdout"
        document_number = index % 8 + 1
        kind = REGION_KINDS[index % len(REGION_KINDS)]
        code = f"VX-{ordinal:03d}"
        source = _source_text(kind, ordinal, code)
        rows.append(
            {
                "dataset_revision": DATASET_REVISION,
                "region_id": f"p6v1-region-{ordinal:03d}",
                "split": split,
                "document_id": f"p6v1-doc-{document_number:02d}",
                "document_version_id": f"p6v1-doc-{document_number:02d}-v1",
                "generation_id": f"p6v1-doc-{document_number:02d}-g1",
                "page_number": index // 8 + 1,
                "region_kind": kind,
                "bbox": [0.05 + (index % 3) * 0.1, 0.08, 0.62, 0.42 + (index % 2) * 0.1],
                "source_text": source,
                # This intentionally mirrors today's limited OCR/Markdown evidence.
                "baseline_text": f"{kind.title()} {code}",
            }
        )
    return rows


def _source_text(kind: str, ordinal: int, code: str) -> str:
    north = 10 + ordinal
    south = 17 + ordinal
    if kind == "figure":
        return (
            f"{code}: the amber intake pump feeds the cobalt valve, which sends flow "
            f"to chamber {ordinal}."
        )
    if kind == "chart":
        return f"{code}: North={north} units; South={south} units; South exceeds North by 7."
    if kind == "diagram":
        return (
            f"{code}: request node {ordinal} flows to approval, then encryption, then archive."
        )
    if kind == "table":
        return (
            f"{code}: Region | Q1 | Q2; North | {north} | {north + 4}; "
            f"South | {south} | {south + 6}."
        )
    return f"{code}: a red safety lever is left of a blue pressure gauge marked {north} PSI."


def _questions(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    query_number = 0
    by_split = {
        split: [row for row in regions if row["split"] == split] for split in SPLIT_CLASS_COUNTS
    }
    for split, class_counts in SPLIT_CLASS_COUNTS.items():
        pools = {
            "figure_relationship": [
                row for row in by_split[split] if row["region_kind"] in {"figure", "diagram", "photo"}
            ],
            "chart": [row for row in by_split[split] if row["region_kind"] == "chart"],
            "table_lookup": [row for row in by_split[split] if row["region_kind"] == "table"],
            "calculation": [row for row in by_split[split] if row["region_kind"] == "table"],
        }
        for query_class, count in class_counts.items():
            for class_index in range(count):
                query_number += 1
                if query_class == "negative":
                    output.append(
                        _negative_question(
                            query_number=query_number,
                            split=split,
                            class_index=class_index,
                            split_regions=by_split[split],
                        )
                    )
                    continue
                target = pools[query_class][class_index % len(pools[query_class])]
                output.append(
                    _answerable_question(
                        query_number=query_number,
                        query_class=query_class,
                        class_index=class_index,
                        target=target,
                    )
                )
    return output


def _answerable_question(
    *, query_number: int, query_class: str, class_index: int, target: dict[str, Any]
) -> dict[str, Any]:
    ordinal = int(str(target["region_id"]).rsplit("-", 1)[1])
    code = f"VX-{ordinal:03d}"
    north = 10 + ordinal
    south = 17 + ordinal
    include_code = class_index % 3 == 0
    prefix = f"For {code}, " if include_code else ""
    suffix = f" (case {query_number})"
    if query_class == "figure_relationship":
        query = f"{prefix}what object or step comes immediately after the first element in scene {ordinal}?{suffix}"
    elif query_class == "chart":
        query = f"{prefix}which region has the larger plotted value in comparison {ordinal}?{suffix}"
    elif query_class == "table_lookup":
        query = f"{prefix}what is the South Q2 entry in report {ordinal}?{suffix}"
    else:
        operation = ("sum", "difference", "average", "ratio")[class_index % 4]
        if operation == "sum":
            expected = str(north + south)
            query = f"{prefix}what is North Q1 plus South Q1 in report {ordinal}?{suffix}"
        elif operation == "difference":
            expected = str(south - north)
            query = f"{prefix}how much larger is South Q1 than North Q1 in report {ordinal}?{suffix}"
        elif operation == "average":
            expected = f"{(north + south) / 2:.1f}"
            query = f"{prefix}what is the average of North Q1 and South Q1 in report {ordinal}?{suffix}"
        else:
            expected = f"{south / north:.6f}"
            query = f"{prefix}what is the South-to-North Q1 ratio in report {ordinal}?{suffix}"
    row: dict[str, Any] = {
        "dataset_revision": DATASET_REVISION,
        "query_id": f"p6v1-q{query_number:03d}",
        "split": target["split"],
        "query_class": query_class,
        "query": query,
        "allowed_document_ids": [target["document_id"]],
        "answerable": True,
        "relevance": [{"region_id": target["region_id"], "grade": 3}],
    }
    if query_class == "calculation":
        row.update(
            {
                "expected_operation": operation,
                "expected_value": expected,
                "expected_unit": "units",
            }
        )
    return row


def _negative_question(
    *, query_number: int, split: str, class_index: int, split_regions: list[dict[str, Any]]
) -> dict[str, Any]:
    kind = ("unanswerable", "ambiguous_calculation", "unauthorized_scope")[class_index % 3]
    target = split_regions[class_index % len(split_regions)]
    row: dict[str, Any] = {
        "dataset_revision": DATASET_REVISION,
        "query_id": f"p6v1-q{query_number:03d}",
        "split": split,
        "query_class": "negative",
        "allowed_document_ids": [target["document_id"]],
        "answerable": False,
        "relevance": [],
        "negative_kind": kind,
    }
    if kind == "unanswerable":
        row["query"] = f"Which purple moon icon approves deletion in missing panel {query_number}?"
    elif kind == "ambiguous_calculation":
        row["query"] = f"What is the total without naming a row, column, or unit in report {query_number}?"
    else:
        excluded = next(
            region for region in split_regions if region["document_id"] != target["document_id"]
        )
        ordinal = int(str(excluded["region_id"]).rsplit("-", 1)[1])
        row["query"] = f"Show restricted visual VX-{ordinal:03d} for audit {query_number}."
        row["excluded_relevant_region_ids"] = [excluded["region_id"]]
    return row


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return ("\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows) + "\n").encode()


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(values: list[str]) -> str:
    return _sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode())


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the deterministic Phase 6 v1 fixture")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = rendered_files()
    if args.check:
        mismatches = [name for name, content in files.items() if not (OUTPUT / name).is_file() or (OUTPUT / name).read_bytes() != content]
        if mismatches:
            raise SystemExit(f"Phase 6 fixture drift: {', '.join(mismatches)}")
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (OUTPUT / name).write_bytes(content)


if __name__ == "__main__":
    main()
