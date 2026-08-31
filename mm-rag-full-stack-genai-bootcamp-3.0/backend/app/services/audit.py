from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import BinaryIO, ContextManager
from uuid import UUID, uuid4

from sqlalchemy import Select, select
from sqlalchemy.orm import Session
from structlog.contextvars import get_contextvars

from backend.app.models.audit import (
    AuditActorKind,
    AuditEvent,
    AuditResult,
    ComplianceExport,
)
from backend.app.models.user import User
from backend.app.services.policy import (
    POLICY_REVISION,
    PolicyAction,
    PolicyDeniedError,
    PolicyNotFoundError,
    PolicyService,
)
from backend.app.storage.base import ObjectStorage, ObjectStorageError
from backend.app.storage.keys import compliance_export_key

_ACTION = re.compile(r"^[a-z][a-z0-9_.-]{1,79}$")
_RESOURCE_TYPE = re.compile(r"^[a-z][a-z0-9_.-]{1,39}$")
_ACTOR = re.compile(r"^[a-z][a-z0-9_.-]{1,79}$")
_CORRELATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}$")
_MAX_DETAILS_BYTES = 2048
_MAX_EXPORT_EVENTS = 5000
_MAX_EXPORT_RANGE = timedelta(days=31)
_SAFE_DETAIL_FIELDS = frozenset(
    {
        "assistant_message_id",
        "chunk_count",
        "citation_count",
        "content_sha256",
        "document_id",
        "event_count",
        "export_id",
        "job_id",
        "media_type",
        "policy_revision",
        "predecessor_job_id",
        "previous_visibility",
        "principal_user_id",
        "range_end",
        "range_start",
        "requested_action",
        "denial_reason",
        "target_type",
        "version_id",
        "version_number",
        "visibility",
    }
)


class AuditNotFoundError(Exception):
    pass


class AuditPermissionError(Exception):
    pass


class AuditValidationError(Exception):
    pass


class ComplianceExportError(Exception):
    pass


class ComplianceExportNotFoundError(ComplianceExportError):
    pass


class ComplianceExportPermissionError(ComplianceExportError):
    pass


class ComplianceExportValidationError(ComplianceExportError):
    pass


class ComplianceExportUnavailableError(ComplianceExportError):
    pass


@dataclass(frozen=True, slots=True)
class SecurityAuditFilter:
    range_start: datetime | None = None
    range_end: datetime | None = None
    action: str | None = None
    result: AuditResult | None = None
    actor_kind: AuditActorKind | None = None


def record_audit_event(
    session: Session,
    *,
    workspace_id: UUID,
    actor_user_id: UUID | None = None,
    service_actor: str | None = None,
    action: str,
    resource_type: str,
    resource_id: UUID | None,
    result: AuditResult = AuditResult.SUCCEEDED,
    policy_revision: str = POLICY_REVISION,
    correlation_id: str | None = None,
    details: dict[str, object] | None = None,
) -> AuditEvent:
    safe_details = validate_audit_details(details or {})
    if not _ACTION.fullmatch(action) or not _RESOURCE_TYPE.fullmatch(resource_type):
        raise AuditValidationError
    if actor_user_id is not None and service_actor is not None:
        raise AuditValidationError
    if actor_user_id is None and not service_actor:
        raise AuditValidationError
    if service_actor is not None and not _ACTOR.fullmatch(service_actor):
        raise AuditValidationError
    if not _ACTOR.fullmatch(policy_revision):
        raise AuditValidationError

    event_id = uuid4()
    resolved_correlation = correlation_id or str(
        get_contextvars().get("request_id") or event_id
    )
    if not _CORRELATION.fullmatch(resolved_correlation):
        raise AuditValidationError
    event = AuditEvent(
        id=event_id,
        workspace_id=workspace_id,
        actor_kind=(
            AuditActorKind.USER.value
            if actor_user_id is not None
            else AuditActorKind.SERVICE.value
        ),
        actor_user_id=actor_user_id,
        service_actor=service_actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result.value,
        policy_revision=policy_revision,
        correlation_id=resolved_correlation,
        schema_version=1,
        details=safe_details,
    )
    session.add(event)
    return event


def validate_audit_details(details: dict[str, object]) -> dict[str, object]:
    if not set(details).issubset(_SAFE_DETAIL_FIELDS):
        raise AuditValidationError
    for value in details.values():
        if value is None or isinstance(value, (bool, int)):
            continue
        if not isinstance(value, str) or len(value) > 255:
            raise AuditValidationError
    encoded = json.dumps(details, sort_keys=True, separators=(",", ":")).encode()
    if len(encoded) > _MAX_DETAILS_BYTES:
        raise AuditValidationError
    return dict(details)


class AuditService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._policy = PolicyService(session)

    def list_events(
        self, *, user: User, workspace_id: UUID, limit: int
    ) -> list[tuple[AuditEvent, User | None]]:
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
            .outerjoin(User, User.id == AuditEvent.actor_user_id)
            .where(AuditEvent.workspace_id == workspace_id)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit)
        )
        return [(row[0], row[1]) for row in self._session.execute(statement).all()]

    def list_security_events(
        self,
        *,
        user: User,
        workspace_id: UUID,
        filters: SecurityAuditFilter,
        limit: int,
    ) -> list[AuditEvent]:
        try:
            self._policy.require(
                user=user,
                workspace_id=workspace_id,
                action=PolicyAction.SECURITY_AUDIT_READ,
            )
        except PolicyNotFoundError as exc:
            raise AuditNotFoundError from exc
        except PolicyDeniedError as exc:
            raise AuditPermissionError from exc
        statement = _event_statement(workspace_id, filters).order_by(
            AuditEvent.created_at.desc(), AuditEvent.id.desc()
        )
        events = list(self._session.scalars(statement.limit(limit)))
        record_audit_event(
            self._session,
            workspace_id=workspace_id,
            actor_user_id=user.id,
            action="security.audit_viewed",
            resource_type="workspace",
            resource_id=workspace_id,
            result=AuditResult.ALLOWED,
        )
        self._session.commit()
        return events


class ComplianceExportService:
    def __init__(self, session: Session, storage: ObjectStorage) -> None:
        self._session = session
        self._storage = storage
        self._policy = PolicyService(session)

    def create(
        self,
        *,
        user: User,
        workspace_id: UUID,
        range_start: datetime,
        range_end: datetime,
        now: datetime | None = None,
    ) -> ComplianceExport:
        current = _utc(now or datetime.now(UTC))
        start, end = _utc(range_start), _utc(range_end)
        if start >= end or end > current or end - start > _MAX_EXPORT_RANGE:
            raise ComplianceExportValidationError
        key: str | None = None
        try:
            self._require(user, workspace_id, PolicyAction.SECURITY_EXPORT_CREATE)
            existing = self._session.scalar(
                select(ComplianceExport).where(
                    ComplianceExport.workspace_id == workspace_id,
                    ComplianceExport.range_start == start,
                    ComplianceExport.range_end == end,
                    ComplianceExport.schema_version == 1,
                )
            )
            if existing is not None:
                return existing
            events = list(
                self._session.scalars(
                    _event_statement(
                        workspace_id,
                        SecurityAuditFilter(range_start=start, range_end=end),
                    )
                    .order_by(AuditEvent.created_at, AuditEvent.id)
                    .limit(_MAX_EXPORT_EVENTS + 1)
                )
            )
            if len(events) > _MAX_EXPORT_EVENTS:
                raise ComplianceExportValidationError
            content = _export_content(workspace_id, start, end, events)
            content_sha256 = hashlib.sha256(content).hexdigest()
            export_id = uuid4()
            key = compliance_export_key(workspace_id=workspace_id, export_id=export_id)
            self._storage.put(
                key,
                content,
                media_type="application/json",
                metadata={"schema-version": "1", "content-sha256": content_sha256},
            )
            export = ComplianceExport(
                id=export_id,
                workspace_id=workspace_id,
                requested_by_user_id=user.id,
                range_start=start,
                range_end=end,
                status="ready",
                schema_version=1,
                event_count=len(events),
                content_sha256=content_sha256,
                byte_size=len(content),
                object_key=key,
                completed_at=current,
            )
            self._session.add(export)
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="security.export_created",
                resource_type="compliance_export",
                resource_id=export.id,
                details={
                    "export_id": str(export.id),
                    "range_start": start.isoformat(),
                    "range_end": end.isoformat(),
                    "event_count": len(events),
                    "content_sha256": content_sha256,
                },
            )
            self._session.commit()
            return export
        except Exception:
            self._session.rollback()
            if key is not None:
                self._storage.delete(key)
            raise

    def get(
        self, *, user: User, workspace_id: UUID, export_id: UUID
    ) -> ComplianceExport:
        self._require(user, workspace_id, PolicyAction.SECURITY_EXPORT_CREATE)
        export = self._session.scalar(
            select(ComplianceExport).where(
                ComplianceExport.id == export_id,
                ComplianceExport.workspace_id == workspace_id,
            )
        )
        if export is None:
            raise ComplianceExportNotFoundError
        return export

    def open_content(
        self, *, user: User, workspace_id: UUID, export_id: UUID
    ) -> tuple[ComplianceExport, ContextManager[BinaryIO]]:
        export = self.get(user=user, workspace_id=workspace_id, export_id=export_id)
        try:
            stored = self._storage.head(export.object_key)
            if (
                stored.byte_size != export.byte_size
                or stored.content_sha256 != export.content_sha256
                or stored.media_type != "application/json"
            ):
                raise ComplianceExportUnavailableError
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="security.export_downloaded",
                resource_type="compliance_export",
                resource_id=export.id,
                details={"export_id": str(export.id)},
            )
            self._session.commit()
            return export, self._storage.open_stream(export.object_key)
        except ObjectStorageError as exc:
            self._session.rollback()
            raise ComplianceExportUnavailableError from exc

    def _require(self, user: User, workspace_id: UUID, action: PolicyAction) -> None:
        try:
            self._policy.require(user=user, workspace_id=workspace_id, action=action)
        except PolicyNotFoundError as exc:
            raise ComplianceExportNotFoundError from exc
        except PolicyDeniedError as exc:
            raise ComplianceExportPermissionError from exc


def _event_statement(
    workspace_id: UUID, filters: SecurityAuditFilter
) -> Select[tuple[AuditEvent]]:
    statement = select(AuditEvent).where(AuditEvent.workspace_id == workspace_id)
    if filters.range_start is not None:
        statement = statement.where(
            AuditEvent.created_at >= _audit_utc(filters.range_start)
        )
    if filters.range_end is not None:
        statement = statement.where(AuditEvent.created_at < _audit_utc(filters.range_end))
    if filters.action is not None:
        if not _ACTION.fullmatch(filters.action):
            raise AuditValidationError
        statement = statement.where(AuditEvent.action == filters.action)
    if filters.result is not None:
        statement = statement.where(AuditEvent.result == filters.result.value)
    if filters.actor_kind is not None:
        statement = statement.where(AuditEvent.actor_kind == filters.actor_kind.value)
    return statement


def _export_content(
    workspace_id: UUID,
    range_start: datetime,
    range_end: datetime,
    events: list[AuditEvent],
) -> bytes:
    payload = {
        "events": [
            {
                "action": event.action,
                "actor_id": (
                    str(event.actor_user_id)
                    if event.actor_user_id is not None
                    else event.service_actor
                ),
                "actor_kind": event.actor_kind,
                "correlation_id": event.correlation_id,
                "details": event.details,
                "event_id": str(event.id),
                "occurred_at": _database_utc(event.created_at).isoformat(),
                "policy_revision": event.policy_revision,
                "resource_id": str(event.resource_id) if event.resource_id else None,
                "resource_type": event.resource_type,
                "result": event.result,
                "schema_version": event.schema_version,
            }
            for event in events
        ],
        "range_end": range_end.isoformat(),
        "range_start": range_start.isoformat(),
        "schema_version": 1,
        "workspace_id": str(workspace_id),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ComplianceExportValidationError
    return value.astimezone(UTC)


def _database_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _audit_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise AuditValidationError
    return value.astimezone(UTC)
