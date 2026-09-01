from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.models.access import ResourceACLGrant, ResourceVisibility
from backend.app.models.conversation import Conversation
from backend.app.models.document import Collection, Document
from backend.app.models.user import User
from backend.app.repositories.access import ResourceACLRepository
from backend.app.repositories.conversations import ConversationRepository
from backend.app.repositories.documents import CollectionRepository, DocumentRepository
from backend.app.repositories.workspaces import WorkspaceRepository
from backend.app.services.audit import record_audit_event
from backend.app.services.policy import (
    POLICY_REVISION,
    PolicyAction,
    PolicyDeniedError,
    PolicyNotFoundError,
    PolicyService,
    ResourceContext,
    ResourceType,
    resource_context,
)


class AccessControlError(Exception):
    pass


class AccessResourceNotFoundError(AccessControlError):
    pass


class AccessPermissionDeniedError(AccessControlError):
    pass


class AccessPrincipalNotFoundError(AccessControlError):
    pass


class AccessControlService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._policy = PolicyService(session)
        self._grants = ResourceACLRepository(session)
        self._workspaces = WorkspaceRepository(session)
        self._documents = DocumentRepository(session)
        self._collections = CollectionRepository(session)
        self._conversations = ConversationRepository(session)

    def get_access(
        self,
        *,
        user: User,
        workspace_id: UUID,
        resource_type: ResourceType,
        resource_id: UUID,
    ) -> tuple[ResourceContext, list[ResourceACLGrant]]:
        context = self._load_context(workspace_id, resource_type, resource_id)
        self._require(
            user=user,
            workspace_id=workspace_id,
            action=PolicyAction.POLICY_INSPECT,
            resource=context,
        )
        return context, self._grants.list_grants(
            workspace_id=workspace_id,
            resource_type=resource_type.value,
            resource_id=resource_id,
        )

    def set_visibility(
        self,
        *,
        user: User,
        workspace_id: UUID,
        resource_type: ResourceType,
        resource_id: UUID,
        visibility: ResourceVisibility,
    ) -> tuple[ResourceContext, list[ResourceACLGrant]]:
        with self._session.begin():
            resource = self._load_resource(workspace_id, resource_type, resource_id)
            context = resource_context(resource)
            self._require(
                user=user,
                workspace_id=workspace_id,
                action=PolicyAction.ACL_UPDATE,
                resource=context,
            )
            previous = resource.visibility
            resource.visibility = visibility.value
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="policy.visibility_updated",
                resource_type=resource_type.value,
                resource_id=resource_id,
                details={
                    "previous_visibility": previous,
                    "visibility": visibility.value,
                    "policy_revision": POLICY_REVISION,
                },
            )
        return self.get_access(
            user=user,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )

    def grant(
        self,
        *,
        user: User,
        workspace_id: UUID,
        resource_type: ResourceType,
        resource_id: UUID,
        principal_user_id: UUID,
    ) -> tuple[ResourceContext, list[ResourceACLGrant]]:
        with self._session.begin():
            context = self._load_context(workspace_id, resource_type, resource_id)
            self._require(
                user=user,
                workspace_id=workspace_id,
                action=PolicyAction.ACL_UPDATE,
                resource=context,
            )
            if self._workspaces.get_for_user(workspace_id, principal_user_id) is None:
                raise AccessPrincipalNotFoundError
            if not self._grants.has_grant(
                workspace_id=workspace_id,
                resource_type=resource_type.value,
                resource_id=resource_id,
                principal_user_id=principal_user_id,
            ):
                self._grants.add_grant(
                    workspace_id=workspace_id,
                    resource_type=resource_type.value,
                    resource_id=resource_id,
                    principal_user_id=principal_user_id,
                    granted_by_user_id=user.id,
                )
                record_audit_event(
                    self._session,
                    workspace_id=workspace_id,
                    actor_user_id=user.id,
                    action="policy.acl_granted",
                    resource_type=resource_type.value,
                    resource_id=resource_id,
                    details={
                        "principal_user_id": str(principal_user_id),
                        "policy_revision": POLICY_REVISION,
                    },
                )
        return self.get_access(
            user=user,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )

    def revoke(
        self,
        *,
        user: User,
        workspace_id: UUID,
        resource_type: ResourceType,
        resource_id: UUID,
        principal_user_id: UUID,
    ) -> tuple[ResourceContext, list[ResourceACLGrant]]:
        with self._session.begin():
            context = self._load_context(workspace_id, resource_type, resource_id)
            self._require(
                user=user,
                workspace_id=workspace_id,
                action=PolicyAction.ACL_UPDATE,
                resource=context,
            )
            if self._grants.remove_grant(
                workspace_id=workspace_id,
                resource_type=resource_type.value,
                resource_id=resource_id,
                principal_user_id=principal_user_id,
            ):
                record_audit_event(
                    self._session,
                    workspace_id=workspace_id,
                    actor_user_id=user.id,
                    action="policy.acl_revoked",
                    resource_type=resource_type.value,
                    resource_id=resource_id,
                    details={
                        "principal_user_id": str(principal_user_id),
                        "policy_revision": POLICY_REVISION,
                    },
                )
        return self.get_access(
            user=user,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )

    def _load_context(
        self, workspace_id: UUID, resource_type: ResourceType, resource_id: UUID
    ) -> ResourceContext:
        return resource_context(self._load_resource(workspace_id, resource_type, resource_id))

    def _load_resource(
        self, workspace_id: UUID, resource_type: ResourceType, resource_id: UUID
    ) -> Document | Collection | Conversation:
        resource: Document | Collection | Conversation | None
        if resource_type == ResourceType.DOCUMENT:
            resource = self._documents.get_document(workspace_id, resource_id)
        elif resource_type == ResourceType.COLLECTION:
            resource = self._collections.get_collection(workspace_id, resource_id)
        else:
            resource = self._conversations.get(workspace_id, resource_id)
        if resource is None:
            raise AccessResourceNotFoundError
        return resource

    @staticmethod
    def _translate_policy(exc: Exception) -> AccessControlError:
        if isinstance(exc, PolicyNotFoundError):
            return AccessResourceNotFoundError()
        return AccessPermissionDeniedError()

    def _require(self, **kwargs) -> None:
        try:
            self._policy.require(**kwargs)
        except (PolicyNotFoundError, PolicyDeniedError) as exc:
            raise self._translate_policy(exc) from exc
