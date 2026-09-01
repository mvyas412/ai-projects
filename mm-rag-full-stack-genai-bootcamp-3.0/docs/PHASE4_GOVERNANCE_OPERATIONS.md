# Phase 4 governance, lifecycle, and incident operations

This runbook covers the accepted ADR 0017 controls in the Phase 4 development
environment. It contains no credentials or provider coordinates. Use only an
authenticated owner/admin session and the documented backend APIs; never copy an
access token into a ticket, log, terminal transcript, or source file.

## Safety model

- A document deletion request is owner-only. A conversation deletion request is
  allowed for its creator or a workspace owner/admin.
- The first action is a PostgreSQL tombstone. Product list, retrieval, citation,
  indexing, job-creation, and download paths stop exposing the resource immediately.
- Documents and conversations remain recoverable for 30 days by default.
- Irreversible cleanup is owner-only and requires a fresh preview token. Apply fails
  if the eligible scope changes after preview.
- Holds exclude a resource from deletion and retention. Removing a hold is audited.
- Cross-store deletion records vector, artifact, original, and metadata checkpoints.
  Missing data is success only after trusted workspace/document/version scope is
  re-established. Partial failures become `blocked` and can be safely retried.
- No retention apply is scheduled automatically in Phase 4. An owner must review
  and invoke each bounded batch.

## Retention profile

| Data class | Initial window |
| --- | --- |
| Terminal outbox evidence | 30 days |
| Inactive, unreferenced generations | 30 days |
| Rechecked orphan objects | 7 days from first evidence |
| Owner-requested document deletion | 30-day tombstone |
| Deleted conversations | 30-day tombstone |
| Eligible terminal jobs/attempts | 90 days |
| Security audit events | 365 days |

The values are configuration, but the policy revision is durable. Shortening a
window does not delete anything by itself; it only changes the next preview scope.

## Routine lifecycle procedure

1. Confirm `/api/v1/health/ready` reports PostgreSQL, Qdrant, and configured object
   storage ready. Confirm the ingestion worker/dispatcher health before deletion.
2. Place a hold first if an incident, legal request, or investigation is active.
3. Request document or conversation deletion through the governance endpoint.
4. Confirm the resource disappears from list, detail, chat scope, citation, and
   download paths. Do not inspect object keys directly.
5. Restore during the recoverable period if the request was mistaken. Restore is
   refused after any destructive checkpoint begins.
6. Run orphan inventory. The response reports counts only; object keys remain private.
7. Request retention preview and review every returned count. Keep the preview token
   in memory only long enough to submit the matching apply request.
8. Submit apply as the workspace owner. A nonzero `blocked_plans` result requires
   investigation and a new preview; do not bypass the hold or active-work checks.
9. Confirm a second preview no longer includes completed scope and review the
   security audit events for the tombstone, hold, restore, and purge actions.

Relevant routes, all below `/api/v1/workspaces/{workspace_id}/governance`, are:

- `POST /documents/{document_id}/deletion` and `POST /documents/{document_id}/restore`
- `POST /conversations/{conversation_id}/deletion` and
  `POST /conversations/{conversation_id}/restore`
- `PUT` or `DELETE /holds/{document|conversation}/{resource_id}`
- `POST /retention/orphan-inventory`
- `GET /retention/preview`
- `POST /retention/apply`

## Blocked deletion recovery

1. Read the safe plan state and error category. Do not add raw provider errors or
   object identifiers to user-visible output.
2. If active ingestion remains, request cancellation and run the accepted expired-
   lease recovery. A live attempt or non-terminal job must never be purged.
3. If a store was unavailable, restore that dependency and repeat preview/apply.
   Completed checkpoints are idempotent and are not re-promoted.
4. If a hold exists, resolve the incident or legal owner before removing it.
5. If reconciliation repeatedly fails, isolate the runtime and preserve the plan,
   database backup, aggregate health, and compliance export for investigation.

## Encryption posture

- Local Compose traffic is loopback-only development traffic. It is not evidence of
  production encryption.
- Production configuration rejects non-local HTTP Qdrant/S3, non-local plain AMQP,
  and non-local PostgreSQL without a required TLS mode.
- Production S3-compatible storage requires explicit server-side encryption.
  `AES256` represents provider-managed keys; `aws:kms` additionally requires a KMS
  key identifier held only in ignored secret configuration.
- Database, Qdrant, backup, key-rotation, regional, and disaster-recovery provider
  selection remains a Phase 8 deployment ADR. Application-level content encryption
  remains deferred until recovery and key ownership are designed together.

## Incident response

### Contain

1. Suspend or remove affected workspace members and revoke resource ACLs.
2. Place retention holds on affected resources before evidence collection.
3. Stop the worker and dispatcher if untrusted work may still be running. Do not
   delete queues, volumes, or databases.
4. Expire browser sessions/download capability through the identity provider and
   rotate only the credentials identified by the incident owner.
5. Restrict network access to FastAPI and dependencies while preserving health and
   audit evidence.

### Preserve and assess

1. Create a bounded compliance export for the affected interval.
2. Capture aggregate operations status, migration revision, application revision,
   and UTC timestamps. Never capture secrets or document content in the incident log.
3. Create and verify the normal logical PostgreSQL backup. Preserve Qdrant and object
   storage snapshots according to the selected environment's recovery procedure.
4. Determine whether any audit-write, queue, object, or vector gap exists. A gap is
   an explicit finding, not assumed success.

### Recover

1. Restore into an isolated environment and apply migrations before reopening access.
2. Reconcile active generation identities, object hashes/sizes, and lifecycle plan
   checkpoints using trusted database scope.
3. Rotate affected credentials, restart one dependency/process at a time, and verify
   readiness plus tenant-isolation tests.
4. Remove holds only with incident-owner approval. Use restore for mistaken deletion;
   use preview/apply for approved irreversible cleanup.
5. Record closure and follow-up actions in the security audit and private project
   context without including content, credentials, or raw object keys.

## Free local exercise

The Phase 4 gate exercises reversible migration `20260831_0013`, local tombstone,
restore, hold, owner preview/apply, object absence, metadata tombstone retention,
worker promotion fencing, and orphan recheck. The full free live gate additionally
uses PostgreSQL, Qdrant, SeaweedFS, and RabbitMQ. Real OpenAI acceptance is unrelated
to lifecycle behavior and must not be run without explicit approval.
