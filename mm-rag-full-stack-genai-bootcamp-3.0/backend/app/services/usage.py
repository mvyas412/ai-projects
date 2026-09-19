from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.app.models.enterprise import UsageLedgerEntry, UsageReservation


class UsageError(Exception):
    """Base class for safe usage-ledger failures."""


class QuotaExceededError(UsageError):
    pass


class UsageConflictError(UsageError):
    pass


class UsageLedgerService:
    """Reserve and settle quota against immutable tenant-scoped usage entries."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def reserve(
        self,
        *,
        workspace_id: UUID,
        idempotency_key: str,
        meter: str,
        quantity: int,
        quota: int,
        expires_at: datetime,
    ) -> UsageReservation:
        if quantity <= 0 or quota < 0:
            raise UsageConflictError("The reservation values are invalid")
        existing = self._session.scalar(
            select(UsageReservation).where(
                UsageReservation.workspace_id == workspace_id,
                UsageReservation.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.meter != meter or existing.quantity != quantity:
                raise UsageConflictError("The reservation key was reused")
            return existing
        self._lock_quota(workspace_id, meter)
        tuple(
            self._session.scalars(
                select(UsageReservation)
                .where(
                    UsageReservation.workspace_id == workspace_id,
                    UsageReservation.meter == meter,
                    UsageReservation.state == "active",
                )
                .with_for_update()
            )
        )
        used = self._quantity(UsageLedgerEntry, workspace_id, meter)
        reserved = self._quantity(UsageReservation, workspace_id, meter, active=True)
        if used + reserved + quantity > quota:
            raise QuotaExceededError("The workspace quota is exhausted")
        reservation = UsageReservation(
            workspace_id=workspace_id,
            idempotency_key=idempotency_key,
            meter=meter,
            quantity=quantity,
            expires_at=_utc(expires_at),
        )
        self._session.add(reservation)
        self._session.flush()
        return reservation

    def settle(
        self,
        *,
        workspace_id: UUID,
        reservation_id: UUID,
        actual_quantity: int,
        meter_version: int,
        unit: str,
        resource_type: str,
        resource_id: UUID | None,
        occurred_at: datetime,
    ) -> UsageLedgerEntry:
        reservation = self._session.scalar(
            select(UsageReservation)
            .where(
                UsageReservation.id == reservation_id,
                UsageReservation.workspace_id == workspace_id,
            )
            .with_for_update()
        )
        if reservation is None or actual_quantity <= 0:
            raise UsageConflictError("The reservation cannot be settled")
        if reservation.state == "settled" and reservation.settled_entry_id is not None:
            entry = self._session.get(UsageLedgerEntry, reservation.settled_entry_id)
            if entry is None or entry.quantity != actual_quantity:
                raise UsageConflictError("The settlement conflicts with prior usage")
            return entry
        if reservation.state != "active" or actual_quantity > reservation.quantity:
            raise UsageConflictError("The settlement exceeds its reservation")
        entry = UsageLedgerEntry(
            workspace_id=workspace_id,
            idempotency_key=f"settle:{reservation.id}",
            meter=reservation.meter,
            meter_version=meter_version,
            quantity=actual_quantity,
            unit=unit,
            resource_type=resource_type,
            resource_id=resource_id,
            occurred_at=_utc(occurred_at),
            created_at=datetime.now(UTC),
        )
        self._session.add(entry)
        self._session.flush()
        reservation.state = "settled"
        reservation.settled_entry_id = entry.id
        self._session.flush()
        return entry

    def correct(
        self,
        *,
        workspace_id: UUID,
        original_entry_id: UUID,
        idempotency_key: str,
        quantity: int,
        occurred_at: datetime,
    ) -> UsageLedgerEntry:
        original = self._session.scalar(
            select(UsageLedgerEntry).where(
                UsageLedgerEntry.id == original_entry_id,
                UsageLedgerEntry.workspace_id == workspace_id,
            )
        )
        if original is None or quantity == 0:
            raise UsageConflictError("The correction is invalid")
        correction = UsageLedgerEntry(
            workspace_id=workspace_id,
            idempotency_key=idempotency_key,
            meter=original.meter,
            meter_version=original.meter_version,
            quantity=quantity,
            unit=original.unit,
            resource_type=original.resource_type,
            resource_id=original.resource_id,
            correction_of_id=original.id,
            occurred_at=_utc(occurred_at),
            created_at=datetime.now(UTC),
        )
        self._session.add(correction)
        self._session.flush()
        return correction

    def _quantity(self, model, workspace_id: UUID, meter: str, *, active: bool = False) -> int:
        query = select(func.coalesce(func.sum(model.quantity), 0)).where(
            model.workspace_id == workspace_id,
            model.meter == meter,
        )
        if active:
            query = query.where(model.state == "active")
        return int(self._session.scalar(query) or 0)

    def _lock_quota(self, workspace_id: UUID, meter: str) -> None:
        bind = self._session.get_bind()
        if bind.dialect.name == "postgresql":
            self._session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"{workspace_id}:{meter}"},
            )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
