# Phase 8 OCI learning-deployment operations

This runbook turns the accepted Phase 8 ADRs into repeatable evidence. It does not
authorize cloud provisioning, image publication, DNS changes, paid model calls, or
frontend promotion. Use synthetic/non-sensitive learning data only.

## 1. Pre-provision review

Use the [OCI onboarding checklist](PHASE8_OCI_ONBOARDING.md) to collect the exact
non-secret inputs and approvals without placing credentials in Terraform.

1. Confirm Phase 7 is accepted and its SLO thresholds are frozen.
2. Confirm OCI home region, compartment and tenancy OCIDs, an availability domain with
   A1 capacity, an exact operator `/32`, public SSH key, unique backup bucket, and alert
   email. Never put a private key or application secret in Terraform.
3. Copy `terraform.tfvars.example` to ignored `terraform.tfvars`.
4. Run `terraform fmt -check`, `terraform init -backend=false`, `terraform validate`,
   and `terraform plan -out` locally. Review the plan and current free-tier eligibility.
5. Obtain separate approval before `terraform apply`. The USD 1 OCI budget alerts but
   cannot stop spend.

## 2. Release preparation and deployment

1. Publish the approved multiarch app image through the manually protected GitHub
   workflow. Record the signed digest and scan/SBOM evidence.
2. Resolve immutable digests for all service images. Complete a private release manifest
   from `deploy/oci/release-manifest.example.json`; validate it with
   `python -m scripts.phase8_release`.
3. Copy only the approved checkout, ignored `runtime.env`, and ignored Streamlit secrets
   to `/opt/mm-rag`. Keep secrets mode `0600`; never print them.
4. Run `docker compose config --quiet`, pull by digest, start persistence services, run
   the one-shot migration and model jobs, then start API/worker/UI/edge.
5. Verify HTTPS, Auth0 callback/logout, authenticated email/workspace, API readiness,
   tenant isolation, upload/job completion, grounded chat, citations, and logout.

Streamlit remains the default upstream. The `nextjs-candidate` profile and upstream
switch are for a separately approved parity test only. Revert the edge upstream to
`ui:8503` after testing.

## 3. Capacity and safe-degradation evidence

Run the read-only progressive probe at 1, 3, 5, and 10 simultaneous users. It makes no
model calls and has no retry:

```bash
uv run python -m scripts.phase8_evidence probe \
  --base-url https://HOST \
  --path /api/v1/health/ready \
  --path /api/v1/users/me \
  --requests-per-stage 30
```

Keep the access token in `MM_RAG_ACCESS_TOKEN`; the script never prints it or response
bodies. Compare every stage's p95/error data with the frozen Phase 7 SLO rather than
inventing a threshold. Record CPU, memory, disk, queue age/depth, active jobs, model
latency and cost. Use free simulated provider responses for sustained mixed-workload
testing; any real-provider smoke remains separately approved and bounded. Scale-up review
is triggered by repeated SLO breach, sustained >80% memory/disk, queue age beyond the
approved SLO, or resource exhaustion at or below ten simultaneous users.

Exercise each failure one at a time against the learning host: worker restart, broker,
PostgreSQL, Qdrant, SeaweedFS and telemetry unavailability, plus bounded disk pressure.
Use `docker compose stop SERVICE`, observe timeouts/backpressure/non-disclosing errors,
then restart it immediately. Never fill the root filesystem; use a bounded disposable
file and retain at least 20% free disk. Verify durable jobs resume without duplicate
promotion and telemetry failure does not break user traffic.

## 4. Encrypted backup and clean restore

Quiesce writers first. Export PostgreSQL with custom-format `pg_dump`, create/download
Qdrant collection snapshots, and copy both SeaweedFS S3 buckets into a mode-0700 staging
directory with members `postgres.dump`, `qdrant/`, and `objects/`. Record service and
schema versions outside document content.

Create the client-encrypted bundle:

```bash
PHASE8_BACKUP_AGE_RECIPIENT='age1...' \
  uv run python -m scripts.phase8_backup create STAGING_DIR phase8-YYYYMMDD.tar.gz.age
```

Upload only the `.age` bundle to the private versioned OCI bucket. Do not upload the
plaintext staging directory. Delete plaintext staging after checksum/upload verification.

For the restore exercise, use a clean isolated host or clean temporary Compose project.
Decrypt, safely extract, and verify into a destination that does not already exist:

```bash
uv run python -m scripts.phase8_backup restore phase8-YYYYMMDD.tar.gz.age \
  RESTORED_DIR --identity-file /offline/path/to/age-identity.txt
```

The restore command rejects absolute paths, traversal, links, duplicate archive members,
unmanifested files, missing service exports, and checksum mismatches. Then restore
PostgreSQL/Qdrant/objects, migrate forward only if the release
manifest requires it, then verify row/vector/object counts, tenant isolation, content
checksums, ingestion state, citation retrieval and readiness. Record measured data age
(RPO, maximum 24 hours) and elapsed recovery time (RTO, maximum 8 hours).

## 5. Rollback and release gate

Retain the previous release manifest and images. Before deployment, prove the database
migration is backward compatible or take a tested backup. To roll back, quiesce writers,
restore the previous digest manifest, apply only an explicitly reviewed database recovery
step, start persistence then application roles, and verify tenant-data integrity.

The release is not accepted until all ten evidence scenarios pass:

```bash
uv run python -m scripts.phase8_evidence gate evaluation/phase8/results/RELEASE_ID
```

Also require clean free tests, live service contracts, image scan/SBOM/signature,
dependency audits, Auth0 browser flow, accessibility review, restore evidence, and an
operator review that the deployment is a learning system without an SLA.
