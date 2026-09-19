from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import BinaryIO, ContextManager, Protocol
from uuid import UUID

from backend.app.connectors.credentials import CredentialReference


class ConnectorError(Exception):
    """Base class for provider-neutral, non-disclosing connector failures."""


class ConnectorNotConfiguredError(ConnectorError):
    pass


class ConnectorUnavailableError(ConnectorError):
    pass


class ConnectorCursorExpiredError(ConnectorError):
    pass


class PrincipalKind(StrEnum):
    USER = "user"
    GROUP = "group"
    DOMAIN = "domain"
    TENANT = "tenant"
    PUBLIC = "public"


class ChangeKind(StrEnum):
    UPSERT = "upsert"
    PERMISSIONS = "permissions"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class ConnectorContext:
    workspace_id: UUID
    connector_id: UUID
    credential: CredentialReference

    def __post_init__(self) -> None:
        if self.credential.workspace_id != self.workspace_id:
            raise ValueError("Credential reference belongs to another workspace")
        if self.credential.connector_id != self.connector_id:
            raise ValueError("Credential reference belongs to another connector")


@dataclass(frozen=True, slots=True)
class Principal:
    kind: PrincipalKind
    external_id: str

    def __post_init__(self) -> None:
        if not self.external_id.strip():
            raise ValueError("Principal external identity must not be empty")


@dataclass(frozen=True, slots=True)
class PermissionSnapshot:
    object_external_id: str
    fingerprint: str
    principals: tuple[Principal, ...]
    observed_at: datetime

    def __post_init__(self) -> None:
        if not self.object_external_id.strip():
            raise ValueError("Permission object identity must not be empty")
        if len(self.fingerprint) != 64:
            raise ValueError("Permission fingerprint must be a SHA-256 hex digest")
        if len(set(self.principals)) != len(self.principals):
            raise ValueError("Permission principals must be unique")


@dataclass(frozen=True, slots=True)
class ConnectorObject:
    external_id: str
    name: str
    media_type: str
    modified_at: datetime
    parent_external_id: str | None = None


@dataclass(frozen=True, slots=True)
class ConnectorVersion:
    object_external_id: str
    version_external_id: str
    content_sha256: str | None
    byte_size: int | None
    modified_at: datetime


@dataclass(frozen=True, slots=True)
class ConnectorChange:
    sequence: str
    kind: ChangeKind
    object_external_id: str
    version_external_id: str | None = None
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RateLimitHint:
    retry_after_seconds: float | None = None
    remaining: int | None = None
    resets_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ConnectorPage:
    changes: tuple[ConnectorChange, ...]
    next_cursor: str | None
    has_more: bool
    rate_limit: RateLimitHint | None = None

    def __post_init__(self) -> None:
        if self.has_more and not self.next_cursor:
            raise ValueError("A non-terminal page requires an opaque next cursor")
        if not self.has_more and self.next_cursor is not None:
            raise ValueError("A terminal page must not expose a next cursor")


@dataclass(frozen=True, slots=True)
class ConnectorHealth:
    available: bool
    checked_at: datetime
    reason_code: str | None = None


class Connector(Protocol):
    kind: str

    def health(self, context: ConnectorContext) -> ConnectorHealth: ...

    def discover(self, context: ConnectorContext) -> Iterator[ConnectorObject]: ...

    def list_changes(
        self, context: ConnectorContext, *, cursor: str | None
    ) -> ConnectorPage: ...

    def get_version(
        self, context: ConnectorContext, *, object_external_id: str
    ) -> ConnectorVersion: ...

    def open_content(
        self,
        context: ConnectorContext,
        *,
        object_external_id: str,
        version_external_id: str,
    ) -> ContextManager[BinaryIO]: ...

    def get_permissions(
        self, context: ConnectorContext, *, object_external_id: str
    ) -> PermissionSnapshot: ...


class ConnectorRegistry:
    def __init__(self, connectors: Mapping[str, Connector] | None = None) -> None:
        self._connectors: dict[str, Connector] = {}
        for kind, connector in (connectors or {}).items():
            self.register(kind, connector)

    def register(self, kind: str, connector: Connector) -> None:
        normalized = kind.strip().lower()
        if not normalized:
            raise ValueError("Connector kind must not be empty")
        if connector.kind.strip().lower() != normalized:
            raise ValueError("Connector kind does not match its registry key")
        if normalized in self._connectors:
            raise ValueError("Connector kind is already registered")
        self._connectors[normalized] = connector

    def get(self, kind: str) -> Connector:
        connector = self._connectors.get(kind.strip().lower())
        if connector is None:
            raise ConnectorNotConfiguredError("The connector is not configured")
        return connector
