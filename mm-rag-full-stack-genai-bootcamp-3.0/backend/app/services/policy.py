from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.db.rls import DatabasePurpose, set_rls_context
from backend.app.models.access import ResourceVisibility
from backend.app.models.user import User
from backend.app.models.workspace import WorkspaceRole
from backend.app.repositories.access import ResourceACLRepository
from backend.app.repositories.workspaces import WorkspaceRepository

POLICY_REVISION = "phase4-v1"


class PolicyAction(StrEnum):
    WORKSPACE_VIEW = "workspace.view"
    WORKSPACE_SETTINGS_UPDATE = "workspace.settings.update"
    WORKSPACE_MEMBERS_MANAGE = "workspace.members.manage"
    WORKSPACE_TRANSFER = "workspace.transfer"
    WORKSPACE_PURGE = "workspace.purge"
    POLICY_INSPECT = "policy.inspect"
    ACL_UPDATE = "acl.update"
    DOCUMENT_CREATE = "document.create"
    DOCUMENT_READ = "document.read"
    DOCUMENT_DOWNLOAD = "document.download"
    DOCUMENT_VERSION_CREATE = "document.version.create"
    DOCUMENT_INDEX = "document.index"
    DOCUMENT_ARCHIVE = "document.archive"
    DOCUMENT_RESTORE = "document.restore"
    DOCUMENT_PURGE = "document.purge"
    COLLECTION_CREATE = "collection.create"
    COLLECTION_READ = "collection.read"
    COLLECTION_MEMBERSHIP_UPDATE = "collection.membership.update"
    COLLECTION_ARCHIVE = "collection.archive"
    COLLECTION_RESTORE = "collection.restore"
    CONVERSATION_CREATE = "conversation.create"
    CONVERSATION_READ = "conversation.read"
    CONVERSATION_MESSAGE_CREATE = "conversation.message.create"
    CONVERSATION_EXPORT = "conversation.export"
    CONVERSATION_UPDATE = "conversation.update"
    CONVERSATION_DELETE = "conversation.delete"
    JOB_READ = "job.read"
    JOB_CANCEL = "job.cancel"
    JOB_RETRY = "job.retry"
    ACTIVITY_READ = "activity.read"
    SECURITY_AUDIT_READ = "security.audit.read"
    SECURITY_EXPORT_CREATE = "security.export.create"
    RETENTION_PREVIEW = "retention.preview"
    RETENTION_APPLY = "retention.apply"


class ResourceType(StrEnum):
    DOCUMENT = "document"
    COLLECTION = "collection"
    CONVERSATION = "conversation"


class GovernedResource(Protocol):
    id: UUID
    workspace_id: UUID
    created_by_user_id: UUID
    visibility: str


@dataclass(frozen=True, slots=True)
class ResourceContext:
    workspace_id: UUID
    resource_type: ResourceType
    resource_id: UUID
    created_by_user_id: UUID
    visibility: ResourceVisibility
    tombstoned: bool = False


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    discoverable: bool
    policy_revision: str
    reason: str
    role: WorkspaceRole | None = None


class PolicyNotFoundError(Exception):
    pass


class PolicyDeniedError(Exception):
    pass


_OWNER_ONLY = frozenset(
    {
        PolicyAction.WORKSPACE_TRANSFER,
        PolicyAction.WORKSPACE_PURGE,
        PolicyAction.DOCUMENT_PURGE,
        PolicyAction.RETENTION_APPLY,
    }
)
_ADMIN_ACTIONS = frozenset(
    {
        PolicyAction.WORKSPACE_SETTINGS_UPDATE,
        PolicyAction.WORKSPACE_MEMBERS_MANAGE,
        PolicyAction.POLICY_INSPECT,
        PolicyAction.ACL_UPDATE,
        PolicyAction.DOCUMENT_ARCHIVE,
        PolicyAction.DOCUMENT_RESTORE,
        PolicyAction.COLLECTION_ARCHIVE,
        PolicyAction.COLLECTION_RESTORE,
        PolicyAction.SECURITY_AUDIT_READ,
        PolicyAction.SECURITY_EXPORT_CREATE,
        PolicyAction.RETENTION_PREVIEW,
    }
)
_MEMBER_ACTIONS = frozenset(
    {
        PolicyAction.WORKSPACE_VIEW,
        PolicyAction.POLICY_INSPECT,
        PolicyAction.DOCUMENT_CREATE,
        PolicyAction.DOCUMENT_READ,
        PolicyAction.DOCUMENT_DOWNLOAD,
        PolicyAction.DOCUMENT_VERSION_CREATE,
        PolicyAction.DOCUMENT_INDEX,
        PolicyAction.COLLECTION_CREATE,
        PolicyAction.COLLECTION_READ,
        PolicyAction.COLLECTION_MEMBERSHIP_UPDATE,
        PolicyAction.CONVERSATION_CREATE,
        PolicyAction.CONVERSATION_READ,
        PolicyAction.CONVERSATION_MESSAGE_CREATE,
        PolicyAction.CONVERSATION_EXPORT,
        PolicyAction.CONVERSATION_UPDATE,
        PolicyAction.CONVERSATION_DELETE,
        PolicyAction.JOB_READ,
        PolicyAction.JOB_CANCEL,
        PolicyAction.JOB_RETRY,
        PolicyAction.ACTIVITY_READ,
    }
)
_VIEWER_ACTIONS = frozenset(
    {
        PolicyAction.WORKSPACE_VIEW,
        PolicyAction.POLICY_INSPECT,
        PolicyAction.DOCUMENT_READ,
        PolicyAction.DOCUMENT_DOWNLOAD,
        PolicyAction.COLLECTION_READ,
        PolicyAction.CONVERSATION_CREATE,
        PolicyAction.CONVERSATION_READ,
        PolicyAction.CONVERSATION_MESSAGE_CREATE,
        PolicyAction.CONVERSATION_EXPORT,
        PolicyAction.CONVERSATION_UPDATE,
        PolicyAction.CONVERSATION_DELETE,
        PolicyAction.JOB_READ,
        PolicyAction.ACTIVITY_READ,
    }
)


class PolicyService:
    """Evaluate the accepted Phase 4 role ceiling and resource visibility contract."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._workspaces = WorkspaceRepository(session)
        self._grants = ResourceACLRepository(session)

    def evaluate(
        self,
        *,
        user: User,
        workspace_id: UUID,
        action: PolicyAction | str,
        resource: ResourceContext | None = None,
        requester_user_id: UUID | None = None,
    ) -> PolicyDecision:
        try:
            normalized_action = PolicyAction(action)
        except ValueError:
            return self._deny(False, "unknown_action")

        membership = self._workspaces.get_for_user(workspace_id, user.id)
        if membership is None:
            return self._deny(False, "workspace_membership_required")
        role = membership[1]

        if resource is not None and resource.workspace_id != workspace_id:
            return self._deny(False, "resource_workspace_mismatch", role)
        if resource is not None and resource.tombstoned:
            return self._deny(False, "resource_tombstoned", role)

        visible = resource is None or self._is_visible(user, role, resource)
        if not visible:
            return self._deny(False, "resource_not_visible", role)

        if normalized_action in _OWNER_ONLY:
            allowed = role == WorkspaceRole.OWNER
        elif role in {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}:
            allowed = True
        elif normalized_action == PolicyAction.ACL_UPDATE:
            allowed = self._creator_can_manage(user, role, resource)
        elif role == WorkspaceRole.MEMBER:
            allowed = normalized_action in _MEMBER_ACTIONS
        else:
            allowed = normalized_action in _VIEWER_ACTIONS

        if (
            normalized_action in {PolicyAction.JOB_CANCEL, PolicyAction.JOB_RETRY}
            and role not in {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}
        ):
            allowed = allowed and role == WorkspaceRole.MEMBER and requester_user_id == user.id

        if not allowed:
            return self._deny(True, "role_ceiling", role)
        return PolicyDecision(True, True, POLICY_REVISION, "allowed", role)

    def require(
        self,
        *,
        user: User,
        workspace_id: UUID,
        action: PolicyAction | str,
        resource: ResourceContext | None = None,
        requester_user_id: UUID | None = None,
    ) -> PolicyDecision:
        decision = self.evaluate(
            user=user,
            workspace_id=workspace_id,
            action=action,
            resource=resource,
            requester_user_id=requester_user_id,
        )
        if decision.allowed:
            set_rls_context(
                self._session,
                purpose=DatabasePurpose.API,
                workspace_id=workspace_id,
                principal_id=user.id,
            )
            return decision
        if decision.discoverable:
            raise PolicyDeniedError
        raise PolicyNotFoundError

    def can_read(self, *, user: User, resource: ResourceContext) -> bool:
        action = {
            ResourceType.DOCUMENT: PolicyAction.DOCUMENT_READ,
            ResourceType.COLLECTION: PolicyAction.COLLECTION_READ,
            ResourceType.CONVERSATION: PolicyAction.CONVERSATION_READ,
        }[resource.resource_type]
        return self.evaluate(
            user=user,
            workspace_id=resource.workspace_id,
            action=action,
            resource=resource,
        ).allowed

    def _is_visible(
        self, user: User, role: WorkspaceRole, resource: ResourceContext
    ) -> bool:
        if role in {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}:
            return True
        if resource.visibility == ResourceVisibility.WORKSPACE:
            return True
        if resource.created_by_user_id == user.id:
            return True
        return self._grants.has_grant(
            workspace_id=resource.workspace_id,
            resource_type=resource.resource_type.value,
            resource_id=resource.resource_id,
            principal_user_id=user.id,
        )

    @staticmethod
    def _creator_can_manage(
        user: User, role: WorkspaceRole, resource: ResourceContext | None
    ) -> bool:
        if resource is None or resource.created_by_user_id != user.id:
            return False
        if resource.resource_type == ResourceType.CONVERSATION:
            return role in {WorkspaceRole.MEMBER, WorkspaceRole.VIEWER}
        return role == WorkspaceRole.MEMBER

    @staticmethod
    def _deny(
        discoverable: bool, reason: str, role: WorkspaceRole | None = None
    ) -> PolicyDecision:
        return PolicyDecision(False, discoverable, POLICY_REVISION, reason, role)


def resource_context(resource: GovernedResource) -> ResourceContext:
    resource_type = ResourceType(resource.__class__.__name__.lower())
    return ResourceContext(
        workspace_id=resource.workspace_id,
        resource_type=resource_type,
        resource_id=resource.id,
        created_by_user_id=resource.created_by_user_id,
        visibility=ResourceVisibility(resource.visibility),
        tombstoned=getattr(resource, "tombstoned_at", None) is not None,
    )
