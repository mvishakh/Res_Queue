import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import ANY_STAFF, OWNER_ONLY, TABLE_FLOOR_STAFF, StaffContext
from app.models.enums import TableStatus
from app.schemas.tables import MarkAvailableIn, MarkAvailableOut, TableCreateIn, TableOut, TableUpdateIn
from app.services import table_service

router = APIRouter(prefix="/tables", tags=["tables"])


@router.get("", response_model=list[TableOut])
def list_tables(ctx: StaffContext = Depends(ANY_STAFF), db: Session = Depends(get_db)):
    return table_service.list_tables(db, ctx)


@router.post("", response_model=TableOut, status_code=status.HTTP_201_CREATED)
def create_table(data: TableCreateIn, ctx: StaffContext = Depends(OWNER_ONLY), db: Session = Depends(get_db)):
    return table_service.serialize_table(table_service.create_table(db, ctx, data))


@router.patch("/{table_id}", response_model=TableOut)
def update_table(
    table_id: uuid.UUID, data: TableUpdateIn, ctx: StaffContext = Depends(OWNER_ONLY), db: Session = Depends(get_db)
):
    return table_service.serialize_table(table_service.update_table(db, ctx, table_id, data))


@router.delete("/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_table(table_id: uuid.UUID, ctx: StaffContext = Depends(OWNER_ONLY), db: Session = Depends(get_db)):
    table_service.archive_table(db, ctx, table_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{table_id}/available", response_model=MarkAvailableOut)
def mark_available(
    table_id: uuid.UUID,
    data: MarkAvailableIn | None = None,
    ctx: StaffContext = Depends(TABLE_FLOOR_STAFF),
    db: Session = Depends(get_db),
):
    """Waiter action: the party has left. Frees the table and triggers automatic allocation.

    Send `{"allocation_id": <the allocation shown on the card>}` (null for an occupied table
    without a tracked party) so that repeated taps cannot end a newly seated party."""
    check = data is not None and "allocation_id" in data.model_fields_set
    table, freed, allocation = table_service.mark_available(
        db, ctx, table_id, data.allocation_id if data else None, check_expected=check
    )
    out = table_service.serialize_table(table)
    if out.current and allocation:
        message = f"Table {table.table_number} allocated to {out.current.queue_number} ({out.current.party_size} guests)"
    elif check and freed is None and table.status == TableStatus.OCCUPIED:
        message = f"Table {table.table_number} was already updated — no change made"
    else:
        message = f"Table {table.table_number} is available — no waiting party fits it right now"
    return MarkAvailableOut(table=out, freed_queue_number=freed, new_allocation=out.current if allocation else None, message=message)


@router.post("/{table_id}/undo-available", response_model=TableOut)
def undo_available(table_id: uuid.UUID, ctx: StaffContext = Depends(ANY_STAFF), db: Session = Depends(get_db)):
    """Correct an accidental 'Mark as Available' (see table_service.undo_mark_available)."""
    return table_service.serialize_table(table_service.undo_mark_available(db, ctx, table_id))
