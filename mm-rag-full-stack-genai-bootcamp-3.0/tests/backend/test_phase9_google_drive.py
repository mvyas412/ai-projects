from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from backend.app.connectors.base import (
    ChangeKind,
    ConnectorContext,
    ConnectorCursorExpiredError,
    ConnectorUnavailableError,
    PrincipalKind,
)
from backend.app.connectors.credentials import (
    CredentialReference,
    CredentialState,
    ResolvedCredential,
)
from backend.app.connectors.google_drive import GoogleDriveConnector


class _Resolver:
    @contextmanager
    def resolve(
        self, reference, *, workspace_id, connector_id
    ) -> Iterator[ResolvedCredential]:
        assert reference.workspace_id == workspace_id
        assert reference.connector_id == connector_id
        yield ResolvedCredential({"access_token": SecretStr("test-access-token")})


def _context() -> ConnectorContext:
    workspace_id = uuid4()
    connector_id = uuid4()
    reference = CredentialReference(
        id=uuid4(),
        workspace_id=workspace_id,
        connector_id=connector_id,
        reference="vault://google-drive/test",
        granted_scopes=("https://www.googleapis.com/auth/drive.readonly",),
        state=CredentialState.ACTIVE,
    )
    return ConnectorContext(workspace_id, connector_id, reference)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_google_drive_initializes_checkpoint_without_replaying_history() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-access-token"
        assert request.url.path.endswith("/changes/startPageToken")
        return httpx.Response(200, json={"startPageToken": "initial-token"})

    connector = GoogleDriveConnector(_Resolver(), client=_client(handler))

    page = connector.list_changes(_context(), cursor=None)

    assert page.changes == ()
    assert page.next_cursor is None
    assert page.checkpoint_cursor == "initial-token"
    assert not page.has_more


def test_google_drive_maps_changes_and_promotes_only_terminal_checkpoint() -> None:
    responses = iter(
        [
            {
                "nextPageToken": "page-2",
                "changes": [
                    {
                        "fileId": "file-1",
                        "time": "2026-09-19T18:00:00Z",
                        "file": {
                            "id": "file-1",
                            "version": "7",
                            "modifiedTime": "2026-09-19T18:00:00Z",
                            "mimeType": "application/pdf",
                        },
                    }
                ],
            },
            {
                "newStartPageToken": "future-token",
                "changes": [
                    {
                        "fileId": "file-2",
                        "removed": True,
                        "time": "2026-09-19T18:01:00Z",
                    }
                ],
            },
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["includeRemoved"] == "true"
        return httpx.Response(200, json=next(responses))

    connector = GoogleDriveConnector(_Resolver(), client=_client(handler))
    first = connector.list_changes(_context(), cursor="current-token")
    second = connector.list_changes(_context(), cursor=first.next_cursor)

    assert first.has_more and first.next_cursor == "page-2"
    assert first.checkpoint_cursor is None
    assert first.changes[0].kind is ChangeKind.UPSERT
    assert not second.has_more and second.next_cursor is None
    assert second.checkpoint_cursor == "future-token"
    assert second.changes[0].kind is ChangeKind.DELETE


def test_google_drive_permission_snapshot_uses_opaque_ids_not_emails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/files/file-1/permissions")
        return httpx.Response(
            200,
            json={
                "permissions": [
                    {
                        "id": "opaque-user-id",
                        "type": "user",
                        "role": "reader",
                        "emailAddress": "must-not-persist@example.com",
                        "permissionDetails": [{"inherited": False}],
                    },
                    {
                        "id": "opaque-group-id",
                        "type": "group",
                        "role": "writer",
                        "permissionDetails": [{"inherited": True}],
                    },
                ]
            },
        )

    connector = GoogleDriveConnector(_Resolver(), client=_client(handler))
    snapshot = connector.get_permissions(_context(), object_external_id="file-1")

    assert len(snapshot.fingerprint) == 64
    assert snapshot.principals[0].kind is PrincipalKind.GROUP
    assert snapshot.principals[0].inherited
    assert "example.com" not in repr(snapshot)


def test_google_drive_downloads_blob_and_exports_native_document() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith("/files/blob") and "alt=media" not in str(request.url):
            return httpx.Response(
                200,
                json={
                    "id": "blob",
                    "mimeType": "application/pdf",
                    "modifiedTime": "2026-09-19T18:00:00Z",
                    "version": "1",
                    "size": "3",
                    "capabilities": {"canDownload": True},
                },
            )
        if request.url.path.endswith("/files/native"):
            return httpx.Response(
                200,
                json={
                    "id": "native",
                    "mimeType": "application/vnd.google-apps.document",
                    "modifiedTime": "2026-09-19T18:00:00Z",
                    "version": "2",
                    "capabilities": {"canDownload": True},
                },
            )
        if request.url.path.endswith("/files/blob"):
            return httpx.Response(200, content=b"pdf")
        if request.url.path.endswith("/files/native/export"):
            assert request.url.params["mimeType"] == "application/pdf"
            return httpx.Response(200, content=b"exported")
        raise AssertionError(f"Unexpected request: {request.url}")

    connector = GoogleDriveConnector(_Resolver(), client=_client(handler))
    context = _context()
    with connector.open_content(
        context, object_external_id="blob", version_external_id="1"
    ) as stream:
        assert stream.read() == b"pdf"
    with connector.open_content(
        context, object_external_id="native", version_external_id="2"
    ) as stream:
        assert stream.read() == b"exported"
    assert any("alt=media" in call for call in calls)


def test_google_drive_refuses_content_when_source_version_changed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "alt=media" not in str(request.url)
        return httpx.Response(
            200,
            json={
                "id": "file-1",
                "mimeType": "application/pdf",
                "modifiedTime": "2026-09-19T18:00:00Z",
                "version": "new-version",
                "capabilities": {"canDownload": True},
            },
        )

    connector = GoogleDriveConnector(_Resolver(), client=_client(handler))

    with pytest.raises(ConnectorUnavailableError, match="source version changed"):
        with connector.open_content(
            _context(),
            object_external_id="file-1",
            version_external_id="old-version",
        ):
            pass


def test_google_drive_rejects_expired_cursor_without_provider_details() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(410, json={"error": {"message": "provider detail"}})

    connector = GoogleDriveConnector(_Resolver(), client=_client(handler))

    with pytest.raises(ConnectorCursorExpiredError, match="checkpoint expired") as raised:
        connector.list_changes(_context(), cursor="expired")
    assert "provider detail" not in str(raised.value)


def test_google_drive_discovery_skips_folders_and_trashed_items() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "files": [
                    {
                        "id": "file-1",
                        "name": "Evidence.pdf",
                        "mimeType": "application/pdf",
                        "modifiedTime": "2026-09-19T18:00:00Z",
                        "parents": ["folder-1"],
                    },
                    {
                        "id": "folder-1",
                        "name": "Folder",
                        "mimeType": "application/vnd.google-apps.folder",
                        "modifiedTime": "2026-09-19T18:00:00Z",
                    },
                    {
                        "id": "trashed-1",
                        "name": "Deleted.pdf",
                        "mimeType": "application/pdf",
                        "modifiedTime": "2026-09-19T18:00:00Z",
                        "trashed": True,
                    },
                ]
            },
        )

    connector = GoogleDriveConnector(_Resolver(), client=_client(handler))

    objects = list(connector.discover(_context()))

    assert [(item.external_id, item.parent_external_id) for item in objects] == [
        ("file-1", "folder-1")
    ]
