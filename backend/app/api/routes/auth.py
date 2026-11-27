from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_staff
from app.models import RestaurantStaff, StaffProfile
from app.models.enums import StaffRole
from app.schemas.admin import MeOut, MembershipOut

router = APIRouter(prefix="/auth", tags=["auth"])


def dashboard_for(role: StaffRole) -> str:
    """Owners/administrators and queue managers use Dashboard 1; waiters use Dashboard 2."""
    return "waiter" if role == StaffRole.WAITER else "queue-manager"


@router.get("/me", response_model=MeOut)
def me(staff: StaffProfile = Depends(get_current_staff), db: Session = Depends(get_db)) -> MeOut:
    memberships = db.scalars(
        select(RestaurantStaff).where(RestaurantStaff.staff_id == staff.id, RestaurantStaff.is_active.is_(True))
    ).all()
    return MeOut(
        id=staff.id,
        email=staff.email,
        full_name=staff.full_name,
        memberships=[
            MembershipOut(
                restaurant_id=m.restaurant_id,
                restaurant_name=m.restaurant.name,
                restaurant_slug=m.restaurant.slug,
                role=m.role,
                dashboard=dashboard_for(m.role),
            )
            for m in memberships
        ],
    )
