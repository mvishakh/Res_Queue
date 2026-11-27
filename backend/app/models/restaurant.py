import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, Timestamps, UUIDPrimaryKey, pg_enum
from app.models.enums import StaffRole


class Restaurant(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "restaurants"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Used in the public menu URL: /menu/<slug>
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    address: Mapped[str | None] = mapped_column(Text)
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata", server_default="Asia/Kolkata")
    # ISO 3166 region used when staff type a phone number without a country code
    default_phone_region: Mapped[str] = mapped_column(String(2), nullable=False, default="IN", server_default="IN")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR", server_default="INR")
    logo_url: Mapped[str | None] = mapped_column(Text)
    menu_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    menu_intro: Mapped[str | None] = mapped_column(Text)


class StaffProfile(CreatedAt, Base):
    """One row per Supabase Auth user. `id` equals auth.users.id."""

    __tablename__ = "staff_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)


class RestaurantStaff(UUIDPrimaryKey, CreatedAt, Base):
    """Membership of a staff member in a restaurant, with their role."""

    __tablename__ = "restaurant_staff"
    __table_args__ = (UniqueConstraint("restaurant_id", "staff_id"),)

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staff_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[StaffRole] = mapped_column(pg_enum(StaffRole, "staff_role"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    restaurant: Mapped[Restaurant] = relationship(lazy="joined")
    staff: Mapped[StaffProfile] = relationship(lazy="joined")
