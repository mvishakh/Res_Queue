import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, Timestamps, UUIDPrimaryKey, pg_enum
from app.models.enums import QueueStatus


class Customer(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("restaurant_id", "phone_e164"),)

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Normalized E.164 format, e.g. +919876543210
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False)
    whatsapp_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    whatsapp_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QueueCounter(Base):
    """Per-restaurant, per-business-day counter used to issue Q001, Q002, ..."""

    __tablename__ = "queue_counters"

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), primary_key=True
    )
    business_date: Mapped[date] = mapped_column(Date, primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


ACTIVE_QUEUE_STATUSES = (QueueStatus.WAITING, QueueStatus.ASSIGNED)


class QueueEntry(UUIDPrimaryKey, CreatedAt, Base):
    """A single visit to the waiting list. `created_at` is the arrival time (server clock)
    and is never modified — it is the FCFS priority key."""

    __tablename__ = "queue_entries"
    __table_args__ = (
        UniqueConstraint("restaurant_id", "business_date", "sequence_number"),
        CheckConstraint("party_size BETWEEN 1 AND 50", name="party_size_range"),
        # A customer can have at most one active (WAITING/ASSIGNED) entry per restaurant.
        Index(
            "uq_queue_entries_one_active_per_customer",
            "restaurant_id",
            "customer_id",
            unique=True,
            postgresql_where=text("status IN ('WAITING', 'ASSIGNED')"),
        ),
        Index("ix_queue_entries_fcfs", "restaurant_id", "status", "created_at", "sequence_number"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    queue_number: Mapped[str] = mapped_column(String(16), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    party_size: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[QueueStatus] = mapped_column(
        pg_enum(QueueStatus, "queue_status"), nullable=False, default=QueueStatus.WAITING
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_profiles.id", ondelete="SET NULL"))
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_profiles.id", ondelete="SET NULL"))

    customer: Mapped[Customer] = relationship(lazy="joined")
