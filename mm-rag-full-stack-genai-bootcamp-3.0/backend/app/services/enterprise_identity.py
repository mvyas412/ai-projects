from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.enterprise import EnterpriseGroupMapping, EnterpriseIdentity
from backend.app.models.user import User

ALLOWED_GROUP_ROLES = frozenset({"admin", "member", "viewer"})


class EnterpriseIdentityError(Exception):
    """Base class for non-disclosing enterprise identity failures."""


class EnterpriseIdentityConflictError(EnterpriseIdentityError):
    pass


class EnterpriseIdentityService:
    """Apply ordered SCIM-compatible lifecycle records without trusting provider roles."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def apply_user(
        self,
        *,
        workspace_id: UUID,
        user: User,
        provider: str,
        external_id: str,
        sequence: int,
        active: bool,
    ) -> EnterpriseIdentity:
        identity = self._session.scalar(
            select(EnterpriseIdentity)
            .where(
                EnterpriseIdentity.workspace_id == workspace_id,
                EnterpriseIdentity.provider == provider,
                EnterpriseIdentity.external_id == external_id,
            )
            .with_for_update()
        )
        if identity is not None and sequence < identity.sequence:
            raise EnterpriseIdentityConflictError("The identity event is stale")
        if identity is None:
            identity = EnterpriseIdentity(
                workspace_id=workspace_id,
                user_id=user.id,
                provider=provider,
                external_id=external_id,
                sequence=sequence,
            )
            self._session.add(identity)
        elif identity.user_id != user.id:
            raise EnterpriseIdentityConflictError("The identity mapping conflicts")
        identity.sequence = sequence
        identity.state = "active" if active else "suspended"
        self._session.flush()
        return identity

    def map_group(
        self,
        *,
        workspace_id: UUID,
        provider: str,
        external_group_id: str,
        role: str,
        enabled: bool = True,
    ) -> EnterpriseGroupMapping:
        if role not in ALLOWED_GROUP_ROLES:
            raise EnterpriseIdentityConflictError("The requested group role is not allowed")
        mapping = self._session.scalar(
            select(EnterpriseGroupMapping)
            .where(
                EnterpriseGroupMapping.workspace_id == workspace_id,
                EnterpriseGroupMapping.provider == provider,
                EnterpriseGroupMapping.external_group_id == external_group_id,
            )
            .with_for_update()
        )
        if mapping is None:
            mapping = EnterpriseGroupMapping(
                workspace_id=workspace_id,
                provider=provider,
                external_group_id=external_group_id,
                role=role,
                enabled=enabled,
            )
            self._session.add(mapping)
        else:
            mapping.role = role
            mapping.enabled = enabled
        self._session.flush()
        return mapping
