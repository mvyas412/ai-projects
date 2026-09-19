# Phase 9 Google Drive OAuth learning setup

## Scope and safety

This procedure configures the private Phase 9 learning connector. It uses a Google
Cloud project in testing mode, a Desktop OAuth client, one explicit test user, and only
the `https://www.googleapis.com/auth/drive.readonly` scope. It does not authorize the
application to create, modify, delete, or share Drive content.

The OAuth client JSON and token file are credentials. Keep both under the ignored
`data/runtime/credentials/` directory with file mode `0600`. Never paste their contents
into chat, logs, issues, commits, or support output.

## Google Cloud configuration

1. Create or select a dedicated learning project with no billing requirement.
2. Enable **Google Drive API**.
3. In **Google Auth Platform**, configure:
   - app name: `MM-RAG Learning`;
   - audience: **External** in **Testing** mode;
   - developer contact: the project owner's Google account;
   - test users: only the account used for the bounded proof;
   - data access: `.../auth/drive.readonly` only.
4. Under **Clients**, create a **Desktop app** client named
   `MM-RAG Local Connector` and download its JSON once.
5. Move the download to the ignored runtime credential directory and restrict it:

   ```bash
   mkdir -p data/runtime/credentials
   chmod 700 data/runtime/credentials
   mv /path/to/downloaded-client.json \
     data/runtime/credentials/google-drive-client.json
   chmod 600 data/runtime/credentials/google-drive-client.json
   ```

Do not add web redirect URIs. The local helper creates a random loopback callback on
`127.0.0.1`, opens the system browser, validates OAuth `state`, and uses PKCE.

## Authorize the local connector

From the `3.0` application directory:

```bash
GOOGLE_DRIVE_CLIENT_CONFIG=data/runtime/credentials/google-drive-client.json \
  make google-drive-authorize
```

Sign in as the configured test user and approve the read-only Drive request. The helper
stores the refresh/access token in the ignored runtime directory with mode `0600`; it
does not print token values.

## Aggregate-only verification

Run the bounded metadata probe:

```bash
GOOGLE_DRIVE_CLIENT_CONFIG=data/runtime/credentials/google-drive-client.json \
  make google-drive-probe
```

The probe obtains a change checkpoint, samples at most ten non-folder objects, and
counts principals for the first sample. Its output contains aggregate booleans/counts
only—no names, source IDs, content, permission IDs, or credentials—and it downloads no
document content.

The first bounded learning proof completed on 2026-09-19: provider health and checkpoint
creation succeeded, ten objects were sampled, and the first sampled object's permission
count was returned without content download or identity disclosure. Credential files
were verified ignored and mode `0600`.

## Revoke or rotate

- Revoke the app from the Google Account third-party access page when the proof ends or
  if either credential file may be exposed.
- Delete both local credential files after revocation.
- To rotate, create a replacement Desktop client, complete authorization again, verify
  the new credential, and only then revoke the previous client.
- Keep the app in testing mode. Public/production use of the restricted Drive scope is
  outside this learning proof and requires a separate verification/security review.
