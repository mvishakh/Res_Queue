"""Supabase security: Row Level Security, grants and Realtime publication.

* RLS is enabled on every table. The FastAPI backend connects as the table owner
  (`postgres`), which bypasses RLS, and enforces permissions itself.
* Browser clients (anon / authenticated roles through PostgREST and Realtime) get
  read-only access to just the rows the dashboards need for live updates, scoped to
  restaurants the signed-in staff member belongs to. Waiters cannot read customer or
  queue rows. Nothing is writable from the browser.
* The Supabase-specific parts are skipped on a plain PostgreSQL database (tests).

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ALL_TABLES = [
    "restaurants", "staff_profiles", "restaurant_staff", "customers", "queue_counters", "queue_entries",
    "dining_tables", "table_allocations", "menu_categories", "menu_items", "whatsapp_configurations",
    "whatsapp_messages", "activity_logs",
]
REALTIME_TABLES = ["dining_tables", "table_allocations", "queue_entries", "whatsapp_messages"]

# table -> SQL condition on the member role (NULL role = not a member)
SELECT_POLICIES = {
    "restaurants": "public.smartqueue_staff_role(id) IS NOT NULL",
    "dining_tables": "public.smartqueue_staff_role(restaurant_id) IS NOT NULL",
    "table_allocations": "public.smartqueue_staff_role(restaurant_id) IS NOT NULL",
    "queue_entries": "public.smartqueue_staff_role(restaurant_id) IN ('OWNER', 'QUEUE_MANAGER')",
    "whatsapp_messages": "public.smartqueue_staff_role(restaurant_id) IN ('OWNER', 'QUEUE_MANAGER')",
}


def _is_supabase() -> bool:
    return bool(op.get_bind().exec_driver_sql("SELECT 1 FROM pg_namespace WHERE nspname = 'auth'").scalar())


def upgrade() -> None:
    for table in ALL_TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")

    if not _is_supabase():
        return

    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.smartqueue_staff_role(p_restaurant_id uuid) RETURNS text
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $fn$
            SELECT rs.role::text FROM public.restaurant_staff rs
             WHERE rs.restaurant_id = p_restaurant_id
               AND rs.staff_id = auth.uid()
               AND rs.is_active
        $fn$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION public.smartqueue_staff_role(uuid) FROM PUBLIC, anon")
    op.execute("GRANT EXECUTE ON FUNCTION public.smartqueue_staff_role(uuid) TO authenticated")

    for table in ALL_TABLES:
        op.execute(f"REVOKE ALL ON public.{table} FROM anon, authenticated")
    for table, condition in SELECT_POLICIES.items():
        op.execute(f"GRANT SELECT ON public.{table} TO authenticated")
        op.execute(
            f"CREATE POLICY staff_read_{table} ON public.{table} FOR SELECT TO authenticated USING ({condition})"
        )

    for table in REALTIME_TABLES:
        op.execute(
            f"""
            DO $do$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime')
                   AND NOT EXISTS (
                       SELECT 1 FROM pg_publication_tables
                        WHERE pubname = 'supabase_realtime' AND schemaname = 'public' AND tablename = '{table}'
                   ) THEN
                    ALTER PUBLICATION supabase_realtime ADD TABLE public.{table};
                END IF;
            END
            $do$;
            """
        )


def downgrade() -> None:
    if _is_supabase():
        for table in REALTIME_TABLES:
            op.execute(
                f"""
                DO $do$
                BEGIN
                    IF EXISTS (SELECT 1 FROM pg_publication_tables
                                WHERE pubname = 'supabase_realtime' AND schemaname = 'public' AND tablename = '{table}') THEN
                        ALTER PUBLICATION supabase_realtime DROP TABLE public.{table};
                    END IF;
                END
                $do$;
                """
            )
        for table in SELECT_POLICIES:
            op.execute(f"DROP POLICY IF EXISTS staff_read_{table} ON public.{table}")
        op.execute("DROP FUNCTION IF EXISTS public.smartqueue_staff_role(uuid)")
    for table in ALL_TABLES:
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
