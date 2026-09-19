# Phase 9 enterprise operations

## Safety boundary

Phase 9 runs provider-neutral and simulated controls by default. Never place OAuth
tokens, webhook secrets, source content, payment data, or provider payloads in Git,
jobs, logs, evidence, or support output. Real billing is prohibited in this phase.

## Connector and sync operations

1. Register only an opaque credential reference for the tenant and connector.
2. Resolve credentials at execution time and use the read-only connector contract.
3. Treat webhooks as hints; reconciliation and the stored checkpoint remain truth.
4. On permission contraction or deletion, deny retrieval before cleanup.
5. Promote a terminal provider checkpoint only from the active fenced attempt.
6. On an expired cursor, create a bounded reconciliation/rescan; never guess a cursor.

Revoke an installation by setting it to `revoked`, invalidating its external credential,
and leaving prior evidence intact. A revoked connector cannot create a new sync run.

## Identity operations

OIDC remains authentication. SCIM-compatible lifecycle events map opaque external IDs to
stable internal users. Apply monotonically ordered events only. Suspension and deletion
deny product access immediately. Group mappings must use `admin`, `member`, or `viewer`;
`owner` is never provider-granted.

## Usage and simulated billing

Define product meters and quota values in a reviewed decision before exposing them to
users. Reserve quota before work, settle actual successful usage, and release unused
reservations. Never update or delete ledger entries; corrections are new linked entries.
The Phase 9 billing adapter is simulated, verifies HMAC signatures, stores only a payload
hash and minimal envelope, and reconciles versioned local entitlements.

## Compliance workflow

Privileged lifecycle work follows preview → reauthorize → apply. Recompute the scope at
reauthorization and apply; fail if its fingerprint changes. A retention hold blocks
destruction but never blocks access revocation. Evidence manifests contain identifiers,
counts, timestamps, and checksums only—never document or prompt content.

## Validation

Run focused Phase 9 checks with:

```bash
uv run pytest -q tests/backend/test_phase9_*.py
```

With local PostgreSQL available, prove RLS isolation with:

```bash
MM_RAG_RUN_INTEGRATION_TESTS=1 uv run pytest -q \
  tests/backend/test_phase9_rls_integration.py
```

Before commit or release, run `make check`. Live Google OAuth, provider propagation,
external SCIM, and billing-sandbox proofs require separate credentials and approval.
