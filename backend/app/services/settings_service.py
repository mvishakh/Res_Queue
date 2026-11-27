"""Restaurant settings, WhatsApp configuration and staff management (Owner only)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.core.security import StaffContext
from app.models import Restaurant, RestaurantStaff, StaffProfile, WhatsAppConfiguration
from app.models.enums import StaffRole
from app.schemas.admin import (
    RestaurantUpdate,
    StaffCreateIn,
    StaffOut,
    StaffUpdateIn,
    WhatsAppConfigIn,
    WhatsAppConfigOut,
)
from app.services import supabase_admin
from app.services.common import log_activity


def get_restaurant(db: Session, ctx: StaffContext) -> Restaurant:
    return db.get(Restaurant, ctx.restaurant_id)


def update_restaurant(db: Session, ctx: StaffContext, data: RestaurantUpdate) -> Restaurant:
    r = db.get(Restaurant, ctx.restaurant_id)
    changes = data.model_dump(exclude_unset=True)
    if "timezone" in changes:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(changes["timezone"])
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValidationFailed("Unknown timezone") from exc
    for k, v in changes.items():
        setattr(r, k, v.upper() if k in ("default_phone_region", "currency") and v else v)
    log_activity(db, restaurant_id=r.id, action="RESTAURANT_UPDATED", entity_type="restaurant", entity_id=r.id,
                 actor_id=ctx.staff_id, details=data.model_dump(exclude_unset=True, mode="json"))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("That menu link name is already taken") from exc
    return r


def _whatsapp_out(config: WhatsAppConfiguration) -> WhatsAppConfigOut:
    s = get_settings()
    return WhatsAppConfigOut(
        is_enabled=config.is_enabled,
        phone_number_id=config.phone_number_id,
        menu_template_name=config.menu_template_name,
        table_ready_template_name=config.table_ready_template_name,
        template_language=config.template_language,
        server_credentials_configured=bool(s.whatsapp_access_token and (config.phone_number_id or s.whatsapp_phone_number_id)),
        webhook_configured=bool(s.whatsapp_app_secret and s.whatsapp_webhook_verify_token),
    )


def get_whatsapp_config(db: Session, ctx: StaffContext) -> WhatsAppConfigOut:
    config = db.get(WhatsAppConfiguration, ctx.restaurant_id) or WhatsAppConfiguration(
        restaurant_id=ctx.restaurant_id,
        is_enabled=False,
        menu_template_name="smartqueue_menu_link",
        table_ready_template_name="smartqueue_table_ready",
        template_language="en",
    )
    return _whatsapp_out(config)


def update_whatsapp_config(db: Session, ctx: StaffContext, data: WhatsAppConfigIn) -> WhatsAppConfigOut:
    config = db.get(WhatsAppConfiguration, ctx.restaurant_id)
    if config is None:
        config = WhatsAppConfiguration(restaurant_id=ctx.restaurant_id)
        db.add(config)
    for k, v in data.model_dump().items():
        setattr(config, k, (v.strip() or None) if isinstance(v, str) and k == "phone_number_id" else v)
    log_activity(db, restaurant_id=ctx.restaurant_id, action="WHATSAPP_CONFIG_UPDATED", entity_type="restaurant",
                 entity_id=ctx.restaurant_id, actor_id=ctx.staff_id, details=data.model_dump(mode="json"))
    db.commit()
    return _whatsapp_out(config)


def _staff_out(m: RestaurantStaff) -> StaffOut:
    return StaffOut(
        membership_id=m.id, staff_id=m.staff_id, email=m.staff.email, full_name=m.staff.full_name,
        role=m.role, is_active=m.is_active,
    )


def list_staff(db: Session, ctx: StaffContext) -> list[StaffOut]:
    rows = db.scalars(
        select(RestaurantStaff).where(RestaurantStaff.restaurant_id == ctx.restaurant_id).order_by(RestaurantStaff.created_at)
    )
    return [_staff_out(m) for m in rows]


def add_staff(db: Session, ctx: StaffContext, data: StaffCreateIn) -> StaffOut:
    email = data.email.lower()
    profile = db.scalar(select(StaffProfile).where(func.lower(StaffProfile.email) == email))
    if profile is None:
        try:
            user_id = supabase_admin.create_auth_user(email, data.temporary_password, data.full_name)
        except ConflictError:
            user_id = supabase_admin.find_auth_user_id(email)
            if user_id is None:
                raise
        profile = StaffProfile(id=uuid.UUID(user_id), email=email, full_name=data.full_name)
        db.add(profile)
        db.flush()
    existing = db.scalar(
        select(RestaurantStaff).where(
            RestaurantStaff.restaurant_id == ctx.restaurant_id, RestaurantStaff.staff_id == profile.id
        )
    )
    if existing is not None:
        raise ConflictError("This person is already a staff member of this restaurant")
    m = RestaurantStaff(id=uuid.uuid4(), restaurant_id=ctx.restaurant_id, staff_id=profile.id, role=data.role)
    db.add(m)
    log_activity(db, restaurant_id=ctx.restaurant_id, action="STAFF_ADDED", entity_type="staff", entity_id=profile.id,
                 actor_id=ctx.staff_id, details={"email": email, "role": data.role.value})
    db.commit()
    db.refresh(m)
    return _staff_out(m)


def update_staff(db: Session, ctx: StaffContext, membership_id: uuid.UUID, data: StaffUpdateIn) -> StaffOut:
    m = db.get(RestaurantStaff, membership_id)
    if m is None or m.restaurant_id != ctx.restaurant_id:
        raise NotFoundError("Staff member not found")
    changes = data.model_dump(exclude_unset=True)
    demoting_owner = m.role == StaffRole.OWNER and (
        changes.get("role", StaffRole.OWNER) != StaffRole.OWNER or changes.get("is_active") is False
    )
    if demoting_owner:
        owners = db.scalar(
            select(func.count()).select_from(RestaurantStaff).where(
                RestaurantStaff.restaurant_id == ctx.restaurant_id,
                RestaurantStaff.role == StaffRole.OWNER,
                RestaurantStaff.is_active.is_(True),
            )
        )
        if owners <= 1:
            raise ConflictError("A restaurant must keep at least one active owner")
    for k, v in changes.items():
        setattr(m, k, v)
    m.updated_at = func.now()
    log_activity(db, restaurant_id=ctx.restaurant_id, action="STAFF_UPDATED", entity_type="staff", entity_id=m.staff_id,
                 actor_id=ctx.staff_id, details=data.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    db.refresh(m)
    return _staff_out(m)
