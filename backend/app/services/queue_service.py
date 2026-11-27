"""Customer registration and waiting-list operations."""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.core.security import StaffContext
from app.models import Customer, QueueCounter, QueueEntry, TableAllocation, WhatsAppMessage
from app.models.enums import AllocationStatus, QueueStatus
from app.models.queue import ACTIVE_QUEUE_STATUSES
from app.schemas.queue import AllocationRef, CustomerOut, MessageSummary, QueueEntryOut, QueueRegistrationIn
from app.services import allocation_service, whatsapp_service
from app.services.common import db_now, lock_restaurant, log_activity
from app.utils.phone import normalize_phone
from app.utils.time import business_date


def next_queue_sequence(db: Session, restaurant_id: uuid.UUID, day) -> int:
    """Atomically issue the next queue number for the restaurant's business day."""
    stmt = (
        insert(QueueCounter)
        .values(restaurant_id=restaurant_id, business_date=day, last_number=1)
        .on_conflict_do_update(
            index_elements=[QueueCounter.restaurant_id, QueueCounter.business_date],
            set_={"last_number": QueueCounter.last_number + 1},
        )
        .returning(QueueCounter.last_number)
    )
    return db.execute(stmt).scalar_one()


def format_queue_number(sequence: int) -> str:
    return f"Q{sequence:03d}"


def register_customer(db: Session, ctx: StaffContext, data: QueueRegistrationIn) -> QueueEntry:
    restaurant = lock_restaurant(db, ctx.restaurant_id)
    phone = normalize_phone(data.phone, restaurant.default_phone_region)
    now = db_now(db)

    customer = db.scalar(
        select(Customer).where(Customer.restaurant_id == restaurant.id, Customer.phone_e164 == phone)
    )
    if customer is not None:
        existing = db.scalar(
            select(QueueEntry).where(
                QueueEntry.customer_id == customer.id, QueueEntry.status.in_(ACTIVE_QUEUE_STATUSES)
            )
        )
        if existing is not None:
            # Do not silently create or merge: show staff the existing registration.
            raise ConflictError(
                f"{phone} already has an active registration ({existing.queue_number})",
                code="duplicate_active_registration",
                details={"existing_entry": serialize_entry(db, existing).model_dump(mode="json")},
            )
        customer.full_name = data.name
    else:
        customer = Customer(id=uuid.uuid4(), restaurant_id=restaurant.id, full_name=data.name, phone_e164=phone)
        db.add(customer)

    if data.whatsapp_consent != customer.whatsapp_consent or customer.whatsapp_consent_at is None:
        customer.whatsapp_consent = data.whatsapp_consent
        customer.whatsapp_consent_at = now  # time the current consent decision was recorded
    db.flush()

    day = business_date(now, restaurant.timezone)
    sequence = next_queue_sequence(db, restaurant.id, day)
    entry = QueueEntry(
        id=uuid.uuid4(),
        restaurant_id=restaurant.id,
        customer_id=customer.id,
        queue_number=format_queue_number(sequence),
        business_date=day,
        sequence_number=sequence,
        party_size=data.party_size,
        notes=data.notes,
        status=QueueStatus.WAITING,
        created_at=now,  # arrival time from the database clock; never modified afterwards
        created_by=ctx.staff_id,
    )
    db.add(entry)
    db.flush()
    db.refresh(entry, ["customer"])

    log_activity(
        db,
        restaurant_id=restaurant.id,
        action="CUSTOMER_REGISTERED",
        entity_type="queue_entry",
        entity_id=entry.id,
        actor_id=ctx.staff_id,
        details={"queue_number": entry.queue_number, "party_size": entry.party_size},
    )
    whatsapp_service.queue_menu_message(db, restaurant=restaurant, entry=entry)
    # A table that fits may already be free.
    allocation_service.run_allocation(db, restaurant.id, trigger="customer_registered")
    whatsapp_service.commit_and_dispatch(db)
    return entry


def get_entry(db: Session, ctx: StaffContext, entry_id: uuid.UUID, *, lock: bool = False) -> QueueEntry:
    stmt = select(QueueEntry).where(QueueEntry.id == entry_id, QueueEntry.restaurant_id == ctx.restaurant_id)
    if lock:
        stmt = stmt.with_for_update(of=QueueEntry)
    entry = db.scalar(stmt)
    if entry is None:
        raise NotFoundError("Queue entry not found")
    return entry


def cancel_entry(db: Session, ctx: StaffContext, entry_id: uuid.UUID, reason: str | None) -> QueueEntry:
    lock_restaurant(db, ctx.restaurant_id)
    entry = get_entry(db, ctx, entry_id, lock=True)
    if entry.status == QueueStatus.ASSIGNED:
        raise ConflictError(
            "This customer already has a table. Release the allocation from Allocation History instead.",
            code="entry_assigned",
        )
    if entry.status != QueueStatus.WAITING:
        raise ConflictError(f"Only waiting customers can be cancelled (status is {entry.status.value})")
    now = db_now(db)
    entry.status = QueueStatus.CANCELLED
    entry.cancelled_at = now
    entry.cancelled_by = ctx.staff_id
    entry.cancellation_reason = reason or "Cancelled by staff"
    log_activity(
        db,
        restaurant_id=ctx.restaurant_id,
        action="QUEUE_CANCELLED",
        entity_type="queue_entry",
        entity_id=entry.id,
        actor_id=ctx.staff_id,
        details={"queue_number": entry.queue_number, "reason": entry.cancellation_reason},
    )
    db.commit()
    return entry


def list_entries(
    db: Session,
    ctx: StaffContext,
    *,
    statuses: list[QueueStatus] | None,
    search: str | None,
    limit: int = 200,
) -> list[QueueEntry]:
    stmt = select(QueueEntry).join(QueueEntry.customer).where(QueueEntry.restaurant_id == ctx.restaurant_id)
    if statuses:
        stmt = stmt.where(QueueEntry.status.in_(statuses))
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Customer.full_name.ilike(term),
                Customer.phone_e164.ilike(term),
                QueueEntry.queue_number.ilike(term),
            )
        )
    if statuses and set(statuses) <= set(ACTIVE_QUEUE_STATUSES):
        # Active list: always the original FCFS order
        stmt = stmt.order_by(QueueEntry.created_at, QueueEntry.sequence_number)
    else:
        stmt = stmt.order_by(QueueEntry.created_at.desc())
    return list(db.scalars(stmt.limit(limit)).unique())


def serialize_entries(db: Session, entries: list[QueueEntry]) -> list[QueueEntryOut]:
    if not entries:
        return []
    ids = [e.id for e in entries]
    active_allocs = {
        a.queue_entry_id: a
        for a in db.scalars(
            select(TableAllocation).where(
                TableAllocation.queue_entry_id.in_(ids), TableAllocation.status == AllocationStatus.ACTIVE
            )
        )
    }
    # Latest allocation of any status, for history display of completed entries
    latest_allocs: dict[uuid.UUID, TableAllocation] = {}
    for a in db.scalars(
        select(TableAllocation).where(TableAllocation.queue_entry_id.in_(ids)).order_by(TableAllocation.allocated_at)
    ):
        latest_allocs[a.queue_entry_id] = a
    messages: dict[uuid.UUID, list[MessageSummary]] = {}
    for m in db.scalars(
        select(WhatsAppMessage).where(WhatsAppMessage.queue_entry_id.in_(ids)).order_by(WhatsAppMessage.created_at)
    ):
        messages.setdefault(m.queue_entry_id, []).append(
            MessageSummary(id=m.id, message_type=m.message_type, status=m.status, last_error=m.last_error)
        )

    out = []
    for e in entries:
        alloc = active_allocs.get(e.id) or latest_allocs.get(e.id)
        out.append(
            QueueEntryOut(
                id=e.id,
                queue_number=e.queue_number,
                business_date=e.business_date.isoformat(),
                party_size=e.party_size,
                notes=e.notes,
                status=e.status,
                arrived_at=e.created_at,
                assigned_at=e.assigned_at,
                completed_at=e.completed_at,
                cancelled_at=e.cancelled_at,
                cancellation_reason=e.cancellation_reason,
                customer=CustomerOut.model_validate(e.customer),
                allocation=AllocationRef(
                    allocation_id=alloc.id,
                    table_id=alloc.table_id,
                    table_number=alloc.table.table_number,
                    allocated_at=alloc.allocated_at,
                )
                if alloc
                else None,
                messages=messages.get(e.id, []),
            )
        )
    return out


def serialize_entry(db: Session, entry: QueueEntry) -> QueueEntryOut:
    return serialize_entries(db, [entry])[0]
