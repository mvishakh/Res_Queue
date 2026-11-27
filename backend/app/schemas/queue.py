import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import MessageStatus, MessageType, QueueStatus


class QueueRegistrationIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=5, max_length=32)
    party_size: int = Field(ge=1, le=50)
    notes: str | None = Field(default=None, max_length=500)
    whatsapp_consent: bool

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("Name is required")
        return v

    @field_validator("notes")
    @classmethod
    def strip_notes(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        return v or None


class CancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    phone_e164: str
    whatsapp_consent: bool
    whatsapp_consent_at: datetime | None


class MessageSummary(BaseModel):
    id: uuid.UUID
    message_type: MessageType
    status: MessageStatus
    last_error: str | None


class AllocationRef(BaseModel):
    allocation_id: uuid.UUID
    table_id: uuid.UUID
    table_number: str
    allocated_at: datetime


class QueueEntryOut(BaseModel):
    id: uuid.UUID
    queue_number: str
    business_date: str
    party_size: int
    notes: str | None
    status: QueueStatus
    arrived_at: datetime
    assigned_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    customer: CustomerOut
    allocation: AllocationRef | None = None
    messages: list[MessageSummary] = []


class QueueListOut(BaseModel):
    server_time: datetime
    items: list[QueueEntryOut]
