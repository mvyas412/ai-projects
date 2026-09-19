from __future__ import annotations

import argparse
import json
from itertools import islice
from pathlib import Path
from uuid import uuid4

import httpx

from backend.app.connectors.base import ConnectorContext, ConnectorError
from backend.app.connectors.credentials import CredentialReference, CredentialState
from backend.app.connectors.google_drive import GoogleDriveConnector
from backend.app.connectors.google_oauth import (
    GOOGLE_DRIVE_READONLY_SCOPE,
    GoogleDriveFileCredentialResolver,
    GoogleOAuthCredentialError,
)

DEFAULT_TOKEN_PATH = Path("data/runtime/credentials/google-drive-token.json")


def probe(client_config_path: Path, token_path: Path, max_objects: int) -> dict[str, object]:
    workspace_id = uuid4()
    connector_id = uuid4()
    reference = CredentialReference(
        id=uuid4(),
        workspace_id=workspace_id,
        connector_id=connector_id,
        reference=token_path.resolve().as_uri(),
        granted_scopes=(GOOGLE_DRIVE_READONLY_SCOPE,),
        state=CredentialState.ACTIVE,
    )
    context = ConnectorContext(workspace_id, connector_id, reference)
    with (
        httpx.Client(timeout=15.0, follow_redirects=False) as oauth_client,
        httpx.Client(timeout=30.0, follow_redirects=False) as drive_client,
    ):
        resolver = GoogleDriveFileCredentialResolver(
            client_config_path,
            client=oauth_client,
        )
        connector = GoogleDriveConnector(resolver, client=drive_client)
        health = connector.health(context)
        if not health.available:
            raise GoogleOAuthCredentialError("Google Drive is unavailable")
        checkpoint = connector.list_changes(context, cursor=None)
        objects = tuple(islice(connector.discover(context), max_objects))
        permission_count = 0
        if objects:
            snapshot = connector.get_permissions(
                context,
                object_external_id=objects[0].external_id,
            )
            permission_count = len(snapshot.principals)
    return {
        "available": True,
        "checkpoint_received": checkpoint.checkpoint_cursor is not None,
        "objects_sampled": len(objects),
        "sample_limit": max_objects,
        "first_object_permission_principals": permission_count,
        "content_downloaded": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an aggregate-only MM-RAG Google Drive read-only probe"
    )
    parser.add_argument("--client-config", type=Path, required=True)
    parser.add_argument("--token-path", type=Path, default=DEFAULT_TOKEN_PATH)
    parser.add_argument("--max-objects", type=int, default=10)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.max_objects < 1 or args.max_objects > 25:
        raise SystemExit("--max-objects must be between 1 and 25")
    try:
        result = probe(args.client_config, args.token_path, args.max_objects)
    except (ConnectorError, GoogleOAuthCredentialError) as exc:
        raise SystemExit(str(exc)) from None
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
