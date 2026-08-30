"""Establish the Phase 2 migration baseline.

Revision ID: 20260829_0001
Revises:
Create Date: 2026-08-29
"""

from collections.abc import Sequence

revision: str = "20260829_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Record the infrastructure baseline before product tables are introduced."""


def downgrade() -> None:
    """Remove the infrastructure baseline revision marker."""
