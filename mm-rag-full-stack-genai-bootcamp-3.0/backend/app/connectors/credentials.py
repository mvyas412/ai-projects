from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import ContextManager, Protocol
from uuid import UUID

from pydantic import SecretStr


class CredentialState(StrEnum):
    ACTIVE = "active"
    ROTATION_REQUIRED = "rotation_required"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class CredentialReference:
    """Opaque metadata only; secret material is resolved at execution time."""

    id: UUID
    workspace_id: UUID
    connector_id: UUID
    reference: str
    granted_scopes: tuple[str, ...]
    state: CredentialState
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.reference.strip():
            raise ValueError("Credential reference must not be empty")
        if any(not scope.strip() for scope in self.granted_scopes):
            raise ValueError("Credential scopes must not be empty")
        if len(set(self.granted_scopes)) != len(self.granted_scopes):
            raise ValueError("Credential scopes must be unique")


@dataclass(frozen=True, slots=True)
class ResolvedCredential:
    """Short-lived secret values whose repr remains redacted by SecretStr."""

    values: Mapping[str, SecretStr]

    def __post_init__(self) -> None:
        if not self.values or any(not key.strip() for key in self.values):
            raise ValueError("Resolved credential values require named entries")


class CredentialResolver(Protocol):
    def resolve(
        self,
        reference: CredentialReference,
        *,
        workspace_id: UUID,
        connector_id: UUID,
    ) -> ContextManager[ResolvedCredential]: ...
