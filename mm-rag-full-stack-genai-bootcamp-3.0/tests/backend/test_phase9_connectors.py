from contextlib import contextmanager
from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

import pytest
from pydantic import SecretStr

from backend.app.connectors.base import (
    ConnectorContext,
    ConnectorNotConfiguredError,
    ConnectorPage,
    ConnectorRegistry,
)
from backend.app.connectors.credentials import (
    CredentialReference,
    CredentialState,
    ResolvedCredential,
)


def _reference(*, workspace_id=None, connector_id=None) -> CredentialReference:
    return CredentialReference(
        id=uuid4(),
        workspace_id=workspace_id or uuid4(),
        connector_id=connector_id or uuid4(),
        reference="vault://tenant/connectors/credential",
        granted_scopes=("content.read", "permissions.read"),
        state=CredentialState.ACTIVE,
    )


def test_connector_context_rejects_cross_tenant_credential_reference() -> None:
    reference = _reference()

    with pytest.raises(ValueError, match="another workspace"):
        ConnectorContext(uuid4(), reference.connector_id, reference)
    with pytest.raises(ValueError, match="another connector"):
        ConnectorContext(reference.workspace_id, uuid4(), reference)


def test_credential_contract_keeps_secret_values_redacted() -> None:
    resolved = ResolvedCredential({"access_token": SecretStr("never-display-me")})

    assert "never-display-me" not in repr(resolved)
    assert "**********" in repr(resolved)


@pytest.mark.parametrize(
    ("next_cursor", "has_more"),
    [(None, True), ("opaque-cursor", False)],
)
def test_change_page_requires_consistent_cursor_state(next_cursor, has_more) -> None:
    with pytest.raises(ValueError):
        ConnectorPage((), next_cursor, has_more)


class _FakeConnector:
    kind = "fake"

    def health(self, context):
        raise NotImplementedError

    def discover(self, context):
        return iter(())

    def list_changes(self, context, *, cursor):
        return ConnectorPage((), None, False)

    def get_version(self, context, *, object_external_id):
        raise NotImplementedError

    @contextmanager
    def open_content(self, context, *, object_external_id, version_external_id):
        yield BytesIO(b"")

    def get_permissions(self, context, *, object_external_id):
        raise NotImplementedError


def test_connector_registry_is_explicit_and_non_disclosing() -> None:
    connector = _FakeConnector()
    registry = ConnectorRegistry({"FAKE": connector})

    assert registry.get("fake") is connector
    with pytest.raises(ValueError, match="already registered"):
        registry.register("fake", connector)
    with pytest.raises(ConnectorNotConfiguredError, match="not configured"):
        registry.get("missing-provider")


def test_credential_reference_requires_unique_non_empty_scopes() -> None:
    with pytest.raises(ValueError, match="unique"):
        CredentialReference(
            id=uuid4(),
            workspace_id=uuid4(),
            connector_id=uuid4(),
            reference="vault://credential",
            granted_scopes=("read", "read"),
            state=CredentialState.ACTIVE,
            expires_at=datetime.now(UTC),
        )
