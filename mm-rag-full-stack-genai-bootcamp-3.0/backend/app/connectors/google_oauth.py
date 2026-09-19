from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from uuid import UUID

import httpx
from pydantic import SecretStr

from backend.app.connectors.credentials import (
    CredentialReference,
    CredentialState,
    ResolvedCredential,
)

GOOGLE_DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


class GoogleOAuthCredentialError(Exception):
    """Non-disclosing failure at the local Google OAuth credential boundary."""


@dataclass(frozen=True, slots=True)
class GoogleOAuthClientConfig:
    client_id: str
    client_secret: SecretStr

    @classmethod
    def load(cls, path: Path) -> GoogleOAuthClientConfig:
        payload = _read_private_json(path)
        installed = payload.get("installed")
        if not isinstance(installed, dict):
            raise GoogleOAuthCredentialError("A Google Desktop app client is required")
        client_id = installed.get("client_id")
        client_secret = installed.get("client_secret")
        if not isinstance(client_id, str) or not client_id:
            raise GoogleOAuthCredentialError("The Google OAuth client is invalid")
        if not isinstance(client_secret, str) or not client_secret:
            raise GoogleOAuthCredentialError("The Google OAuth client is invalid")
        return cls(client_id=client_id, client_secret=SecretStr(client_secret))


@dataclass(frozen=True, slots=True)
class GoogleOAuthToken:
    refresh_token: SecretStr
    access_token: SecretStr | None
    expires_at: datetime | None
    scopes: tuple[str, ...]


class GoogleTokenStore:
    def load(self, reference: str) -> GoogleOAuthToken:
        path = _file_reference_path(reference)
        payload = _read_private_json(path)
        refresh_token = payload.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise GoogleOAuthCredentialError("The Google OAuth credential is incomplete")
        access_token = payload.get("access_token")
        expires_value = payload.get("expires_at")
        scopes = payload.get("scopes")
        if access_token is not None and not isinstance(access_token, str):
            raise GoogleOAuthCredentialError("The Google OAuth credential is invalid")
        if not isinstance(scopes, list) or any(not isinstance(item, str) for item in scopes):
            raise GoogleOAuthCredentialError("The Google OAuth credential is invalid")
        expires_at = _parse_time(expires_value) if isinstance(expires_value, str) else None
        return GoogleOAuthToken(
            refresh_token=SecretStr(refresh_token),
            access_token=SecretStr(access_token) if access_token else None,
            expires_at=expires_at,
            scopes=tuple(scopes),
        )

    def save(self, reference: str, token: GoogleOAuthToken) -> None:
        path = _file_reference_path(reference)
        payload = {
            "refresh_token": token.refresh_token.get_secret_value(),
            "access_token": (token.access_token.get_secret_value() if token.access_token else None),
            "expires_at": token.expires_at.isoformat() if token.expires_at else None,
            "scopes": list(token.scopes),
        }
        _write_private_json(path, payload)


class GoogleDriveFileCredentialResolver:
    """Resolve and refresh a local learning credential without durable secret exposure."""

    def __init__(
        self,
        client_config_path: Path,
        *,
        store: GoogleTokenStore | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._client_config = GoogleOAuthClientConfig.load(client_config_path)
        self._store = store or GoogleTokenStore()
        self._client = client or httpx.Client(timeout=15.0, follow_redirects=False)

    @contextmanager
    def resolve(
        self,
        reference: CredentialReference,
        *,
        workspace_id: UUID,
        connector_id: UUID,
    ) -> Iterator[ResolvedCredential]:
        if reference.workspace_id != workspace_id or reference.connector_id != connector_id:
            raise GoogleOAuthCredentialError("The connector credential scope is invalid")
        if reference.state is not CredentialState.ACTIVE:
            raise GoogleOAuthCredentialError("The connector credential is not active")
        if GOOGLE_DRIVE_READONLY_SCOPE not in reference.granted_scopes:
            raise GoogleOAuthCredentialError("The required connector scope is unavailable")
        token = self._store.load(reference.reference)
        if GOOGLE_DRIVE_READONLY_SCOPE not in token.scopes:
            raise GoogleOAuthCredentialError("The required connector scope is unavailable")
        if not _access_token_is_fresh(token):
            token = self._refresh(reference.reference, token)
        if token.access_token is None:
            raise GoogleOAuthCredentialError("The Google OAuth credential is unavailable")
        yield ResolvedCredential({"access_token": token.access_token})

    def _refresh(self, reference: str, token: GoogleOAuthToken) -> GoogleOAuthToken:
        try:
            response = self._client.post(
                GOOGLE_TOKEN_ENDPOINT,
                data={
                    "client_id": self._client_config.client_id,
                    "client_secret": self._client_config.client_secret.get_secret_value(),
                    "refresh_token": token.refresh_token.get_secret_value(),
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            payload = response.json()
            access_token = payload["access_token"]
            expires_in = int(payload["expires_in"])
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise GoogleOAuthCredentialError(
                "The Google OAuth credential could not be refreshed"
            ) from exc
        if not isinstance(access_token, str) or not access_token or expires_in <= 0:
            raise GoogleOAuthCredentialError("The Google OAuth refresh response is invalid")
        refreshed = GoogleOAuthToken(
            refresh_token=token.refresh_token,
            access_token=SecretStr(access_token),
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
            scopes=token.scopes,
        )
        self._store.save(reference, refreshed)
        return refreshed


def save_google_token(reference: str, payload: dict[str, Any]) -> None:
    refresh_token = payload.get("refresh_token")
    access_token = payload.get("access_token")
    expires_in = payload.get("expires_in")
    scope = payload.get("scope")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise GoogleOAuthCredentialError("Google did not issue a refresh token")
    if not isinstance(access_token, str) or not access_token:
        raise GoogleOAuthCredentialError("Google did not issue an access token")
    if not isinstance(expires_in, (int, str)):
        raise GoogleOAuthCredentialError("Google returned an invalid token lifetime")
    try:
        lifetime = int(expires_in)
    except ValueError as exc:
        raise GoogleOAuthCredentialError("Google returned an invalid token lifetime") from exc
    scopes = tuple(sorted(str(scope or "").split()))
    if GOOGLE_DRIVE_READONLY_SCOPE not in scopes:
        raise GoogleOAuthCredentialError("Google did not grant the required Drive scope")
    GoogleTokenStore().save(
        reference,
        GoogleOAuthToken(
            refresh_token=SecretStr(refresh_token),
            access_token=SecretStr(access_token),
            expires_at=datetime.now(UTC) + timedelta(seconds=lifetime),
            scopes=scopes,
        ),
    )


def _access_token_is_fresh(token: GoogleOAuthToken) -> bool:
    return (
        token.access_token is not None
        and token.expires_at is not None
        and token.expires_at > datetime.now(UTC) + timedelta(seconds=60)
    )


def _file_reference_path(reference: str) -> Path:
    parsed = urlparse(reference)
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
        raise GoogleOAuthCredentialError("The credential reference is unsupported")
    path = Path(unquote(parsed.path)).resolve()
    if not path.is_absolute():
        raise GoogleOAuthCredentialError("The credential reference is invalid")
    return path


def _read_private_json(path: Path) -> dict[str, Any]:
    try:
        mode = path.stat().st_mode & 0o777
        if mode & 0o077:
            raise GoogleOAuthCredentialError("The credential file permissions are unsafe")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except GoogleOAuthCredentialError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise GoogleOAuthCredentialError("The credential file is unavailable") from exc
    if not isinstance(payload, dict):
        raise GoogleOAuthCredentialError("The credential file is invalid")
    return payload


def _write_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise GoogleOAuthCredentialError("The credential expiry is invalid") from exc
    if parsed.tzinfo is None:
        raise GoogleOAuthCredentialError("The credential expiry is invalid")
    return parsed.astimezone(UTC)
