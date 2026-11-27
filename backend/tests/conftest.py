"""Test fixtures. Tests run against a real PostgreSQL database (row locking, partial
unique indexes and the allocation trigger cannot be tested on SQLite).

Start one locally with:  docker compose -f docker-compose.dev.yml up -d postgres
Override with TEST_DATABASE_URL if needed.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:54329/smartqueue_test"
)
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["SUPABASE_JWT_SECRET"] = "test-jwt-secret-for-automated-tests-only-0123456789"
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
os.environ["WHATSAPP_ACCESS_TOKEN"] = "test-token"
os.environ["WHATSAPP_PHONE_NUMBER_ID"] = "1234567890"
os.environ["WHATSAPP_APP_SECRET"] = "test-app-secret"
os.environ["WHATSAPP_WEBHOOK_VERIFY_TOKEN"] = "test-verify-token"
os.environ["PUBLIC_APP_URL"] = "https://menu.example.test"

import jwt  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal, engine  # noqa: E402
from app.core.security import StaffContext  # noqa: E402
from app.models import DiningTable, Restaurant, RestaurantStaff, StaffProfile, WhatsAppConfiguration  # noqa: E402
from app.models.enums import StaffRole, TableStatus  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_database() -> None:
    url = make_url(TEST_DB_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    _ensure_database()
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    cfg.attributes["database_url"] = TEST_DB_URL
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


TABLES_TO_TRUNCATE = (
    "activity_logs, whatsapp_messages, whatsapp_configurations, table_allocations, dining_tables, "
    "queue_entries, queue_counters, customers, menu_items, menu_categories, restaurant_staff, "
    "staff_profiles, restaurants"
)


@pytest.fixture(autouse=True)
def clean_database(migrated_database):
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES_TO_TRUNCATE} CASCADE"))
    yield


@pytest.fixture(autouse=True)
def captured_dispatch(monkeypatch):
    """Capture Celery hand-offs instead of talking to Redis."""
    sent: list[uuid.UUID] = []
    from app.workers import dispatch

    monkeypatch.setattr(dispatch, "enqueue_messages", lambda ids: sent.extend(ids))
    return sent


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_restaurant(db, name="Spice Garden", slug=None, whatsapp_enabled=True) -> Restaurant:
    r = Restaurant(id=uuid.uuid4(), name=name, slug=slug or f"r-{uuid.uuid4().hex[:8]}", timezone="Asia/Kolkata")
    db.add(r)
    db.flush()
    db.add(WhatsAppConfiguration(restaurant_id=r.id, is_enabled=whatsapp_enabled))
    db.commit()
    return r


def make_staff(db, restaurant: Restaurant, role: StaffRole, name: str | None = None) -> StaffProfile:
    sid = uuid.uuid4()
    profile = StaffProfile(id=sid, email=f"{sid.hex[:10]}@example.test", full_name=name or role.value.title())
    db.add(profile)
    db.flush()
    db.add(RestaurantStaff(id=uuid.uuid4(), restaurant_id=restaurant.id, staff_id=sid, role=role))
    db.commit()
    return profile


def make_table(db, restaurant: Restaurant, number: str, capacity: int) -> DiningTable:
    t = DiningTable(id=uuid.uuid4(), restaurant_id=restaurant.id, table_number=number, capacity=capacity, status=TableStatus.AVAILABLE)
    db.add(t)
    db.commit()
    return t


def ctx_for(restaurant: Restaurant, staff: StaffProfile, role: StaffRole) -> StaffContext:
    return StaffContext(staff_id=staff.id, restaurant_id=restaurant.id, role=role)


def token_for(staff_id: uuid.UUID, *, expired: bool = False, secret: str | None = None) -> str:
    now = datetime.now(UTC)
    exp = now - timedelta(minutes=5) if expired else now + timedelta(hours=1)
    return jwt.encode(
        {"sub": str(staff_id), "aud": "authenticated", "role": "authenticated", "iat": now, "exp": exp},
        secret or get_settings().supabase_jwt_secret,
        algorithm="HS256",
    )


@pytest.fixture
def restaurant(db):
    return make_restaurant(db)


@pytest.fixture
def owner(db, restaurant):
    return make_staff(db, restaurant, StaffRole.OWNER, "Olivia Owner")


@pytest.fixture
def manager(db, restaurant):
    return make_staff(db, restaurant, StaffRole.QUEUE_MANAGER, "Meera Manager")


@pytest.fixture
def waiter(db, restaurant):
    return make_staff(db, restaurant, StaffRole.WAITER, "Wasim Waiter")


@pytest.fixture
def manager_ctx(restaurant, manager):
    return ctx_for(restaurant, manager, StaffRole.QUEUE_MANAGER)


@pytest.fixture
def waiter_ctx(restaurant, waiter):
    return ctx_for(restaurant, waiter, StaffRole.WAITER)


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


def auth(staff: StaffProfile, restaurant: Restaurant | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token_for(staff.id)}"}
    if restaurant is not None:
        headers["X-Restaurant-Id"] = str(restaurant.id)
    return headers
