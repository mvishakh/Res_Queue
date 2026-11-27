import uuid

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, UUIDPrimaryKey


class ActivityLog(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "activity_logs"
    __table_args__ = (Index("ix_activity_logs_restaurant_time", "restaurant_id", "created_at"),)

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False
    )
    # NULL means the action was performed by the system (e.g. automatic allocation)
    actor_staff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_profiles.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
