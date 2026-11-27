import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import QUEUE_STAFF, StaffContext
from app.models.enums import QueueStatus
from app.schemas.queue import CancelIn, QueueEntryOut, QueueListOut, QueueRegistrationIn
from app.services import queue_service
from app.services.common import db_now

router = APIRouter(prefix="/queue", tags=["queue"])


@router.post("", response_model=QueueEntryOut, status_code=status.HTTP_201_CREATED)
def register(data: QueueRegistrationIn, ctx: StaffContext = Depends(QUEUE_STAFF), db: Session = Depends(get_db)):
    """Register a waiting customer: issues a queue number, records the arrival time,
    queues the WhatsApp menu message and runs the allocation engine."""
    entry = queue_service.register_customer(db, ctx, data)
    return queue_service.serialize_entry(db, entry)


@router.get("", response_model=QueueListOut)
def list_queue(
    status_: list[QueueStatus] | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=200, ge=1, le=500),
    ctx: StaffContext = Depends(QUEUE_STAFF),
    db: Session = Depends(get_db),
):
    entries = queue_service.list_entries(db, ctx, statuses=status_, search=search, limit=limit)
    return QueueListOut(server_time=db_now(db), items=queue_service.serialize_entries(db, entries))


@router.get("/{entry_id}", response_model=QueueEntryOut)
def get_entry(entry_id: uuid.UUID, ctx: StaffContext = Depends(QUEUE_STAFF), db: Session = Depends(get_db)):
    return queue_service.serialize_entry(db, queue_service.get_entry(db, ctx, entry_id))


@router.patch("/{entry_id}/cancel", response_model=QueueEntryOut)
def cancel(entry_id: uuid.UUID, data: CancelIn, ctx: StaffContext = Depends(QUEUE_STAFF), db: Session = Depends(get_db)):
    entry = queue_service.cancel_entry(db, ctx, entry_id, data.reason)
    return queue_service.serialize_entry(db, entry)
