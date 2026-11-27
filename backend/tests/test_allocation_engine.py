"""Allocation engine against PostgreSQL: transactions, locks, constraints, concurrency."""

import threading

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.core.errors import ConflictError, PermissionDenied
from app.models import ActivityLog, QueueEntry, TableAllocation
from app.models.enums import AllocationEndReason, AllocationStatus, QueueStatus, StaffRole, TableStatus
from app.schemas.queue import QueueRegistrationIn
from app.services import allocation_service, queue_service, table_service
from tests.conftest import ctx_for, make_restaurant, make_staff, make_table

PHONES = iter(f"+9198765{n:05d}" for n in range(10000))


def register(db, ctx, name, size, phone=None, consent=True) -> QueueEntry:
    return queue_service.register_customer(
        db, ctx, QueueRegistrationIn(name=name, phone=phone or next(PHONES), party_size=size, whatsapp_consent=consent)
    )


def occupy_all(db, ctx, restaurant, tables):
    """Seat throwaway parties at the given tables so they start OCCUPIED."""
    for t in tables:
        register(db, ctx, f"Seed {t.table_number}", 1)
        db.refresh(t)
        assert t.status == TableStatus.OCCUPIED


def status_of(db, entry):
    db.expire_all()
    return db.get(QueueEntry, entry.id).status


# ---------------------------------------------------------------------------
# Registration and queue numbers
# ---------------------------------------------------------------------------


def test_registration_issues_sequential_queue_numbers_and_waits(db, manager_ctx):
    a = register(db, manager_ctx, "Arun Kumar", 4)
    b = register(db, manager_ctx, "Vijay", 2)
    assert (a.queue_number, b.queue_number) == ("Q001", "Q002")
    assert a.status == QueueStatus.WAITING and b.status == QueueStatus.WAITING
    assert a.created_at is not None and a.created_at <= b.created_at
    assert a.customer.phone_e164.startswith("+91")


def test_queue_numbers_are_per_restaurant(db):
    r1, r2 = make_restaurant(db, slug="one"), make_restaurant(db, slug="two")
    m1, m2 = make_staff(db, r1, StaffRole.QUEUE_MANAGER), make_staff(db, r2, StaffRole.QUEUE_MANAGER)
    assert register(db, ctx_for(r1, m1, StaffRole.QUEUE_MANAGER), "A", 2).queue_number == "Q001"
    assert register(db, ctx_for(r2, m2, StaffRole.QUEUE_MANAGER), "B", 2).queue_number == "Q001"


def test_phone_is_normalized_to_e164(db, manager_ctx):
    e = register(db, manager_ctx, "Local Format", 2, phone="098765 43210")
    assert e.customer.phone_e164 == "+919876543210"


def test_duplicate_active_registration_is_rejected_with_existing_details(db, manager_ctx):
    first = register(db, manager_ctx, "Arun", 4, phone="+919800000001")
    with pytest.raises(ConflictError) as exc:
        register(db, manager_ctx, "Arun again", 2, phone="9800000001")
    db.rollback()
    assert exc.value.code == "duplicate_active_registration"
    assert exc.value.details["existing_entry"]["queue_number"] == first.queue_number
    assert db.scalar(select(QueueEntry).where(QueueEntry.queue_number == "Q002")) is None


def test_registration_allowed_again_after_cancellation(db, manager_ctx):
    first = register(db, manager_ctx, "Arun", 4, phone="+919800000002")
    queue_service.cancel_entry(db, manager_ctx, first.id, "Left")
    second = register(db, manager_ctx, "Arun", 4, phone="+919800000002")
    assert second.customer_id == first.customer_id and second.queue_number == "Q002"


# ---------------------------------------------------------------------------
# FCFS + Table Matching through the real workflow
# ---------------------------------------------------------------------------


def test_specification_example_end_to_end(db, restaurant, manager_ctx, waiter_ctx):
    t5 = make_table(db, restaurant, "T5", 4)
    occupy_all(db, manager_ctx, restaurant, [t5])

    arun = register(db, manager_ctx, "Arun", 6)
    vijay = register(db, manager_ctx, "Vijay", 2)
    rohit = register(db, manager_ctx, "Rohit", 4)
    karthik = register(db, manager_ctx, "Karthik", 2)
    arrival_before = {e.id: e.created_at for e in (arun, vijay, rohit, karthik)}

    table, freed, allocation = table_service.mark_available(db, waiter_ctx, t5.id)

    assert freed == "Q001"  # the seed party
    assert allocation is not None and allocation.queue_entry_id == vijay.id
    assert table.status == TableStatus.OCCUPIED
    assert status_of(db, vijay) == QueueStatus.ASSIGNED
    for e in (arun, rohit, karthik):
        assert status_of(db, e) == QueueStatus.WAITING

    waiting = queue_service.list_entries(db, manager_ctx, statuses=[QueueStatus.WAITING], search=None)
    assert [e.queue_number for e in waiting] == [arun.queue_number, rohit.queue_number, karthik.queue_number]
    for e in waiting:  # arrival timestamps and queue numbers are untouched
        assert e.created_at == arrival_before[e.id]

    alloc = db.get(TableAllocation, allocation.id)
    assert alloc.status == AllocationStatus.ACTIVE and alloc.allocated_at is not None
    assert db.get(type(t5), t5.id).current_allocation_id == alloc.id


def test_skipped_customer_gets_priority_when_suitable_table_frees(db, restaurant, manager_ctx, waiter_ctx):
    t4, t8 = make_table(db, restaurant, "T4", 4), make_table(db, restaurant, "T8", 8)
    occupy_all(db, manager_ctx, restaurant, [t4, t8])
    arun = register(db, manager_ctx, "Arun", 6)
    vijay = register(db, manager_ctx, "Vijay", 2)
    rohit = register(db, manager_ctx, "Rohit", 6)

    table_service.mark_available(db, waiter_ctx, t4.id)
    assert status_of(db, vijay) == QueueStatus.ASSIGNED
    assert status_of(db, arun) == QueueStatus.WAITING

    _, _, alloc = table_service.mark_available(db, waiter_ctx, t8.id)
    assert alloc.queue_entry_id == arun.id  # earlier than Rohit, who also fits
    assert status_of(db, rohit) == QueueStatus.WAITING


def test_table_stays_available_when_nobody_fits(db, restaurant, manager_ctx, waiter_ctx):
    t2 = make_table(db, restaurant, "T2", 2)
    occupy_all(db, manager_ctx, restaurant, [t2])
    big = register(db, manager_ctx, "Big family", 6)

    table, _, allocation = table_service.mark_available(db, waiter_ctx, t2.id)
    assert allocation is None
    assert table.status == TableStatus.AVAILABLE and table.current_allocation_id is None
    assert status_of(db, big) == QueueStatus.WAITING


def test_registration_is_seated_immediately_when_a_fitting_table_is_free(db, restaurant, manager_ctx):
    t6, t2 = make_table(db, restaurant, "T6", 6), make_table(db, restaurant, "T2", 2)
    e = register(db, manager_ctx, "Pair", 2)
    db.refresh(t2)
    db.refresh(t6)
    assert e.status == QueueStatus.ASSIGNED
    assert t2.status == TableStatus.OCCUPIED  # smallest fitting table
    assert t6.status == TableStatus.AVAILABLE


def test_mark_available_is_idempotent(db, restaurant, manager_ctx, waiter_ctx):
    t2 = make_table(db, restaurant, "T2", 2)
    occupy_all(db, manager_ctx, restaurant, [t2])
    table_service.mark_available(db, waiter_ctx, t2.id)
    table_service.mark_available(db, waiter_ctx, t2.id)
    logs = db.scalars(select(ActivityLog).where(ActivityLog.action == "TABLE_MARKED_AVAILABLE")).all()
    assert len(logs) == 1


def test_completed_party_is_never_allocated_again(db, restaurant, manager_ctx, waiter_ctx):
    t2 = make_table(db, restaurant, "T2", 2)
    seeded = register(db, manager_ctx, "Seed", 2)
    table_service.mark_available(db, waiter_ctx, t2.id)
    assert status_of(db, seeded) == QueueStatus.COMPLETED
    db.refresh(t2)
    assert t2.status == TableStatus.AVAILABLE


def test_cancelled_customer_is_excluded_from_allocation(db, restaurant, manager_ctx, waiter_ctx):
    t2 = make_table(db, restaurant, "T2", 2)
    occupy_all(db, manager_ctx, restaurant, [t2])
    first = register(db, manager_ctx, "Cancels", 2)
    second = register(db, manager_ctx, "Stays", 2)
    cancelled = queue_service.cancel_entry(db, manager_ctx, first.id, "Changed plans")
    assert cancelled.status == QueueStatus.CANCELLED and cancelled.cancelled_at is not None

    _, _, alloc = table_service.mark_available(db, waiter_ctx, t2.id)
    assert alloc.queue_entry_id == second.id
    assert db.get(QueueEntry, first.id).queue_number == "Q002"  # history preserved


def test_cannot_cancel_an_assigned_entry(db, restaurant, manager_ctx):
    make_table(db, restaurant, "T2", 2)
    e = register(db, manager_ctx, "Seated", 2)
    with pytest.raises(ConflictError):
        queue_service.cancel_entry(db, manager_ctx, e.id, None)


# ---------------------------------------------------------------------------
# Database guarantees
# ---------------------------------------------------------------------------


def test_database_rejects_second_active_allocation_for_table(db, restaurant, manager_ctx):
    t4 = make_table(db, restaurant, "T4", 4)
    seated = register(db, manager_ctx, "Seated", 2)
    other = register(db, manager_ctx, "Other", 2)
    assert seated.status == QueueStatus.ASSIGNED
    db.add(TableAllocation(restaurant_id=restaurant.id, table_id=t4.id, queue_entry_id=other.id,
                           status=AllocationStatus.ACTIVE, allocated_at=seated.assigned_at))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_database_rejects_second_active_allocation_for_customer(db, restaurant, manager_ctx):
    make_table(db, restaurant, "T4", 4)
    t6 = make_table(db, restaurant, "T6", 6)
    seated = register(db, manager_ctx, "Seated", 2)
    db.add(TableAllocation(restaurant_id=restaurant.id, table_id=t6.id, queue_entry_id=seated.id,
                           status=AllocationStatus.ACTIVE, allocated_at=seated.assigned_at))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_database_trigger_rejects_insufficient_capacity(db, restaurant, manager_ctx):
    t2 = make_table(db, restaurant, "T2", 2)
    occupy_all(db, manager_ctx, restaurant, [t2])
    big = register(db, manager_ctx, "Big", 6)
    db.add(TableAllocation(restaurant_id=restaurant.id, table_id=t2.id, queue_entry_id=big.id,
                           status=AllocationStatus.COMPLETED, allocated_at=big.created_at))
    with pytest.raises(IntegrityError, match="capacity"):
        db.commit()
    db.rollback()


def test_database_trigger_rejects_cross_restaurant_allocation(db, restaurant, manager_ctx):
    other_r = make_restaurant(db, slug="other")
    foreign_table = make_table(db, other_r, "T1", 4)
    e = register(db, manager_ctx, "Guest", 2)
    db.add(TableAllocation(restaurant_id=restaurant.id, table_id=foreign_table.id, queue_entry_id=e.id,
                           status=AllocationStatus.COMPLETED, allocated_at=e.created_at))
    with pytest.raises(IntegrityError, match="same restaurant"):
        db.commit()
    db.rollback()


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def _run_parallel(fns):
    barrier = threading.Barrier(len(fns))
    errors: list[BaseException] = []

    def wrap(fn):
        def run():
            barrier.wait()
            try:
                fn()
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
        return run

    threads = [threading.Thread(target=wrap(f)) for f in fns]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return errors


def test_simultaneous_table_availability_never_double_allocates(db, restaurant, manager_ctx, waiter_ctx):
    tables = [make_table(db, restaurant, f"T{i}", 4) for i in range(1, 7)]
    occupy_all(db, manager_ctx, restaurant, tables)
    waiting = [register(db, manager_ctx, f"Guest {i}", 2 + (i % 3)) for i in range(4)]

    def free(table_id):
        def go():
            with SessionLocal() as s:
                table_service.mark_available(s, waiter_ctx, table_id)
        return go

    errors = _run_parallel([free(t.id) for t in tables])
    assert errors == []

    db.expire_all()
    active = db.scalars(select(TableAllocation).where(TableAllocation.status == AllocationStatus.ACTIVE)).all()
    assert len(active) == 4  # each waiting party got exactly one table
    assert len({a.table_id for a in active}) == 4
    assert {a.queue_entry_id for a in active} == {e.id for e in waiting}
    # FCFS: the earliest parties were processed first, each at a fitting table
    for a in active:
        assert a.table.capacity >= a.queue_entry.party_size


def test_repeated_taps_on_same_table_free_only_the_party_the_waiter_saw(db, restaurant, manager_ctx, waiter_ctx):
    t2 = make_table(db, restaurant, "T2", 2)
    seed = register(db, manager_ctx, "Seed", 2)
    nxt = register(db, manager_ctx, "Next", 2)
    db.refresh(t2)
    seen_allocation = t2.current_allocation_id

    def tap():
        with SessionLocal() as s:
            table_service.mark_available(s, waiter_ctx, t2.id, seen_allocation, check_expected=True)

    assert _run_parallel([tap, tap, tap]) == []
    db.expire_all()
    assert status_of(db, seed) == QueueStatus.COMPLETED
    # Next was seated by the first tap; the repeated taps must not end Next's allocation.
    assert status_of(db, nxt) == QueueStatus.ASSIGNED
    active_for_table = db.scalars(
        select(TableAllocation).where(TableAllocation.table_id == t2.id, TableAllocation.status == AllocationStatus.ACTIVE)
    ).all()
    assert len(active_for_table) == 1 and active_for_table[0].queue_entry_id == nxt.id


def test_concurrent_registrations_get_unique_queue_numbers(db, restaurant, manager_ctx):
    def reg(i):
        def go():
            with SessionLocal() as s:
                register(s, manager_ctx, f"Guest {i}", 2, phone=f"+91990000{i:04d}")
        return go

    assert _run_parallel([reg(i) for i in range(10)]) == []
    numbers = db.scalars(select(QueueEntry.queue_number).where(QueueEntry.restaurant_id == restaurant.id)).all()
    assert sorted(numbers) == [f"Q{i:03d}" for i in range(1, 11)]


# ---------------------------------------------------------------------------
# Controlled corrections
# ---------------------------------------------------------------------------


def test_release_no_show_frees_table_for_next_party(db, restaurant, manager_ctx):
    t2 = make_table(db, restaurant, "T2", 2)
    no_show = register(db, manager_ctx, "No show", 2)
    nxt = register(db, manager_ctx, "Next", 2)
    alloc = db.scalar(select(TableAllocation).where(TableAllocation.queue_entry_id == no_show.id))

    allocation_service.release_allocation(db, manager_ctx, alloc.id, None)
    db.expire_all()
    assert db.get(TableAllocation, alloc.id).status == AllocationStatus.RELEASED
    assert db.get(TableAllocation, alloc.id).end_reason == AllocationEndReason.NO_SHOW
    assert status_of(db, no_show) == QueueStatus.CANCELLED
    assert status_of(db, nxt) == QueueStatus.ASSIGNED
    assert db.scalar(select(ActivityLog).where(ActivityLog.action == "MANUAL_OVERRIDE_RELEASE")) is not None
    assert db.get(type(t2), t2.id).status == TableStatus.OCCUPIED


def test_reassign_moves_party_and_offers_old_table(db, restaurant, manager_ctx):
    t2, t4 = make_table(db, restaurant, "T2", 2), make_table(db, restaurant, "T4", 4)
    pair = register(db, manager_ctx, "Pair", 2)  # gets T2
    old = db.scalar(select(TableAllocation).where(TableAllocation.queue_entry_id == pair.id))
    assert old.table_id == t2.id

    new = allocation_service.reassign_allocation(db, manager_ctx, old.id, t4.id, "Asked for a bigger table")
    db.expire_all()
    assert new.table_id == t4.id and new.allocation_type.value == "MANUAL_OVERRIDE"
    assert db.get(TableAllocation, old.id).end_reason == AllocationEndReason.REASSIGNED
    assert db.get(type(t2), t2.id).status == TableStatus.AVAILABLE


def test_reassign_rejects_too_small_table(db, restaurant, manager_ctx):
    make_table(db, restaurant, "T6", 6)
    t2 = make_table(db, restaurant, "T2", 2)
    family = register(db, manager_ctx, "Family", 5)  # T2 is too small, so family gets T6
    alloc = db.scalar(select(TableAllocation).where(TableAllocation.queue_entry_id == family.id))
    with pytest.raises(ConflictError):
        allocation_service.reassign_allocation(db, manager_ctx, alloc.id, t2.id, None)


def test_waiter_can_undo_accidental_mark_available(db, restaurant, manager_ctx, waiter_ctx):
    t2 = make_table(db, restaurant, "T2", 2)
    diner = register(db, manager_ctx, "Still eating", 2)
    table_service.mark_available(db, waiter_ctx, t2.id)
    assert status_of(db, diner) == QueueStatus.COMPLETED

    table = table_service.undo_mark_available(db, waiter_ctx, t2.id)
    assert table.status == TableStatus.OCCUPIED
    assert status_of(db, diner) == QueueStatus.ASSIGNED
    assert db.scalar(select(ActivityLog).where(ActivityLog.action == "TABLE_AVAILABLE_UNDONE")) is not None


def test_undo_after_reallocation_requires_manager_and_restores_priority(db, restaurant, manager_ctx, waiter_ctx):
    t2 = make_table(db, restaurant, "T2", 2)
    diner = register(db, manager_ctx, "Still eating", 2)
    nxt = register(db, manager_ctx, "Next", 2)
    original_arrival = nxt.created_at
    table_service.mark_available(db, waiter_ctx, t2.id)
    assert status_of(db, nxt) == QueueStatus.ASSIGNED

    with pytest.raises(PermissionDenied):
        table_service.undo_mark_available(db, waiter_ctx, t2.id)
    db.rollback()

    table_service.undo_mark_available(db, manager_ctx, t2.id)
    db.expire_all()
    assert status_of(db, diner) == QueueStatus.ASSIGNED
    restored = db.get(QueueEntry, nxt.id)
    assert restored.status == QueueStatus.WAITING
    assert restored.created_at == original_arrival
    reverted = db.scalar(
        select(TableAllocation).where(TableAllocation.queue_entry_id == nxt.id)
    )
    assert reverted.status == AllocationStatus.RELEASED and reverted.end_reason == AllocationEndReason.REVERTED
