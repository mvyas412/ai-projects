# ADR 0050: Google Drive as the first enterprise connector

- Status: Accepted
- Date: 2026-09-19
- Milestone: 9.1–9.2

## Context

The user approved Google Drive as the first provider after reviewing the Phase 9
scorecard recommendation. Drive offers free learning access, v3 change tokens, explicit
removal events, file permissions, blob download, and native-document export. A personal
test account does not prove enterprise groups or SCIM, and whole-Drive read access uses
a restricted OAuth scope.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| Microsoft SharePoint/OneDrive | Strong enterprise ACL and identity fit | Free sandbox availability and tenant administration are less predictable |
| Box | Clear enterprise content model | Smaller learning fit and separate account setup |
| Generic authenticated API | Fully controlled fixture | Does not prove real permission/change semantics |
| Google Drive | Free familiar account, change feed, permissions, exports | Restricted read scope and limited enterprise-group proof on a personal account |

## Decision

Implement a read-only Google Drive API v3 adapter behind the accepted connector SDK.
Use opaque `changes.getStartPageToken`/`changes.list` cursors, include removals, and
promote `newStartPageToken` only after the terminal page succeeds. Read permissions via
`permissions.list`, retain opaque permission IDs rather than email addresses, and hash
the canonical principal/role/inheritance set. Download blob files with `files.get`
`alt=media`; export supported Google-native documents to PDF after checking
`capabilities.canDownload`.

For the private learning proof, request read-only Drive access and keep the OAuth app in
testing mode with an explicit test user. OAuth client data, refresh/access tokens, and
consent artifacts remain outside Git and are resolved only through the runtime credential
boundary. No write/delete/share API is permitted. A public or production deployment
would require a separate Google restricted-scope verification/security review.

## Recommendation

Implement and test the adapter with mocked HTTP first. Gate live OAuth setup and a
bounded read-only proof on explicit user participation, then add shared-drive/group
evidence only if a Workspace sandbox becomes available.

## Consequences

- Provider behavior exercises the canonical SDK without becoming product authorization.
- Initial acceptance can use a personal Drive test account, but cannot claim enterprise
  group lifecycle or Google Workspace administration.
- Cursor expiry triggers a bounded rescan; it never guesses a continuation.
- Provider credentials and live source content remain outside deterministic CI.

## Decision record

Accepted by the user on 2026-09-19. Google Drive is the first connector under the
read-only, testing-mode, secret-safe, and separately gated live-proof constraints above.
