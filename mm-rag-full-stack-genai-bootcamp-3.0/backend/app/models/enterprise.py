from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models.mixins import TimestampMixin


class ConnectorInstallation(TimestampMixin, Base):
    __tablename__ = "connector_installations"
    __table_args__ = (
        CheckConstraint("state IN ('active', 'revoked', 'error')", name="ck_connectors_state"),
        CheckConstraint("revision > 0", name="ck_connectors_revision"),
        UniqueConstraint("id", "workspace_id", name="uq_connectors_id_workspace"),
        UniqueConstraint("workspace_id", "kind", "name", name="uq_connectors_name"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    credential_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    checkpoint_cursor: Mapped[str | None] = mapped_column(String(2000))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConnectorSyncRun(TimestampMixin, Base):
    __tablename__ = "connector_sync_runs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending', 'running', 'retry_scheduled', 'succeeded', 'failed', 'cancelled')",
            name="ck_connector_sync_runs_state",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_connector_sync_runs_attempts"),
        CheckConstraint("max_attempts > 0", name="ck_connector_sync_runs_max_attempts"),
        CheckConstraint("attempt_count <= max_attempts", name="ck_connector_sync_runs_budget"),
        CheckConstraint("fencing_token >= 0", name="ck_connector_sync_runs_fence"),
        ForeignKeyConstraint(
            ["connector_id", "workspace_id"],
            ["connector_installations.id", "connector_installations.workspace_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("id", "workspace_id", name="uq_connector_sync_runs_workspace"),
        UniqueConstraint(
            "workspace_id", "connector_id", "idempotency_key", name="uq_connector_sync_run_key"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    connector_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    base_cursor: Mapped[str | None] = mapped_column(String(2000))
    proposed_cursor: Mapped[str | None] = mapped_column(String(2000))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))


class ConnectorSyncAttempt(Base):
    __tablename__ = "connector_sync_attempts"
    __table_args__ = (
        CheckConstraint(
            "state IN ('running', 'succeeded', 'retryable_failure', 'permanent_failure', 'lease_expired')",
            name="ck_connector_sync_attempts_state",
        ),
        CheckConstraint("attempt_number > 0", name="ck_connector_sync_attempts_number"),
        CheckConstraint("fencing_token > 0", name="ck_connector_sync_attempts_fence"),
        ForeignKeyConstraint(
            ["run_id", "workspace_id"],
            ["connector_sync_runs.id", "connector_sync_runs.workspace_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("run_id", "attempt_number", name="uq_connector_sync_attempt_number"),
        UniqueConstraint("run_id", "fencing_token", name="uq_connector_sync_attempt_fence"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="running")
    worker_id: Mapped[str] = mapped_column(String(200), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))


class ConnectorSourceObject(TimestampMixin, Base):
    __tablename__ = "connector_source_objects"
    __table_args__ = (
        CheckConstraint(
            "visibility_state IN ('pending', 'visible', 'denied', 'deleted')",
            name="ck_connector_source_objects_visibility",
        ),
        CheckConstraint("length(permission_fingerprint) = 64", name="ck_source_object_acl_hash"),
        ForeignKeyConstraint(
            ["connector_id", "workspace_id"],
            ["connector_installations.id", "connector_installations.workspace_id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "workspace_id", "connector_id", "external_id", name="uq_connector_source_object"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    connector_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    external_id: Mapped[str] = mapped_column(String(500), nullable=False)
    version_external_id: Mapped[str | None] = mapped_column(String(500))
    permission_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    visibility_state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    document_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    document_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("document_versions.id", ondelete="SET NULL")
    )
    last_sequence: Mapped[str] = mapped_column(String(128), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EnterpriseIdentity(TimestampMixin, Base):
    __tablename__ = "enterprise_identities"
    __table_args__ = (
        CheckConstraint(
            "state IN ('active', 'suspended', 'deleted')", name="ck_enterprise_identity_state"
        ),
        UniqueConstraint("workspace_id", "provider", "external_id", name="uq_enterprise_identity"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class EnterpriseGroupMapping(TimestampMixin, Base):
    __tablename__ = "enterprise_group_mappings"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'member', 'viewer')", name="ck_enterprise_group_role"),
        UniqueConstraint(
            "workspace_id", "provider", "external_group_id", name="uq_enterprise_group"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    external_group_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class EntitlementPolicy(TimestampMixin, Base):
    __tablename__ = "entitlement_policies"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_entitlement_policy_version"),
        UniqueConstraint("workspace_id", "version", name="uq_entitlement_policy_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    rules: Mapped[dict] = mapped_column(JSON, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UsageLedgerEntry(Base):
    __tablename__ = "usage_ledger_entries"
    __table_args__ = (
        CheckConstraint("quantity != 0", name="ck_usage_ledger_quantity"),
        CheckConstraint("meter_version > 0", name="ck_usage_ledger_meter_version"),
        UniqueConstraint("workspace_id", "idempotency_key", name="uq_usage_ledger_key"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    meter: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    meter_version: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(40), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    correction_of_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("usage_ledger_entries.id", ondelete="RESTRICT")
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UsageReservation(TimestampMixin, Base):
    __tablename__ = "usage_reservations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_usage_reservation_quantity"),
        CheckConstraint(
            "state IN ('active', 'settled', 'released')", name="ck_usage_reservation_state"
        ),
        UniqueConstraint("workspace_id", "idempotency_key", name="uq_usage_reservation_key"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    meter: Mapped[str] = mapped_column(String(80), nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settled_entry_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("usage_ledger_entries.id", ondelete="RESTRICT")
    )


class BillingEvent(Base):
    __tablename__ = "billing_events"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending', 'processed', 'rejected')", name="ck_billing_event_state"
        ),
        UniqueConstraint("provider", "external_event_id", name="uq_billing_event_provider"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ComplianceWorkflow(TimestampMixin, Base):
    __tablename__ = "compliance_workflows"
    __table_args__ = (
        CheckConstraint(
            "state IN ('previewed', 'authorized', 'running', 'blocked', 'completed', 'failed')",
            name="ck_compliance_workflow_state",
        ),
        CheckConstraint("length(scope_fingerprint) = 64", name="ck_compliance_scope_hash"),
        UniqueConstraint("workspace_id", "idempotency_key", name="uq_compliance_workflow_key"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    requested_by_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    policy_revision: Mapped[str] = mapped_column(String(80), nullable=False)
    scope_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="previewed")
    authorized_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_manifest: Mapped[dict | None] = mapped_column(JSON)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
