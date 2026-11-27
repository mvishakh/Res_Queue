"""Authentication, role permissions and restaurant data isolation through the HTTP API."""

import uuid

import pytest

from app.models.enums import StaffRole
from tests.conftest import auth, make_restaurant, make_staff, make_table, token_for

REG = {"name": "Arun Kumar", "phone": "+919876543210", "party_size": 4, "whatsapp_consent": True}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_requests_without_token_are_rejected(client):
    r = client.get("/api/tables")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


def test_invalid_and_expired_tokens_are_rejected(client, manager):
    assert client.get("/api/tables", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401
    expired = token_for(manager.id, expired=True)
    assert client.get("/api/tables", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    forged = token_for(manager.id, secret="some-other-secret-that-is-long-enough-123456")
    assert client.get("/api/tables", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_authenticated_user_without_staff_profile_is_forbidden(client, restaurant):
    r = client.get("/api/tables", headers={"Authorization": f"Bearer {token_for(uuid.uuid4())}"})
    assert r.status_code == 403


def test_deactivated_staff_lose_access(client, db, restaurant, manager):
    from app.models import RestaurantStaff

    m = db.query(RestaurantStaff).filter_by(staff_id=manager.id).one()
    m.is_active = False
    db.commit()
    assert client.get("/api/queue", headers=auth(manager)).status_code == 403


@pytest.mark.parametrize(
    "role,dashboard",
    [(StaffRole.OWNER, "queue-manager"), (StaffRole.QUEUE_MANAGER, "queue-manager"), (StaffRole.WAITER, "waiter")],
)
def test_me_returns_role_based_dashboard(client, db, restaurant, role, dashboard):
    staff = make_staff(db, restaurant, role)
    r = client.get("/api/auth/me", headers=auth(staff))
    assert r.status_code == 200
    membership = r.json()["memberships"][0]
    assert membership["role"] == role.value
    assert membership["dashboard"] == dashboard


# ---------------------------------------------------------------------------
# Queue Manager permissions
# ---------------------------------------------------------------------------


def test_queue_manager_can_register_and_list(client, restaurant, manager):
    r = client.post("/api/queue", json=REG, headers=auth(manager))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["queue_number"] == "Q001" and body["status"] == "WAITING"
    assert body["customer"]["phone_e164"] == "+919876543210"
    listing = client.get("/api/queue?status=WAITING", headers=auth(manager)).json()
    assert [e["queue_number"] for e in listing["items"]] == ["Q001"]


def test_registration_validation_errors(client, manager):
    bad = {**REG, "party_size": 0}
    r = client.post("/api/queue", json=bad, headers=auth(manager))
    assert r.status_code == 422
    r = client.post("/api/queue", json={**REG, "phone": "12345"}, headers=auth(manager))
    assert r.status_code == 422
    assert "valid WhatsApp number" in r.json()["error"]["message"]


def test_duplicate_registration_returns_existing_entry(client, manager):
    client.post("/api/queue", json=REG, headers=auth(manager))
    r = client.post("/api/queue", json={**REG, "name": "Someone else"}, headers=auth(manager))
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "duplicate_active_registration"
    assert err["details"]["existing_entry"]["queue_number"] == "Q001"


def test_queue_manager_cannot_mark_tables_available_or_configure_tables(client, db, restaurant, manager):
    t = make_table(db, restaurant, "T1", 2)
    assert client.patch(f"/api/tables/{t.id}/available", headers=auth(manager)).status_code == 403
    assert client.post("/api/tables", json={"table_number": "T9", "capacity": 4}, headers=auth(manager)).status_code == 403
    assert client.get("/api/staff", headers=auth(manager)).status_code == 403
    # ...but can view tables and allocations
    assert client.get("/api/tables", headers=auth(manager)).status_code == 200
    assert client.get("/api/allocations", headers=auth(manager)).status_code == 200


# ---------------------------------------------------------------------------
# Waiter permissions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/queue"),
        ("get", "/api/queue"),
        ("get", "/api/customers"),
        ("get", "/api/menu"),
        ("post", "/api/menu/categories"),
        ("get", "/api/analytics"),
        ("get", "/api/dashboard/overview"),
        ("get", "/api/notifications"),
        ("get", "/api/settings/whatsapp"),
        ("get", "/api/staff"),
        ("post", "/api/tables"),
    ],
)
def test_waiter_is_denied_queue_manager_features(client, waiter, method, path):
    r = getattr(client, method)(path, headers=auth(waiter), **({"json": {}} if method == "post" else {}))
    assert r.status_code == 403, (path, r.status_code)


def test_waiter_marks_table_available_and_sees_allocation(client, db, restaurant, manager, waiter):
    t = make_table(db, restaurant, "T5", 4)
    client.post("/api/queue", json={**REG, "phone": "+919800000010", "party_size": 2}, headers=auth(manager))  # seated at T5
    client.post("/api/queue", json={**REG, "phone": "+919800000011", "party_size": 6}, headers=auth(manager))
    client.post("/api/queue", json={**REG, "phone": "+919800000012", "party_size": 3, "name": "Rohit"}, headers=auth(manager))

    tables = client.get("/api/tables", headers=auth(waiter)).json()
    assert tables[0]["status"] == "OCCUPIED" and tables[0]["current"]["queue_number"] == "Q001"
    assert "phone" not in str(tables[0]["current"])  # floor staff never see phone numbers

    seen = tables[0]["current"]["allocation_id"]
    r = client.patch(f"/api/tables/{t.id}/available", json={"allocation_id": seen}, headers=auth(waiter))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["freed_queue_number"] == "Q001"
    assert body["new_allocation"]["queue_number"] == "Q003"  # Q002 (6 guests) skipped, keeps priority
    assert body["table"]["status"] == "OCCUPIED"

    # A repeated tap with the stale allocation id changes nothing
    again = client.patch(f"/api/tables/{t.id}/available", json={"allocation_id": seen}, headers=auth(waiter)).json()
    assert again["table"]["current"]["queue_number"] == "Q003"
    assert "already updated" in again["message"]


def test_waiter_can_view_allocation_updates(client, waiter):
    assert client.get("/api/allocations", headers=auth(waiter)).status_code == 200


# ---------------------------------------------------------------------------
# Owner permissions
# ---------------------------------------------------------------------------


def test_owner_configures_tables_and_settings(client, owner):
    r = client.post("/api/tables", json={"table_number": "t1", "capacity": 4}, headers=auth(owner))
    assert r.status_code == 201 and r.json()["table_number"] == "T1"
    dup = client.post("/api/tables", json={"table_number": "T1", "capacity": 2}, headers=auth(owner))
    assert dup.status_code == 409
    r = client.patch("/api/settings/restaurant", json={"name": "Spice Garden Annex"}, headers=auth(owner))
    assert r.status_code == 200 and r.json()["name"] == "Spice Garden Annex"
    assert client.get("/api/staff", headers=auth(owner)).status_code == 200


def test_staff_creation_requires_supabase_service_key(client, owner):
    r = client.post(
        "/api/staff",
        json={"email": "new.staff@example.com", "full_name": "New", "role": "WAITER", "temporary_password": "longpassword"},
        headers=auth(owner),
    )
    assert r.status_code == 503  # honest failure: no service-role key configured in tests


def test_cannot_remove_last_owner(client, db, owner):
    staff = client.get("/api/staff", headers=auth(owner)).json()
    me = next(s for s in staff if s["staff_id"] == str(owner.id))
    r = client.patch(f"/api/staff/{me['membership_id']}", json={"role": "WAITER"}, headers=auth(owner))
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# Restaurant data isolation
# ---------------------------------------------------------------------------


def test_staff_cannot_access_another_restaurants_data(client, db, restaurant, manager):
    other = make_restaurant(db, name="Other Place", slug="other-place")
    other_manager = make_staff(db, other, StaffRole.QUEUE_MANAGER)
    other_table = make_table(db, other, "T1", 4)
    entry = client.post("/api/queue", json=REG, headers=auth(other_manager)).json()

    # Not visible in listings
    assert client.get("/api/queue", headers=auth(manager)).json()["items"] == []
    assert client.get("/api/customers", headers=auth(manager)).json() == []
    assert client.get("/api/tables", headers=auth(manager)).json() == []
    # Direct access by id fails
    assert client.get(f"/api/queue/{entry['id']}", headers=auth(manager)).status_code == 404
    assert client.patch(f"/api/queue/{entry['id']}/cancel", json={}, headers=auth(manager)).status_code == 404
    assert client.get(f"/api/customers/{entry['customer']['id']}", headers=auth(manager)).status_code == 404
    # Selecting the other restaurant explicitly is refused
    assert client.get("/api/queue", headers=auth(manager, other)).status_code == 403
    # Same phone in two restaurants = two separate customer records
    mine = client.post("/api/queue", json=REG, headers=auth(manager)).json()
    assert mine["customer"]["id"] != entry["customer"]["id"]
    assert other_table  # untouched


def test_public_menu_needs_no_auth_and_exposes_no_customer_data(client, db, restaurant, manager):
    cat = client.post("/api/menu/categories", json={"name": "Starters"}, headers=auth(manager)).json()
    client.post(
        "/api/menu/items",
        json={"category_id": cat["id"], "name": "Paneer Tikka", "price": "249.00", "dietary_type": "VEG"},
        headers=auth(manager),
    )
    client.post(
        "/api/menu/items",
        json={"category_id": cat["id"], "name": "Sold out", "price": "99", "is_available": False},
        headers=auth(manager),
    )
    client.post("/api/queue", json=REG, headers=auth(manager))
    r = client.get(f"/api/public/menu/{restaurant.slug}")
    assert r.status_code == 200
    menu = r.json()
    assert menu["restaurant_name"] == restaurant.name
    assert [i["name"] for i in menu["categories"][0]["items"]] == ["Paneer Tikka"]
    assert "9876543210" not in r.text and "Arun" not in r.text
    assert client.get("/api/public/menu/does-not-exist").status_code == 404
