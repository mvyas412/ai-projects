# ADR 0001 — Auth0 through OpenID Connect

- **Status:** Accepted
- **Date:** 2026-08-29
- **Phase:** 2.1

## Context

The product needs managed login, standards-based tokens, and a backend security
boundary without building password storage, reset, verification, or MFA systems.
The Streamlit frontend must authenticate users while FastAPI independently
validates every protected API request.

## Decision

Use Auth0 as the managed OpenID Connect provider.

- Streamlit uses `st.login("auth0")` with Authorization Code flow settings in
  ignored `.streamlit/secrets.toml`.
- Streamlit exposes only the API access token and sends it as a Bearer token.
- FastAPI validates Auth0 RS256 signatures through JWKS and requires matching
  issuer, audience, subject, issued-at, and expiration claims.
- FastAPI maps the trusted external `sub` claim to an internal user UUID.
- Auth0 proves identity; PostgreSQL workspace membership controls authorization.
- Missing, invalid, expired, wrong-issuer, and wrong-audience tokens fail closed.

## Consequences

- Real Auth0 tenant, application, and API configuration is required per environment.
- Secrets remain outside Git; only safe templates and identifiers are tracked.
- The identity-provider boundary remains standards-based, but Auth0-specific
  operational setup is now an intentional dependency.
- Live login cannot be validated until local Auth0 credentials are supplied.
