# ADR 0016: Security audit and compliance export

- Status: Proposed
- Date: 2026-08-31
- Milestone: 4.0–4.4

## Context

ADR 0006 provides immutable workspace activity for principal product mutations.
Phase 4 adds policy changes, denials, administrative content access, lifecycle
actions, and compliance export. The product must explain who attempted or completed
an action, on which governed resource, and when, without turning audit storage into
a second copy of document, message, token, or provider data.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Keep the existing activity feed unchanged | No schema or UX work | Cannot explain policy decisions, denials, exports, or service actions |
| Log everything to application logs | Easy operational search | Mutable retention, weak transaction coupling, disclosure risk, and poor tenant export |
| Append-only PostgreSQL security events plus safe exports | Transaction-aware, tenant-scoped, testable, and reuses the product authority | Requires a strict schema, privileges, retention, and separate high-volume telemetry |
| External tamper-evident compliance ledger now | Strong independent evidence | New provider, cost, delivery guarantees, and operational scope before requirements justify it |

## Proposed decision

Extend the existing append-only PostgreSQL activity model into a versioned security
audit event contract. Keep high-volume diagnostics in logs/metrics; audit stores
only durable, safe, policy-relevant evidence.

### Event contract

Each event records a stable event ID, workspace, actor kind and internal actor ID,
action, resource type and ID, allow/deny/result, policy revision, correlation ID,
server time, and a small schema-validated safe-details object. Service actors use
named internal identities; there is no anonymous superuser actor.

Never store access/refresh tokens, credentials, raw document/message/query content,
filenames when unnecessary, object keys, provider endpoints, unfiltered IP/user-agent
data, stack traces, or raw dependency errors.

### Durability rules

- Privileged mutations, ACL/member changes, exports, deletion approvals, and final
  lifecycle transitions write audit evidence in the same PostgreSQL transaction.
- A required audit-write failure aborts a privileged mutation.
- Denials remain denied even if their best-effort audit write fails; audit health
  records the gap without converting failure into access.
- Successful ordinary reads are not all retained as audit events. Administrative
  reads of restricted content, source download capabilities, audit exports, and
  other high-risk reads are audited.
- Rows are append-only to application roles. Corrections use linked superseding events.

### Views and export

The existing safe workspace Activity feed remains available to all members with a
presentation-safe subset. Owner/admin receive a separate bounded security view.
Compliance export is owner/admin-only, asynchronous for large ranges, date-bounded,
schema-versioned, checksummed, and itself audited. The export contains safe event
fields only and is downloaded through the same authorized object boundary.

A cryptographic hash chain, external write-once sink, SIEM provider, and formal
regulatory retention are deferred until Phase 7/9 requirements justify them.

## Consequences

- Security decisions and administrative actions become explainable without copying content.
- PostgreSQL remains sufficient for the first governance release.
- Audit volume and retention require explicit limits and operational health.
- The design is append-only but not yet an independently tamper-evident compliance ledger.

## Approval points

The recommendation requests approval for same-transaction audit on privileged
mutations, owner/admin-only security views and exports, and deferring an external
ledger/SIEM selection.

## Acceptance evidence required

- Privileged mutations roll back when required audit persistence fails.
- Denials never become allowed when audit persistence is unavailable.
- Role, ACL, admin-read, export, retention, and incident actions have stable event fixtures.
- Members cannot access the security view/export; outsiders receive non-enumerating responses.
- Export is bounded, checksummed, authorized, reproducible, and records its own creation/download.
- Schema tests reject secret-bearing, content-bearing, oversized, and unknown detail fields.
- Application roles cannot update or delete audit rows.
