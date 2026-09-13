# Phase 8 OCI learning-deployment onboarding

Use this checklist only after Phase 7 is accepted and the user separately approves
cloud provisioning. Completing it prepares a reviewed Terraform plan; it does not
authorize `terraform apply`, image publication, DNS changes, or paid model calls.

## 1. User-provided, non-secret choices

- [ ] Confirm the existing OCI account is active and note its **home region**.
- [ ] Choose or create a dedicated learning compartment and record its compartment OCID.
- [ ] Record the tenancy OCID and select an availability domain where an A1 Flex shape is
      offered. Free-tier eligibility and capacity must be rechecked immediately before apply.
- [ ] Provide the operator's current public IP as one exact IPv4 `/32`; do not use
      `0.0.0.0/0` for SSH.
- [ ] Provide an SSH **public** key. Keep the private key outside the repository.
- [ ] Choose a globally unique private backup-bucket name.
- [ ] Provide an email address for the USD 1 actual/forecast budget alerts.
- [ ] Choose a free hostname provider/name for HTTPS. A paid or owned production domain is
      not required for this learning deployment.

OCIDs, the public IP, public key, hostname, and alert email are operational metadata, not
application secrets, but keep the populated `terraform.tfvars` ignored and private.

## 2. Secrets prepared outside Terraform

- [ ] Auth0 client secret and application configuration.
- [ ] OpenAI API key and any approved model-provider credentials.
- [ ] PostgreSQL, RabbitMQ, SeaweedFS, session, and internal service credentials.
- [ ] The offline `age` identity used to decrypt backups.

Place runtime values only in the ignored `deploy/oci/runtime.env` and ignored Streamlit
secrets file on the host, both mode `0600`. Never put them in Terraform variables,
cloud-init, command output, GitHub logs, screenshots, or release evidence.

## 3. Read-only preparation that Codex can perform

- [ ] Copy `deploy/oci/terraform/terraform.tfvars.example` to ignored
      `terraform.tfvars` and populate only reviewed non-secret values.
- [ ] Run format, initialization without a backend, validation, and a saved plan.
- [ ] Review resource count, region, shape, boot volume, network ingress, bucket privacy and
      versioning, budget notifications, and whether every intended resource is still
      Always Free-eligible.
- [ ] Record the plan summary without copying sensitive values into tracked files.

Terraform state remains local and ignored for this learning deployment. A remote-state
backend is a future decision, not an implicit addition.

## 4. Explicit approvals still required

- [ ] Approve the exact reviewed `terraform apply` plan.
- [ ] Approve publishing the signed multiarch image digest through the protected workflow.
- [ ] Approve DNS/hostname and Auth0 callback, logout, and web-origin updates.
- [ ] Approve any bounded paid model acceptance run separately.

## 5. Post-provision acceptance

- [ ] Deploy only digest-pinned service images and the reviewed release manifest.
- [ ] Verify HTTPS, sign-in, authenticated email, personal workspace, readiness, upload,
      durable ingestion, grounded chat/citations, and logout.
- [ ] Run the bounded 1–3-user capacity and dependency-failure scenarios.
- [ ] Create an encrypted backup, restore it into a clean target, and verify database,
      vector, object, authorization, checksum, readiness, RPO, and RTO evidence.
- [ ] Exercise rollback to the previous immutable manifest without tenant-data loss.
- [ ] Confirm all ten release-evidence scenarios pass before Phase 8 acceptance.

This topology is a low-cost learning system with no high-availability or production SLA
claim. Stop and review rather than silently adding paid capacity when free capacity is
unavailable.
