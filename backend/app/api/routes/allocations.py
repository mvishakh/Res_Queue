import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import ANY_STAFF, QUEUE_STAFF, StaffContext
from app.models.enums import AllocationStatus
from app.schemas.tables import AllocationOut, ReassignIn, ReleaseIn
from app.services import allocation_service, report_service

router = APIRouter(prefix="/allocations", tags=["allocations"])


@router.get("", response_model=list[AllocationOut])
def list_allocations(
    status: AllocationStatus | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    ctx: StaffContext = Depends(ANY_STAFF),
    db: Session = Depends(get_db),
):
    return report_service.list_allocations(db, ctx, status=status, limit=limit)


@router.post("/{allocation_id}/release", response_model=AllocationOut)
def release(allocation_id: uuid.UUID, data: ReleaseIn, ctx: StaffContext = Depends(QUEUE_STAFF), db: Session = Depends(get_db)):
    """Manager override: customer did not arrive — release the table (logged)."""
    allocation = allocation_service.release_allocation(db, ctx, allocation_id, data.reason)
    return report_service.serialize_allocations(db, [allocation])[0]


@router.post("/{allocation_id}/reassign", response_model=AllocationOut)
def reassign(allocation_id: uuid.UUID, data: ReassignIn, ctx: StaffContext = Depends(QUEUE_STAFF), db: Session = Depends(get_db)):
    """Manager override: move a party to another available table that fits (logged)."""
    allocation = allocation_service.reassign_allocation(db, ctx, allocation_id, data.table_id, data.reason)
    return report_service.serialize_allocations(db, [allocation])[0]
