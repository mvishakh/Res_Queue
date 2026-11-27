import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import MessageStatus, MessageType, StaffRole


class MembershipOut(BaseModel):
    restaurant_id: uuid.UUID
    restaurant_name: str
    restaurant_slug: str
    role: StaffRole
    dashboard: str  # "queue-manager" | "waiter"


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    memberships: list[MembershipOut]


class RestaurantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    address: str | None
    contact_phone: str | None
    timezone: str
    default_phone_region: str
    currency: str
    logo_url: str | None
    menu_published: bool
    menu_intro: str | None


class RestaurantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=3, max_length=80)
    address: str | None = Field(default=None, max_length=500)
    contact_phone: str | None = Field(default=None, max_length=20)
    timezone: str | None = Field(default=None, max_length=64)
    default_phone_region: str | None = Field(default=None, min_length=2, max_length=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    logo_url: str | None = Field(default=None, max_length=1000)
    menu_published: bool | None = None
    menu_intro: str | None = Field(default=None, max_length=1000)

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, v: str | None) -> str | None:
        if v is not None and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", v):
            raise ValueError("Use lowercase letters, numbers and hyphens only")
        return v


class WhatsAppConfigOut(BaseModel):
    is_enabled: bool
    phone_number_id: str | None
    menu_template_name: str
    table_ready_template_name: str
    template_language: str
    server_credentials_configured: bool
    webhook_configured: bool


class WhatsAppConfigIn(BaseModel):
    is_enabled: bool
    phone_number_id: str | None = Field(default=None, max_length=64)
    menu_template_name: str = Field(min_length=1, max_length=512)
    table_ready_template_name: str = Field(min_length=1, max_length=512)
    template_language: str = Field(min_length=2, max_length=15)


class StaffOut(BaseModel):
    membership_id: uuid.UUID
    staff_id: uuid.UUID
    email: str
    full_name: str
    role: StaffRole
    is_active: bool


class StaffCreateIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    role: StaffRole
    temporary_password: str = Field(min_length=8, max_length=72)


class StaffUpdateIn(BaseModel):
    role: StaffRole | None = None
    is_active: bool | None = None


class MessageOut(BaseModel):
    id: uuid.UUID
    message_type: MessageType
    status: MessageStatus
    to_phone: str
    customer_name: str
    queue_number: str | None
    attempt_count: int
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None
    delivered_at: datetime | None
    read_at: datetime | None
    failed_at: datetime | None


class ActivityOut(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    actor_name: str | None
    details: dict
    created_at: datetime
