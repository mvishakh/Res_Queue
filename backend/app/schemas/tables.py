import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import AllocationEndReason, AllocationStatus, AllocationType, MessageStatus, TableStatus


class TableCreateIn(BaseModel):
    table_number: str = Field(min_length=1, max_length=20)
    capacity: int = Field(ge=1, le=50)

    @field_validator("table_number")
    @classmethod
    def clean(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("Table number is required")
        return v


class TableUpdateIn(BaseModel):
    table_number: str | None = Field(default=None, min_length=1, max_length=20)
    capacity: int | None = Field(default=None, ge=1, le=50)

    @field_validator("table_number")
    @classmethod
    def clean(cls, v: str | None) -> str | None:
        return v.strip().upper() if v else v


class CurrentParty(BaseModel):
    """What floor staff need to know about the party at a table — no phone numbers."""

    allocation_id: uuid.UUID
    queue_entry_id: uuid.UUID
    queue_number: str
    customer_name: str
    party_size: int
    allocated_at: datetime
    allocation_type: AllocationType


class TableOut(BaseModel):
    id: uuid.UUID
    table_number: str
    capacity: int
    status: TableStatus
    current: CurrentParty | None
    updated_at: datetime
    can_undo_available: bool = False


class MarkAvailableIn(BaseModel):
    # The allocation currently displayed on the waiter's card (guards against stale taps)
    allocation_id: uuid.UUID | None = None


class MarkAvailableOut(BaseModel):
    table: TableOut
    freed_queue_number: str | None
    new_allocation: CurrentParty | None
    message: str


class AllocationOut(BaseModel):
    id: uuid.UUID
    table_id: uuid.UUID
    table_number: str
    table_capacity: int
    queue_entry_id: uuid.UUID
    queue_number: str
    customer_name: str
    party_size: int
    status: AllocationStatus
    allocation_type: AllocationType
    allocated_at: datetime
    ended_at: datetime | None
    end_reason: AllocationEndReason | None
    notification_status: MessageStatus | None


class ReleaseIn(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class ReassignIn(BaseModel):
    table_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=255)
