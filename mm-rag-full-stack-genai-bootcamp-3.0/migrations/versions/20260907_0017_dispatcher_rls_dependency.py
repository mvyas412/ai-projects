"""Allow the dispatcher to evaluate ingestion-job RLS safely.

Revision ID: 20260907_0017
Revises: 20260907_0016
Create Date: 2026-09-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260907_0017"
down_revision: str | None = "20260907_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        # The ingestion_jobs policy references documents. PostgreSQL checks that
        # dependency's table privilege even when the dispatcher branch is true.
        op.execute("GRANT SELECT ON documents TO mm_rag_dispatcher")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("REVOKE SELECT ON documents FROM mm_rag_dispatcher")
