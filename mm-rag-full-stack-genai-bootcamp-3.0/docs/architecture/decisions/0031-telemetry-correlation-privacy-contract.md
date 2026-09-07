# ADR 0031: Telemetry correlation and privacy contract

- Status: Proposed
- Date: 2026-09-07
- Milestone: 7.0

## Context

The product already emits bounded request logs, durable job state, audit events,
retrieval traces, and calculation traces. Those records serve different purposes
and do not yet form one end-to-end operational trace. Phase 7 must correlate the
frontend, API, dispatcher, worker, retrieval, model, and persistence boundaries
without turning customer content or credentials into telemetry.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Keep independent component logs | No new contract | Slow incident diagnosis and inconsistent redaction |
| Log complete prompts, documents, and model responses | Easy debugging | Unacceptable privacy, retention, and disclosure risk |
| Correlated metadata-only telemetry with explicit diagnostic capture | Useful by default and privacy bounded | Requires schemas, propagation, redaction tests, and governed escalation |

## Proposed decision

Adopt a versioned, OpenTelemetry-compatible signal contract:

- propagate W3C trace context plus the existing safe correlation ID through UI,
  API, outbox, broker, jobs, retrieval, model calls, and persistence;
- use an allowlist of structured attributes such as operation, outcome, duration,
  bounded counts, profile/version, retry class, and opaque internal identity;
- never emit tokens, credentials, object keys, raw documents, prompts, retrieved
  passages, model responses, user comments, or unrestricted exception text;
- keep security audit records and immutable calculation/retrieval evidence separate
  from operational logs and traces;
- hash or omit user-facing identifiers and apply tenant authorization to any
  diagnostic lookup that can be mapped back to product state;
- define head sampling for normal traffic and bounded tail/error sampling without
  overriding privacy rules; and
- permit content-bearing diagnostic capture only through a separately approved,
  time-limited, encrypted workflow with explicit access and deletion records.

## Recommendation

Approve the metadata-only contract and W3C/OpenTelemetry propagation. It provides
useful end-to-end diagnosis while preserving the existing non-disclosure boundary.
Do not add raw prompt or document capture as a shortcut.

## Approval questions

1. Approve metadata-only telemetry as the default?
2. Approve correlation across asynchronous jobs without exposing broker payloads?
3. Keep content-bearing diagnostic capture disabled until a separate reviewed need?

## Consequences

- Instrumentation must pass redaction and cardinality tests before export.
- Existing audit/evidence records remain authoritative for security and citations.
- A trace can explain timing and failure location, not reveal private source content.

