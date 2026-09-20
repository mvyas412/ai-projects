# OCI learning deployment bundle

This directory prepares the accepted Phase 8 single-VM learning topology. It does not
create an OCI account or resource. The first deployment keeps Streamlit as the working
frontend and uses private Compose networking behind Caddy HTTPS.

## Safety boundaries

- Use only synthetic or non-sensitive learning data.
- Set every image to an immutable `@sha256:` digest.
- Keep `runtime.env` and `streamlit-secrets.toml` mode `0600`; both are ignored. On
  the host, own the Streamlit file as application UID/GID `10001:10001` so the
  non-root image can read the bind mount without broadening permissions.
- Expose only ports 80 and 443. Keep database, vector, broker, object-storage, and
  observability administration private.
- Do not enable a paid OCI shape or exceed an Always Free allowance without approval.
- `APP_ENV=staging` is deliberate: this is a production-shaped learning deployment,
  not a production availability claim.

## Prepare without provisioning

1. Copy `runtime.env.example` to the ignored `runtime.env` and replace every placeholder.
2. Copy `streamlit-secrets.toml.example` to the ignored `streamlit-secrets.toml`.
3. Add the final HTTPS callback, logout, and web-origin URL to the Auth0 application.
4. Run `make phase8-deployment-validate`.
5. Render the Compose model without starting services:

   ```bash
   docker compose --env-file deploy/oci/runtime.env \
     -f deploy/oci/compose.yaml config --quiet
   ```

The one-shot `models` service downloads the accepted Phase 5 and Phase 6 CPU model
artifacts into persistent volumes before the API and worker start. Budget disk space
and outbound transfer for this first start.

Run migration and model provisioning as separate one-shot commands. Do not combine
them with `--abort-on-container-exit`: a successful migration exits before the larger
model job and would force-stop that healthy download.

The Phase 7 telemetry stack is optional during bootstrap. Set `TELEMETRY_ENABLED=true`
and include `--profile observability` once its memory budget and private SSH-tunnel
operator access have been reviewed; Grafana and Collector ports are never public.

The plan-only Terraform module, release manifest, Next.js candidate, capacity probe,
encrypted backup bundler, and evidence gate are documented in
`docs/PHASE8_OCI_OPERATIONS.md`. Never run `terraform apply` or `docker compose up` from
this bundle until Phase 7 is accepted and the OCI provisioning action is separately approved.

Phase 10 adds disabled-by-default systemd examples in `systemd/`. Review and supervise
one encrypted backup cycle before enabling its timer; clean-host drills, host replacement,
retention apply and cloud-object deletion keep separate approval boundaries. See
`docs/PHASE10_OPERATIONS.md`.
