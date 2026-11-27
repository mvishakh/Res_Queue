import uuid

from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.security import StaffContext
from app.models import Customer, QueueEntry
from app.models.enums import QueueStatus
from app.schemas.queue import CustomerOut, QueueEntryOut
from app.services import queue_service


class CustomerSummaryOut(CustomerOut):
    visits: int
    completed_visits: int
    last_visit_at: str | None


class CustomerDetailOut(BaseModel):
    customer: CustomerOut
    history: list[QueueEntryOut]


def list_customers(db: Session, ctx: StaffContext, search: str | None, limit: int = 100) -> list[CustomerSummaryOut]:
    stats = (
        select(
            QueueEntry.customer_id.label("cid"),
            func.count().label("visits"),
            func.count().filter(QueueEntry.status == QueueStatus.COMPLETED).label("completed"),
            func.max(QueueEntry.created_at).label("last_visit"),
        )
        .where(QueueEntry.restaurant_id == ctx.restaurant_id)
        .group_by(QueueEntry.customer_id)
        .subquery()
    )
    stmt = (
        select(Customer, stats.c.visits, stats.c.completed, stats.c.last_visit)
        .outerjoin(stats, stats.c.cid == Customer.id)
        .where(Customer.restaurant_id == ctx.restaurant_id)
    )
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(or_(Customer.full_name.ilike(term), Customer.phone_e164.ilike(term)))
    stmt = stmt.order_by(stats.c.last_visit.desc().nulls_last()).limit(limit)
    return [
        CustomerSummaryOut(
            **CustomerOut.model_validate(c).model_dump(),
            visits=visits or 0,
            completed_visits=completed or 0,
            last_visit_at=last.isoformat() if last else None,
        )
        for c, visits, completed, last in db.execute(stmt)
    ]


def get_customer(db: Session, ctx: StaffContext, customer_id: uuid.UUID) -> CustomerDetailOut:
    c = db.get(Customer, customer_id)
    if c is None or c.restaurant_id != ctx.restaurant_id:
        raise NotFoundError("Customer not found")
    entries = list(
        db.scalars(select(QueueEntry).where(QueueEntry.customer_id == c.id).order_by(QueueEntry.created_at.desc()))
    )
    return CustomerDetailOut(customer=CustomerOut.model_validate(c), history=queue_service.serialize_entries(db, entries))
