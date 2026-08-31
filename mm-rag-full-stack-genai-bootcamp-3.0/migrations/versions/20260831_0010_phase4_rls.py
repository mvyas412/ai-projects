"""Add Phase 4 PostgreSQL runtime roles and row-level-security policies.

Revision ID: 20260831_0010
Revises: 20260831_0009
Create Date: 2026-08-31
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260831_0010"
down_revision: str | None = "20260831_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLES = ("mm_rag_api", "mm_rag_worker", "mm_rag_dispatcher", "mm_rag_operations")


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for role in _ROLES:
        op.execute(
            f"""
            DO $$ BEGIN
                CREATE ROLE {role} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
            EXCEPTION WHEN duplicate_object THEN
                ALTER ROLE {role} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
            END $$
            """
        )
        op.execute(f"GRANT {role} TO CURRENT_USER")
        op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION mm_rag_is_member(target_workspace uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM public.workspace_memberships membership
                WHERE membership.workspace_id = target_workspace
                  AND membership.user_id = NULLIF(
                      current_setting('mm_rag.principal_id', true), ''
                  )::uuid
            )
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION mm_rag_can_read_resource(
            target_workspace uuid,
            target_type text,
            target_id uuid,
            target_creator uuid,
            target_visibility text
        ) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            WITH actor AS (
                SELECT membership.role, membership.user_id
                FROM public.workspace_memberships membership
                WHERE membership.workspace_id = target_workspace
                  AND membership.user_id = NULLIF(
                      current_setting('mm_rag.principal_id', true), ''
                  )::uuid
            )
            SELECT EXISTS (
                SELECT 1 FROM actor
                WHERE role IN ('owner', 'admin')
                   OR target_visibility = 'workspace'
                   OR user_id = target_creator
                   OR EXISTS (
                       SELECT 1 FROM public.resource_acl_grants grant_row
                       WHERE grant_row.workspace_id = target_workspace
                         AND grant_row.principal_user_id = actor.user_id
                         AND (
                             (target_type = 'document' AND grant_row.document_id = target_id)
                             OR (target_type = 'collection' AND grant_row.collection_id = target_id)
                             OR (target_type = 'conversation' AND grant_row.conversation_id = target_id)
                         )
                   )
            )
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION mm_rag_can_access_job(
            target_job uuid,
            target_workspace uuid
        ) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM public.ingestion_jobs job
                JOIN public.documents document ON document.id = job.document_id
                WHERE job.id = target_job
                  AND job.workspace_id = target_workspace
                  AND public.mm_rag_can_read_resource(
                      document.workspace_id,
                      'document',
                      document.id,
                      document.created_by_user_id,
                      document.visibility
                  )
            )
        $$
        """
    )
    for function in (
        "mm_rag_is_member(uuid)",
        "mm_rag_can_read_resource(uuid, text, uuid, uuid, text)",
        "mm_rag_can_access_job(uuid, uuid)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {function} FROM PUBLIC")
        op.execute(
            f"GRANT EXECUTE ON FUNCTION {function} TO " + ", ".join(_ROLES)
        )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mm_rag_api"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON ingestion_jobs, ingestion_attempts, "
        "ingestion_generations, ingestion_outbox_events, document_versions, audit_events "
        "TO mm_rag_worker"
    )
    op.execute("GRANT SELECT ON documents TO mm_rag_worker")
    op.execute(
        "GRANT SELECT, UPDATE ON ingestion_outbox_events, ingestion_jobs "
        "TO mm_rag_dispatcher"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
        "TO mm_rag_operations"
    )

    _policy(
        "users",
        "id = NULLIF(current_setting('mm_rag.principal_id', true), '')::uuid "
        "OR current_setting('mm_rag.purpose', true) = 'operations' "
        "OR EXISTS (SELECT 1 FROM workspace_memberships m WHERE m.user_id = users.id "
        "AND m.workspace_id = NULLIF(current_setting('mm_rag.workspace_id', true), '')::uuid)",
    )
    _policy(
        "workspaces",
        "current_setting('mm_rag.purpose', true) = 'operations' "
        "OR mm_rag_is_member(id) "
        "OR created_by_user_id = NULLIF(current_setting('mm_rag.principal_id', true), '')::uuid",
    )
    _policy(
        "workspace_memberships",
        "current_setting('mm_rag.purpose', true) = 'operations' "
        "OR user_id = NULLIF(current_setting('mm_rag.principal_id', true), '')::uuid "
        "OR mm_rag_is_member(workspace_id)",
    )
    for table, resource_type in (
        ("documents", "document"),
        ("collections", "collection"),
        ("conversations", "conversation"),
    ):
        _policy(
            table,
            "current_setting('mm_rag.purpose', true) = 'operations' "
            f"OR mm_rag_can_read_resource(workspace_id, '{resource_type}', id, "
            "created_by_user_id, visibility) "
            "OR (current_setting('mm_rag.purpose', true) = 'worker' "
            "AND workspace_id = NULLIF(current_setting('mm_rag.workspace_id', true), '')::uuid)",
        )

    _policy(
        "resource_acl_grants",
        "current_setting('mm_rag.purpose', true) = 'operations' "
        "OR (mm_rag_is_member(workspace_id) AND workspace_id = "
        "NULLIF(current_setting('mm_rag.workspace_id', true), '')::uuid)",
    )
    _child_policy("document_versions", "documents", "document_id")
    _child_policy("collection_documents", "collections", "collection_id")
    _child_policy("conversation_documents", "conversations", "conversation_id")
    _child_policy("conversation_messages", "conversations", "conversation_id")
    _ingestion_job_policy()
    _job_policy("ingestion_attempts", "job_id")
    _job_policy("ingestion_generations", "job_id")
    _job_policy("ingestion_outbox_events", "job_id")
    _policy(
        "audit_events",
        "current_setting('mm_rag.purpose', true) = 'operations' "
        "OR (workspace_id = NULLIF(current_setting('mm_rag.workspace_id', true), '')::uuid "
        "AND (mm_rag_is_member(workspace_id) "
        "OR current_setting('mm_rag.purpose', true) = 'worker'))",
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    tables = (
        "audit_events",
        "ingestion_outbox_events",
        "ingestion_generations",
        "ingestion_attempts",
        "ingestion_jobs",
        "conversation_messages",
        "conversation_documents",
        "collection_documents",
        "document_versions",
        "resource_acl_grants",
        "conversations",
        "collections",
        "documents",
        "workspace_memberships",
        "workspaces",
        "users",
    )
    for table in tables:
        op.execute(f"DROP POLICY IF EXISTS phase4_scope ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION IF EXISTS mm_rag_can_access_job(uuid, uuid)")
    op.execute("DROP FUNCTION IF EXISTS mm_rag_can_read_resource(uuid, text, uuid, uuid, text)")
    op.execute("DROP FUNCTION IF EXISTS mm_rag_is_member(uuid)")
    for role in reversed(_ROLES):
        op.execute(f"DROP OWNED BY {role}")
        op.execute(f"REVOKE {role} FROM CURRENT_USER")
        op.execute(f"DROP ROLE {role}")


def _policy(table: str, expression: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY phase4_scope ON {table} USING ({expression}) WITH CHECK ({expression})"
    )


def _child_policy(table: str, parent: str, foreign_key: str) -> None:
    expression = (
        "current_setting('mm_rag.purpose', true) = 'operations' OR EXISTS ("
        f"SELECT 1 FROM {parent} parent_row WHERE parent_row.id = {table}.{foreign_key} "
        f"AND parent_row.workspace_id = {table}.workspace_id) OR ("
        "current_setting('mm_rag.purpose', true) = 'worker' AND workspace_id = "
        "NULLIF(current_setting('mm_rag.workspace_id', true), '')::uuid)"
    )
    _policy(table, expression)


def _job_policy(table: str, job_column: str) -> None:
    expression = (
        "current_setting('mm_rag.purpose', true) IN ('operations', 'dispatcher') "
        "OR (current_setting('mm_rag.purpose', true) = 'worker' AND ("
        "workspace_id = NULLIF(current_setting('mm_rag.workspace_id', true), '')::uuid "
        f"OR {table}.{job_column} = NULLIF(current_setting('mm_rag.job_id', true), '')::uuid)) "
        f"OR mm_rag_can_access_job({table}.{job_column}, {table}.workspace_id)"
    )
    _policy(table, expression)


def _ingestion_job_policy() -> None:
    worker_scope = (
        "current_setting('mm_rag.purpose', true) = 'worker' AND ("
        "workspace_id = NULLIF(current_setting('mm_rag.workspace_id', true), '')::uuid "
        "OR id = NULLIF(current_setting('mm_rag.job_id', true), '')::uuid)"
    )
    privileged_scope = (
        "current_setting('mm_rag.purpose', true) IN ('operations', 'dispatcher')"
    )
    document_scope = (
        "EXISTS ("
        "SELECT 1 FROM documents parent_row "
        "WHERE parent_row.id = ingestion_jobs.document_id "
        "AND parent_row.workspace_id = ingestion_jobs.workspace_id)"
    )
    expression = f"{privileged_scope} OR ({worker_scope}) OR {document_scope}"
    op.execute("ALTER TABLE ingestion_jobs ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY phase4_scope ON ingestion_jobs "
        f"USING ({expression}) WITH CHECK ({expression})"
    )
