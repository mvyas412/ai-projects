# Phase 9 enterprise kickoff contract

## Status

ADRs 0043–0049 are accepted. Milestone 9.0 requirements and threat boundaries are
defined, and the provider-neutral connector SDK contract is implemented. The first
connector, external credentials, propagation objective, identity/billing providers,
initial meters/quotas, and automatic retention schedule remain unselected.

## Scope and requirements

Phase 9 must:

- connect tenant-owned enterprise sources through least-privilege, revocable adapters;
- propagate source content, permission contractions, and deletions without widening access;
- provision and deprovision enterprise identities predictably;
- record immutable content-free usage and enforce concurrent quotas correctly;
- reconcile subscription state without making a billing provider product truth; and
- produce authorized, content-free lifecycle and compliance evidence.

The accepted FastAPI authorization boundary, PostgreSQL relational truth, tenant-scoped
SQL/vector/object/job controls, immutable generations, evidence provenance, and
non-disclosing errors remain unchanged. The modular monolith remains the default.

## Threat model

| Threat | Required control | Initial evidence |
| --- | --- | --- |
| Cross-tenant credential use | Credential reference binds workspace and connector; runtime resolver rechecks both | Negative unit and integration tests |
| Secret disclosure | Opaque references in durable state; `SecretStr` runtime values; redacted telemetry | Repr/log scanning and secret scan |
| Connector impersonation or substitution | Explicit kind registry and reviewed adapter configuration | Unknown/duplicate/mismatched-kind rejection |
| Lost, duplicated, or reordered change events | Idempotent identities, durable attempts, fenced leases, promoted checkpoints | Replay and stale-fence tests |
| Stale source permission | Deny retrieval before cleanup; reconcile permission fingerprints | Permission contraction test |
| Source deletion remains searchable | Tombstone first, then checkpointed cross-store purge | Delete-before-cleanup test |
| Identity group grants excessive role | Allowlisted mapping beneath the RBAC ceiling | Negative mapping tests |
| Concurrent quota overspend | Transactional reservation and settlement | Contention integration test |
| Billing webhook replay or outage | Signature verification, idempotent envelopes, scheduled reconciliation, bounded grace | Replay/outage tests |
| Privileged lifecycle misuse | Preview fingerprint, reauthorization, separation of duties, append-only audit | Changed-scope and hold-precedence tests |

## Connector SDK boundary

The connector SDK exposes discovery, opaque-cursor change listing, immutable source
versions, streamed content, permission snapshots, health, and rate-limit hints. Adapters
return canonical values only; they cannot write product stores, select tenant scope, or
make authorization decisions. Credential resolution is a separate runtime-only context
manager, so secrets cannot be serialized into connector jobs or checkpoints.

## First-connector scorecard

Score each candidate from 0 (unavailable) to 3 (strong). Do not select a provider until
the user reviews the result and confirms access to a free sandbox/account.

| Criterion | Weight | What to verify |
| --- | ---: | --- |
| Learning demand | 3 | Source matches the intended demonstration and user familiarity |
| Free test access | 3 | No paid tenant, trial expiry dependency, or production data required |
| Permission fidelity | 3 | Users/groups and permission contraction can be observed reliably |
| Delta and deletion fidelity | 3 | Durable cursor/change token and explicit deletion behavior exist |
| Credential safety | 3 | Minimum read scopes, rotation, and revocation are practical |
| Testability | 2 | Fixtures/emulator or deterministic sandbox behavior is available |
| Operational burden | 2 | Rate limits, webhooks, and reconciliation fit the learning deployment |
| Portability value | 1 | Adapter exercises the canonical contract without provider leakage |

Candidate set: Google Drive, Microsoft SharePoint/OneDrive, Box, and a generic
authenticated web/API adapter. Selection is intentionally TBD.

## Approval boundaries still open

- first connector and provider-specific propagation objective;
- credential-vault implementation and external tenant configuration;
- identity and billing provider/sandbox choice;
- initial meter names, quota quantities, and settlement rules; and
- automatic retention schedule, which remains disabled.
