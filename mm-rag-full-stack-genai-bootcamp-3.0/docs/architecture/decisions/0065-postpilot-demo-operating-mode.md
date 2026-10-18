# ADR 0065: Retained post-pilot inspection demo

- Status: Accepted
- Date: 2026-10-18
- Approval: Explicit operator instruction to retain the demo, keep the worker stopped
  and maintenance unchanged, with no new paid calls or resources

## Context and decision

Phase 11 was accepted only for the two-person guided learning pilot under ADR 0064.
PR #31 squash-merged the acceptance records as `768a67f`. This is project closure,
not a new application deployment, public launch or larger-cohort validation.

Keep the existing deployment available for inspection by existing authorized accounts.
Keep the worker stopped with restart policy `no`, preserve all existing Phase 10
maintenance schedules and safeguards, and authorize no new provider calls or resources.
Record this disposition separately in `operations/phase11-demo-v1.json`; do not rewrite
the acceptance or historical scope/evidence records.

## Safe demonstration boundary

Show sign-in, existing READY documents, saved answers, existing source/page citations,
persistence, architecture and existing status. Do not submit new questions or uploads,
retry/rebuild/reindex a job, start a connector sync or start the worker. The ingestion
worker being stopped does **not** disable provider-backed chat in the API. These are
operator-controlled restrictions, not a claim that new runtime/UI interlocks exist.
Do not invite more users, expand access or publish another frontend through this decision.

Existing backup and capacity timers remain unchanged, including planned backup
quiescence and existing cost/backup-age/certificate alerts. A brief maintenance outage
is compatible with this learning demo; no production SLA is promised. Do not enable
another observability stack, automatic retention apply, unattended upgrades, paid
capacity, new resources or replacement infrastructure. Restore/release operations
and any future paid demonstration require separate explicit approval. The historical
OCI zero-cost report is not a guarantee of future hosting cost.

The aggregate-evidence retention review stays November 17, 2026, at
`2026-11-17T23:10:45Z`. Any removal is reviewed and manual; do not automatically delete
aggregate evidence, participant accounts, product documents or saved conversations.

## Consequences and documentation

The agreed learning-project work is complete, with Phase 5 closed without quality
acceptance and five-/ten-user validation and Next.js promotion deferred. Hosting and
existing maintenance continue; they are not new feature development or participant QA.
Keep current documentation and editable Mermaid/SVG views aligned. Retain old phase
posters as explicitly historical/target views, not evidence of current execution.
No paid image generation is needed for native diagrams.

This instruction permits local documentation/diagram updates. It does not authorize
commit/push, merge, release tags, deployment, access changes or service mutations.
No new host audit is claimed merely from updating documentation.

The operator subsequently explicitly approves committing and pushing the demo
documentation and diagram follow-up after the free verification gate. This separate
source-publication approval does not authorize a merge, tag, deployment, runtime or
access change, paid call, or new resource. The demo JSON preserves the narrower
authority of the original disposition decision rather than rewriting its history.
