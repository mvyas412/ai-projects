# ADR 0017: Governed retention, deletion, encryption, and incident controls

- Status: Proposed
- Date: 2026-08-31
- Milestone: 4.0–4.5

## Context

ADR 0008 deliberately disables inactive-generation deletion until a retention
window is approved. Phase 3 also retains immutable originals, promoted and inactive
vectors/artifacts, conversations, jobs/attempts, outbox evidence, and audit rows
across PostgreSQL, Qdrant, and object storage. A direct request-time delete cannot
atomically remove all copies and could leave searchable or recoverable data behind.

Phase 4 needs a safe lifecycle contract before enabling destructive automation.
Production cloud encryption/KMS and disaster-recovery providers remain Phase 8
deployment decisions; legal hold and regulatory policy remain extensible for Phase 9.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Retain everything indefinitely | Safest against accidental loss | Unbounded cost, privacy exposure, and no user deletion outcome |
| Delete all stores synchronously in the API request | Immediate result | Partial failure creates inconsistent remnants and timeouts |
| Provider lifecycle rules only | Low application effort | Cannot coordinate PostgreSQL, Qdrant, object references, jobs, or audit evidence |
| Tombstone plus durable idempotent deletion workflow | Immediate access denial, retryable cross-store purge, and reviewable evidence | Requires lifecycle state, durable work, reconciliation, and explicit retention classes |

## Proposed decision

Use a versioned lifecycle policy and a durable, idempotent deletion workflow.
Tombstone the governed resource in PostgreSQL first so new reads, retrieval, jobs,
and downloads deny immediately. A lifecycle worker then removes derived vectors,
objects, child metadata, and eligible originals in a recorded order, retries partial
failure, reconciles absence, and marks completion only when all required stores agree.

### Proposed initial retention profile

| Data class | Recommendation |
| --- | --- |
| Published/discarded outbox rows | Keep the accepted 30-day Phase 3 policy |
| Inactive, unreferenced generations | 30 days after supersession, then preview-first cleanup |
| Unreferenced/orphan objects from failed intake | 7 days after first inventory evidence, then recheck and cleanup |
| Archived documents | Retain until an owner explicitly requests deletion |
| Owner-requested document deletion | 30-day recoverable tombstone, then durable purge |
| Conversations | Retain until creator or owner/admin deletes; 30-day recoverable tombstone |
| Jobs and attempts | 90 days after terminal state, preserving safe audit summary afterward |
| Security audit events | 365 days initially; a legal/regulatory profile may extend but not silently shorten it |

All windows are environment-configurable policy revisions, not hard-coded provider
lifecycle rules. Shortening a window requires owner-visible preview and audit.
Deletion remains disabled until this ADR and the exact migration/rollback plan are
accepted.

### Deletion order and safety

1. Authorize and record the request; create a recoverable tombstone and deletion plan.
2. Prevent new chat scope, downloads, indexing, ACL grants, and promotion.
3. Cancel or supersede non-terminal jobs at safe fenced checkpoints.
4. Delete all Qdrant generations with mandatory workspace/document/version scope.
5. Delete derived and original objects by trusted database references, never prefix
   input from a client.
6. Delete or redact eligible product metadata while retaining the minimum audit
   tombstone required to prove completion.
7. Reconcile SQL, vectors, and objects; record safe counts/checksums and terminal state.

Missing external data is an idempotent success only after trusted scope is proved.
An active/live attempt, legal/incident hold, unknown provider response, or failed
reconciliation blocks terminal completion.

### Encryption and incident controls

- TLS is required across non-local boundaries; storage/database encryption at rest
  is a deployment requirement for Phase 8.
- Provider-managed keys are the initial production recommendation. Customer-managed
  keys, rotation schedule, and crypto-shredding require a deployment/compliance ADR.
- Application-level content encryption is not added without a key/recovery design.
- Incident controls include member suspension/removal, ACL revocation, download-
  capability expiry, job cancellation, credential rotation, runtime isolation,
  audit export, and documented recovery. They never expose credentials in the UI.

## Consequences

- Access can stop immediately while physical deletion completes safely in the background.
- Inactive-generation cleanup from ADR 0008 can finally be enabled after approval.
- Retention windows create product policy that must be visible, versioned, and testable.
- Audit tombstones may outlive deleted content but contain no content or object coordinates.
- Production encryption provider choices remain properly deferred to Phase 8.

## Approval points

The recommendation requests approval for the proposed retention windows, owner-only
irreversible purge, tombstone-first deletion, durable cross-store reconciliation,
and provider-managed encryption as the initial future production posture.

## Acceptance evidence required

- Preview and apply select the same eligible scope unless state changes, in which case apply fails closed.
- Active generations, live attempts, held resources, and non-terminal jobs cannot be purged.
- Tombstoned resources disappear immediately from list, retrieval, citation, and download paths.
- Failure after each deletion step resumes idempotently without cross-workspace deletion.
- Qdrant, object, and PostgreSQL reconciliation proves no governed copy remains before completion.
- Audit tombstones and reports contain no deleted content, credentials, or raw object keys.
- Backup/restore, retention rollback, and incident runbooks are exercised with free local services.
