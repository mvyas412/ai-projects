from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from qdrant_client import models
from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.orm import Session, aliased

from backend.app.core.config import Settings
from backend.app.db.rls import DatabasePurpose, set_rls_context
from backend.app.models.access import ResourceACLGrant
from backend.app.models.audit import AuditEvent, ComplianceExport
from backend.app.models.conversation import (
    Conversation,
    ConversationDocument,
    ConversationMessage,
)
from backend.app.models.document import CollectionDocument, Document, DocumentVersion
from backend.app.models.generation import IngestionGeneration
from backend.app.models.ingestion import (
    IngestionAttempt,
    IngestionAttemptState,
    IngestionJob,
    IngestionJobState,
)
from backend.app.models.lifecycle import (
    LifecycleDeletionPlan,
    LifecyclePlanState,
    LifecycleResourceType,
    OrphanObjectEvidence,
    RetentionHold,
)
from backend.app.models.outbox import IngestionOutboxEvent
from backend.app.models.source_permission import (
    SourcePermissionPrincipal,
    SourcePermissionSnapshot,
)
from backend.app.models.user import User
from backend.app.repositories.conversations import ConversationRepository
from backend.app.repositories.documents import DocumentRepository
from backend.app.retrieval.scope import VectorScope
from backend.app.services.audit import record_audit_event
from backend.app.services.ingestion_jobs import IngestionJobStateMachine
from backend.app.services.policy import (
    PolicyAction,
    PolicyDeniedError,
    PolicyNotFoundError,
    PolicyService,
    resource_context,
)
from backend.app.storage.base import ObjectStorage
from backend.app.storage.keys import attempt_artifact_key

_TERMINAL_JOB_STATES = (
    IngestionJobState.SUCCEEDED.value,
    IngestionJobState.FAILED.value,
    IngestionJobState.CANCELLED.value,
)
_NONTERMINAL_JOB_STATES = (
    IngestionJobState.PENDING.value,
    IngestionJobState.QUEUED.value,
    IngestionJobState.RUNNING.value,
    IngestionJobState.RETRY_SCHEDULED.value,
)
_RETENTION_BATCH_LIMIT = 500


class LifecycleError(Exception):
    """Base class for non-disclosing lifecycle failures."""


class LifecycleNotFoundError(LifecycleError):
    pass


class LifecyclePermissionError(LifecycleError):
    pass


class LifecycleConflictError(LifecycleError):
    pass


class LifecyclePreviewChangedError(LifecycleConflictError):
    pass


class LifecycleDependencyError(LifecycleError):
    pass


@dataclass(frozen=True, slots=True)
class RetentionScope:
    plans: tuple[tuple[UUID, str, UUID, str], ...]
    generations: tuple[UUID, ...]
    jobs: tuple[UUID, ...]
    audits: tuple[UUID, ...]
    orphans: tuple[UUID, ...]

    @property
    def token(self) -> str:
        payload = {
            "plans": [
                [str(plan_id), resource_type, str(resource_id), updated_at]
                for plan_id, resource_type, resource_id, updated_at in self.plans
            ],
            "generations": [str(item) for item in self.generations],
            "jobs": [str(item) for item in self.jobs],
            "audits": [str(item) for item in self.audits],
            "orphans": [str(item) for item in self.orphans],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class RetentionPreview:
    policy_revision: str
    generated_at: datetime
    scope: RetentionScope

    @property
    def due_document_deletions(self) -> int:
        return sum(
            item[1] == LifecycleResourceType.DOCUMENT.value for item in self.scope.plans
        )

    @property
    def due_conversation_deletions(self) -> int:
        return sum(
            item[1] == LifecycleResourceType.CONVERSATION.value
            for item in self.scope.plans
        )


@dataclass(frozen=True, slots=True)
class RetentionApplyResult:
    policy_revision: str
    completed_plans: int
    blocked_plans: int
    deleted_inactive_generations: int
    deleted_terminal_jobs: int
    deleted_security_audit_events: int
    deleted_orphan_objects: int


@dataclass(frozen=True, slots=True)
class OrphanInventoryResult:
    observed_objects: int
    orphan_objects: int
    new_evidence: int
    cleared_evidence: int


class LifecycleService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        original_storage: ObjectStorage,
        artifact_storage: ObjectStorage,
        qdrant_client,
    ) -> None:
        self._session = session
        self._settings = settings
        self._originals = original_storage
        self._artifacts = artifact_storage
        self._qdrant = qdrant_client
        self._documents = DocumentRepository(session)
        self._conversations = ConversationRepository(session)
        self._policy = PolicyService(session)

    def request_document_deletion(
        self,
        *,
        user: User,
        workspace_id: UUID,
        document_id: UUID,
        now: datetime | None = None,
    ) -> LifecycleDeletionPlan:
        requested_at = _utc(now or datetime.now(UTC))
        with self._session.begin():
            document = self._documents.get_document(
                workspace_id,
                document_id,
                include_archived=True,
                include_tombstoned=True,
            )
            if document is None:
                raise LifecycleNotFoundError
            if document.tombstoned_at is not None:
                self._require(user, workspace_id, PolicyAction.DOCUMENT_PURGE)
                plan = self._plan_for(
                    workspace_id, LifecycleResourceType.DOCUMENT, document_id
                )
                if plan is None:
                    raise LifecycleConflictError("Deletion state is incomplete")
                return plan
            self._require(
                user,
                workspace_id,
                PolicyAction.DOCUMENT_PURGE,
                resource=resource_context(document),
            )
            self._require_no_hold(
                workspace_id, LifecycleResourceType.DOCUMENT, document_id
            )
            state_machine = IngestionJobStateMachine(self._session)
            for job in self._session.scalars(
                select(IngestionJob)
                .where(
                    IngestionJob.workspace_id == workspace_id,
                    IngestionJob.document_id == document_id,
                    IngestionJob.state.in_(_NONTERMINAL_JOB_STATES),
                )
                .with_for_update()
            ):
                state_machine.request_cancellation(
                    user=user,
                    workspace_id=workspace_id,
                    job_id=job.id,
                    now=requested_at,
                )
            expires_at = requested_at + timedelta(
                days=self._settings.document_tombstone_retention_days
            )
            document.tombstoned_at = requested_at
            document.tombstone_expires_at = expires_at
            document.tombstoned_by_user_id = user.id
            plan = LifecycleDeletionPlan(
                workspace_id=workspace_id,
                resource_type=LifecycleResourceType.DOCUMENT.value,
                resource_id=document_id,
                requested_by_user_id=user.id,
                policy_revision=self._settings.lifecycle_policy_revision,
                execute_after=expires_at,
                jobs_fenced_at=requested_at,
            )
            self._session.add(plan)
            self._session.flush()
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="lifecycle.document_tombstoned",
                resource_type="document",
                resource_id=document_id,
                details={"lifecycle_plan_id": str(plan.id)},
            )
            return plan

    def request_conversation_deletion(
        self,
        *,
        user: User,
        workspace_id: UUID,
        conversation_id: UUID,
        now: datetime | None = None,
    ) -> LifecycleDeletionPlan:
        requested_at = _utc(now or datetime.now(UTC))
        with self._session.begin():
            conversation = self._conversations.get(
                workspace_id, conversation_id, include_tombstoned=True
            )
            if conversation is None:
                raise LifecycleNotFoundError
            visible_context = replace(resource_context(conversation), tombstoned=False)
            self._require(
                user,
                workspace_id,
                PolicyAction.CONVERSATION_DELETE,
                resource=visible_context,
            )
            if conversation.tombstoned_at is not None:
                plan = self._plan_for(
                    workspace_id, LifecycleResourceType.CONVERSATION, conversation_id
                )
                if plan is None:
                    raise LifecycleConflictError("Deletion state is incomplete")
                return plan
            self._require_no_hold(
                workspace_id, LifecycleResourceType.CONVERSATION, conversation_id
            )
            expires_at = requested_at + timedelta(
                days=self._settings.conversation_tombstone_retention_days
            )
            conversation.tombstoned_at = requested_at
            conversation.tombstone_expires_at = expires_at
            conversation.tombstoned_by_user_id = user.id
            plan = LifecycleDeletionPlan(
                workspace_id=workspace_id,
                resource_type=LifecycleResourceType.CONVERSATION.value,
                resource_id=conversation_id,
                requested_by_user_id=user.id,
                policy_revision=self._settings.lifecycle_policy_revision,
                execute_after=expires_at,
                jobs_fenced_at=requested_at,
            )
            self._session.add(plan)
            self._session.flush()
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="lifecycle.conversation_tombstoned",
                resource_type="conversation",
                resource_id=conversation_id,
                details={"lifecycle_plan_id": str(plan.id)},
            )
            return plan

    def restore_document(
        self, *, user: User, workspace_id: UUID, document_id: UUID
    ) -> None:
        with self._session.begin():
            self._require(user, workspace_id, PolicyAction.DOCUMENT_RESTORE)
            document = self._documents.get_document(
                workspace_id,
                document_id,
                include_archived=True,
                include_tombstoned=True,
            )
            if document is None or document.tombstoned_at is None:
                raise LifecycleNotFoundError
            plan = self._restorable_plan(
                workspace_id, LifecycleResourceType.DOCUMENT, document_id
            )
            document.tombstoned_at = None
            document.tombstone_expires_at = None
            document.tombstoned_by_user_id = None
            self._session.delete(plan)
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="lifecycle.document_restored",
                resource_type="document",
                resource_id=document_id,
            )

    def restore_conversation(
        self, *, user: User, workspace_id: UUID, conversation_id: UUID
    ) -> None:
        with self._session.begin():
            conversation = self._conversations.get(
                workspace_id, conversation_id, include_tombstoned=True
            )
            if conversation is None or conversation.tombstoned_at is None:
                raise LifecycleNotFoundError
            self._require(
                user,
                workspace_id,
                PolicyAction.CONVERSATION_DELETE,
                resource=replace(resource_context(conversation), tombstoned=False),
            )
            plan = self._restorable_plan(
                workspace_id, LifecycleResourceType.CONVERSATION, conversation_id
            )
            conversation.tombstoned_at = None
            conversation.tombstone_expires_at = None
            conversation.tombstoned_by_user_id = None
            self._session.delete(plan)
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="lifecycle.conversation_restored",
                resource_type="conversation",
                resource_id=conversation_id,
            )

    def place_hold(
        self,
        *,
        user: User,
        workspace_id: UUID,
        resource_type: LifecycleResourceType,
        resource_id: UUID,
        reason_code: str,
    ) -> RetentionHold:
        with self._session.begin():
            self._require(user, workspace_id, PolicyAction.RETENTION_PREVIEW)
            self._require_resource_exists(workspace_id, resource_type, resource_id)
            existing = self._hold_for(workspace_id, resource_type, resource_id)
            if existing is not None:
                if existing.reason_code != reason_code:
                    raise LifecycleConflictError("A different hold is already active")
                return existing
            hold = RetentionHold(
                workspace_id=workspace_id,
                resource_type=resource_type.value,
                resource_id=resource_id,
                placed_by_user_id=user.id,
                reason_code=reason_code,
            )
            self._session.add(hold)
            self._session.flush()
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="lifecycle.hold_placed",
                resource_type=resource_type.value,
                resource_id=resource_id,
                details={"reason_code": reason_code},
            )
            return hold

    def remove_hold(
        self,
        *,
        user: User,
        workspace_id: UUID,
        resource_type: LifecycleResourceType,
        resource_id: UUID,
    ) -> None:
        with self._session.begin():
            self._require(user, workspace_id, PolicyAction.RETENTION_PREVIEW)
            hold = self._hold_for(workspace_id, resource_type, resource_id)
            if hold is None:
                raise LifecycleNotFoundError
            self._session.delete(hold)
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="lifecycle.hold_removed",
                resource_type=resource_type.value,
                resource_id=resource_id,
                details={"reason_code": hold.reason_code},
            )

    def preview_retention(
        self,
        *,
        user: User,
        workspace_id: UUID,
        now: datetime | None = None,
    ) -> RetentionPreview:
        generated_at = _utc(now or datetime.now(UTC))
        with self._session.begin():
            self._require(user, workspace_id, PolicyAction.RETENTION_PREVIEW)
            scope = self._retention_scope(workspace_id, generated_at)
        return RetentionPreview(
            policy_revision=self._settings.lifecycle_policy_revision,
            generated_at=generated_at,
            scope=scope,
        )

    def inventory_orphans(
        self,
        *,
        user: User,
        workspace_id: UUID,
        now: datetime | None = None,
    ) -> OrphanInventoryResult:
        observed_at = _utc(now or datetime.now(UTC))
        prefix = f"workspaces/{workspace_id}"
        with self._session.begin():
            self._require(user, workspace_id, PolicyAction.RETENTION_PREVIEW)
        try:
            records_by_class = {
                "originals": [
                    item
                    for item in self._originals.list_objects(prefix)
                    if item.key.endswith("/original")
                ],
                "artifacts": [
                    item
                    for item in self._artifacts.list_objects(prefix)
                    if "/artifacts/" in item.key or "/compliance-exports/" in item.key
                ],
            }
        except Exception as exc:
            raise LifecycleDependencyError from exc

        with self._session.begin():
            self._require(user, workspace_id, PolicyAction.RETENTION_PREVIEW)
            referenced = self._referenced_object_keys(workspace_id)
            existing = {
                (row.storage_class, row.object_key): row
                for row in self._session.scalars(
                    select(OrphanObjectEvidence).where(
                        OrphanObjectEvidence.workspace_id == workspace_id
                    )
                )
            }
            seen_orphans: set[tuple[str, str]] = set()
            new_evidence = 0
            observed = 0
            for storage_class, records in records_by_class.items():
                observed += len(records)
                for record in records:
                    identity = (storage_class, record.key)
                    if record.key in referenced[storage_class]:
                        continue
                    seen_orphans.add(identity)
                    evidence = existing.get(identity)
                    if evidence is None:
                        evidence = OrphanObjectEvidence(
                            workspace_id=workspace_id,
                            storage_class=storage_class,
                            object_key=record.key,
                            byte_size=record.byte_size,
                            content_sha256=record.content_sha256,
                            first_seen_at=observed_at,
                            last_seen_at=observed_at,
                            evidence_count=1,
                        )
                        self._session.add(evidence)
                        new_evidence += 1
                    elif (
                        evidence.byte_size != record.byte_size
                        or evidence.content_sha256 != record.content_sha256
                    ):
                        evidence.byte_size = record.byte_size
                        evidence.content_sha256 = record.content_sha256
                        evidence.first_seen_at = observed_at
                        evidence.last_seen_at = observed_at
                        evidence.evidence_count = 1
                    else:
                        evidence.last_seen_at = observed_at
                        evidence.evidence_count += 1

            cleared = 0
            for identity, evidence in existing.items():
                if identity not in seen_orphans:
                    self._session.delete(evidence)
                    cleared += 1
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="retention.orphan_inventory_completed",
                resource_type="workspace",
                resource_id=workspace_id,
                details={"event_count": len(seen_orphans)},
            )
            return OrphanInventoryResult(
                observed_objects=observed,
                orphan_objects=len(seen_orphans),
                new_evidence=new_evidence,
                cleared_evidence=cleared,
            )

    def apply_retention(
        self,
        *,
        user: User,
        workspace_id: UUID,
        preview_token: str,
        now: datetime | None = None,
    ) -> RetentionApplyResult:
        applied_at = _utc(now or datetime.now(UTC))
        with self._session.begin():
            self._require(user, workspace_id, PolicyAction.RETENTION_APPLY)
            set_rls_context(
                self._session,
                purpose=DatabasePurpose.OPERATIONS,
                workspace_id=workspace_id,
                principal_id=user.id,
            )
            scope = self._retention_scope(workspace_id, applied_at)
            if scope.token != preview_token:
                raise LifecyclePreviewChangedError(
                    "Retention scope changed; create a new preview"
                )

        completed = 0
        blocked = 0
        for plan_id, _, _, _ in scope.plans:
            if self._purge_plan(user, workspace_id, plan_id, applied_at):
                completed += 1
            else:
                blocked += 1
        deleted_generations = sum(
            self._purge_inactive_generation(user, workspace_id, item, applied_at)
            for item in scope.generations
        )
        deleted_jobs = self._purge_terminal_jobs(
            user, workspace_id, scope.jobs, applied_at
        )
        deleted_audits = self._purge_audits(
            user, workspace_id, scope.audits, applied_at
        )
        deleted_orphans = self._purge_orphans(
            user, workspace_id, scope.orphans, applied_at
        )
        return RetentionApplyResult(
            policy_revision=self._settings.lifecycle_policy_revision,
            completed_plans=completed,
            blocked_plans=blocked,
            deleted_inactive_generations=deleted_generations,
            deleted_terminal_jobs=deleted_jobs,
            deleted_security_audit_events=deleted_audits,
            deleted_orphan_objects=deleted_orphans,
        )

    def _retention_scope(self, workspace_id: UUID, now: datetime) -> RetentionScope:
        hold_exists = exists(
            select(RetentionHold.id).where(
                RetentionHold.workspace_id == LifecycleDeletionPlan.workspace_id,
                RetentionHold.resource_type == LifecycleDeletionPlan.resource_type,
                RetentionHold.resource_id == LifecycleDeletionPlan.resource_id,
            )
        )
        plans = tuple(
            (
                row.id,
                row.resource_type,
                row.resource_id,
                _utc(row.updated_at).isoformat(),
            )
            for row in self._session.scalars(
                select(LifecycleDeletionPlan)
                .where(
                    LifecycleDeletionPlan.workspace_id == workspace_id,
                    LifecycleDeletionPlan.state.in_(
                        (
                            LifecyclePlanState.RECOVERABLE.value,
                            LifecyclePlanState.BLOCKED.value,
                        )
                    ),
                    LifecycleDeletionPlan.execute_after <= now,
                    ~hold_exists,
                )
                .order_by(
                    LifecycleDeletionPlan.execute_after,
                    LifecycleDeletionPlan.id,
                )
                .limit(_RETENTION_BATCH_LIMIT)
            )
        )

        generation_cutoff = now - timedelta(
            days=self._settings.inactive_generation_retention_days
        )
        live_attempt = exists(
            select(IngestionAttempt.id).where(
                IngestionAttempt.id == IngestionGeneration.attempt_id,
                IngestionAttempt.state == IngestionAttemptState.RUNNING.value,
            )
        )
        document_hold = exists(
            select(RetentionHold.id).where(
                RetentionHold.workspace_id == IngestionGeneration.workspace_id,
                RetentionHold.resource_type == LifecycleResourceType.DOCUMENT.value,
                RetentionHold.resource_id == IngestionGeneration.document_id,
            )
        )
        generations = tuple(
            self._session.scalars(
                select(IngestionGeneration.id)
                .join(DocumentVersion, DocumentVersion.id == IngestionGeneration.document_version_id)
                .where(
                    IngestionGeneration.workspace_id == workspace_id,
                    IngestionGeneration.created_at < generation_cutoff,
                    or_(
                        DocumentVersion.active_generation_id.is_(None),
                        DocumentVersion.active_generation_id != IngestionGeneration.id,
                    ),
                    ~live_attempt,
                    ~document_hold,
                )
                .order_by(IngestionGeneration.created_at, IngestionGeneration.id)
                .limit(_RETENTION_BATCH_LIMIT)
            )
        )

        job_cutoff = now - timedelta(days=self._settings.terminal_job_retention_days)
        generation_exists = exists(
            select(IngestionGeneration.id).where(
                IngestionGeneration.job_id == IngestionJob.id
            )
        )
        successor = aliased(IngestionJob)
        successor_exists = exists(
            select(successor.id).where(successor.predecessor_job_id == IngestionJob.id)
        )
        job_hold = exists(
            select(RetentionHold.id).where(
                RetentionHold.workspace_id == IngestionJob.workspace_id,
                RetentionHold.resource_type == LifecycleResourceType.DOCUMENT.value,
                RetentionHold.resource_id == IngestionJob.document_id,
            )
        )
        jobs = tuple(
            self._session.scalars(
                select(IngestionJob.id)
                .where(
                    IngestionJob.workspace_id == workspace_id,
                    IngestionJob.state.in_(_TERMINAL_JOB_STATES),
                    IngestionJob.completed_at < job_cutoff,
                    ~generation_exists,
                    ~successor_exists,
                    ~job_hold,
                )
                .order_by(IngestionJob.completed_at, IngestionJob.id)
                .limit(_RETENTION_BATCH_LIMIT)
            )
        )

        audit_cutoff = now - timedelta(days=self._settings.security_audit_retention_days)
        audits = tuple(
            self._session.scalars(
                select(AuditEvent.id)
                .where(
                    AuditEvent.workspace_id == workspace_id,
                    AuditEvent.created_at < audit_cutoff,
                )
                .order_by(AuditEvent.created_at, AuditEvent.id)
                .limit(_RETENTION_BATCH_LIMIT)
            )
        )
        orphan_cutoff = now - timedelta(days=self._settings.orphan_object_retention_days)
        orphans = tuple(
            self._session.scalars(
                select(OrphanObjectEvidence.id)
                .where(
                    OrphanObjectEvidence.workspace_id == workspace_id,
                    OrphanObjectEvidence.first_seen_at < orphan_cutoff,
                )
                .order_by(
                    OrphanObjectEvidence.first_seen_at,
                    OrphanObjectEvidence.id,
                )
                .limit(_RETENTION_BATCH_LIMIT)
            )
        )
        return RetentionScope(plans, generations, jobs, audits, orphans)

    def _purge_plan(
        self, user: User, workspace_id: UUID, plan_id: UUID, now: datetime
    ) -> bool:
        try:
            with self._session.begin():
                self._require(user, workspace_id, PolicyAction.RETENTION_APPLY)
                plan = self._session.scalar(
                    select(LifecycleDeletionPlan)
                    .where(
                        LifecycleDeletionPlan.id == plan_id,
                        LifecycleDeletionPlan.workspace_id == workspace_id,
                    )
                    .with_for_update()
                )
                if plan is None or plan.state == LifecyclePlanState.COMPLETED.value:
                    return plan is not None
                if _utc(plan.execute_after) > now:
                    raise LifecycleConflictError("Deletion plan is not due")
                self._require_no_hold(
                    workspace_id,
                    LifecycleResourceType(plan.resource_type),
                    plan.resource_id,
                )
                plan.state = LifecyclePlanState.PURGING.value
                plan.last_error_code = None
                plan.last_error_message = None
                resource_type = LifecycleResourceType(plan.resource_type)
                resource_id = plan.resource_id

            if resource_type == LifecycleResourceType.DOCUMENT:
                self._purge_document(plan_id, user, workspace_id, resource_id, now)
            else:
                self._purge_conversation(plan_id, user, workspace_id, resource_id, now)
            return True
        except LifecycleConflictError as exc:
            self._mark_blocked(plan_id, workspace_id, "purge_blocked", str(exc))
            return False
        except Exception as exc:
            origin = getattr(exc, "orig", None)
            category = type(exc).__name__
            if origin is not None:
                category = f"{category}:{type(origin).__name__}:{getattr(origin, 'sqlstate', '')}"
            self._mark_blocked(
                plan_id,
                workspace_id,
                "dependency_unavailable",
                "A governed store could not be reconciled "
                f"({category}).",
            )
            return False

    def _purge_document(
        self,
        plan_id: UUID,
        user: User,
        workspace_id: UUID,
        document_id: UUID,
        now: datetime,
    ) -> None:
        with self._session.begin():
            self._require(user, workspace_id, PolicyAction.RETENTION_APPLY)
            document = self._documents.get_document(
                workspace_id,
                document_id,
                include_archived=True,
                include_tombstoned=True,
            )
            if document is None:
                raise LifecycleConflictError("Document metadata is missing")
            if document.tombstoned_at is None:
                raise LifecycleConflictError("Document tombstone is missing")
            active_jobs = int(
                self._session.scalar(
                    select(func.count(IngestionJob.id)).where(
                        IngestionJob.workspace_id == workspace_id,
                        IngestionJob.document_id == document_id,
                        IngestionJob.state.in_(_NONTERMINAL_JOB_STATES),
                    )
                )
                or 0
            )
            if active_jobs:
                raise LifecycleConflictError("Document still has active ingestion work")
            versions = list(
                self._session.scalars(
                    select(DocumentVersion).where(
                        DocumentVersion.workspace_id == workspace_id,
                        DocumentVersion.document_id == document_id,
                    )
                )
            )
            generations = list(
                self._session.scalars(
                    select(IngestionGeneration).where(
                        IngestionGeneration.workspace_id == workspace_id,
                        IngestionGeneration.document_id == document_id,
                    )
                )
            )
            attempts = list(
                self._session.scalars(
                    select(IngestionAttempt)
                    .join(IngestionJob, IngestionJob.id == IngestionAttempt.job_id)
                    .where(
                        IngestionJob.workspace_id == workspace_id,
                        IngestionJob.document_id == document_id,
                    )
                )
            )
            plan = self._session.get(LifecycleDeletionPlan, plan_id)
            if plan is None:
                raise LifecycleConflictError("Deletion plan is missing")
            vector_checkpoint = plan.vectors_deleted_at
            artifact_checkpoint = plan.artifacts_deleted_at
            original_checkpoint = plan.originals_deleted_at

        vector_count = 0
        vectors_present = any(
            self._vector_count(workspace_id, document_id, version.id) > 0
            for version in versions
        )
        if vector_checkpoint is None or vectors_present:
            for version in versions:
                vector_count += self._delete_vectors(
                    workspace_id, document_id, version.id
                )
            with self._session.begin():
                plan = self._session.get(LifecycleDeletionPlan, plan_id)
                if plan is None:
                    raise LifecycleConflictError("Deletion plan is missing")
                plan.vectors_deleted_at = now
                plan.deleted_vector_count += vector_count

        artifact_keys = {
            generation.manifest_object_key
            for generation in generations
            if generation.manifest_object_key is not None
        }
        artifact_keys.update(
            attempt_artifact_key(
                workspace_id=workspace_id,
                job_id=attempt.job_id,
                attempt_id=attempt.id,
                artifact_name="manifest.json",
            )
            for attempt in attempts
        )
        artifact_count = 0
        artifacts_present = any(self._artifacts.exists(key) for key in artifact_keys)
        if artifact_checkpoint is None or artifacts_present:
            artifact_count = self._delete_objects(self._artifacts, artifact_keys)
            with self._session.begin():
                plan = self._session.get(LifecycleDeletionPlan, plan_id)
                if plan is None:
                    raise LifecycleConflictError("Deletion plan is missing")
                plan.artifacts_deleted_at = now
                plan.deleted_object_count += artifact_count

        original_keys = {version.object_key for version in versions}
        original_count = 0
        originals_present = any(self._originals.exists(key) for key in original_keys)
        if original_checkpoint is None or originals_present:
            original_count = self._delete_objects(self._originals, original_keys)
            with self._session.begin():
                plan = self._session.get(LifecycleDeletionPlan, plan_id)
                if plan is None:
                    raise LifecycleConflictError("Deletion plan is missing")
                plan.originals_deleted_at = now
                plan.deleted_object_count += original_count

        for version in versions:
            if self._vector_count(workspace_id, document_id, version.id) != 0:
                raise LifecycleDependencyError
        if any(self._artifacts.exists(key) for key in artifact_keys):
            raise LifecycleDependencyError
        if any(self._originals.exists(key) for key in original_keys):
            raise LifecycleDependencyError

        with self._session.begin():
            self._require(user, workspace_id, PolicyAction.RETENTION_APPLY)
            set_rls_context(
                self._session,
                purpose=DatabasePurpose.OPERATIONS,
                workspace_id=workspace_id,
                principal_id=user.id,
            )
            if self._hold_for(
                workspace_id, LifecycleResourceType.DOCUMENT, document_id
            ) is not None:
                raise LifecycleConflictError("Document is held")
            if self._session.scalar(
                select(func.count(IngestionJob.id)).where(
                    IngestionJob.workspace_id == workspace_id,
                    IngestionJob.document_id == document_id,
                    IngestionJob.state.in_(_NONTERMINAL_JOB_STATES),
                )
            ):
                raise LifecycleConflictError("Document still has active ingestion work")
            version_ids = select(DocumentVersion.id).where(
                DocumentVersion.workspace_id == workspace_id,
                DocumentVersion.document_id == document_id,
            )
            job_ids = select(IngestionJob.id).where(
                IngestionJob.workspace_id == workspace_id,
                IngestionJob.document_id == document_id,
            )
            snapshot_ids = select(SourcePermissionSnapshot.id).where(
                SourcePermissionSnapshot.workspace_id == workspace_id,
                SourcePermissionSnapshot.document_id == document_id,
            )
            self._session.execute(
                update(DocumentVersion)
                .where(DocumentVersion.id.in_(version_ids))
                .values(active_generation_id=None, active_generation_promoted_at=None)
            )
            self._session.execute(
                update(IngestionJob)
                .where(IngestionJob.id.in_(job_ids))
                .values(predecessor_job_id=None)
            )
            self._session.execute(
                delete(SourcePermissionPrincipal).where(
                    SourcePermissionPrincipal.snapshot_id.in_(snapshot_ids)
                )
            )
            self._session.execute(
                delete(SourcePermissionSnapshot).where(
                    SourcePermissionSnapshot.workspace_id == workspace_id,
                    SourcePermissionSnapshot.document_id == document_id,
                )
            )
            self._session.execute(
                delete(IngestionOutboxEvent).where(
                    IngestionOutboxEvent.job_id.in_(job_ids)
                )
            )
            self._session.execute(
                delete(IngestionGeneration).where(
                    IngestionGeneration.workspace_id == workspace_id,
                    IngestionGeneration.document_id == document_id,
                )
            )
            self._session.execute(
                delete(IngestionAttempt).where(IngestionAttempt.job_id.in_(job_ids))
            )
            self._session.execute(
                delete(IngestionJob).where(
                    IngestionJob.workspace_id == workspace_id,
                    IngestionJob.document_id == document_id,
                )
            )
            self._session.execute(
                delete(ConversationDocument).where(
                    ConversationDocument.workspace_id == workspace_id,
                    ConversationDocument.document_id == document_id,
                )
            )
            self._session.execute(
                delete(CollectionDocument).where(
                    CollectionDocument.workspace_id == workspace_id,
                    CollectionDocument.document_id == document_id,
                )
            )
            self._session.execute(
                delete(ResourceACLGrant).where(
                    ResourceACLGrant.workspace_id == workspace_id,
                    ResourceACLGrant.document_id == document_id,
                )
            )
            self._session.execute(delete(DocumentVersion).where(DocumentVersion.id.in_(version_ids)))
            self._session.execute(
                delete(Document).where(
                    Document.workspace_id == workspace_id,
                    Document.id == document_id,
                    Document.tombstoned_at.is_not(None),
                )
            )
            plan = self._session.get(LifecycleDeletionPlan, plan_id)
            if plan is None:
                raise LifecycleConflictError("Deletion plan is missing")
            plan.metadata_deleted_at = now
            plan.completed_at = now
            plan.state = LifecyclePlanState.COMPLETED.value
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="lifecycle.document_purged",
                resource_type="document",
                resource_id=document_id,
                details={
                    "lifecycle_plan_id": str(plan.id),
                    "deleted_vector_count": plan.deleted_vector_count,
                    "deleted_object_count": plan.deleted_object_count,
                },
            )

    def _purge_conversation(
        self,
        plan_id: UUID,
        user: User,
        workspace_id: UUID,
        conversation_id: UUID,
        now: datetime,
    ) -> None:
        with self._session.begin():
            self._require(user, workspace_id, PolicyAction.RETENTION_APPLY)
            set_rls_context(
                self._session,
                purpose=DatabasePurpose.OPERATIONS,
                workspace_id=workspace_id,
                principal_id=user.id,
            )
            conversation = self._conversations.get(
                workspace_id, conversation_id, include_tombstoned=True
            )
            if conversation is None or conversation.tombstoned_at is None:
                raise LifecycleConflictError("Conversation tombstone is missing")
            self._require_no_hold(
                workspace_id, LifecycleResourceType.CONVERSATION, conversation_id
            )
            self._session.execute(
                delete(ConversationMessage).where(
                    ConversationMessage.workspace_id == workspace_id,
                    ConversationMessage.conversation_id == conversation_id,
                )
            )
            self._session.execute(
                delete(ConversationDocument).where(
                    ConversationDocument.workspace_id == workspace_id,
                    ConversationDocument.conversation_id == conversation_id,
                )
            )
            self._session.execute(
                delete(ResourceACLGrant).where(
                    ResourceACLGrant.workspace_id == workspace_id,
                    ResourceACLGrant.conversation_id == conversation_id,
                )
            )
            self._session.execute(
                delete(Conversation).where(
                    Conversation.workspace_id == workspace_id,
                    Conversation.id == conversation_id,
                    Conversation.tombstoned_at.is_not(None),
                )
            )
            plan = self._session.get(LifecycleDeletionPlan, plan_id)
            if plan is None:
                raise LifecycleConflictError("Deletion plan is missing")
            plan.vectors_deleted_at = now
            plan.artifacts_deleted_at = now
            plan.originals_deleted_at = now
            plan.metadata_deleted_at = now
            plan.completed_at = now
            plan.state = LifecyclePlanState.COMPLETED.value
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="lifecycle.conversation_purged",
                resource_type="conversation",
                resource_id=conversation_id,
                details={"lifecycle_plan_id": str(plan.id)},
            )

    def _purge_inactive_generation(
        self,
        user: User,
        workspace_id: UUID,
        generation_id: UUID,
        now: datetime,
    ) -> int:
        try:
            with self._session.begin():
                self._require(user, workspace_id, PolicyAction.RETENTION_APPLY)
                generation = self._session.scalar(
                    select(IngestionGeneration).where(
                        IngestionGeneration.id == generation_id,
                        IngestionGeneration.workspace_id == workspace_id,
                    )
                )
                if generation is None:
                    return 0
                version = self._session.get(DocumentVersion, generation.document_version_id)
                if version is None or version.active_generation_id == generation.id:
                    return 0
                attempt = self._session.get(IngestionAttempt, generation.attempt_id)
                if attempt is not None and attempt.state == IngestionAttemptState.RUNNING.value:
                    return 0
                final_key = generation.manifest_object_key
                attempt_key = (
                    attempt_artifact_key(
                        workspace_id=workspace_id,
                        job_id=generation.job_id,
                        attempt_id=generation.attempt_id,
                        artifact_name="manifest.json",
                    )
                    if attempt is not None
                    else None
                )
                document_id = generation.document_id
                version_id = generation.document_version_id
            self._delete_generation_vectors(
                workspace_id, document_id, version_id, generation_id
            )
            self._delete_objects(
                self._artifacts,
                {key for key in (final_key, attempt_key) if key is not None},
            )
            with self._session.begin():
                self._require(user, workspace_id, PolicyAction.RETENTION_APPLY)
                generation = self._session.scalar(
                    select(IngestionGeneration).where(
                        IngestionGeneration.id == generation_id,
                        IngestionGeneration.workspace_id == workspace_id,
                    )
                )
                if generation is None:
                    return 0
                version = self._session.get(DocumentVersion, generation.document_version_id)
                if version is None or version.active_generation_id == generation.id:
                    return 0
                self._session.delete(generation)
                record_audit_event(
                    self._session,
                    workspace_id=workspace_id,
                    actor_user_id=user.id,
                    action="retention.generation_purged",
                    resource_type="document",
                    resource_id=document_id,
                    details={"deleted_vector_count": 0},
                )
            return 1
        except LifecycleConflictError:
            return 0

    def _purge_terminal_jobs(
        self,
        user: User,
        workspace_id: UUID,
        job_ids: tuple[UUID, ...],
        now: datetime,
    ) -> int:
        if not job_ids:
            return 0
        with self._session.begin():
            self._require(user, workspace_id, PolicyAction.RETENTION_APPLY)
            eligible = tuple(
                self._session.scalars(
                    select(IngestionJob.id).where(
                        IngestionJob.workspace_id == workspace_id,
                        IngestionJob.id.in_(job_ids),
                        IngestionJob.state.in_(_TERMINAL_JOB_STATES),
                        ~exists(
                            select(IngestionGeneration.id).where(
                                IngestionGeneration.job_id == IngestionJob.id
                            )
                        ),
                    )
                )
            )
            if not eligible:
                return 0
            self._session.execute(
                update(IngestionJob)
                .where(IngestionJob.predecessor_job_id.in_(eligible))
                .values(predecessor_job_id=None)
            )
            self._session.execute(
                delete(IngestionOutboxEvent).where(IngestionOutboxEvent.job_id.in_(eligible))
            )
            self._session.execute(
                delete(IngestionAttempt).where(IngestionAttempt.job_id.in_(eligible))
            )
            self._session.execute(delete(IngestionJob).where(IngestionJob.id.in_(eligible)))
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="retention.jobs_purged",
                resource_type="workspace",
                resource_id=workspace_id,
                details={"event_count": len(eligible)},
            )
            return len(eligible)

    def _purge_audits(
        self,
        user: User,
        workspace_id: UUID,
        audit_ids: tuple[UUID, ...],
        now: datetime,
    ) -> int:
        if not audit_ids:
            return 0
        with self._session.begin():
            self._require(user, workspace_id, PolicyAction.RETENTION_APPLY)
            set_rls_context(
                self._session,
                purpose=DatabasePurpose.OPERATIONS,
                workspace_id=workspace_id,
                principal_id=user.id,
            )
            existing = tuple(
                self._session.scalars(
                    select(AuditEvent.id).where(
                        AuditEvent.workspace_id == workspace_id,
                        AuditEvent.id.in_(audit_ids),
                    )
                )
            )
            self._session.execute(
                delete(AuditEvent).where(
                    AuditEvent.workspace_id == workspace_id,
                    AuditEvent.id.in_(existing),
                )
            )
            count = len(existing)
            record_audit_event(
                self._session,
                workspace_id=workspace_id,
                actor_user_id=user.id,
                action="retention.audit_purged",
                resource_type="workspace",
                resource_id=workspace_id,
                details={"event_count": count},
            )
            return count

    def _purge_orphans(
        self,
        user: User,
        workspace_id: UUID,
        evidence_ids: tuple[UUID, ...],
        now: datetime,
    ) -> int:
        deleted_count = 0
        for evidence_id in evidence_ids:
            with self._session.begin():
                self._require(user, workspace_id, PolicyAction.RETENTION_APPLY)
                evidence = self._session.scalar(
                    select(OrphanObjectEvidence).where(
                        OrphanObjectEvidence.id == evidence_id,
                        OrphanObjectEvidence.workspace_id == workspace_id,
                    )
                )
                if evidence is None:
                    continue
                referenced = self._referenced_object_keys(workspace_id)
                if evidence.object_key in referenced[evidence.storage_class]:
                    self._session.delete(evidence)
                    continue
                storage = (
                    self._originals
                    if evidence.storage_class == "originals"
                    else self._artifacts
                )
                storage_class = evidence.storage_class
                object_key = evidence.object_key
                expected_size = evidence.byte_size
                expected_hash = evidence.content_sha256
            if not storage.exists(object_key):
                with self._session.begin():
                    evidence = self._session.get(OrphanObjectEvidence, evidence_id)
                    if evidence is not None:
                        self._session.delete(evidence)
                continue
            current = storage.head(object_key)
            if (
                current.byte_size != expected_size
                or current.content_sha256 != expected_hash
            ):
                with self._session.begin():
                    evidence = self._session.get(OrphanObjectEvidence, evidence_id)
                    if evidence is not None:
                        evidence.byte_size = current.byte_size
                        evidence.content_sha256 = current.content_sha256
                        evidence.first_seen_at = now
                        evidence.last_seen_at = now
                        evidence.evidence_count = 1
                continue
            storage.delete(object_key)
            if storage.exists(object_key):
                raise LifecycleDependencyError
            with self._session.begin():
                evidence = self._session.get(OrphanObjectEvidence, evidence_id)
                if evidence is not None:
                    self._session.delete(evidence)
                record_audit_event(
                    self._session,
                    workspace_id=workspace_id,
                    actor_user_id=user.id,
                    action="retention.orphan_purged",
                    resource_type="workspace",
                    resource_id=workspace_id,
                    details={"resource_type": storage_class},
                )
            deleted_count += 1
        return deleted_count

    def _referenced_object_keys(self, workspace_id: UUID) -> dict[str, set[str]]:
        originals = set(
            self._session.scalars(
                select(DocumentVersion.object_key).where(
                    DocumentVersion.workspace_id == workspace_id
                )
            )
        )
        artifacts = {
            key
            for key in self._session.scalars(
                select(IngestionGeneration.manifest_object_key).where(
                    IngestionGeneration.workspace_id == workspace_id,
                    IngestionGeneration.manifest_object_key.is_not(None),
                )
            )
            if key is not None
        }
        attempts = self._session.execute(
            select(IngestionAttempt.id, IngestionAttempt.job_id).where(
                IngestionAttempt.workspace_id == workspace_id
            )
        )
        artifacts.update(
            attempt_artifact_key(
                workspace_id=workspace_id,
                job_id=job_id,
                attempt_id=attempt_id,
                artifact_name="manifest.json",
            )
            for attempt_id, job_id in attempts
        )
        artifacts.update(
            self._session.scalars(
                select(ComplianceExport.object_key).where(
                    ComplianceExport.workspace_id == workspace_id
                )
            )
        )
        return {"originals": originals, "artifacts": artifacts}

    def _delete_vectors(
        self, workspace_id: UUID, document_id: UUID, version_id: UUID
    ) -> int:
        count = self._vector_count(workspace_id, document_id, version_id)
        if not self._qdrant.collection_exists(self._settings.qdrant_collection_name):
            return 0
        scope = VectorScope(workspace_id, document_id, version_id)
        self._qdrant.delete(
            collection_name=self._settings.qdrant_collection_name,
            points_selector=models.FilterSelector(filter=scope.filter()),
            wait=True,
        )
        if self._vector_count(workspace_id, document_id, version_id) != 0:
            raise LifecycleDependencyError
        return count

    def _delete_generation_vectors(
        self,
        workspace_id: UUID,
        document_id: UUID,
        version_id: UUID,
        generation_id: UUID,
    ) -> None:
        if not self._qdrant.collection_exists(self._settings.qdrant_collection_name):
            return
        scope = VectorScope(workspace_id, document_id, version_id, generation_id)
        self._qdrant.delete(
            collection_name=self._settings.qdrant_collection_name,
            points_selector=models.FilterSelector(filter=scope.filter()),
            wait=True,
        )
        result = self._qdrant.count(
            collection_name=self._settings.qdrant_collection_name,
            count_filter=scope.filter(),
            exact=True,
        )
        if int(result.count) != 0:
            raise LifecycleDependencyError

    def _vector_count(
        self, workspace_id: UUID, document_id: UUID, version_id: UUID
    ) -> int:
        if not self._qdrant.collection_exists(self._settings.qdrant_collection_name):
            return 0
        result = self._qdrant.count(
            collection_name=self._settings.qdrant_collection_name,
            count_filter=VectorScope(workspace_id, document_id, version_id).filter(),
            exact=True,
        )
        return int(result.count)

    @staticmethod
    def _delete_objects(storage: ObjectStorage, keys: set[str]) -> int:
        deleted = 0
        for key in sorted(keys):
            existed = storage.exists(key)
            storage.delete(key)
            if storage.exists(key):
                raise LifecycleDependencyError
            deleted += int(existed)
        return deleted

    def _mark_blocked(
        self, plan_id: UUID, workspace_id: UUID, code: str, message: str
    ) -> None:
        self._session.rollback()
        with self._session.begin():
            set_rls_context(
                self._session,
                purpose=DatabasePurpose.OPERATIONS,
                workspace_id=workspace_id,
            )
            plan = self._session.scalar(
                select(LifecycleDeletionPlan).where(
                    LifecycleDeletionPlan.id == plan_id,
                    LifecycleDeletionPlan.workspace_id == workspace_id,
                )
            )
            if plan is not None and plan.state != LifecyclePlanState.COMPLETED.value:
                plan.state = LifecyclePlanState.BLOCKED.value
                plan.last_error_code = code
                plan.last_error_message = message[:300]
                record_audit_event(
                    self._session,
                    workspace_id=workspace_id,
                    service_actor="lifecycle-worker",
                    action="lifecycle.purge_blocked",
                    resource_type=plan.resource_type,
                    resource_id=plan.resource_id,
                    details={"lifecycle_plan_id": str(plan.id)},
                )

    def _restorable_plan(
        self,
        workspace_id: UUID,
        resource_type: LifecycleResourceType,
        resource_id: UUID,
    ) -> LifecycleDeletionPlan:
        plan = self._plan_for(workspace_id, resource_type, resource_id)
        if plan is None:
            raise LifecycleConflictError("Deletion plan is missing")
        if plan.state != LifecyclePlanState.RECOVERABLE.value or any(
            (
                plan.vectors_deleted_at,
                plan.artifacts_deleted_at,
                plan.originals_deleted_at,
                plan.metadata_deleted_at,
            )
        ):
            raise LifecycleConflictError("Deletion has already started")
        return plan

    def _plan_for(
        self,
        workspace_id: UUID,
        resource_type: LifecycleResourceType,
        resource_id: UUID,
    ) -> LifecycleDeletionPlan | None:
        return self._session.scalar(
            select(LifecycleDeletionPlan).where(
                LifecycleDeletionPlan.workspace_id == workspace_id,
                LifecycleDeletionPlan.resource_type == resource_type.value,
                LifecycleDeletionPlan.resource_id == resource_id,
            )
        )

    def _hold_for(
        self,
        workspace_id: UUID,
        resource_type: LifecycleResourceType,
        resource_id: UUID,
    ) -> RetentionHold | None:
        return self._session.scalar(
            select(RetentionHold).where(
                RetentionHold.workspace_id == workspace_id,
                RetentionHold.resource_type == resource_type.value,
                RetentionHold.resource_id == resource_id,
            )
        )

    def _require_no_hold(
        self,
        workspace_id: UUID,
        resource_type: LifecycleResourceType,
        resource_id: UUID,
    ) -> None:
        if self._hold_for(workspace_id, resource_type, resource_id) is not None:
            raise LifecycleConflictError("Resource is held")

    def _require_resource_exists(
        self,
        workspace_id: UUID,
        resource_type: LifecycleResourceType,
        resource_id: UUID,
    ) -> None:
        if resource_type == LifecycleResourceType.DOCUMENT:
            found = self._documents.get_document(
                workspace_id,
                resource_id,
                include_archived=True,
                include_tombstoned=True,
            ) is not None
        else:
            found = self._conversations.get(
                workspace_id, resource_id, include_tombstoned=True
            ) is not None
        if not found:
            raise LifecycleNotFoundError

    def _require(
        self,
        user: User,
        workspace_id: UUID,
        action: PolicyAction,
        *,
        resource=None,
    ) -> None:
        try:
            self._policy.require(
                user=user,
                workspace_id=workspace_id,
                action=action,
                resource=resource,
            )
        except PolicyNotFoundError as exc:
            raise LifecycleNotFoundError from exc
        except PolicyDeniedError as exc:
            raise LifecyclePermissionError from exc


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
