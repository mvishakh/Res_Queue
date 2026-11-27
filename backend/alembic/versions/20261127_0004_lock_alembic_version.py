"""Lock down Alembic's bookkeeping table.

Supabase grants every new table in `public` to the browser roles by default, and
`alembic_version` is created by Alembic itself (not covered by 0003). Without this,
the public anon key could read or rewrite the schema version through the Data API.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_browser_roles() -> bool:
    return bool(
        op.get_bind().exec_driver_sql(
            "SELECT count(*) = 2 FROM pg_roles WHERE rolname IN ('anon', 'authenticated')"
        ).scalar()
    )


def upgrade() -> None:
    op.execute("ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY")
    if _has_browser_roles():
        op.execute("REVOKE ALL ON public.alembic_version FROM anon, authenticated")


def downgrade() -> None:
    op.execute("ALTER TABLE public.alembic_version DISABLE ROW LEVEL SECURITY")
