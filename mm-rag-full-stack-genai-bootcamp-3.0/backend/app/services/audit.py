from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.audit import AuditEvent
from backend.app.models.user import User
from backend.app.services.policy import PolicyAction, PolicyNotFoundError, PolicyService


class AuditNotFoundError(Exception):
    pass


def record_audit_event(
    session: Session,
    *,
    workspace_id: UUID,
    actor_user_id: UUID,
    action: str,
    resource_type: str,
    resource_id: UUID | None,
    details: dict[str, object] | None = None,
) -> None:
    session.add(
        AuditEvent(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
        )
    )


class AuditService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._policy = PolicyService(session)

    def list_events(
        self, *, user: User, workspace_id: UUID, limit: int
    ) -> list[tuple[AuditEvent, User]]:
        try:
            self._policy.require(
                user=user,
                workspace_id=workspace_id,
                action=PolicyAction.ACTIVITY_READ,
            )
        except PolicyNotFoundError:
            raise AuditNotFoundError
        statement = (
            select(AuditEvent, User)
            .join(User, User.id == AuditEvent.actor_user_id)
            .where(AuditEvent.workspace_id == workspace_id)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit)
        )
        return [(row[0], row[1]) for row in self._session.execute(statement).all()]
