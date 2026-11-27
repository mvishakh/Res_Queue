"""Small helpers shared by the business services."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import ActivityLog, Restaurant


def db_now(db: Session) -> datetime:
    """Current time from the database server, so every business timestamp
    (arrival, allocation, completion) comes from a single clock."""
    return db.scalar(select(func.now()))


def lock_restaurant(db: Session, restaurant_id: uuid.UUID) -> Restaurant:
    """Take a row lock on the restaurant for the rest of the transaction.

    Every operation that changes queue entries, tables or allocations takes this lock
    first. That serializes allocation events per restaurant, so concurrent
    "Mark as Available" clicks are processed one after another in a deterministic order
    and can never hand the same table or customer out twice. Locking the same row
    again within a transaction is a no-op."""
    restaurant = db.scalar(select(Restaurant).where(Restaurant.id == restaurant_id).with_for_update())
    if restaurant is None:
        raise NotFoundError("Restaurant not found")
    return restaurant


def log_activity(
    db: Session,
    *,
    restaurant_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> ActivityLog:
    entry = ActivityLog(
        restaurant_id=restaurant_id,
        actor_staff_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
    )
    db.add(entry)
    return entry
