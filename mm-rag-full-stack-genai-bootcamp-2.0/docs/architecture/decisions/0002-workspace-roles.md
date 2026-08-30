# ADR 0002 — Initial workspace role model

- **Status:** Accepted
- **Date:** 2026-08-29
- **Phase:** 2.1

## Context

Documents, conversations, jobs, and retrieval need an explicit tenant boundary.
The first role model must be understandable in demonstrations and extensible to
later document-level ACL and enterprise governance work.

## Decision

Use four workspace roles:

| Role | Intended responsibility |
| --- | --- |
| `owner` | Workspace lifecycle, ownership, members, settings, and all content |
| `admin` | Members, settings, and content administration except ownership transfer |
| `member` | Create, upload, organize, and chat within permitted workspace content |
| `viewer` | Read and chat with permitted content without administrative mutations |

Every newly provisioned user receives a personal workspace with the `owner`
role. Roles are stored on the user/workspace membership and validated by a
database check constraint. Backend policy dependencies—not Streamlit—will map
roles to actions.

## Consequences

- Membership is the minimum requirement for workspace visibility.
- Unauthorized workspace lookup returns a non-enumerating 404 response.
- Phase 4 may add resource ACLs and finer permissions without changing the
  stable user/workspace identity model.
- Automated negative tests are required for every new tenant-scoped resource.
