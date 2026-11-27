import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, UUIDPrimaryKey, pg_enum
from app.models.enums import MessageStatus, MessageType
from app.models.queue import Customer


class WhatsAppConfiguration(Base):
    """Per-restaurant WhatsApp settings. The Meta access token itself is a server
    environment secret and is never stored in the database."""

    __tablename__ = "whatsapp_configurations"

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), primary_key=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Falls back to WHATSAPP_PHONE_NUMBER_ID when empty
    phone_number_id: Mapped[str | None] = mapped_column(String(64))
    menu_template_name: Mapped[str] = mapped_column(
        String(512), nullable=False, default="smartqueue_menu_link", server_default="smartqueue_menu_link"
    )
    table_ready_template_name: Mapped[str] = mapped_column(
        String(512), nullable=False, default="smartqueue_table_ready", server_default="smartqueue_table_ready"
    )
    template_language: Mapped[str] = mapped_column(String(15), nullable=False, default="en", server_default="en")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class WhatsAppMessage(UUIDPrimaryKey, CreatedAt, Base):
    """Outgoing message record. Also acts as the transactional outbox: rows are inserted
    in the same DB transaction as the business change, then delivered by Celery."""

    __tablename__ = "whatsapp_messages"
    __table_args__ = (
        Index("ix_whatsapp_messages_outbox", "status", "next_attempt_at"),
        Index("ix_whatsapp_messages_restaurant_time", "restaurant_id", "created_at"),
        Index(
            "uq_whatsapp_messages_menu_per_entry",
            "queue_entry_id",
            unique=True,
            postgresql_where=text("message_type = 'MENU'"),
        ),
        Index(
            "uq_whatsapp_messages_ready_per_allocation",
            "allocation_id",
            unique=True,
            postgresql_where=text("message_type = 'TABLE_READY'"),
        ),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), nullable=False)
    queue_entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("queue_entries.id"), nullable=False, index=True)
    allocation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("table_allocations.id"))
    message_type: Mapped[MessageType] = mapped_column(pg_enum(MessageType, "whatsapp_message_type"), nullable=False)
    to_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    template_name: Mapped[str | None] = mapped_column(String(512))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[MessageStatus] = mapped_column(
        pg_enum(MessageStatus, "whatsapp_message_status"), nullable=False, default=MessageStatus.PENDING
    )
    wa_message_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    customer: Mapped[Customer] = relationship(lazy="joined")
