import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from backend.app.connectors.credentials import CredentialReference, CredentialState
from backend.app.connectors.google_oauth import (
    GOOGLE_DRIVE_READONLY_SCOPE,
    GoogleDriveFileCredentialResolver,
    GoogleOAuthClientConfig,
    GoogleOAuthCredentialError,
    GoogleOAuthToken,
    GoogleTokenStore,
)
from scripts.google_drive_oauth import authorization_url, exchange_code


def _private_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)
    return path


def _client_config(path: Path) -> Path:
    return _private_json(
        path,
        {"installed": {"client_id": "client-id", "client_secret": "client-secret"}},
    )


def test_client_config_requires_private_desktop_credential(tmp_path: Path) -> None:
    path = _client_config(tmp_path / "client.json")
    config = GoogleOAuthClientConfig.load(path)

    assert config.client_id == "client-id"
    assert "client-secret" not in repr(config)
    path.chmod(0o644)
    with pytest.raises(GoogleOAuthCredentialError, match="permissions are unsafe"):
        GoogleOAuthClientConfig.load(path)


def test_token_store_writes_mode_0600_and_redacts_values(tmp_path: Path) -> None:
    path = tmp_path / "credentials" / "token.json"
    reference = path.resolve().as_uri()
    token = GoogleOAuthToken(
        refresh_token=SecretStr("refresh-secret"),
        access_token=SecretStr("access-secret"),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        scopes=(GOOGLE_DRIVE_READONLY_SCOPE,),
    )

    GoogleTokenStore().save(reference, token)
    restored = GoogleTokenStore().load(reference)

    assert path.stat().st_mode & 0o777 == 0o600
    assert restored.refresh_token.get_secret_value() == "refresh-secret"
    assert "refresh-secret" not in repr(restored)


def test_resolver_refreshes_expired_token_without_exposing_secrets(tmp_path: Path) -> None:
    client_path = _client_config(tmp_path / "client.json")
    token_path = tmp_path / "token.json"
    reference_uri = token_path.resolve().as_uri()
    GoogleTokenStore().save(
        reference_uri,
        GoogleOAuthToken(
            refresh_token=SecretStr("refresh-secret"),
            access_token=None,
            expires_at=None,
            scopes=(GOOGLE_DRIVE_READONLY_SCOPE,),
        ),
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"access_token": "new-access", "expires_in": 3600})

    resolver = GoogleDriveFileCredentialResolver(
        client_path, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    workspace_id, connector_id = uuid4(), uuid4()
    reference = CredentialReference(
        id=uuid4(),
        workspace_id=workspace_id,
        connector_id=connector_id,
        reference=reference_uri,
        granted_scopes=(GOOGLE_DRIVE_READONLY_SCOPE,),
        state=CredentialState.ACTIVE,
    )

    with resolver.resolve(
        reference, workspace_id=workspace_id, connector_id=connector_id
    ) as credential:
        assert credential.values["access_token"].get_secret_value() == "new-access"
        assert "new-access" not in repr(credential)
    assert len(requests) == 1
    stored = GoogleTokenStore().load(reference_uri)
    assert stored.access_token is not None
    assert stored.access_token.get_secret_value() == "new-access"


def test_authorization_url_uses_pkce_state_and_read_only_scope() -> None:
    url = authorization_url(
        client_id="client-id",
        redirect_uri="http://127.0.0.1:1234/oauth2callback",
        state="state-value",
        code_challenge="challenge-value",
    )

    assert "drive.readonly" in url
    assert "state=state-value" in url
    assert "code_challenge=challenge-value" in url
    assert "code_challenge_method=S256" in url
    assert "access_type=offline" in url


def test_code_exchange_uses_verifier_and_rejects_provider_details() -> None:
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, json={"access_token": "access", "refresh_token": "refresh"})

    payload = exchange_code(
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        config=GoogleOAuthClientConfig("client", SecretStr("secret")),
        code="authorization-code",
        code_verifier="verifier",
        redirect_uri="http://127.0.0.1:1234/oauth2callback",
    )

    assert payload["refresh_token"] == "refresh"
    assert b"code_verifier=verifier" in observed[0].content

    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error_description": "provider-secret-detail"})

    with pytest.raises(GoogleOAuthCredentialError) as raised:
        exchange_code(
            client=httpx.Client(transport=httpx.MockTransport(failing_handler)),
            config=GoogleOAuthClientConfig("client", SecretStr("secret")),
            code="bad-code",
            code_verifier="verifier",
            redirect_uri="http://127.0.0.1:1234/oauth2callback",
        )
    assert "provider-secret-detail" not in str(raised.value)
