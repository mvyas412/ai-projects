# OCI learning infrastructure

This module describes one production-shaped learning host and a private, versioned
off-host backup bucket. It is intentionally not wired to an automatic `terraform apply`.

## Safety and cost boundary

- The default ARM shape is `VM.Standard.A1.Flex` with 2 OCPUs and 12 GB RAM.
- Public ingress is limited to HTTP/HTTPS; SSH is restricted to `operator_cidr`.
- The backup bucket is private and versioned. Backup payloads must be encrypted before upload.
- The compute instance uses an OCI instance principal for backup upload. Its policy grants
  only `OBJECT_CREATE` in the exact backup bucket; it cannot administer the bucket or list,
  read, overwrite, or delete objects. No user API key is installed on the host.
- OCI-managed encryption is the default; customer-managed keys are deferred to a later budget review.
- A USD 1 monthly budget produces forecast and actual-spend alerts. A budget is an alert,
  not a hard spending cap, and free-tier eligibility/capacity must be rechecked in the console.
- Terraform state can contain identifiers and configuration. Keep it local and ignored until
  a separately approved remote-state design is available; never pass application secrets here.

## Review before provisioning

1. Copy `terraform.tfvars.example` to ignored `terraform.tfvars`.
2. Select the account home region and an availability domain with A1 capacity.
3. Use only a public SSH key and an exact operator `/32` CIDR.
4. Run `terraform init`, `terraform fmt -check`, `terraform validate`, and `terraform plan`.
5. Review the plan, OCI free-tier eligibility, public IP, disk size, budget alert, and
   the exact instance-principal dynamic-group and bucket-scoped IAM statement.
6. Obtain explicit provisioning approval before running `terraform apply`.

The cloud-init phase installs and hardens the container host only. It does not clone,
start, or configure the application and cannot contain runtime credentials.
OCI treats instance `user_data` as create-only, so Terraform ignores later changes to
that metadata field rather than replacing the VM implicitly. Apply corrected cloud-init
to future rebuilds through a separately reviewed replacement plan, and require clean
cloud-init completion before deploying application artifacts.
