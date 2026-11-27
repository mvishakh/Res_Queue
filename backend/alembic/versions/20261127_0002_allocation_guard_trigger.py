"""Database-level guard for allocations: capacity and restaurant isolation.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION smartqueue_check_allocation() RETURNS trigger
        LANGUAGE plpgsql AS $fn$
        DECLARE
            v_capacity integer;
            v_table_restaurant uuid;
            v_party_size integer;
            v_entry_restaurant uuid;
        BEGIN
            SELECT capacity, restaurant_id INTO v_capacity, v_table_restaurant
              FROM dining_tables WHERE id = NEW.table_id;
            SELECT party_size, restaurant_id INTO v_party_size, v_entry_restaurant
              FROM queue_entries WHERE id = NEW.queue_entry_id;
            IF v_table_restaurant IS DISTINCT FROM NEW.restaurant_id
               OR v_entry_restaurant IS DISTINCT FROM NEW.restaurant_id THEN
                RAISE EXCEPTION 'allocation must reference a table and queue entry of the same restaurant'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF v_capacity < v_party_size THEN
                RAISE EXCEPTION 'table capacity % is smaller than party size %', v_capacity, v_party_size
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END
        $fn$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_table_allocations_guard
        BEFORE INSERT OR UPDATE OF table_id, queue_entry_id, restaurant_id ON table_allocations
        FOR EACH ROW EXECUTE FUNCTION smartqueue_check_allocation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_table_allocations_guard ON table_allocations")
    op.execute("DROP FUNCTION IF EXISTS smartqueue_check_allocation()")
