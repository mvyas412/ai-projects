# Phase 11 invitation-only product pilot kickoff

Status: **Two-person learning pilot accepted; PR #31 merged; inspection demo retained**

The kickoff proposal below is historical. Final limited acceptance is recorded in
`operations/phase11-acceptance-v1.json` and ADR 0064; ADR 0065 and the
[demo runbook](DEMO_RUNBOOK.md) govern the post-pilot deployment. Worker stopped/
restart-no, existing maintenance unchanged, no new paid calls or resources. Existing
READY documents and saved answers/citations only. A stopped worker does not disable
API chat; inspection-only is an operator instruction, not a runtime interlock.
Five-/ten-user validation remains deferred, not passed; no new enrollment is approved.

## Original recommended direction

Run a small, invitation-only learning pilot for at most ten registered users on the
accepted free-first OCI deployment. The purpose is to validate onboarding, everyday
document workflows, answer usefulness, evidence comprehension, accessibility, and
operator support without claiming public production readiness.

## Alternatives

| Direction | Benefit | Main tradeoff |
| --- | --- | --- |
| Stop after Phase 10 | No additional scope or operational exposure | No evidence that new users can use the product successfully |
| Public launch | Fastest route to broad feedback | Premature privacy, abuse, support, availability, and cost obligations |
| Invitation-only pilot | Bounded real-user learning with reversible exposure | Requires consent, support, stop conditions, and careful evidence governance |
| Infrastructure modernization first | Could improve scale and UI flexibility | Solves unmeasured problems and risks paid complexity |

Recommendation: use the invitation-only pilot. Keep Streamlit and the accepted OCI
topology initially; reconsider Next.js, managed services, and paid capacity only after
measured pilot evidence demonstrates a need.

## Proposed pilot stages

1. **Design:** accept ADRs, participant rules, evidence schema, and stop conditions.
2. **Internal rehearsal:** prove onboarding, logout, upload, ingestion, chat, citations,
   feedback, account disablement, support, backup, and rollback with synthetic users.
3. **Two-user canary:** invite at most two users and review daily aggregate evidence.
4. **Bounded expansion:** increase to five, then ten registered users only when the prior
   stage passes its gate.
5. **Close or promote:** accept the pilot, remediate and repeat a bounded stage, or stop
   and roll back invitations without deleting retained data automatically.

## Proposed evidence

- Invitation acceptance and account-disablement outcomes, without identity disclosure.
- Task completion for sign-in, upload, ingestion, chat, evidence inspection, and logout.
- Aggregate latency, error, queue, storage, cost, support, and accessibility results.
- Voluntary thumbs/rating/category feedback separated from document content.
- Authorization, cross-tenant, citation, non-disclosure, backup, and rollback regression
  gates before each expansion.

## Explicit non-goals

- Public self-service signup, anonymous access, marketing launch, or production SLA.
- Paid capacity, autoscaling, Kubernetes, managed data services, or provider migration.
- Automatic retention apply, unattended upgrades, real billing, or external SCIM.
- Promotion of the deferred Next.js candidate without a separate parity decision.
- Collection of raw prompts, documents, identities, or secrets as pilot evidence.

## Implementation boundary

ADRs 0057–0065 are accepted. The versioned policy, synthetic rehearsal, evidence gate,
tests and operating guide were implemented. The earlier one-human/two-account
technical rehearsal remains non-validating historical evidence under ADR 0063.
The later independently consenting second participant completed the real two-person
pilot; qualified acceptance was explicitly approved October 18 and merged in PR #31
at `768a67f`. Larger cohorts and Next.js promotion remain deferred. Retaining the
existing demo under ADR 0065 does not authorize new workflows, invitations, paid work,
cloud changes, publication of these follow-up docs, tags or deployments.
