"""Supabase Auth JWT verification and role-based access control.

The frontend signs staff in with Supabase Auth and sends the access token as a Bearer
token. FastAPI verifies the token (asymmetric JWKS keys, or the legacy HS256 secret when
configured), loads the staff profile, and resolves the staff member's role in the
restaurant selected with the `X-Restaurant-Id` header.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AuthenticationFailed, PermissionDenied
from app.models import RestaurantStaff, StaffProfile
from app.models.enums import StaffRole

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)


def decode_supabase_token(token: str) -> dict:
    settings = get_settings()
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg")
        if alg == "HS256":
            if not settings.supabase_jwt_secret:
                raise AuthenticationFailed("HS256 tokens are not accepted (SUPABASE_JWT_SECRET not configured)")
            key: object = settings.supabase_jwt_secret
        elif alg in ("ES256", "RS256"):
            if not settings.supabase_url:
                raise AuthenticationFailed("SUPABASE_URL is not configured")
            jwks_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
            key = _jwks_client(jwks_url).get_signing_key_from_jwt(token).key
        else:
            raise AuthenticationFailed("Unsupported token algorithm")
        return jwt.decode(token, key, algorithms=[alg], audience="authenticated")
    except AuthenticationFailed:
        raise
    except jwt.PyJWTError as exc:
        raise AuthenticationFailed("Invalid or expired session") from exc


def get_current_staff(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> StaffProfile:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationFailed("Missing bearer token")
    claims = decode_supabase_token(credentials.credentials)
    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthenticationFailed("Invalid token subject") from exc
    staff = db.get(StaffProfile, user_id)
    if staff is None:
        raise PermissionDenied("This account is not registered as restaurant staff")
    return staff


@dataclass(frozen=True)
class StaffContext:
    """The authenticated staff member acting within one restaurant."""

    staff_id: uuid.UUID
    restaurant_id: uuid.UUID
    role: StaffRole

    @property
    def is_owner(self) -> bool:
        return self.role == StaffRole.OWNER


def get_staff_context(
    staff: StaffProfile = Depends(get_current_staff),
    db: Session = Depends(get_db),
    x_restaurant_id: str | None = Header(default=None),
) -> StaffContext:
    stmt = select(RestaurantStaff).where(
        RestaurantStaff.staff_id == staff.id, RestaurantStaff.is_active.is_(True)
    )
    if x_restaurant_id:
        try:
            restaurant_id = uuid.UUID(x_restaurant_id)
        except ValueError as exc:
            raise PermissionDenied("Invalid restaurant identifier") from exc
        stmt = stmt.where(RestaurantStaff.restaurant_id == restaurant_id)
    memberships = db.scalars(stmt).all()
    if not memberships:
        raise PermissionDenied("You do not have access to this restaurant")
    if len(memberships) > 1:
        raise PermissionDenied("Select a restaurant with the X-Restaurant-Id header")
    m = memberships[0]
    return StaffContext(staff_id=staff.id, restaurant_id=m.restaurant_id, role=m.role)


def require_roles(*roles: StaffRole) -> Callable[..., StaffContext]:
    """Dependency factory that enforces role-based permissions on the backend."""

    allowed = set(roles)

    def dependency(ctx: StaffContext = Depends(get_staff_context)) -> StaffContext:
        if ctx.role not in allowed:
            raise PermissionDenied("Your role does not permit this action")
        return ctx

    return dependency


# Permission groups (see docs/DASHBOARD_ROLES.md)
ANY_STAFF = require_roles(StaffRole.OWNER, StaffRole.QUEUE_MANAGER, StaffRole.WAITER)
QUEUE_STAFF = require_roles(StaffRole.OWNER, StaffRole.QUEUE_MANAGER)
TABLE_FLOOR_STAFF = require_roles(StaffRole.OWNER, StaffRole.WAITER)
OWNER_ONLY = require_roles(StaffRole.OWNER)
