from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import datetime
from io import BytesIO
from typing import Any, BinaryIO, Iterator, cast
from urllib.parse import quote

import httpx

from backend.app.connectors.base import (
    ChangeKind,
    ConnectorChange,
    ConnectorContext,
    ConnectorCursorExpiredError,
    ConnectorHealth,
    ConnectorObject,
    ConnectorPage,
    ConnectorUnavailableError,
    ConnectorVersion,
    PermissionSnapshot,
    Principal,
    PrincipalKind,
)
from backend.app.connectors.credentials import CredentialResolver

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
GOOGLE_FOLDER_MEDIA_TYPE = "application/vnd.google-apps.folder"
GOOGLE_NATIVE_PREFIX = "application/vnd.google-apps."
GOOGLE_EXPORT_MEDIA_TYPE = "application/pdf"


class GoogleDriveConnector:
    """Read-only Drive v3 adapter; credential refresh/storage belongs to the resolver."""

    kind = "google_drive"

    def __init__(
        self,
        credential_resolver: CredentialResolver,
        *,
        client: httpx.Client | None = None,
        max_download_bytes: int = 25 * 1024 * 1024,
    ) -> None:
        if max_download_bytes <= 0:
            raise ValueError("Download limit must be positive")
        self._credentials = credential_resolver
        self._client = client or httpx.Client(timeout=30.0, follow_redirects=False)
        self._max_download_bytes = max_download_bytes

    def health(self, context: ConnectorContext) -> ConnectorHealth:
        try:
            self._request_json(
                context,
                "/changes/startPageToken",
                params={"supportsAllDrives": "true"},
            )
        except ConnectorUnavailableError:
            return ConnectorHealth(False, datetime.now().astimezone(), "unavailable")
        return ConnectorHealth(True, datetime.now().astimezone())

    def discover(self, context: ConnectorContext) -> Iterator[ConnectorObject]:
        page_token: str | None = None
        while True:
            params = {
                "q": "trashed = false",
                "corpora": "user",
                "spaces": "drive",
                "pageSize": "1000",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
                "fields": (
                    "nextPageToken,files(id,name,mimeType,modifiedTime,parents,trashed)"
                ),
            }
            if page_token:
                params["pageToken"] = page_token
            payload = self._request_json(context, "/files", params=params)
            for item in _list_of_objects(payload, "files"):
                if item.get("trashed") is True or item.get("mimeType") == GOOGLE_FOLDER_MEDIA_TYPE:
                    continue
                yield _object_from_file(item)
            page_token = _optional_string(payload, "nextPageToken")
            if page_token is None:
                return

    def list_changes(
        self, context: ConnectorContext, *, cursor: str | None
    ) -> ConnectorPage:
        if cursor is None:
            payload = self._request_json(
                context,
                "/changes/startPageToken",
                params={"supportsAllDrives": "true"},
            )
            return ConnectorPage(
                (),
                None,
                False,
                checkpoint_cursor=_required_string(payload, "startPageToken"),
            )

        payload = self._request_json(
            context,
            "/changes",
            params={
                "pageToken": cursor,
                "pageSize": "1000",
                "spaces": "drive",
                "includeRemoved": "true",
                "includeItemsFromAllDrives": "true",
                "supportsAllDrives": "true",
                "fields": (
                    "nextPageToken,newStartPageToken,changes("
                    "fileId,removed,time,file(id,mimeType,modifiedTime,trashed,version))"
                ),
            },
            cursor_request=True,
        )
        changes = tuple(_change_from_payload(item) for item in _list_of_objects(payload, "changes"))
        next_cursor = _optional_string(payload, "nextPageToken")
        checkpoint_cursor = _optional_string(payload, "newStartPageToken")
        has_more = next_cursor is not None
        if not has_more and checkpoint_cursor is None:
            raise ConnectorUnavailableError("The connector returned an incomplete change page")
        return ConnectorPage(
            changes,
            next_cursor,
            has_more,
            checkpoint_cursor=checkpoint_cursor,
        )

    def get_version(
        self, context: ConnectorContext, *, object_external_id: str
    ) -> ConnectorVersion:
        payload = self._file_metadata(context, object_external_id)
        version = _optional_string(payload, "version") or _required_string(
            payload, "modifiedTime"
        )
        size_value = payload.get("size")
        byte_size = int(size_value) if isinstance(size_value, str) else None
        return ConnectorVersion(
            object_external_id=_required_string(payload, "id"),
            version_external_id=version,
            content_sha256=None,
            byte_size=byte_size,
            modified_at=_parse_time(_required_string(payload, "modifiedTime")),
        )

    @contextmanager
    def open_content(
        self,
        context: ConnectorContext,
        *,
        object_external_id: str,
        version_external_id: str,
    ) -> Iterator[BinaryIO]:
        metadata = self._file_metadata(context, object_external_id)
        current_version = _optional_string(metadata, "version") or _required_string(
            metadata, "modifiedTime"
        )
        if current_version != version_external_id:
            raise ConnectorUnavailableError("The source version changed before download")
        capabilities = metadata.get("capabilities")
        if not isinstance(capabilities, dict) or capabilities.get("canDownload") is not True:
            raise ConnectorUnavailableError("The source content cannot be downloaded")
        media_type = _required_string(metadata, "mimeType")
        encoded_id = quote(object_external_id, safe="")
        if media_type.startswith(GOOGLE_NATIVE_PREFIX):
            path = f"/files/{encoded_id}/export"
            params = {"mimeType": GOOGLE_EXPORT_MEDIA_TYPE}
        else:
            path = f"/files/{encoded_id}"
            params = {"alt": "media"}
        content = self._request_bytes(context, path, params=params)
        if len(content) > self._max_download_bytes:
            raise ConnectorUnavailableError("The source content exceeds the configured limit")
        stream = BytesIO(content)
        try:
            yield stream
        finally:
            stream.close()

    def get_permissions(
        self, context: ConnectorContext, *, object_external_id: str
    ) -> PermissionSnapshot:
        principals: list[Principal] = []
        page_token: str | None = None
        encoded_id = quote(object_external_id, safe="")
        while True:
            params = {
                "pageSize": "100",
                "supportsAllDrives": "true",
                "fields": (
                    "nextPageToken,permissions("
                    "id,type,role,deleted,permissionDetails(inherited))"
                ),
            }
            if page_token:
                params["pageToken"] = page_token
            payload = self._request_json(
                context, f"/files/{encoded_id}/permissions", params=params
            )
            principals.extend(
                _principal_from_permission(item)
                for item in _list_of_objects(payload, "permissions")
                if item.get("deleted") is not True
            )
            page_token = _optional_string(payload, "nextPageToken")
            if page_token is None:
                break
        ordered = tuple(
            sorted(
                principals,
                key=lambda item: (item.kind.value, item.external_id, item.role, item.inherited),
            )
        )
        fingerprint_payload = [
            [item.kind.value, item.external_id, item.role, item.inherited] for item in ordered
        ]
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, separators=(",", ":")).encode()
        ).hexdigest()
        return PermissionSnapshot(
            object_external_id=object_external_id,
            fingerprint=fingerprint,
            principals=ordered,
            observed_at=datetime.now().astimezone(),
        )

    def _file_metadata(
        self, context: ConnectorContext, object_external_id: str
    ) -> dict[str, Any]:
        return self._request_json(
            context,
            f"/files/{quote(object_external_id, safe='')}",
            params={
                "supportsAllDrives": "true",
                "fields": "id,mimeType,modifiedTime,version,size,capabilities(canDownload)",
            },
        )

    def _request_json(
        self,
        context: ConnectorContext,
        path: str,
        *,
        params: dict[str, str],
        cursor_request: bool = False,
    ) -> dict[str, Any]:
        response = self._request(context, path, params=params, cursor_request=cursor_request)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ConnectorUnavailableError("The connector returned an invalid response") from exc
        if not isinstance(payload, dict):
            raise ConnectorUnavailableError("The connector returned an invalid response")
        return cast(dict[str, Any], payload)

    def _request_bytes(
        self, context: ConnectorContext, path: str, *, params: dict[str, str]
    ) -> bytes:
        return self._request(context, path, params=params).content

    def _request(
        self,
        context: ConnectorContext,
        path: str,
        *,
        params: dict[str, str],
        cursor_request: bool = False,
    ) -> httpx.Response:
        try:
            with self._credentials.resolve(
                context.credential,
                workspace_id=context.workspace_id,
                connector_id=context.connector_id,
            ) as resolved:
                token = resolved.values["access_token"].get_secret_value()
                response = self._client.get(
                    f"{DRIVE_API_BASE}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
            response.raise_for_status()
            return response
        except KeyError as exc:
            raise ConnectorUnavailableError("The connector credential is unavailable") from exc
        except httpx.HTTPStatusError as exc:
            if cursor_request and exc.response.status_code == 410:
                raise ConnectorCursorExpiredError("The connector checkpoint expired") from None
            raise ConnectorUnavailableError("The connector is temporarily unavailable") from None
        except httpx.HTTPError:
            raise ConnectorUnavailableError("The connector is temporarily unavailable") from None


def _object_from_file(payload: dict[str, Any]) -> ConnectorObject:
    parents = payload.get("parents")
    parent = parents[0] if isinstance(parents, list) and parents and isinstance(parents[0], str) else None
    return ConnectorObject(
        external_id=_required_string(payload, "id"),
        name=_required_string(payload, "name"),
        media_type=_required_string(payload, "mimeType"),
        modified_at=_parse_time(_required_string(payload, "modifiedTime")),
        parent_external_id=parent,
    )


def _change_from_payload(payload: dict[str, Any]) -> ConnectorChange:
    file_id = _required_string(payload, "fileId")
    file_payload = payload.get("file")
    removed = payload.get("removed") is True
    trashed = isinstance(file_payload, dict) and file_payload.get("trashed") is True
    kind = ChangeKind.DELETE if removed or trashed else ChangeKind.UPSERT
    version = (
        _optional_string(cast(dict[str, Any], file_payload), "version")
        if isinstance(file_payload, dict)
        else None
    )
    observed = _optional_string(payload, "time")
    identity = json.dumps(
        [file_id, kind.value, version, observed], separators=(",", ":")
    ).encode()
    return ConnectorChange(
        sequence=hashlib.sha256(identity).hexdigest(),
        kind=kind,
        object_external_id=file_id,
        version_external_id=version,
        observed_at=_parse_time(observed) if observed else None,
    )


def _principal_from_permission(payload: dict[str, Any]) -> Principal:
    permission_type = _required_string(payload, "type")
    kind_map = {
        "user": PrincipalKind.USER,
        "group": PrincipalKind.GROUP,
        "domain": PrincipalKind.DOMAIN,
        "anyone": PrincipalKind.PUBLIC,
    }
    try:
        kind = kind_map[permission_type]
    except KeyError as exc:
        raise ConnectorUnavailableError("The connector returned an unsupported permission") from exc
    details = payload.get("permissionDetails")
    inherited = bool(
        isinstance(details, list)
        and any(isinstance(item, dict) and item.get("inherited") is True for item in details)
    )
    return Principal(
        kind=kind,
        external_id=_required_string(payload, "id"),
        role=_required_string(payload, "role"),
        inherited=inherited,
    )


def _list_of_objects(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ConnectorUnavailableError("The connector returned an invalid response")
    return cast(list[dict[str, Any]], value)


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ConnectorUnavailableError("The connector returned an incomplete response")
    return value


def _optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ConnectorUnavailableError("The connector returned an invalid response")
    return value


def _parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConnectorUnavailableError("The connector returned an invalid timestamp") from exc
