# ADR 0014: PostgreSQL row-level-security defense

- Status: Accepted
- Date: 2026-08-31
- Milestone: 4.0–4.2

## Context

Application services already include workspace predicates and composite tenant
foreign keys. A future missing predicate could still expose or mutate another
workspace because the current runtime database user can execute unrestricted SQL.
Phase 4 requires database-level defense without replacing the central application
policy or breaking pooled connections, migrations, workers, and operational jobs.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Application filters only | Portable and already implemented | One omitted predicate can become a critical tenant breach |
| PostgreSQL RLS as the only policy engine | Strong database enforcement | Poor fit for action semantics, object/vector access, and non-SQL resources |
| RLS defense beneath central application policy | Defense in depth while preserving one product policy | Requires database roles, transaction context, policy migrations, and live tests |
| Separate database/schema per workspace | Strong physical isolation | High migration, pooling, backup, and operational cost for the current scale |

## Decision

Use PostgreSQL row-level security as defense in depth beneath ADR 0013. Application
policy decides whether an action is allowed; RLS ensures a runtime query cannot read
or mutate rows outside the trusted transaction context.

### Roles and ownership

- A migration/DDL role owns tables and is never used by FastAPI or workers.
- FastAPI uses a non-owner, non-superuser role without `BYPASSRLS`.
- Ingestion workers use a distinct non-owner role and set one trusted workspace for
  each claimed job before touching tenant content.
- The outbox dispatcher receives only the minimum cross-workspace infrastructure
  privileges required to claim and publish outbox rows; it cannot read document or
  conversation content.
- Operational/export/retention roles are separate and action-limited. There is no
  shared all-purpose system bypass in normal runtime code.

### Transaction context

Every tenant transaction uses transaction-local settings for the trusted internal
principal, workspace, and service purpose. Context is set only after JWT/membership
resolution or durable job reload. Use transaction-local state rather than session-
global state so pooled connections cannot leak a previous request's tenant.

RLS policies cover tenant-owned identity/membership links, documents and versions,
collections, conversations/messages, jobs/attempts/generations, outbox, and audit.
Policies use stable workspace columns and current membership/ACL relations; they do
not parse JWTs or trust request-supplied IDs.

Schema migrations must prove that new tenant tables either have reviewed RLS or an
explicit documented exemption. SQLite remains useful for deterministic domain tests,
but RLS acceptance requires PostgreSQL integration tests.

## Consequences

- Missing repository predicates fail closed at the database in normal runtime roles.
- Database-role provisioning and local/CI startup become more explicit.
- RLS does not protect Qdrant or object storage and cannot replace ADR 0013.
- Incorrect transaction context can deny valid work; diagnostics must remain safe.
- Table owners and privileged maintenance sessions require tight operational control.

## Acceptance resolution

The review accepted on 2026-08-31 the use of separate migration, API, worker,
dispatcher, and controlled-operation database roles, with no general runtime
`BYPASSRLS` role. Exact role names and local passwords remain environment configuration.

## Acceptance evidence required

- API and worker roles cannot disable or bypass RLS.
- A deliberately unscoped SQL query cannot observe another workspace.
- Reused pooled connections do not retain prior tenant context.
- Worker processing is limited to the durable job workspace.
- Dispatcher privileges cannot read document, conversation, object-reference, or message content.
- Alembic upgrade/downgrade and policy/schema drift checks pass.
- Live PostgreSQL tests cover read, insert, update, delete, role downgrade, and concurrent tenants.
