from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.enterprise import ComplianceWorkflow
from backend.app.models.lifecycle import RetentionHold


class ComplianceWorkflowError(Exception):
    """Base class for non-disclosing administrative workflow failures."""


class ComplianceScopeChangedError(ComplianceWorkflowError):
    pass


class ComplianceAdminService:
    """Enforce preview, reauthorization, hold precedence, and content-free evidence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def preview(
        self,
        *,
        workspace_id: UUID,
        requested_by_user_id: UUID,
        operation: str,
        reason_code: str,
        idempotency_key: str,
        policy_revision: str,
        resource_ids: tuple[UUID, ...],
    ) -> ComplianceWorkflow:
        fingerprint = _scope_fingerprint(operation, policy_revision, resource_ids)
        existing = self._session.scalar(
            select(ComplianceWorkflow).where(
                ComplianceWorkflow.workspace_id == workspace_id,
                ComplianceWorkflow.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.scope_fingerprint != fingerprint:
                raise ComplianceScopeChangedError("The workflow scope changed")
            return existing
        workflow = ComplianceWorkflow(
            workspace_id=workspace_id,
            requested_by_user_id=requested_by_user_id,
            operation=operation,
            reason_code=reason_code,
            idempotency_key=idempotency_key,
            policy_revision=policy_revision,
            scope_fingerprint=fingerprint,
        )
        self._session.add(workflow)
        self._session.flush()
        return workflow

    def authorize(
        self,
        *,
        workflow_id: UUID,
        workspace_id: UUID,
        authorized_by_user_id: UUID,
        resource_ids: tuple[UUID, ...],
        now: datetime,
    ) -> ComplianceWorkflow:
        workflow = self._workflow(workflow_id, workspace_id)
        current = _scope_fingerprint(workflow.operation, workflow.policy_revision, resource_ids)
        if current != workflow.scope_fingerprint:
            raise ComplianceScopeChangedError("The workflow scope changed")
        workflow.authorized_by_user_id = authorized_by_user_id
        workflow.authorized_at = _utc(now)
        workflow.state = "authorized"
        self._session.flush()
        return workflow

    def complete(
        self,
        *,
        workflow_id: UUID,
        workspace_id: UUID,
        resource_ids: tuple[UUID, ...],
        deleted_counts: dict[str, int],
        now: datetime,
    ) -> ComplianceWorkflow:
        workflow = self._workflow(workflow_id, workspace_id)
        if workflow.state != "authorized":
            raise ComplianceWorkflowError("The workflow is not authorized")
        current = _scope_fingerprint(workflow.operation, workflow.policy_revision, resource_ids)
        if current != workflow.scope_fingerprint:
            raise ComplianceScopeChangedError("The workflow scope changed")
        held = self._session.scalar(
            select(RetentionHold.id).where(
                RetentionHold.workspace_id == workspace_id,
                RetentionHold.resource_id.in_(resource_ids),
            )
        )
        if held is not None:
            workflow.state = "blocked"
            self._session.flush()
            return workflow
        manifest = {
            "schema": "phase9-compliance-evidence-v1",
            "scope_fingerprint": workflow.scope_fingerprint,
            "counts": {key: int(value) for key, value in sorted(deleted_counts.items())},
            "completed_at": _utc(now).isoformat(),
        }
        manifest["manifest_sha256"] = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        workflow.evidence_manifest = manifest
        workflow.state = "completed"
        workflow.completed_at = _utc(now)
        self._session.flush()
        return workflow

    def _workflow(self, workflow_id: UUID, workspace_id: UUID) -> ComplianceWorkflow:
        workflow = self._session.scalar(
            select(ComplianceWorkflow)
            .where(
                ComplianceWorkflow.id == workflow_id,
                ComplianceWorkflow.workspace_id == workspace_id,
            )
            .with_for_update()
        )
        if workflow is None:
            raise ComplianceWorkflowError("The workflow was not found")
        return workflow


def _scope_fingerprint(operation: str, policy_revision: str, resource_ids: tuple[UUID, ...]) -> str:
    payload = [operation, policy_revision, sorted(str(item) for item in resource_ids)]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
