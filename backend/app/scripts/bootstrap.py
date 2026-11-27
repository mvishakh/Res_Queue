"""Create a restaurant and its first owner account.

Usage (from backend/, with .env configured):

    python -m app.scripts.bootstrap \
        --restaurant "Spice Garden" --slug spice-garden \
        --owner-email owner@example.com --owner-name "Restaurant Owner" \
        --tables "T1:2,T2:2,T3:4,T4:4,T5:6"

If the owner does not yet exist in Supabase Auth you will be prompted for a password
(requires SUPABASE_SERVICE_ROLE_KEY). Further staff are added from Settings > Staff.
"""

import argparse
import getpass
import re
import secrets
import uuid

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models import DiningTable, Restaurant, RestaurantStaff, StaffProfile, WhatsAppConfiguration
from app.models.enums import StaffRole, TableStatus
from app.services import supabase_admin


def parse_tables(spec: str) -> list[tuple[str, int]]:
    tables = []
    for part in filter(None, (p.strip() for p in spec.split(","))):
        number, _, cap = part.partition(":")
        tables.append((number.strip().upper(), int(cap)))
    return tables


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--restaurant", required=True)
    p.add_argument("--slug", required=True, help="Used in the public menu URL /menu/<slug>")
    p.add_argument("--timezone", default="Asia/Kolkata")
    p.add_argument("--phone-region", default="IN")
    p.add_argument("--owner-email", required=True)
    p.add_argument("--owner-name", required=True)
    p.add_argument("--tables", default="", help='e.g. "T1:2,T2:4,T3:6"')
    p.add_argument(
        "--password-file",
        help="Non-interactive: if the owner must be created, generate a temporary password "
        "and write it to this file (keep it out of git; change the password after first login)",
    )
    args = p.parse_args()

    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.slug):
        raise SystemExit("Slug must be lowercase letters, numbers and hyphens")
    email = args.owner_email.lower()

    with SessionLocal() as db:
        if db.scalar(select(Restaurant).where(Restaurant.slug == args.slug)):
            raise SystemExit(f"A restaurant with slug '{args.slug}' already exists")

        profile = db.scalar(select(StaffProfile).where(func.lower(StaffProfile.email) == email))
        if profile is None:
            user_id = supabase_admin.find_auth_user_id(email)
            if user_id is None:
                if args.password_file:
                    password = secrets.token_urlsafe(18)
                    with open(args.password_file, "w", encoding="utf-8") as fh:
                        fh.write(f"ResQ / Smart Queue owner login\nemail: {email}\ntemporary password: {password}\n"
                                 "Change it after first login, then delete this file.\n")
                else:
                    password = getpass.getpass(f"Password for new Supabase user {email}: ")
                if len(password) < 8:
                    raise SystemExit("Password must be at least 8 characters")
                user_id = supabase_admin.create_auth_user(email, password, args.owner_name)
                print(f"Created Supabase Auth user {email}"
                      + (f" (temporary password written to {args.password_file})" if args.password_file else ""))
            profile = StaffProfile(id=uuid.UUID(user_id), email=email, full_name=args.owner_name)
            db.add(profile)

        restaurant = Restaurant(
            id=uuid.uuid4(), name=args.restaurant, slug=args.slug,
            timezone=args.timezone, default_phone_region=args.phone_region.upper(),
        )
        db.add(restaurant)
        db.flush()
        db.add(RestaurantStaff(restaurant_id=restaurant.id, staff_id=profile.id, role=StaffRole.OWNER))
        db.add(WhatsAppConfiguration(restaurant_id=restaurant.id, is_enabled=False))
        for number, capacity in parse_tables(args.tables):
            db.add(DiningTable(restaurant_id=restaurant.id, table_number=number, capacity=capacity, status=TableStatus.AVAILABLE))
        db.commit()
        print(f"Restaurant '{restaurant.name}' created (id {restaurant.id}); {email} is the owner.")


if __name__ == "__main__":
    main()
