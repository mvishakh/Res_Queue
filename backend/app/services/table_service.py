"""Table configuration and the waiter's "Mark as Available" workflow."""

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, PermissionDenied
from app.core.security import StaffContext
from app.models import DiningTable, TableAllocation
from app.models.enums import (
    AllocationEndReason,
    AllocationStatus,
    AllocationType,
    QueueStatus,
    StaffRole,
    TableStatus,
)
from app.schemas.tables import CurrentParty, TableCreateIn, TableOut, TableUpdateIn
from app.services import allocation_service, whatsapp_service
from app.services.allocation_service import _natural_key
from app.services.common import db_now, lock_restaurant, log_activity

# How long after "Mark as Available" the action can still be undone. This is an undo
# window for a mis-tap, not a no-show timeout (no-shows are handled manually).
UNDO_WINDOW = timedelta(minutes=15)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def _current_party(allocation: TableAllocation | None) -> CurrentParty | None:
    if allocation is None or allocation.status != AllocationStatus.ACTIVE:
        return None
    entry = allocation.queue_entry
    return CurrentParty(
        allocation_id=allocation.id,
        queue_entry_id=entry.id,
        queue_number=entry.queue_number,
        customer_name=entry.customer.full_name,
        party_size=entry.party_size,
        allocated_at=allocation.allocated_at,
        allocation_type=allocation.allocation_type,
    )


def serialize_table(table: DiningTable, *, can_undo: bool = False) -> TableOut:
    return TableOut(
        id=table.id,
        table_number=table.table_number,
        capacity=table.capacity,
        status=table.status,
        current=_current_party(table.current_allocation),
        updated_at=table.updated_at,
        can_undo_available=can_undo,
    )


def list_tables(db: Session, ctx: StaffContext) -> list[TableOut]:
    tables = db.scalars(
        select(DiningTable).where(DiningTable.restaurant_id == ctx.restaurant_id, DiningTable.archived_at.is_(None))
    ).all()
    undoable = _undoable_table_ids(db, ctx, [t.id for t in tables])
    tables = sorted(tables, key=lambda t: _natural_key(t.table_number))
    return [serialize_table(t, can_undo=t.id in undoable) for t in tables]


def get_table(db: Session, ctx: StaffContext, table_id: uuid.UUID, *, lock: bool = False) -> DiningTable:
    stmt = select(DiningTable).where(
        DiningTable.id == table_id,
        DiningTable.restaurant_id == ctx.restaurant_id,
        DiningTable.archived_at.is_(None),
    )
    if lock:
        stmt = stmt.with_for_update(of=DiningTable)
    table = db.scalar(stmt)
    if table is None:
        raise NotFoundError("Table not found")
    return table


# ---------------------------------------------------------------------------
# Mark as Available (Waiter Dashboard)
# ---------------------------------------------------------------------------


def mark_available(
    db: Session,
    ctx: StaffContext,
    table_id: uuid.UUID,
    expected_allocation_id: uuid.UUID | None = None,
    *,
    check_expected: bool = False,
) -> tuple[DiningTable, str | None, TableAllocation | None]:
    """Party has left: complete their allocation, free the table and immediately run the
    allocation engine.

    Idempotent: repeating the call on an AVAILABLE table changes nothing. When the client
    says which allocation it saw on the table (`check_expected`), a stale or repeated tap
    (double-click, two waiters at once) whose party has already been replaced by a newly
    seated party is ignored instead of ending the new party's allocation.

    Returns (table, queue number of the party that left, new allocation on this table)."""
    lock_restaurant(db, ctx.restaurant_id)
    table = get_table(db, ctx, table_id, lock=True)

    if check_expected and table.current_allocation_id != expected_allocation_id:
        db.rollback()
        return table, None, None

    freed_queue_number: str | None = None
    if table.status == TableStatus.OCCUPIED:
        now = db_now(db)
        allocation = table.current_allocation
        if allocation is not None and allocation.status == AllocationStatus.ACTIVE:
            entry = allocation.queue_entry
            freed_queue_number = entry.queue_number
            allocation_service.end_allocation(
                db,
                allocation,
                status=AllocationStatus.COMPLETED,
                reason=AllocationEndReason.TABLE_FREED,
                now=now,
                actor_id=ctx.staff_id,
            )
            entry.status = QueueStatus.COMPLETED
            entry.completed_at = now
        else:
            # Occupied without a tracked party (e.g. configured as occupied at setup).
            table.status = TableStatus.AVAILABLE
            table.current_allocation_id = None
        log_activity(
            db,
            restaurant_id=ctx.restaurant_id,
            action="TABLE_MARKED_AVAILABLE",
            entity_type="table",
            entity_id=table.id,
            actor_id=ctx.staff_id,
            details={"table_number": table.table_number, "freed_queue_number": freed_queue_number},
        )
        db.flush()

    new_allocations = allocation_service.run_allocation(db, ctx.restaurant_id, trigger="table_marked_available")
    whatsapp_service.commit_and_dispatch(db)
    db.refresh(table)
    mine = next((a for a in new_allocations if a.table_id == table.id), None)
    return table, freed_queue_number, mine


def _last_freed_allocation(db: Session, table_id: uuid.UUID) -> TableAllocation | None:
    return db.scalar(
        select(TableAllocation)
        .where(
            TableAllocation.table_id == table_id,
            TableAllocation.status == AllocationStatus.COMPLETED,
            TableAllocation.end_reason == AllocationEndReason.TABLE_FREED,
        )
        .order_by(TableAllocation.ended_at.desc())
        .limit(1)
    )


def _allocations_since(db: Session, table_id: uuid.UUID, since) -> list[TableAllocation]:
    return list(
        db.scalars(
            select(TableAllocation).where(TableAllocation.table_id == table_id, TableAllocation.allocated_at >= since)
        )
    )


def _undoable_table_ids(db: Session, ctx: StaffContext, table_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not table_ids:
        return set()
    now = db_now(db)
    result: set[uuid.UUID] = set()
    for table_id in table_ids:
        last = _last_freed_allocation(db, table_id)
        if last is None or last.ended_at is None or now - last.ended_at > UNDO_WINDOW:
            continue
        later = [a for a in _allocations_since(db, table_id, last.ended_at) if a.id != last.id]
        if not later:
            result.add(table_id)
        elif (
            len(later) == 1
            and later[0].status == AllocationStatus.ACTIVE
            and later[0].allocation_type == AllocationType.AUTOMATIC
            and ctx.role in (StaffRole.OWNER, StaffRole.QUEUE_MANAGER)
        ):
            result.add(table_id)
    return result


def undo_mark_available(db: Session, ctx: StaffContext, table_id: uuid.UUID) -> DiningTable:
    """Correct an accidental "Mark as Available".

    * Nobody was seated yet: the previous party's allocation is restored.
    * The engine already gave the table to the next party: only a Queue Manager / Owner may
      correct it. That new allocation is RELEASED, the party returns to WAITING with its
      original arrival time (so it keeps its priority), and the previous party is restored.
    Every correction is written to the activity log."""
    lock_restaurant(db, ctx.restaurant_id)
    table = get_table(db, ctx, table_id, lock=True)
    now = db_now(db)

    previous = _last_freed_allocation(db, table.id)
    if previous is None or previous.ended_at is None:
        raise ConflictError("There is no recent 'Mark as Available' action to undo for this table")
    if now - previous.ended_at > UNDO_WINDOW:
        raise ConflictError("The undo window has passed. Ask a queue manager to correct the records.")

    later = [a for a in _allocations_since(db, table.id, previous.ended_at) if a.id != previous.id]
    reverted: TableAllocation | None = None
    if later:
        if len(later) != 1 or later[0].status != AllocationStatus.ACTIVE or later[0].allocation_type != AllocationType.AUTOMATIC:
            raise ConflictError("The table has changed since it was marked available; this cannot be undone automatically")
        if ctx.role not in (StaffRole.OWNER, StaffRole.QUEUE_MANAGER):
            raise PermissionDenied(
                "The table was already allocated to the next customer. A queue manager must make this correction."
            )
        reverted = later[0]
        reverted_entry = reverted.queue_entry
        allocation_service.end_allocation(
            db, reverted, status=AllocationStatus.RELEASED, reason=AllocationEndReason.REVERTED, now=now, actor_id=ctx.staff_id
        )
        whatsapp_service.supersede_pending_messages(db, allocation_id=reverted.id, reason="Allocation reverted by staff")
        # Back to WAITING with the original created_at — priority is preserved.
        reverted_entry.status = QueueStatus.WAITING
        reverted_entry.assigned_at = None

    prev_entry = previous.queue_entry
    if prev_entry.status != QueueStatus.COMPLETED:
        raise ConflictError("The previous party's record has changed; this cannot be undone automatically")
    previous.status = AllocationStatus.ACTIVE
    previous.ended_at = None
    previous.end_reason = None
    previous.ended_by = None
    prev_entry.status = QueueStatus.ASSIGNED
    prev_entry.completed_at = None
    db.flush()
    table.status = TableStatus.OCCUPIED
    table.current_allocation_id = previous.id
    db.flush()

    log_activity(
        db,
        restaurant_id=ctx.restaurant_id,
        action="TABLE_AVAILABLE_UNDONE",
        entity_type="table",
        entity_id=table.id,
        actor_id=ctx.staff_id,
        details={
            "table_number": table.table_number,
            "restored_queue_number": prev_entry.queue_number,
            "reverted_queue_number": reverted.queue_entry.queue_number if reverted else None,
        },
    )
    allocation_service.run_allocation(db, ctx.restaurant_id, trigger="undo_mark_available")
    whatsapp_service.commit_and_dispatch(db)
    db.refresh(table)
    return table


# ---------------------------------------------------------------------------
# Table configuration (Owner)
# ---------------------------------------------------------------------------


def create_table(db: Session, ctx: StaffContext, data: TableCreateIn) -> DiningTable:
    lock_restaurant(db, ctx.restaurant_id)
    table = DiningTable(
        id=uuid.uuid4(),
        restaurant_id=ctx.restaurant_id,
        table_number=data.table_number,
        capacity=data.capacity,
        status=TableStatus.AVAILABLE,
    )
    db.add(table)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(f"Table {data.table_number} already exists") from exc
    log_activity(
        db,
        restaurant_id=ctx.restaurant_id,
        action="TABLE_CREATED",
        entity_type="table",
        entity_id=table.id,
        actor_id=ctx.staff_id,
        details={"table_number": table.table_number, "capacity": table.capacity},
    )
    allocation_service.run_allocation(db, ctx.restaurant_id, trigger="table_created")
    whatsapp_service.commit_and_dispatch(db)
    db.refresh(table)
    return table


def update_table(db: Session, ctx: StaffContext, table_id: uuid.UUID, data: TableUpdateIn) -> DiningTable:
    lock_restaurant(db, ctx.restaurant_id)
    table = get_table(db, ctx, table_id, lock=True)
    changes: dict = {}
    if data.capacity is not None and data.capacity != table.capacity:
        alloc = table.current_allocation
        if alloc is not None and alloc.status == AllocationStatus.ACTIVE and alloc.queue_entry.party_size > data.capacity:
            raise ConflictError("The party currently at this table is larger than the new capacity")
        changes["capacity"] = [table.capacity, data.capacity]
        table.capacity = data.capacity
    if data.table_number is not None and data.table_number != table.table_number:
        changes["table_number"] = [table.table_number, data.table_number]
        table.table_number = data.table_number
    if not changes:
        db.rollback()
        return table
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(f"Table {data.table_number} already exists") from exc
    log_activity(
        db,
        restaurant_id=ctx.restaurant_id,
        action="TABLE_UPDATED",
        entity_type="table",
        entity_id=table.id,
        actor_id=ctx.staff_id,
        details=changes,
    )
    allocation_service.run_allocation(db, ctx.restaurant_id, trigger="table_updated")
    whatsapp_service.commit_and_dispatch(db)
    db.refresh(table)
    return table


def archive_table(db: Session, ctx: StaffContext, table_id: uuid.UUID) -> None:
    lock_restaurant(db, ctx.restaurant_id)
    table = get_table(db, ctx, table_id, lock=True)
    if table.status != TableStatus.AVAILABLE:
        raise ConflictError("Only an available table can be removed")
    table.archived_at = db_now(db)
    log_activity(
        db,
        restaurant_id=ctx.restaurant_id,
        action="TABLE_REMOVED",
        entity_type="table",
        entity_id=table.id,
        actor_id=ctx.staff_id,
        details={"table_number": table.table_number},
    )
    db.commit()
