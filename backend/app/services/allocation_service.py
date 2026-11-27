"""FCFS + Table Matching allocation engine.

Policy (finalized — do not change):
  * Walk the waiting list strictly in original arrival order (FCFS).
  * Each waiting party receives the *smallest* available table whose capacity fits it.
  * A party that fits no available table is skipped for this run only: it stays WAITING
    with its original arrival time and queue number, so it keeps priority over everyone
    who arrived later.
  * Tables are never combined, a table is never given to two parties, a party never
    gets two tables, and a table is never given to a party larger than its capacity.

`plan_allocations` is the pure algorithm (no database). `run_allocation` applies it
inside a PostgreSQL transaction while holding the restaurant row lock.

Why one global sweep is equivalent to "allocate the table that was just freed":
after every run, no waiting party fits any available table (otherwise the sweep would
have seated them). So when one table becomes available, the only possible new match is
that table, and the earliest waiting party that fits it gets it — exactly the policy.
When several tables become free at once, the sweep seats parties in arrival order, each
at its smallest fitting table, so customer priority always wins over table fit.
"""

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.core.security import StaffContext
from app.models import DiningTable, QueueEntry, TableAllocation
from app.models.enums import (
    AllocationEndReason,
    AllocationStatus,
    AllocationType,
    QueueStatus,
    TableStatus,
)
from app.services import whatsapp_service
from app.services.common import db_now, lock_restaurant, log_activity

# ---------------------------------------------------------------------------
# Pure algorithm
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WaitingParty:
    entry_id: uuid.UUID
    party_size: int
    arrived_at: datetime
    sequence_number: int = 0


@dataclass(frozen=True)
class OpenTable:
    table_id: uuid.UUID
    capacity: int
    table_number: str = ""


@dataclass(frozen=True)
class PlannedAllocation:
    entry_id: uuid.UUID
    table_id: uuid.UUID


def _natural_key(value: str) -> tuple:
    """'T2' sorts before 'T10'."""
    return tuple(int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", value) if p)


def fcfs_order(parties: Iterable[WaitingParty]) -> list[WaitingParty]:
    return sorted(parties, key=lambda p: (p.arrived_at, p.sequence_number, str(p.entry_id)))


def plan_allocations(
    waiting: Sequence[WaitingParty], tables: Sequence[OpenTable]
) -> list[PlannedAllocation]:
    """Return the allocations FCFS + Table Matching would make. Deterministic for a given input."""
    # Smallest table first; ties broken by table number, then id, so results are stable.
    remaining = sorted(tables, key=lambda t: (t.capacity, _natural_key(t.table_number), str(t.table_id)))
    plan: list[PlannedAllocation] = []
    for party in fcfs_order(waiting):
        if not remaining:
            break
        for index, table in enumerate(remaining):
            if table.capacity >= party.party_size:
                plan.append(PlannedAllocation(entry_id=party.entry_id, table_id=table.table_id))
                del remaining[index]
                break
        # No fitting table: the party is skipped for this run only and keeps its priority.
    return plan


# ---------------------------------------------------------------------------
# Database application
# ---------------------------------------------------------------------------


def run_allocation(db: Session, restaurant_id: uuid.UUID, *, trigger: str) -> list[TableAllocation]:
    """Allocate available tables to waiting parties. Must run inside the caller's
    transaction; the caller commits. Safe to call at any time (idempotent: if nothing
    fits, nothing changes)."""
    restaurant = lock_restaurant(db, restaurant_id)

    waiting_entries = db.scalars(
        select(QueueEntry)
        .where(QueueEntry.restaurant_id == restaurant.id, QueueEntry.status == QueueStatus.WAITING)
        .order_by(QueueEntry.created_at, QueueEntry.sequence_number)
        .with_for_update(of=QueueEntry)
    ).all()
    if not waiting_entries:
        return []

    open_tables = db.scalars(
        select(DiningTable)
        .where(
            DiningTable.restaurant_id == restaurant.id,
            DiningTable.status == TableStatus.AVAILABLE,
            DiningTable.archived_at.is_(None),
        )
        .with_for_update(of=DiningTable)
    ).all()
    if not open_tables:
        return []

    entries_by_id = {e.id: e for e in waiting_entries}
    tables_by_id = {t.id: t for t in open_tables}
    plan = plan_allocations(
        [WaitingParty(e.id, e.party_size, e.created_at, e.sequence_number) for e in waiting_entries],
        [OpenTable(t.id, t.capacity, t.table_number) for t in open_tables],
    )

    now = db_now(db)
    created: list[TableAllocation] = []
    for item in plan:
        entry = entries_by_id[item.entry_id]
        table = tables_by_id[item.table_id]
        allocation = _assign(db, entry, table, now=now, allocation_type=AllocationType.AUTOMATIC, actor_id=None)
        log_activity(
            db,
            restaurant_id=restaurant.id,
            action="AUTOMATIC_ALLOCATION",
            entity_type="allocation",
            entity_id=allocation.id,
            details={
                "queue_number": entry.queue_number,
                "table_number": table.table_number,
                "party_size": entry.party_size,
                "table_capacity": table.capacity,
                "trigger": trigger,
            },
        )
        created.append(allocation)
    return created


def _assign(
    db: Session,
    entry: QueueEntry,
    table: DiningTable,
    *,
    now: datetime,
    allocation_type: AllocationType,
    actor_id: uuid.UUID | None,
) -> TableAllocation:
    # Defensive checks; the DB also enforces these with a trigger and partial unique indexes.
    if table.capacity < entry.party_size:
        raise ConflictError("Table capacity is smaller than the party size")
    if table.status != TableStatus.AVAILABLE or entry.status != QueueStatus.WAITING:
        raise ConflictError("Table or queue entry is no longer free for allocation")

    allocation = TableAllocation(
        id=uuid.uuid4(),
        restaurant_id=entry.restaurant_id,
        table_id=table.id,
        queue_entry_id=entry.id,
        status=AllocationStatus.ACTIVE,
        allocation_type=allocation_type,
        allocated_at=now,
        allocated_by=actor_id,
    )
    db.add(allocation)
    db.flush()

    table.status = TableStatus.OCCUPIED
    table.current_allocation_id = allocation.id
    entry.status = QueueStatus.ASSIGNED
    entry.assigned_at = now
    db.flush()

    whatsapp_service.queue_table_ready_message(db, entry=entry, table=table, allocation=allocation)
    return allocation


def end_allocation(
    db: Session,
    allocation: TableAllocation,
    *,
    status: AllocationStatus,
    reason: AllocationEndReason,
    now: datetime,
    actor_id: uuid.UUID | None,
) -> None:
    allocation.status = status
    allocation.end_reason = reason
    allocation.ended_at = now
    allocation.ended_by = actor_id
    table = allocation.table
    if table.current_allocation_id == allocation.id:
        table.current_allocation_id = None
        table.status = TableStatus.AVAILABLE
    db.flush()


def _get_active_allocation(db: Session, ctx: StaffContext, allocation_id: uuid.UUID) -> TableAllocation:
    allocation = db.scalar(
        select(TableAllocation)
        .where(TableAllocation.id == allocation_id, TableAllocation.restaurant_id == ctx.restaurant_id)
        .with_for_update(of=TableAllocation)
    )
    if allocation is None:
        raise NotFoundError("Allocation not found")
    if allocation.status != AllocationStatus.ACTIVE:
        raise ConflictError("This allocation is no longer active")
    return allocation


# ---------------------------------------------------------------------------
# Controlled manager overrides (every one is written to the activity log)
# ---------------------------------------------------------------------------


def release_allocation(db: Session, ctx: StaffContext, allocation_id: uuid.UUID, reason: str | None) -> TableAllocation:
    """Customer did not arrive: cancel the allocation, cancel the queue entry, free the
    table and let the engine offer it to the next eligible party."""
    lock_restaurant(db, ctx.restaurant_id)
    allocation = _get_active_allocation(db, ctx, allocation_id)
    now = db_now(db)
    entry = allocation.queue_entry

    end_allocation(
        db, allocation, status=AllocationStatus.RELEASED, reason=AllocationEndReason.NO_SHOW, now=now, actor_id=ctx.staff_id
    )
    entry.status = QueueStatus.CANCELLED
    entry.cancelled_at = now
    entry.cancelled_by = ctx.staff_id
    entry.cancellation_reason = reason or "No-show: allocation released by staff"
    whatsapp_service.supersede_pending_messages(db, allocation_id=allocation.id, reason="Allocation released")

    log_activity(
        db,
        restaurant_id=ctx.restaurant_id,
        action="MANUAL_OVERRIDE_RELEASE",
        entity_type="allocation",
        entity_id=allocation.id,
        actor_id=ctx.staff_id,
        details={
            "queue_number": entry.queue_number,
            "table_number": allocation.table.table_number,
            "reason": entry.cancellation_reason,
        },
    )
    run_allocation(db, ctx.restaurant_id, trigger="allocation_released")
    whatsapp_service.commit_and_dispatch(db)
    return allocation


def reassign_allocation(
    db: Session, ctx: StaffContext, allocation_id: uuid.UUID, target_table_id: uuid.UUID, reason: str | None
) -> TableAllocation:
    """Move an active allocation to a different AVAILABLE table that fits the party."""
    lock_restaurant(db, ctx.restaurant_id)
    old = _get_active_allocation(db, ctx, allocation_id)
    target = db.scalar(
        select(DiningTable)
        .where(
            DiningTable.id == target_table_id,
            DiningTable.restaurant_id == ctx.restaurant_id,
            DiningTable.archived_at.is_(None),
        )
        .with_for_update(of=DiningTable)
    )
    if target is None:
        raise NotFoundError("Table not found")
    if target.id == old.table_id:
        raise ValidationFailed("The party is already allocated to this table")
    if target.status != TableStatus.AVAILABLE:
        raise ConflictError("The selected table is not available")
    entry = old.queue_entry
    if target.capacity < entry.party_size:
        raise ConflictError(
            f"Table {target.table_number} seats {target.capacity}, but the party has {entry.party_size} guests"
        )

    now = db_now(db)
    old_table_number = old.table.table_number
    end_allocation(
        db, old, status=AllocationStatus.RELEASED, reason=AllocationEndReason.REASSIGNED, now=now, actor_id=ctx.staff_id
    )
    whatsapp_service.supersede_pending_messages(db, allocation_id=old.id, reason="Allocation reassigned")
    entry.status = QueueStatus.WAITING  # transient, so _assign's invariant check passes
    new = _assign(db, entry, target, now=now, allocation_type=AllocationType.MANUAL_OVERRIDE, actor_id=ctx.staff_id)
    log_activity(
        db,
        restaurant_id=ctx.restaurant_id,
        action="MANUAL_OVERRIDE_REASSIGN",
        entity_type="allocation",
        entity_id=new.id,
        actor_id=ctx.staff_id,
        details={
            "queue_number": entry.queue_number,
            "from_table": old_table_number,
            "to_table": target.table_number,
            "previous_allocation_id": str(old.id),
            "reason": reason,
        },
    )
    # The previous table is now free; offer it to the queue.
    run_allocation(db, ctx.restaurant_id, trigger="allocation_reassigned")
    whatsapp_service.commit_and_dispatch(db)
    return new
