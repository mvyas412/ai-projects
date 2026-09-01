from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.source_permission import (
    SourcePermissionPrincipal,
    SourcePermissionSnapshot,
)
from backend.app.models.workspace import WorkspaceMembership
from backend.app.repositories.documents import DocumentRepository

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_NAMESPACE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
_REVISION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,159}$")


class SourcePermissionError(Exception):
    """Base class for non-disclosing permission-envelope failures."""


class SourcePermissionRejectedError(SourcePermissionError):
    pass


class SourcePermissionConflictError(SourcePermissionError):
    pass


@dataclass(frozen=True, slots=True)
class SourcePermissionEnvelope:
    workspace_id: UUID
    document_id: UUID
    document_version_id: UUID
    source_namespace: str
    source_item_ref_hash: str
    sync_revision: str
    permission_revision: str
    principal_user_ids: tuple[UUID, ...]
    verified_at: datetime
    valid_until: datetime
    schema_version: int = 1
    unresolved_principal_count: int = 0
    semantics_supported: bool = True


class SourcePermissionService:
    """Persist and validate append-only permission evidence for future connectors."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._documents = DocumentRepository(session)

    def record(
        self, envelope: SourcePermissionEnvelope
    ) -> tuple[SourcePermissionSnapshot, bool]:
        principal_ids = self._validate(envelope)
        version = self._documents.get_version(
            envelope.workspace_id,
            envelope.document_id,
            envelope.document_version_id,
        )
        if version is None:
            raise SourcePermissionRejectedError
        if not self._all_current_members(envelope.workspace_id, principal_ids):
            raise SourcePermissionRejectedError

        fingerprint = _fingerprint(envelope, principal_ids)
        existing = self._session.scalar(
            select(SourcePermissionSnapshot).where(
                SourcePermissionSnapshot.workspace_id == envelope.workspace_id,
                SourcePermissionSnapshot.source_namespace == envelope.source_namespace,
                SourcePermissionSnapshot.source_item_ref_hash
                == envelope.source_item_ref_hash,
                SourcePermissionSnapshot.sync_revision == envelope.sync_revision,
                SourcePermissionSnapshot.permission_revision
                == envelope.permission_revision,
            )
        )
        if existing is not None:
            if existing.permission_fingerprint != fingerprint:
                raise SourcePermissionConflictError
            return existing, False

        snapshot = SourcePermissionSnapshot(
            workspace_id=envelope.workspace_id,
            document_id=envelope.document_id,
            document_version_id=envelope.document_version_id,
            source_namespace=envelope.source_namespace,
            source_item_ref_hash=envelope.source_item_ref_hash,
            sync_revision=envelope.sync_revision,
            permission_revision=envelope.permission_revision,
            schema_version=envelope.schema_version,
            permission_fingerprint=fingerprint,
            unresolved_principal_count=envelope.unresolved_principal_count,
            semantics_supported=envelope.semantics_supported,
            verified_at=_utc(envelope.verified_at),
            valid_until=_utc(envelope.valid_until),
        )
        self._session.add(snapshot)
        self._session.flush()
        self._session.add_all(
            SourcePermissionPrincipal(
                snapshot_id=snapshot.id,
                workspace_id=envelope.workspace_id,
                principal_user_id=principal_id,
            )
            for principal_id in principal_ids
        )
        self._session.flush()
        return snapshot, True

    def require_current(
        self,
        *,
        workspace_id: UUID,
        document_id: UUID,
        document_version_id: UUID,
        snapshot_id: UUID,
        now: datetime | None = None,
    ) -> frozenset[UUID]:
        snapshot = self._session.scalar(
            select(SourcePermissionSnapshot).where(
                SourcePermissionSnapshot.id == snapshot_id,
                SourcePermissionSnapshot.workspace_id == workspace_id,
                SourcePermissionSnapshot.document_id == document_id,
                SourcePermissionSnapshot.document_version_id == document_version_id,
            )
        )
        if snapshot is None:
            raise SourcePermissionRejectedError
        principal_ids = tuple(
            sorted(
                self._session.scalars(
                    select(SourcePermissionPrincipal.principal_user_id).where(
                        SourcePermissionPrincipal.snapshot_id == snapshot.id,
                        SourcePermissionPrincipal.workspace_id == workspace_id,
                    )
                ),
                key=str,
            )
        )
        envelope = SourcePermissionEnvelope(
            workspace_id=snapshot.workspace_id,
            document_id=snapshot.document_id,
            document_version_id=snapshot.document_version_id,
            source_namespace=snapshot.source_namespace,
            source_item_ref_hash=snapshot.source_item_ref_hash,
            sync_revision=snapshot.sync_revision,
            permission_revision=snapshot.permission_revision,
            principal_user_ids=principal_ids,
            verified_at=_database_utc(snapshot.verified_at),
            valid_until=_database_utc(snapshot.valid_until),
            schema_version=snapshot.schema_version,
            unresolved_principal_count=snapshot.unresolved_principal_count,
            semantics_supported=snapshot.semantics_supported,
        )
        self._validate(envelope, now=now)
        if snapshot.permission_fingerprint != _fingerprint(envelope, principal_ids):
            raise SourcePermissionRejectedError
        if not self._all_current_members(workspace_id, principal_ids):
            raise SourcePermissionRejectedError
        return frozenset(principal_ids)

    def _all_current_members(
        self, workspace_id: UUID, principal_ids: tuple[UUID, ...]
    ) -> bool:
        if not principal_ids:
            return True
        current = set(
            self._session.scalars(
                select(WorkspaceMembership.user_id).where(
                    WorkspaceMembership.workspace_id == workspace_id,
                    WorkspaceMembership.user_id.in_(principal_ids),
                )
            )
        )
        return current == set(principal_ids)

    @staticmethod
    def _validate(
        envelope: SourcePermissionEnvelope, *, now: datetime | None = None
    ) -> tuple[UUID, ...]:
        verified_at = _utc(envelope.verified_at)
        valid_until = _utc(envelope.valid_until)
        current = _utc(now or datetime.now(UTC))
        principal_ids = tuple(sorted(set(envelope.principal_user_ids), key=str))
        if envelope.schema_version != 1:
            raise SourcePermissionRejectedError
        if not _NAMESPACE.fullmatch(envelope.source_namespace):
            raise SourcePermissionRejectedError
        if not _HEX64.fullmatch(envelope.source_item_ref_hash):
            raise SourcePermissionRejectedError
        if not _REVISION.fullmatch(envelope.sync_revision):
            raise SourcePermissionRejectedError
        if not _REVISION.fullmatch(envelope.permission_revision):
            raise SourcePermissionRejectedError
        if not envelope.semantics_supported or envelope.unresolved_principal_count != 0:
            raise SourcePermissionRejectedError
        if verified_at > current or valid_until <= current or verified_at >= valid_until:
            raise SourcePermissionRejectedError
        return principal_ids


def _fingerprint(
    envelope: SourcePermissionEnvelope, principal_ids: tuple[UUID, ...]
) -> str:
    payload = {
        "document_id": str(envelope.document_id),
        "document_version_id": str(envelope.document_version_id),
        "permission_revision": envelope.permission_revision,
        "principal_user_ids": [str(value) for value in principal_ids],
        "schema_version": envelope.schema_version,
        "semantics_supported": envelope.semantics_supported,
        "source_item_ref_hash": envelope.source_item_ref_hash,
        "source_namespace": envelope.source_namespace,
        "sync_revision": envelope.sync_revision,
        "unresolved_principal_count": envelope.unresolved_principal_count,
        "valid_until": _utc(envelope.valid_until).isoformat(),
        "verified_at": _utc(envelope.verified_at).isoformat(),
        "workspace_id": str(envelope.workspace_id),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise SourcePermissionRejectedError
    return value.astimezone(UTC)


def _database_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
