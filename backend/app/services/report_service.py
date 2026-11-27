"""Read-only dashboard, analytics, notification and activity queries. All numbers are
computed from real database records."""

from datetime import timedelta

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import StaffContext
from app.models import ActivityLog, DiningTable, QueueEntry, Restaurant, StaffProfile, TableAllocation, WhatsAppMessage
from app.models.enums import AllocationStatus, MessageStatus, QueueStatus, TableStatus
from app.schemas.admin import ActivityOut, MessageOut
from app.schemas.tables import AllocationOut
from app.services.common import db_now
from app.utils.time import business_date


class OverviewOut(BaseModel):
    total_tables: int
    available_tables: int
    occupied_tables: int
    waiting_customers: int
    allocated_today: int
    registered_today: int
    failed_notifications: int
    recent_registrations: list[dict]
    recent_allocations: list[AllocationOut]
    recent_messages: list[MessageOut]


class DailyPoint(BaseModel):
    date: str
    registered: int
    served: int
    cancelled: int
    avg_wait_minutes: float | None


class AnalyticsOut(BaseModel):
    days: int
    registered: int
    served: int
    cancelled: int
    no_shows: int
    avg_wait_minutes: float | None
    median_party_size: float | None
    daily: list[DailyPoint]
    by_hour: list[dict]
    table_usage: list[dict]


def serialize_allocations(db: Session, allocations: list[TableAllocation]) -> list[AllocationOut]:
    if not allocations:
        return []
    statuses = {
        m.allocation_id: m.status
        for m in db.scalars(
            select(WhatsAppMessage).where(WhatsAppMessage.allocation_id.in_([a.id for a in allocations]))
        )
    }
    return [
        AllocationOut(
            id=a.id,
            table_id=a.table_id,
            table_number=a.table.table_number,
            table_capacity=a.table.capacity,
            queue_entry_id=a.queue_entry_id,
            queue_number=a.queue_entry.queue_number,
            customer_name=a.queue_entry.customer.full_name,
            party_size=a.queue_entry.party_size,
            status=a.status,
            allocation_type=a.allocation_type,
            allocated_at=a.allocated_at,
            ended_at=a.ended_at,
            end_reason=a.end_reason,
            notification_status=statuses.get(a.id),
        )
        for a in allocations
    ]


def list_allocations(
    db: Session, ctx: StaffContext, *, status: AllocationStatus | None = None, limit: int = 100
) -> list[AllocationOut]:
    stmt = select(TableAllocation).where(TableAllocation.restaurant_id == ctx.restaurant_id)
    if status:
        stmt = stmt.where(TableAllocation.status == status)
    stmt = stmt.order_by(TableAllocation.allocated_at.desc()).limit(limit)
    return serialize_allocations(db, list(db.scalars(stmt)))


def list_messages(
    db: Session, ctx: StaffContext, *, status: MessageStatus | None = None, limit: int = 100
) -> list[MessageOut]:
    stmt = select(WhatsAppMessage).where(WhatsAppMessage.restaurant_id == ctx.restaurant_id)
    if status:
        stmt = stmt.where(WhatsAppMessage.status == status)
    msgs = list(db.scalars(stmt.order_by(WhatsAppMessage.created_at.desc()).limit(limit)))
    numbers = dict(
        db.execute(
            select(QueueEntry.id, QueueEntry.queue_number).where(QueueEntry.id.in_([m.queue_entry_id for m in msgs]))
        ).all()
    ) if msgs else {}
    return [
        MessageOut(
            id=m.id,
            message_type=m.message_type,
            status=m.status,
            to_phone=m.to_phone,
            customer_name=m.customer.full_name,
            queue_number=numbers.get(m.queue_entry_id),
            attempt_count=m.attempt_count,
            last_error=m.last_error,
            created_at=m.created_at,
            sent_at=m.sent_at,
            delivered_at=m.delivered_at,
            read_at=m.read_at,
            failed_at=m.failed_at,
        )
        for m in msgs
    ]


def list_activity(db: Session, ctx: StaffContext, limit: int = 100) -> list[ActivityOut]:
    rows = db.execute(
        select(ActivityLog, StaffProfile.full_name)
        .outerjoin(StaffProfile, StaffProfile.id == ActivityLog.actor_staff_id)
        .where(ActivityLog.restaurant_id == ctx.restaurant_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
    ).all()
    return [
        ActivityOut(
            id=a.id, action=a.action, entity_type=a.entity_type, entity_id=a.entity_id,
            actor_name=name, details=a.details, created_at=a.created_at,
        )
        for a, name in rows
    ]


def overview(db: Session, ctx: StaffContext) -> OverviewOut:
    rid = ctx.restaurant_id
    restaurant = db.get(Restaurant, rid)
    today = business_date(db_now(db), restaurant.timezone)

    table_counts = dict(
        db.execute(
            select(DiningTable.status, func.count())
            .where(DiningTable.restaurant_id == rid, DiningTable.archived_at.is_(None))
            .group_by(DiningTable.status)
        ).all()
    )
    waiting = db.scalar(
        select(func.count()).select_from(QueueEntry).where(QueueEntry.restaurant_id == rid, QueueEntry.status == QueueStatus.WAITING)
    )
    registered_today = db.scalar(
        select(func.count()).select_from(QueueEntry).where(QueueEntry.restaurant_id == rid, QueueEntry.business_date == today)
    )
    allocated_today = db.scalar(
        select(func.count())
        .select_from(TableAllocation)
        .join(QueueEntry, QueueEntry.id == TableAllocation.queue_entry_id)
        .where(
            TableAllocation.restaurant_id == rid,
            QueueEntry.business_date == today,
            TableAllocation.status.in_([AllocationStatus.ACTIVE, AllocationStatus.COMPLETED]),
        )
    )
    failed = db.scalar(
        select(func.count()).select_from(WhatsAppMessage).where(
            WhatsAppMessage.restaurant_id == rid, WhatsAppMessage.status == MessageStatus.FAILED,
            WhatsAppMessage.created_at >= func.now() - timedelta(hours=24),
        )
    )
    recent = db.scalars(
        select(QueueEntry).where(QueueEntry.restaurant_id == rid).order_by(QueueEntry.created_at.desc()).limit(6)
    ).all()
    allocations = db.scalars(
        select(TableAllocation).where(TableAllocation.restaurant_id == rid).order_by(TableAllocation.allocated_at.desc()).limit(6)
    ).all()
    return OverviewOut(
        total_tables=sum(table_counts.values()),
        available_tables=table_counts.get(TableStatus.AVAILABLE, 0),
        occupied_tables=table_counts.get(TableStatus.OCCUPIED, 0),
        waiting_customers=waiting,
        allocated_today=allocated_today,
        registered_today=registered_today,
        failed_notifications=failed,
        recent_registrations=[
            {
                "id": str(e.id), "queue_number": e.queue_number, "customer_name": e.customer.full_name,
                "party_size": e.party_size, "status": e.status.value, "arrived_at": e.created_at.isoformat(),
            }
            for e in recent
        ],
        recent_allocations=serialize_allocations(db, list(allocations)),
        recent_messages=list_messages(db, ctx, limit=6),
    )


def analytics(db: Session, ctx: StaffContext, days: int) -> AnalyticsOut:
    rid = ctx.restaurant_id
    restaurant = db.get(Restaurant, rid)
    end = business_date(db_now(db), restaurant.timezone)
    start = end - timedelta(days=days - 1)
    tz = restaurant.timezone

    entries = db.execute(
        select(
            QueueEntry.business_date, QueueEntry.status, QueueEntry.party_size,
            QueueEntry.created_at, QueueEntry.assigned_at, QueueEntry.cancellation_reason,
        ).where(QueueEntry.restaurant_id == rid, QueueEntry.business_date >= start, QueueEntry.business_date <= end)
    ).all()

    # A party counts as served once it was seated (COMPLETED) or is seated now (ASSIGNED).
    served_statuses = {QueueStatus.ASSIGNED, QueueStatus.COMPLETED}
    by_day: dict = {start + timedelta(days=i): {"reg": 0, "served": 0, "cancelled": 0, "waits": []} for i in range(days)}
    waits, sizes, no_shows = [], [], 0
    for d, status, size, created, assigned, reason in entries:
        bucket = by_day[d]
        bucket["reg"] += 1
        sizes.append(size)
        if status in served_statuses and assigned:
            bucket["served"] += 1
            w = (assigned - created).total_seconds() / 60
            bucket["waits"].append(w)
            waits.append(w)
        elif status == QueueStatus.CANCELLED:
            bucket["cancelled"] += 1
            if reason and reason.lower().startswith("no-show"):
                no_shows += 1

    hours = db.execute(
        select(
            func.extract("hour", func.timezone(tz, QueueEntry.created_at)).label("h"), func.count()
        )
        .where(QueueEntry.restaurant_id == rid, QueueEntry.business_date >= start)
        .group_by("h")
        .order_by("h")
    ).all()

    usage = db.execute(
        select(DiningTable.table_number, DiningTable.capacity, func.count(TableAllocation.id))
        .join(TableAllocation, TableAllocation.table_id == DiningTable.id)
        .join(QueueEntry, QueueEntry.id == TableAllocation.queue_entry_id)
        .where(
            DiningTable.restaurant_id == rid,
            QueueEntry.business_date >= start,
            TableAllocation.status.in_([AllocationStatus.ACTIVE, AllocationStatus.COMPLETED]),
        )
        .group_by(DiningTable.table_number, DiningTable.capacity)
        .order_by(func.count(TableAllocation.id).desc())
    ).all()

    def avg(xs: list[float]) -> float | None:
        return round(sum(xs) / len(xs), 1) if xs else None

    sizes.sort()
    median = None
    if sizes:
        mid = len(sizes) // 2
        median = float(sizes[mid]) if len(sizes) % 2 else (sizes[mid - 1] + sizes[mid]) / 2

    return AnalyticsOut(
        days=days,
        registered=len(entries),
        served=sum(b["served"] for b in by_day.values()),
        cancelled=sum(b["cancelled"] for b in by_day.values()),
        no_shows=no_shows,
        avg_wait_minutes=avg(waits),
        median_party_size=median,
        daily=[
            DailyPoint(date=d.isoformat(), registered=b["reg"], served=b["served"], cancelled=b["cancelled"],
                       avg_wait_minutes=avg(b["waits"]))
            for d, b in sorted(by_day.items())
        ],
        by_hour=[{"hour": int(h), "registrations": c} for h, c in hours],
        table_usage=[{"table_number": t, "capacity": cap, "allocations": c} for t, cap, c in usage],
    )

