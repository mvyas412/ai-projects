from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.access import ResourceACLGrant


class ResourceACLRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _resource_field(resource_type: str):
        fields = {
            "document": ResourceACLGrant.document_id,
            "collection": ResourceACLGrant.collection_id,
            "conversation": ResourceACLGrant.conversation_id,
        }
        try:
            return fields[resource_type]
        except KeyError as exc:
            raise ValueError("Unsupported ACL resource type") from exc

    def has_grant(
        self,
        *,
        workspace_id: UUID,
        resource_type: str,
        resource_id: UUID,
        principal_user_id: UUID,
    ) -> bool:
        field = self._resource_field(resource_type)
        return (
            self._session.scalar(
                select(ResourceACLGrant.id).where(
                    ResourceACLGrant.workspace_id == workspace_id,
                    field == resource_id,
                    ResourceACLGrant.principal_user_id == principal_user_id,
                )
            )
            is not None
        )

    def list_grants(
        self, *, workspace_id: UUID, resource_type: str, resource_id: UUID
    ) -> list[ResourceACLGrant]:
        field = self._resource_field(resource_type)
        return list(
            self._session.scalars(
                select(ResourceACLGrant)
                .where(
                    ResourceACLGrant.workspace_id == workspace_id,
                    field == resource_id,
                )
                .order_by(ResourceACLGrant.created_at, ResourceACLGrant.id)
            )
        )

    def add_grant(
        self,
        *,
        workspace_id: UUID,
        resource_type: str,
        resource_id: UUID,
        principal_user_id: UUID,
        granted_by_user_id: UUID,
    ) -> ResourceACLGrant:
        values: dict[str, UUID] = {
            "workspace_id": workspace_id,
            "principal_user_id": principal_user_id,
            "granted_by_user_id": granted_by_user_id,
            f"{resource_type}_id": resource_id,
        }
        grant = ResourceACLGrant(**values)
        self._session.add(grant)
        self._session.flush()
        return grant

    def remove_grant(
        self,
        *,
        workspace_id: UUID,
        resource_type: str,
        resource_id: UUID,
        principal_user_id: UUID,
    ) -> bool:
        field = self._resource_field(resource_type)
        grant = self._session.scalar(
            select(ResourceACLGrant).where(
                ResourceACLGrant.workspace_id == workspace_id,
                field == resource_id,
                ResourceACLGrant.principal_user_id == principal_user_id,
            )
        )
        if grant is None:
            return False
        self._session.delete(grant)
        return True
