# Phase 10 operations handbook

This handbook implements accepted ADRs 0051–0056 for the free-first OCI learning
deployment. It is not an SLA or authority to spend money, delete application data,
replace a host, expose credentials, or run paid model calls.

## Safety model

Every operation follows **plan → authorize → execute → verify → rollback/restore**.
Plans with exact backup names, hosts, URLs, resource identifiers, or credentials stay in
ignored `operations/private/`. Generated records stay in ignored
`evaluation/phase10/results/`; release evidence contains aggregates and hashes only.
FastAPI and PostgreSQL RLS remain the product authorization boundary.

Before any host operation, record the current full Git revision, immutable image
digests, migration head, fresh verified-backup age, disk/inode headroom, active jobs,
queue age and readiness. Stop when a check changes between plan and execution.

## 10.1 Daily backup verification and monthly restore

The existing `scripts.phase8_backup` format remains canonical. Daily automation must:

1. acquire a single-host lease and stop if another run owns it;
2. quiesce writers at safe checkpoints;
3. export PostgreSQL, Qdrant and both object namespaces to a mode-0700 staging area;
4. create and locally verify one encrypted `.age` bundle;
5. upload only ciphertext to the existing private OCI bucket;
6. verify the uploaded checksum, then remove plaintext staging; and
7. emit content-free `backup-verification` evidence.

Never print the age identity, object coordinates, database URL or OCI identifiers. Keep
seven daily and two monthly verified generations, never deleting the final two known-good
generations. `backup-plan` only computes candidates; cloud deletion remains a separately
reviewed exact plan.

Once per month, restore the latest known-good bundle into disposable, network-restricted
services. Verify schema head, aggregate SQL/vector/object counts, object checksums,
tenant isolation and readiness. The active data plane must remain untouched. Cleanup of
temporary cloud resources is destructive and requires the same reviewed scope.

The disabled systemd examples under `deploy/oci/systemd/` use the previously requested
05:30 Pacific maintenance window with a bounded random delay. Review the rendered unit,
create the ignored mode-0600 environment file, and run one supervised cycle before
enabling the timer. Daily execution needs only the public age recipient; keep the private
identity offline for the separately supervised restore drill.

Example evidence validation:

```bash
uv run python -m scripts.phase10_operations backup-evidence \
  operations/examples/backup-verification.json \
  --output evaluation/phase10/results/backup-verification.json
```

## 10.2 Preview-only retention

Once per month, a workspace owner/admin uses the existing authenticated retention-preview
API. Feed only its aggregate counts, policy revision and one-time preview token into the
Phase 10 validator. The saved report contains a token hash, never the token.

```bash
uv run python -m scripts.phase10_operations retention-preview \
  operations/private/retention-preview.json \
  --output evaluation/phase10/results/retention-preview.json
```

Automatic apply remains disabled. A human must review and reauthorize the unchanged
preview in the application; holds always win. Retention and recovery-window values are
still undecided, so Phase 10 must not schedule physical purge.

## 10.3 Monthly maintenance candidates

Dependabot creates at most one monthly grouped candidate per uv/Python, Next.js, GitHub
Actions and container ecosystem. It cannot merge. Each candidate must pass lockfile,
tests, vulnerability scan, SBOM, provenance and ARM64 checks. Runtime, database or image
promotion also requires an exercised rollback record. Paid acceptance is never started
automatically.

Use the urgent path only for a known-exploited issue affecting MM-RAG, an exploitable
critical issue, or a public-exploit high-severity issue in an exposed component. Even an
urgent candidate remains reviewed and rollback-capable.

## 10.4 Capacity and zero-cost guardrails

Record CPU, memory, disk, inode, queue age, certificate lifetime, verified-backup age and
unexpected paid-resource presence without provider identifiers. Sustained 80% resource
use for 15 minutes requests review; 90% or an older-than-48-hour verified backup is
critical. Queue-age and certificate cutoffs remain explicitly unset until controlled
free tests establish useful values; the report calls this out rather than inventing a
threshold.

At review level, stop optional evaluation and new bulk ingestion before changing
capacity. At critical level, preserve active work, reject new expensive work with a
non-disclosing response, and follow the recovery runbook. Do not auto-scale or select a
paid shape. Compare OCI inventory with the reviewed free-resource allowlist and keep the
existing USD 1 budget alarm.

The disabled capacity timer samples every five minutes so the approved 15-minute
sustained threshold can be measured. Its private inventory-status input is refreshed by
an operator-reviewed OCI inventory query; the collector does not assume that an unknown
resource is free. A failed timer or critical JSON result is a local alert and must be
reviewed in the systemd journal.

## 10.5 Upgrade, rollback and clean-host recovery

Generate preflight evidence with `operator_authorized: false`. Execution requires the
operator to confirm the exact unchanged plan hash. Quiesce workers, take/verify a fresh
backup, pull immutable digests, run forward-only migrations, start persistence before
application roles, and verify readiness and tenant-safe smoke tests. If compatibility
checks fail, use the tested restore branch rather than destructive schema reversal.

Rollback restores the prior immutable manifest only when migration compatibility is
proven; otherwise restore the matched encrypted backup. A clean-host drill starts from
reviewed Terraform and requires a separately approved zero-cost plan for temporary
resources. Secrets are supplied only at runtime, never through Terraform, cloud-init,
logs or evidence. Remove temporary resources only after recovery evidence is captured
and their exact deletion plan is approved.

Validate an ignored exact plan first:

```bash
uv run python -m scripts.phase10_release plan operations/private/release-plan.json
```

Execution is deliberately a separate command and requires both `--authorize` and the
exact printed `--confirm-plan-sha`. A failure does not choose a rollback automatically;
prepare and authorize a separate rollback or restore plan so a bad target cannot broaden
its own recovery authority.

## 10.6 Acceptance and incident learning

Phase 10 acceptance requires content-free evidence for backup verification, isolated
restore, retention preview, maintenance gate, healthy capacity guardrails, upgrade
preflight, rollback drill and clean-host recovery:

```bash
uv run python -m scripts.phase10_operations gate evaluation/phase10/results
```

After an incident, preserve timestamps, aggregate impact, decisions and remediation;
exclude document content, prompts, tokens, user identifiers and provider identifiers.
Update this handbook, architecture, plan and private context in the same work session.
