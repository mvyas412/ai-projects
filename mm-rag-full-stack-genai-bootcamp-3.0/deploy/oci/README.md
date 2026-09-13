# OCI learning deployment bundle

This directory prepares the accepted Phase 8 single-VM learning topology. It does not
create an OCI account or resource. The first deployment keeps Streamlit as the working
frontend and uses private Compose networking behind Caddy HTTPS.

## Safety boundaries

- Use only synthetic or non-sensitive learning data.
- Set every image to an immutable `@sha256:` digest.
- Keep `runtime.env` and `streamlit-secrets.toml` mode `0600`; both are ignored.
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

The Phase 7 telemetry stack is optional during bootstrap. Set `TELEMETRY_ENABLED=true`
and include `--profile observability` once its memory budget and private SSH-tunnel
operator access have been reviewed; Grafana and Collector ports are never public.

The OCI host, free DNS name, firewall, backup upload, and clean restore are later
Milestone 8.1–8.5 steps. Never run `docker compose up` from this bundle until Phase 7
is accepted and the OCI provisioning action is separately approved.
