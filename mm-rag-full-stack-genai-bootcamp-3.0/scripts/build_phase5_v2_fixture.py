from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.core.config import PROJECT_ROOT

DATASET_REVISION = "phase5-retrieval-v2"
OUTPUT_ROOT = PROJECT_ROOT / "evaluation/phase5/v2"


@dataclass(frozen=True, slots=True)
class Topic:
    title: str
    evidence: tuple[str, str]
    confounders: tuple[str, ...]


TOPICS = (
    Topic(
        "Acme Services Agreement",
        (
            "Agreement ACME-774 renews on January 15, 2027 unless timely notice prevents renewal.",
            "Either party can prevent ACME-774 renewal with sixty days written notice to the contract owner.",
        ),
        (
            "Agreement ACME-747 renews on January 15, 2028 after an annual commercial review.",
            "Agreement ACME-744 uses a forty-five day nonrenewal notice period.",
            "The Acme facilities contract ACME-477 expires on July 15, 2027 without automatic renewal.",
            "A procurement addendum requires ninety days notice before changing service volumes.",
            "The vendor review calendar lists a January 15 meeting for contract ACME-707.",
            "An unrelated consulting agreement renews after a sixty-day pricing review.",
            "Contract owners receive renewal reminders seventy-five days before each anniversary.",
            "The Acme support schedule describes monthly service reviews but no renewal right.",
        ),
    ),
    Topic(
        "Zephyr Retention Policy",
        (
            "Policy ZP-204 retains financial records for seven years after the fiscal year closes.",
            "A legal hold overrides deletion under ZP-204; release requires workspace-owner approval.",
        ),
        (
            "Policy ZP-240 retains payroll summaries for six years after calendar-year close.",
            "Policy ZP-402 keeps security alerts for eighteen months unless an investigation is open.",
            "A tax schedule retains supporting worksheets for five years after filing.",
            "The procurement archive removes superseded bids after three years.",
            "A privacy request pauses deletion while identity verification is incomplete.",
            "Department owners review retention exceptions every seven months.",
            "Litigation notices are routed to counsel before any archive action proceeds.",
            "The Zephyr backup guide rotates weekly snapshots after thirty-five days.",
        ),
    ),
    Topic(
        "Orion Incident Review",
        (
            "Incident INC-442 interrupted the west region for forty-seven minutes on May 8, 2026.",
            "INC-442 was caused by an expired service certificate; automated rotation is the corrective action.",
        ),
        (
            "Incident INC-424 interrupted the west region for seventy-four minutes on May 18, 2026.",
            "Incident INC-244 affected the east region for forty-two minutes after a routing error.",
            "A database failover exercise lasted forty-seven minutes but caused no customer outage.",
            "The certificate inventory review found two services within thirty days of expiration.",
            "A DNS incident was corrected by reducing stale-record time to live.",
            "The central region experienced packet loss during a scheduled network test.",
            "On May 8, the operations team completed an unrelated recovery rehearsal.",
            "The Orion action register assigns load-test automation to the platform team.",
        ),
    ),
    Topic(
        "Nimbus Invoice",
        (
            "Invoice INV-908 totals 128450 US dollars and is due September 30, 2026.",
            "Payment for INV-908 must reference purchase order PO-7712.",
        ),
        (
            "Invoice INV-980 totals 128540 US dollars and is due October 30, 2026.",
            "Invoice INV-809 totals 182450 US dollars and references purchase order PO-7172.",
            "Credit memo CM-908 reduces a separate balance by 12845 US dollars.",
            "The September forecast reserves 130000 US dollars for cloud services.",
            "Purchase order PO-7721 covers hardware delivered in the fourth quarter.",
            "Accounts payable closes September submissions on the twenty-fifth.",
            "A vendor statement lists three invoices awaiting receiving confirmation.",
            "Nimbus billing questions are assigned to the accounts-payable operations queue.",
        ),
    ),
    Topic(
        "Atlas Employee Handbook",
        (
            "Eligible employees receive sixteen weeks of paid parental leave after birth, adoption, or placement.",
            "Parental leave may start two weeks early; employees give People Operations thirty days notice when practical.",
        ),
        (
            "Caregiver leave provides six paid weeks for an immediate-family medical event.",
            "Medical recovery leave can continue for twelve weeks with approved documentation.",
            "Employees request planned sabbaticals at least sixty days before departure.",
            "Jury-duty leave remains paid for the length of required service.",
            "A flexible-work request should be submitted fourteen days before the proposed change.",
            "Vacation balances above sixteen days require manager review before year end.",
            "People Operations answers benefit questions through the employee support portal.",
            "Adoption assistance reimburses eligible fees but does not change leave duration.",
        ),
    ),
    Topic(
        "Redwood Security Standard",
        (
            "Administrators must use phishing-resistant multifactor authentication with registered hardware security keys.",
            "Emergency recovery codes are sealed in the security vault and every use creates a high-severity audit event.",
        ),
        (
            "Standard RS-401 requires application users to enroll a time-based authenticator.",
            "Privileged workstation disks use hardware-backed encryption keys.",
            "Physical data-center entry requires a badge and a rotating numeric code.",
            "Service accounts rotate client secrets every ninety days through automation.",
            "Security-key inventory is reconciled monthly by endpoint operations.",
            "Password resets require identity verification through the help desk.",
            "The phishing simulation program sends quarterly training exercises.",
            "A break-glass review verifies sealed credentials without opening their envelopes.",
        ),
    ),
    Topic(
        "Bluebird Product Roadmap",
        (
            "Project Aurora is scheduled for general availability in November 2026 after the October readiness review.",
            "Aurora's launch gate requires accessibility signoff, a recovery exercise, and zero unresolved critical defects.",
        ),
        (
            "Project Borealis is scheduled for general availability in November 2027.",
            "Project Aurelia enters private preview in October 2026 after a design review.",
            "The mobile release requires localization signoff and two weeks of beta stability.",
            "A quarterly roadmap review occurs in November but does not authorize launch.",
            "Critical defects block every production release until verified closed.",
            "The recovery team rehearses rollback before each major platform upgrade.",
            "Accessibility testing starts during feature-complete review in September.",
            "Bluebird documentation must be complete before public preview begins.",
        ),
    ),
    Topic(
        "Cedar Service Level Agreement",
        (
            "The Cedar service target is 99.95 percent monthly availability, excluding approved maintenance windows.",
            "Priority-one incidents receive an initial response within thirty minutes and hourly status updates.",
        ),
        (
            "The Cypress service target is 99.9 percent monthly availability.",
            "The Cedar analytics add-on targets 99.5 percent availability each quarter.",
            "Priority-two incidents receive an initial response within two hours.",
            "A premium support plan targets a fifteen-minute response for security events.",
            "Maintenance windows are announced at least seven days in advance.",
            "Monthly availability excludes customer-controlled network failures.",
            "Status updates for priority-three tickets are issued each business day.",
            "Service credits require a claim within thirty days after the affected month.",
        ),
    ),
    Topic(
        "Harbor Compliance Calendar",
        (
            "The annual SOC 2 evidence review begins June 3, 2026 and audit fieldwork starts June 22.",
            "Control owners upload Harbor evidence and certify completeness by June 15, 2026.",
        ),
        (
            "The ISO 27001 evidence review begins July 3, 2026 and fieldwork starts July 22.",
            "Privacy-assessment evidence is due June 12 before interviews begin June 25.",
            "Control narratives receive editorial review by June 5.",
            "The audit planning call occurs May 22 and does not require final evidence.",
            "Evidence exceptions are documented in the Harbor tracking repository.",
            "Control owners attend readiness workshops throughout the first week of June.",
            "The finance audit starts fieldwork on August 22 after a separate close cycle.",
            "Certification reminders are sent five days before each assigned deadline.",
        ),
    ),
    Topic(
        "Luna Budget Brief",
        (
            "The fourth-quarter marketing budget is 2.4 million US dollars, including 600000 dollars for partner campaigns.",
            "Budget transfers above 100000 dollars require approval from Finance and the business-unit vice president.",
        ),
        (
            "The third-quarter marketing budget is 2.1 million US dollars.",
            "The fourth-quarter sales budget is 2.4 million euros with 650000 for events.",
            "Partner enablement receives 60000 US dollars from the training budget.",
            "Transfers above 50000 dollars require the department director's approval.",
            "Finance reviews forecast changes during the monthly operating meeting.",
            "The business-unit vice president approves new unbudgeted programs.",
            "Campaign purchase orders must identify the benefiting market region.",
            "Unused marketing funds return to the central reserve after quarter close.",
        ),
    ),
    Topic(
        "Polaris Data Residency Guide",
        (
            "European customer content is stored in the Frankfurt region and replicated only within the European Union.",
            "A Polaris residency exception requires customer consent, privacy review, and a documented transfer mechanism.",
        ),
        (
            "United States customer content is stored in Oregon and replicated to Virginia.",
            "Asia-Pacific telemetry is processed in Singapore under a regional operations plan.",
            "The Frankfurt disaster-recovery exercise copies synthetic data only.",
            "A support-access exception requires manager approval and a recorded ticket.",
            "European billing records follow a separate finance retention schedule.",
            "Regional encryption keys remain in the jurisdiction where they were created.",
            "Customers select a primary deployment region during workspace provisioning.",
            "A transfer assessment documents purpose, recipients, safeguards, and duration.",
        ),
    ),
    Topic(
        "Vega Support Playbook",
        (
            "Tier one owns initial triage, tier two handles product defects, and tier three engages engineering incident command.",
            "A customer-impacting escalation includes severity, affected region, start time, and a concise reproduction path.",
        ),
        (
            "The billing queue handles invoice questions before routing technical issues to support.",
            "Tier two owns configuration guidance that does not require a product change.",
            "An account escalation includes subscription level and renewal date.",
            "Engineering office hours review nonurgent feature requests each Friday.",
            "Initial triage records impact, urgency, and the reporter's contact channel.",
            "The incident commander publishes updates during active priority-one events.",
            "Regional support leads coordinate language coverage for customer calls.",
            "A reproduction path should omit credentials and use sanitized test data.",
        ),
    ),
)


def _chunk_id(document_number: int, chunk_number: int) -> str:
    return f"p5v2-doc-{document_number:02}-chunk-{chunk_number:02}"


def document_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for document_number, topic in enumerate(TOPICS, start=1):
        document_id = f"p5v2-doc-{document_number:02}"
        contents = topic.evidence + topic.confounders
        if len(contents) != 10:
            raise RuntimeError(f"{document_id} must define exactly ten chunks")
        for chunk_number, content in enumerate(contents, start=1):
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


def _relevance(*items: tuple[int, int, int]) -> list[dict[str, Any]]:
    return [
        {"chunk_id": _chunk_id(document, chunk), "grade": grade} for document, chunk, grade in items
    ]


def _query(
    number: int,
    split: str,
    query_class: str,
    query: str,
    *,
    relevance: list[dict[str, Any]] | None = None,
    allowed: tuple[str, ...] = ("@workspace",),
    negative_kind: str | None = None,
    excluded: tuple[tuple[int, int], ...] = (),
) -> dict[str, Any]:
    relevance = relevance or []
    row: dict[str, Any] = {
        "dataset_revision": DATASET_REVISION,
        "query_id": f"p5v2-q{number:03}",
        "split": split,
        "query_class": query_class,
        "query": query,
        "allowed_document_ids": list(allowed),
        "answerable": bool(relevance),
        "relevance": relevance,
    }
    if negative_kind is not None:
        row["negative_kind"] = negative_kind
    if excluded:
        row["excluded_relevant_chunk_ids"] = [
            _chunk_id(document, chunk) for document, chunk in excluded
        ]
    return row


def judgment_rows() -> list[dict[str, Any]]:
    rows = [
        _query(
            1,
            "tune",
            "semantic_paraphrase",
            "On what date does the main Acme services term roll forward?",
            relevance=_relevance((1, 1, 3)),
        ),
        _query(
            2,
            "tune",
            "semantic_paraphrase",
            "How long are Zephyr finance records preserved after year close?",
            relevance=_relevance((2, 1, 3)),
        ),
        _query(
            3,
            "tune",
            "semantic_paraphrase",
            "Why did the western Orion service interruption happen?",
            relevance=_relevance((3, 2, 3), (3, 1, 1)),
        ),
        _query(
            4,
            "tune",
            "semantic_paraphrase",
            "What is the payment deadline for the principal Nimbus bill?",
            relevance=_relevance((4, 1, 3)),
        ),
        _query(
            5,
            "tune",
            "semantic_paraphrase",
            "What paid time away is offered after a new child joins a family?",
            relevance=_relevance((5, 1, 3), (5, 2, 1)),
        ),
        _query(
            6,
            "tune",
            "semantic_paraphrase",
            "Which control protects administrator sign-in from credential phishing?",
            relevance=_relevance((6, 1, 3)),
        ),
        _query(
            7,
            "tune",
            "semantic_paraphrase",
            "Which checks must Aurora clear before public launch?",
            relevance=_relevance((7, 2, 3), (7, 1, 1)),
        ),
        _query(
            8,
            "tune",
            "semantic_paraphrase",
            "How soon is the first response for the highest-priority Cedar outage?",
            relevance=_relevance((8, 2, 3)),
        ),
        _query(
            9,
            "validation",
            "semantic_paraphrase",
            "When does the annual Harbor assurance evidence review open?",
            relevance=_relevance((9, 1, 3)),
        ),
        _query(
            10,
            "validation",
            "semantic_paraphrase",
            "Whose consent is needed to move a substantial amount between Luna budgets?",
            relevance=_relevance((10, 2, 3)),
        ),
        _query(
            11,
            "validation",
            "semantic_paraphrase",
            "What safeguards authorize a Polaris data-location exception?",
            relevance=_relevance((11, 2, 3)),
        ),
        _query(
            12,
            "holdout",
            "semantic_paraphrase",
            "Which Vega support level calls in engineering command?",
            relevance=_relevance((12, 1, 3)),
        ),
        _query(
            13,
            "holdout",
            "semantic_paraphrase",
            "What notice stops the primary Acme agreement from renewing?",
            relevance=_relevance((1, 2, 3)),
        ),
        _query(
            14,
            "tune",
            "exact_identifier",
            "ACME-774 January 15 2027",
            relevance=_relevance((1, 1, 3)),
        ),
        _query(
            15,
            "tune",
            "exact_identifier",
            "ZP-204 seven years fiscal close",
            relevance=_relevance((2, 1, 3)),
        ),
        _query(
            16,
            "tune",
            "exact_identifier",
            "INC-442 forty-seven minutes May 8",
            relevance=_relevance((3, 1, 3)),
        ),
        _query(
            17,
            "tune",
            "exact_identifier",
            "INV-908 128450 September 30",
            relevance=_relevance((4, 1, 3)),
        ),
        _query(
            18,
            "tune",
            "exact_identifier",
            "PO-7712 Nimbus payment",
            relevance=_relevance((4, 2, 3)),
        ),
        _query(
            19,
            "tune",
            "exact_identifier",
            "sixteen weeks paid parental leave",
            relevance=_relevance((5, 1, 3)),
        ),
        _query(
            20,
            "tune",
            "exact_identifier",
            "phishing-resistant registered hardware security keys",
            relevance=_relevance((6, 1, 3)),
        ),
        _query(
            21,
            "tune",
            "exact_identifier",
            "Aurora general availability November 2026",
            relevance=_relevance((7, 1, 3)),
        ),
        _query(
            22,
            "validation",
            "exact_identifier",
            "Cedar 99.95 percent monthly",
            relevance=_relevance((8, 1, 3)),
        ),
        _query(
            23,
            "validation",
            "exact_identifier",
            "SOC 2 June 3 June 22 2026",
            relevance=_relevance((9, 1, 3)),
        ),
        _query(
            24,
            "validation",
            "exact_identifier",
            "2.4 million 600000 partner campaigns",
            relevance=_relevance((10, 1, 3)),
        ),
        _query(
            25,
            "holdout",
            "exact_identifier",
            "Frankfurt replicated only European Union",
            relevance=_relevance((11, 1, 3)),
        ),
        _query(
            26,
            "holdout",
            "exact_identifier",
            "Vega tier three engages engineering incident command",
            relevance=_relevance((12, 1, 3)),
        ),
        _query(
            27,
            "tune",
            "multi_document",
            "Compare the Acme nonrenewal notice with Harbor's evidence-certification deadline.",
            relevance=_relevance((1, 2, 3), (9, 2, 3)),
        ),
        _query(
            28,
            "tune",
            "multi_document",
            "Give the Zephyr finance retention period and Polaris's European storage location.",
            relevance=_relevance((2, 1, 3), (11, 1, 3)),
        ),
        _query(
            29,
            "tune",
            "multi_document",
            "State the Orion outage duration and Cedar's priority-one response target.",
            relevance=_relevance((3, 1, 3), (8, 2, 3)),
        ),
        _query(
            30,
            "tune",
            "multi_document",
            "List the Nimbus invoice total and Luna's fourth-quarter marketing allocation.",
            relevance=_relevance((4, 1, 3), (10, 1, 3)),
        ),
        _query(
            31,
            "tune",
            "multi_document",
            "Contrast Atlas's practical notice with Acme's nonrenewal notice.",
            relevance=_relevance((5, 2, 3), (1, 2, 3)),
        ),
        _query(
            32,
            "tune",
            "multi_document",
            "Which anti-phishing control and Aurora launch safeguards are mandatory?",
            relevance=_relevance((6, 1, 3), (7, 2, 3)),
        ),
        _query(
            33,
            "tune",
            "multi_document",
            "Who releases a Zephyr legal hold and who approves a large Luna transfer?",
            relevance=_relevance((2, 2, 3), (10, 2, 3)),
        ),
        _query(
            34,
            "validation",
            "multi_document",
            "Report Aurora's launch month and Harbor's fieldwork start date.",
            relevance=_relevance((7, 1, 3), (9, 1, 3)),
        ),
        _query(
            35,
            "validation",
            "multi_document",
            "Pair Orion's corrective action with the Vega tier that engages engineering.",
            relevance=_relevance((3, 2, 3), (12, 1, 3)),
        ),
        _query(
            36,
            "holdout",
            "multi_document",
            "Combine Cedar's availability objective with Polaris's European region.",
            relevance=_relevance((8, 1, 3), (11, 1, 3)),
        ),
        _query(
            37,
            "holdout",
            "multi_document",
            "Compare the Nimbus due date and the Harbor completeness date.",
            relevance=_relevance((4, 1, 3), (9, 2, 3)),
        ),
        _query(
            38,
            "holdout",
            "multi_document",
            "Give Atlas's parental-leave duration and Cedar's priority-one response time.",
            relevance=_relevance((5, 1, 3), (8, 2, 3)),
        ),
        _query(
            39,
            "tune",
            "negative",
            "Which court governs ACME-774 disputes?",
            allowed=("p5v2-doc-01",),
            negative_kind="unanswerable",
        ),
        _query(
            40,
            "tune",
            "negative",
            "Which cipher does ZP-204 mandate for archives?",
            allowed=("p5v2-doc-02",),
            negative_kind="unanswerable",
        ),
        _query(
            41,
            "tune",
            "negative",
            "How many customers opened tickets during INC-442?",
            allowed=("p5v2-doc-03",),
            negative_kind="unanswerable",
        ),
        _query(
            42,
            "tune",
            "negative",
            "Which bank routing number receives INV-908?",
            allowed=("p5v2-doc-04",),
            negative_kind="unanswerable",
        ),
        _query(
            43,
            "tune",
            "negative",
            "What percentage of salary is paid during Atlas parental leave?",
            allowed=("p5v2-doc-05",),
            negative_kind="unanswerable",
        ),
        _query(
            44,
            "tune",
            "negative",
            "Which manufacturer supplies Redwood's hardware keys?",
            allowed=("p5v2-doc-06",),
            negative_kind="unanswerable",
        ),
        _query(
            45,
            "tune",
            "negative",
            "What month is Aurora generally available?",
            allowed=("p5v2-doc-06",),
            negative_kind="unauthorized_scope",
            excluded=((7, 1),),
        ),
        _query(
            46,
            "validation",
            "negative",
            "What is Cedar's exact availability commitment?",
            allowed=("p5v2-doc-09",),
            negative_kind="unauthorized_scope",
            excluded=((8, 1),),
        ),
        _query(
            47,
            "validation",
            "negative",
            "In which city is European customer content stored?",
            allowed=("p5v2-doc-10",),
            negative_kind="unauthorized_scope",
            excluded=((11, 1),),
        ),
        _query(
            48,
            "holdout",
            "negative",
            "Which Vega tier activates engineering command?",
            allowed=("p5v2-doc-11",),
            negative_kind="unauthorized_scope",
            excluded=((12, 1),),
        ),
        _query(
            49,
            "holdout",
            "negative",
            "What total appears on INV-908?",
            allowed=("p5v2-doc-01",),
            negative_kind="unauthorized_scope",
            excluded=((4, 1),),
        ),
        _query(
            50,
            "holdout",
            "negative",
            "When does ACME-774 roll into its next term?",
            allowed=("p5v2-doc-12",),
            negative_kind="unauthorized_scope",
            excluded=((1, 1),),
        ),
    ]
    return rows


def dense_profile() -> dict[str, Any]:
    return {
        "dataset_revision": DATASET_REVISION,
        "baseline": "dense-v1",
        "source_release": "mm-rag-v4.0.0",
        "source_commit": "996898e6d0d15c00bc04b6bc994e41431cf329a4",
        "pipeline_profile": "phase3-async-v1",
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "qdrant_collection_schema": "unnamed-dense-cosine-with-payload-schema-2",
        "authorization_scope_revision": "adr-0015-v1",
        "retrieval_limit": 8,
        "evaluation_depth": 10,
        "minimum_quality_candidate_pool": 50,
        "metric_revision": "phase5-evaluation-v2",
        "holdout_policy": "validation-before-holdout",
        "paid_run": "explicit-opt-in",
    }


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return "".join(
        json.dumps(row, sort_keys=False, separators=(",", ":")) + "\n" for row in rows
    ).encode()


def rendered_files() -> dict[str, bytes]:
    files = {
        "dense-profile.json": (
            json.dumps(dense_profile(), sort_keys=True, indent=2) + "\n"
        ).encode(),
        "documents.jsonl": _jsonl(document_rows()),
        "judgments.jsonl": _jsonl(judgment_rows()),
    }
    manifest = {
        "dataset_revision": DATASET_REVISION,
        "supersedes": "phase5-retrieval-v1",
        "chunk_count": len(document_rows()),
        "query_count": len(judgment_rows()),
        "minimum_quality_candidate_pool": 50,
        "holdout_policy": "validation-before-holdout",
        "split": {"tune": 30, "validation": 10, "holdout": 10},
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
        raise SystemExit(f"Phase 5 v2 fixture is stale: {', '.join(mismatches)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the synthetic Phase 5 v2 fixture")
    parser.add_argument("--output", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check_fixture(args.output)
        print("Phase 5 v2 fixture is reproducible")
        return
    write_fixture(args.output)
    print(f"Wrote Phase 5 v2 fixture to {args.output}")


if __name__ == "__main__":
    main()
