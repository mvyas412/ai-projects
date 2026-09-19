from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.enterprise import BillingEvent, EntitlementPolicy


class BillingEventError(Exception):
    """Raised when a simulated billing event is invalid or conflicts."""


class SimulatedBillingService:
    """Verify deterministic sandbox events and reconcile local entitlements."""

    provider = "simulated"

    def __init__(self, session: Session, signing_secret: bytes) -> None:
        if not signing_secret:
            raise ValueError("A simulated signing secret is required")
        self._session = session
        self._secret = signing_secret

    def ingest(self, body: bytes, signature: str, *, received_at: datetime) -> BillingEvent:
        expected = hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise BillingEventError("The billing event signature is invalid")
        try:
            payload = json.loads(body)
            workspace_id = UUID(payload["workspace_id"])
            external_event_id = str(payload["event_id"])
            event_type = str(payload["event_type"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise BillingEventError("The billing event is invalid") from exc
        payload_hash = hashlib.sha256(body).hexdigest()
        existing = self._session.scalar(
            select(BillingEvent).where(
                BillingEvent.provider == self.provider,
                BillingEvent.external_event_id == external_event_id,
            )
        )
        if existing is not None:
            if existing.payload_hash != payload_hash:
                raise BillingEventError("The billing event identity conflicts")
            return existing
        event = BillingEvent(
            workspace_id=workspace_id,
            provider=self.provider,
            external_event_id=external_event_id,
            event_type=event_type,
            payload_hash=payload_hash,
            received_at=_utc(received_at),
        )
        self._session.add(event)
        self._session.flush()
        return event

    def process(self, event: BillingEvent, body: bytes, *, now: datetime) -> EntitlementPolicy:
        if event.state == "processed":
            policy = self._session.scalar(
                select(EntitlementPolicy)
                .where(EntitlementPolicy.workspace_id == event.workspace_id)
                .order_by(EntitlementPolicy.version.desc())
            )
            if policy is None:
                raise BillingEventError("The processed billing event is incomplete")
            return policy
        if hashlib.sha256(body).hexdigest() != event.payload_hash:
            raise BillingEventError("The billing event payload changed")
        payload = json.loads(body)
        version = int(payload["entitlement_version"])
        rules = payload.get("rules", {})
        if not isinstance(rules, dict) or version <= 0:
            raise BillingEventError("The entitlement payload is invalid")
        current = self._session.scalar(
            select(EntitlementPolicy)
            .where(EntitlementPolicy.workspace_id == event.workspace_id)
            .order_by(EntitlementPolicy.version.desc())
            .with_for_update()
        )
        if current is not None and version < current.version:
            raise BillingEventError("The entitlement event is stale")
        if current is not None and version == current.version:
            policy = current
        else:
            policy = EntitlementPolicy(
                workspace_id=event.workspace_id,
                version=version,
                state="active",
                rules=rules,
                valid_from=_utc(now),
            )
            self._session.add(policy)
        event.state = "processed"
        event.processed_at = _utc(now)
        self._session.flush()
        return policy


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
