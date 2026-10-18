# ADR 0064: Two person pilot closure scope

- Status: Accepted
- Date: 2026-10-11
- Milestone: 11.5
- Approval: Explicit operator scope approval on 2026-10-11; final acceptance is separate

## Context

The operator wants to conclude Phase 11 without expanding the current two-person
learning pilot. The operator and one independent participant completed the bounded
guided PDF/question workflows and subsequent read-only persistence checks. This is
useful limited evidence, not validation of five- or ten-user product adoption.

[ADR 0062](0062-pilot-rollout-acceptance-rollback.md) originally required the ordered
internal, two-user, five-user and ten-user stages. This accepted amendment narrows
only the closure scope described below. The October 9 formal review records remaining duration,
journey, accessibility, usage/cost and safeguard evidence gaps in the
[pilot runbook](../../PHASE11_PILOT_OPERATIONS.md#formal-canary-review--october-9).

## Alternatives considered

| Alternative | Benefit | Consequence |
| --- | --- | --- |
| Complete the accepted five- and ten-user stages | Preserves the original validation objective | Requires separate invitations, authorization, observation periods and evidence |
| Accept a limited two-person pilot after all retained gates pass | Concludes a smaller learning objective without new enrollment | Larger-cohort validation stays deferred and unproven |
| Close without acceptance through an explicit remediate or stop decision | Ends the pilot without overstating incomplete evidence | No successful Phase 11 acceptance claim |

## Accepted decision

Narrow Phase 11's acceptance objective to the existing two-person invitation-only
learning pilot. Amend only ADR 0062's requirement to
complete the five- and ten-user stages before accepting this limited objective.
Defer those stages; do not label them completed, passed or unnecessary for future
larger-cohort claims. Do not enroll a replacement or additional participant through
this decision.

Retain ADRs 0057–0061's consent, privacy, integrity, authorization, cost, recovery,
support and product-evidence requirements. Preserve ADR 0063's distinction between
one-person/two-account technical rehearsal and two independent human participants.
Keep the original three-day two-person observation minimum, at least 90% completion
of attempted core journeys, and 100% passage of required safeguards. Missing evidence
must be resolved rather than waived or relabeled as a pass.

## Required closure evidence

| Gate | Evidence required before limited acceptance |
| --- | --- |
| Two independent people and consent | Existing private enrollment/consent records, each person's own review, and identity-free participation totals; agent operation does not substitute for human participation |
| Observation duration | At least three elapsed days of eligible observation with both participants active; reconcile safety/recovery pauses and exclude unverified time |
| Core journey completion | Record all attempted/completed in-scope human journeys and assistance, calculate the denominator and completion percentage, and meet the unchanged 90% threshold |
| Accessibility and scope clarity | Each person checks keyboard navigation, visible focus, Library/conversation/citation access and clarity of selected document scope; record problems and dispositions without another paid question |
| Voluntary feedback | Preserve direct or operator-relayed reports with their attribution limits; structured ratings remain optional, and nonresponse is not a positive rating |
| Actual usage and cost | Reconcile content-free aggregate provider request/cost totals for the bounded session and infrastructure cost/resource evidence against existing approvals; unknown or unattributable usage is not zero |
| All safeguards | Map applicable authorization, privacy, integrity, tenant isolation, backup, rollback and cost evidence to every required safeguard; distinguish fresh checks from protected historical proof and resolve regressions/freshness gaps |
| Final operational checkpoint | Fresh read-only UI/TLS/API/anonymous denial and host/queue/job/backup/capacity/timer checks; verify the worker remains stopped with its approved no-restart policy |
| Explicit conclusion | Review the evidence and record accept for the limited scope, remediate, or stop; separately approve any Git publication or operational changes |

The provisional observation review floor was October 10 at 19:08:38 Pacific, based
on approved resumption at `2026-10-08T02:08:38Z` without credit for earlier recovery or
unverified time. That date has passed, but neither elapsed time nor three calendar
visits alone proves eligible observation or final acceptance. Further excluded pauses
must be reconciled. Participants need not remain continuously online.

The first saved answer's wider two-document scope remains part of the evidence. It is
not a proven authorization leak, a diagnosed product defect, or proof that the intended
single-document scope was achieved. Scope-clarity review must preserve that distinction.
Guided workflows do not support a claim of unassisted discovery or comprehensive
negative tenant-isolation testing.

## Authorization and implementation boundary

Scope approval permits adoption of the limited objective and planning its remaining
checks. It does not authorize another paid question, upload, embeddings, rebuild,
worker start, access change, invitation, provider change, upgrade, cloud resource,
destructive operation, unattended workflow, commit, push, merge or release tag.
The original two-PDF/two-question allowance is consumed. Resolve the next evidence
gaps with existing records and read-only checks; any genuinely necessary additional
paid or mutating test requires separate approval.

Before acceptance, align the active closure contract, project plan, architecture and
runbook with the approved scope and verify the relevant tests. Preserve the existing
policy and frozen synthetic/technical evidence as historical contracts. Any necessary
closure-policy addition must be separately versioned rather than rewriting their
hashes, setting historical formal-validation fields to true, or converting technical
rehearsal into independent human evidence. No historical-policy/runtime change is made by this
scope decision. The additive `operations/phase11-closure-scope-v1.json` records the
approved objective and unchanged gates without enabling execution or final acceptance.

Phase 10 safeguards, immutable releases/recovery points, retrieval defaults, protected
evaluation evidence and all backend tenant/citation/provenance boundaries remain
unchanged. No new frontend or public service is promoted. No production SLA, ten-user
product validation, or larger-cohort adoption claim is permitted by limited closure.

## Closure record and operating state

If every retained gate passes and final acceptance is explicitly approved, use:

> Phase 11 accepted for the two-person learning pilot. Five- and ten-user product
> validation stages are deferred and remain unvalidated.

Keep the cohort limit, guided-workflow limitations, unresolved non-gating observations,
evidence references, actual costs, approval and closure date in the closure record.
If a retained gate is incomplete or fails, record remediate or stop instead of limited
acceptance. Approval of this scope proposal is not approval of that later conclusion.

Closing the learning observation does not create an indefinite paid-service mandate
or automatically remove accounts, documents or cloud infrastructure. The worker stays
stopped; scheduled maintenance stays under the existing Phase 10 safeguards. Confirm
the intended post-pilot access/service disposition separately before any mutation.
Apply ADR 0060's 30-day aggregate-evidence retention period from the actual closure
date; removal remains a reviewed manual action, not a deletion scheduled by this ADR.

## Approval record

The operator explicitly approved ADR 0064's two-person-only Phase 11 acceptance
objective on October 11, deferring the five- and ten-user stages while retaining all
other acceptance and safety gates. Phase 11 remains in progress and is not accepted.
Final Phase 11 acceptance, paid work, operational mutations and Git publication remain
separately approval-gated.

### Explicit final acceptance — October 18

After reviewing the limited closure recommendation and qualifications, the operator
explicitly approves recording Phase 11 acceptance at `2026-10-18T23:10:45Z`.
Phase 11 is accepted for the two-person guided learning pilot; five-/ten-user product
validation is deferred and remains unvalidated. The separate versioned
`operations/phase11-acceptance-v1.json` records the final decision without rewriting
the October 11 scope-only authority or frozen evidence. Costs are provider-exported
USD 0.00151422 and operator-reported OCI USD 0, not independently audited OCI billing.
Guided/saved-scope/human-report/historical-proof limitations remain. Worker stays
stopped and maintenance unchanged; Git publication, tags, post-pilot disposition and
further paid/operational actions are not authorized. Aggregate-evidence retention
manual review is due November 17, with automatic deletion/apply disabled.
