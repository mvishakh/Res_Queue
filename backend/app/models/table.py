import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, Timestamps, UUIDPrimaryKey, pg_enum
from app.models.enums import AllocationEndReason, AllocationStatus, AllocationType, TableStatus
from app.models.queue import QueueEntry


class DiningTable(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "dining_tables"
    __table_args__ = (
        Index(
            "uq_dining_tables_number_per_restaurant",
            "restaurant_id",
            "table_number",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
        CheckConstraint("capacity BETWEEN 1 AND 50", name="capacity_range"),
        # A table that references an allocation must be OCCUPIED.
        CheckConstraint(
            "current_allocation_id IS NULL OR status = 'OCCUPIED'", name="allocation_implies_occupied"
        ),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    table_number: Mapped[str] = mapped_column(String(20), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[TableStatus] = mapped_column(
        pg_enum(TableStatus, "table_status"), nullable=False, default=TableStatus.AVAILABLE
    )
    current_allocation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("table_allocations.id", ondelete="SET NULL", use_alter=True)
    )
    # Removed from the floor plan (kept for allocation history). This is configuration,
    # not a table status: archived tables are simply not part of the restaurant anymore.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    current_allocation: Mapped["TableAllocation | None"] = relationship(
        foreign_keys=[current_allocation_id], lazy="select", post_update=True
    )


class TableAllocation(UUIDPrimaryKey, CreatedAt, Base):
    """Immutable-ish history of which queue entry got which table. Rows are never deleted."""

    __tablename__ = "table_allocations"
    __table_args__ = (
        Index(
            "uq_table_allocations_one_active_per_table",
            "table_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index(
            "uq_table_allocations_one_active_per_entry",
            "queue_entry_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index("ix_table_allocations_restaurant_time", "restaurant_id", "allocated_at"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False
    )
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dining_tables.id"), nullable=False, index=True)
    queue_entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("queue_entries.id"), nullable=False, index=True)
    status: Mapped[AllocationStatus] = mapped_column(
        pg_enum(AllocationStatus, "allocation_status"), nullable=False, default=AllocationStatus.ACTIVE
    )
    allocation_type: Mapped[AllocationType] = mapped_column(
        pg_enum(AllocationType, "allocation_type"), nullable=False, default=AllocationType.AUTOMATIC
    )
    allocated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    allocated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_profiles.id", ondelete="SET NULL"))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[AllocationEndReason | None] = mapped_column(
        pg_enum(AllocationEndReason, "allocation_end_reason")
    )
    ended_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_profiles.id", ondelete="SET NULL"))

    table: Mapped[DiningTable] = relationship(foreign_keys=[table_id], lazy="joined")
    queue_entry: Mapped[QueueEntry] = relationship(lazy="joined")
