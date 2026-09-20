from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx

from backend.app.connectors.base import ChangeKind, ConnectorContext, ConnectorError
from backend.app.connectors.credentials import CredentialReference, CredentialState
from backend.app.connectors.google_drive import GoogleDriveConnector
from backend.app.connectors.google_oauth import (
    GOOGLE_DRIVE_READONLY_SCOPE,
    GoogleDriveFileCredentialResolver,
    GoogleOAuthCredentialError,
)

DEFAULT_TOKEN_PATH = Path("data/runtime/credentials/google-drive-token.json")
DEFAULT_EVIDENCE_PATH = Path(
    "data/runtime/evidence/phase9-google-drive-propagation.json"
)


def _connector(
    client_config_path: Path, token_path: Path
) -> tuple[GoogleDriveConnector, ConnectorContext, httpx.Client, httpx.Client]:
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
    oauth_client = httpx.Client(timeout=15.0, follow_redirects=False)
    drive_client = httpx.Client(timeout=30.0, follow_redirects=False)
    resolver = GoogleDriveFileCredentialResolver(
        client_config_path, client=oauth_client
    )
    return (
        GoogleDriveConnector(resolver, client=drive_client),
        context,
        oauth_client,
        drive_client,
    )


def _write_private_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, path)
    path.chmod(0o600)


def _read_evidence(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GoogleOAuthCredentialError("Private propagation evidence is unavailable") from exc
    if not isinstance(payload, dict):
        raise GoogleOAuthCredentialError("Private propagation evidence is invalid")
    return payload


def _checkpoint(connector: GoogleDriveConnector, context: ConnectorContext) -> str:
    cursor = connector.list_changes(context, cursor=None).checkpoint_cursor
    if cursor is None:
        raise GoogleOAuthCredentialError("Google Drive did not return a checkpoint")
    return cursor


def _target_change(
    connector: GoogleDriveConnector,
    context: ConnectorContext,
    *,
    cursor: str,
    object_external_id: str,
) -> tuple[bool, bool, str]:
    saw_target = False
    saw_delete = False
    while True:
        page = connector.list_changes(context, cursor=cursor)
        for change in page.changes:
            if change.object_external_id == object_external_id:
                saw_target = True
                saw_delete = saw_delete or change.kind is ChangeKind.DELETE
        if not page.has_more:
            if page.checkpoint_cursor is None:
                raise GoogleOAuthCredentialError("Google Drive returned an incomplete checkpoint")
            return saw_target, saw_delete, page.checkpoint_cursor
        if page.next_cursor is None:
            raise GoogleOAuthCredentialError("Google Drive returned an incomplete page")
        cursor = page.next_cursor


def capture_baseline(
    connector: GoogleDriveConnector,
    context: ConnectorContext,
    *,
    fixture_name: str,
    evidence_path: Path,
) -> dict[str, object]:
    matches = [item for item in connector.discover(context) if item.name == fixture_name]
    if len(matches) != 1:
        raise GoogleOAuthCredentialError("Expected exactly one propagation fixture")
    target = matches[0]
    permissions = connector.get_permissions(
        context, object_external_id=target.external_id
    )
    _write_private_json(
        evidence_path,
        {
            "fixture_name": fixture_name,
            "object_external_id": target.external_id,
            "baseline_permission_fingerprint": permissions.fingerprint,
            "baseline_principal_count": len(permissions.principals),
            "checkpoint_cursor": _checkpoint(connector, context),
            "permission_expansion_observed": False,
            "permission_contraction_observed": False,
            "deletion_observed": False,
        },
    )
    return {
        "fixture_discovered": True,
        "baseline_captured": True,
        "principal_count": len(permissions.principals),
        "content_downloaded": False,
    }


def verify_permission_transition(
    connector: GoogleDriveConnector,
    context: ConnectorContext,
    *,
    evidence_path: Path,
    expect_restored: bool,
) -> dict[str, object]:
    evidence = _read_evidence(evidence_path)
    object_id = str(evidence["object_external_id"])
    baseline = str(evidence["baseline_permission_fingerprint"])
    cursor = str(evidence["checkpoint_cursor"])
    permissions = connector.get_permissions(context, object_external_id=object_id)
    changed = permissions.fingerprint != baseline
    if changed == expect_restored:
        expectation = "restored" if expect_restored else "expanded"
        raise GoogleOAuthCredentialError(f"Expected permission state was not {expectation}")
    saw_target, _, checkpoint = _target_change(
        connector,
        context,
        cursor=cursor,
        object_external_id=object_id,
    )
    if not saw_target:
        raise GoogleOAuthCredentialError("Permission change was not present in the change feed")
    evidence["checkpoint_cursor"] = checkpoint
    evidence[
        "permission_contraction_observed"
        if expect_restored
        else "permission_expansion_observed"
    ] = True
    _write_private_json(evidence_path, evidence)
    return {
        "permission_change_observed": True,
        "permission_restored": expect_restored,
        "principal_count": len(permissions.principals),
        "content_downloaded": False,
    }


def verify_deletion(
    connector: GoogleDriveConnector,
    context: ConnectorContext,
    *,
    evidence_path: Path,
) -> dict[str, object]:
    evidence = _read_evidence(evidence_path)
    object_id = str(evidence["object_external_id"])
    cursor = str(evidence["checkpoint_cursor"])
    saw_target, saw_delete, checkpoint = _target_change(
        connector,
        context,
        cursor=cursor,
        object_external_id=object_id,
    )
    still_discoverable = any(
        item.external_id == object_id for item in connector.discover(context)
    )
    if not saw_target or not saw_delete or still_discoverable:
        raise GoogleOAuthCredentialError("Deletion propagation has not completed")
    evidence["checkpoint_cursor"] = checkpoint
    evidence["deletion_observed"] = True
    _write_private_json(evidence_path, evidence)
    return {
        "delete_change_observed": True,
        "fixture_absent_from_discovery": True,
        "content_downloaded": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record aggregate-only Google Drive propagation evidence"
    )
    parser.add_argument("stage", choices=("baseline", "expanded", "restored", "deleted"))
    parser.add_argument("--client-config", type=Path, required=True)
    parser.add_argument("--token-path", type=Path, default=DEFAULT_TOKEN_PATH)
    parser.add_argument("--evidence-path", type=Path, default=DEFAULT_EVIDENCE_PATH)
    parser.add_argument("--fixture-name")
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.stage == "baseline" and not args.fixture_name:
        raise SystemExit("--fixture-name is required for the baseline stage")
    connector, context, oauth_client, drive_client = _connector(
        args.client_config, args.token_path
    )
    try:
        if args.stage == "baseline":
            result = capture_baseline(
                connector,
                context,
                fixture_name=args.fixture_name,
                evidence_path=args.evidence_path,
            )
        elif args.stage in {"expanded", "restored"}:
            result = verify_permission_transition(
                connector,
                context,
                evidence_path=args.evidence_path,
                expect_restored=args.stage == "restored",
            )
        else:
            result = verify_deletion(
                connector, context, evidence_path=args.evidence_path
            )
    except (ConnectorError, GoogleOAuthCredentialError, KeyError) as exc:
        raise SystemExit(str(exc)) from None
    finally:
        oauth_client.close()
        drive_client.close()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
