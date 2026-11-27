"""WhatsApp outbox, delivery, retries and webhook handling. The Meta Graph API is
replaced with an httpx MockTransport — no real messages are sent."""

import hashlib
import hmac
import json

import httpx
from sqlalchemy import select

from app.models import ActivityLog, QueueEntry, TableAllocation, WhatsAppMessage
from app.models.enums import AllocationStatus, MessageStatus, MessageType, QueueStatus, TableStatus
from app.schemas.queue import QueueRegistrationIn
from app.services import queue_service, table_service, whatsapp_service
from app.services.whatsapp_service import WhatsAppCloudClient
from tests.conftest import make_restaurant, make_staff, make_table, ctx_for
from app.models.enums import StaffRole


def register(db, ctx, name="Arun", size=2, phone="+919876543210", consent=True):
    return queue_service.register_customer(
        db, ctx, QueueRegistrationIn(name=name, phone=phone, party_size=size, whatsapp_consent=consent)
    )


def client_returning(*responses):
    """A Cloud API client whose HTTP calls return the given responses in order."""
    calls = []
    queue = list(responses)

    def handler(request: httpx.Request):
        calls.append(request)
        r = queue.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    return WhatsAppCloudClient("test-token", "v23.0", http=httpx.Client(transport=httpx.MockTransport(handler))), calls


def ok(wamid="wamid.TEST123"):
    return httpx.Response(200, json={"messaging_product": "whatsapp", "contacts": [{"input": "x", "wa_id": "x"}], "messages": [{"id": wamid}]})


def meta_error(status, code, message="error"):
    return httpx.Response(status, json={"error": {"message": message, "type": "OAuthException", "code": code}})


def messages(db, type_=None):
    db.expire_all()
    stmt = select(WhatsAppMessage)
    if type_:
        stmt = stmt.where(WhatsAppMessage.message_type == type_)
    return db.scalars(stmt.order_by(WhatsAppMessage.created_at)).all()


# ---------------------------------------------------------------------------
# Outbox creation
# ---------------------------------------------------------------------------


def test_registration_queues_menu_message_in_outbox(db, restaurant, manager_ctx, captured_dispatch):
    entry = register(db, manager_ctx)
    [msg] = messages(db, MessageType.MENU)
    assert msg.status == MessageStatus.PENDING and msg.queue_entry_id == entry.id
    assert captured_dispatch == [msg.id]  # handed to Celery only after commit
    template = msg.payload["template"]
    assert msg.payload["to"] == "919876543210"
    assert template["name"] == "smartqueue_menu_link"
    params = [p["text"] for p in template["components"][0]["parameters"]]
    assert params == ["Arun", restaurant.name, "Q001", "2", f"https://menu.example.test/menu/{restaurant.slug}"]


def test_no_consent_means_no_message(db, manager_ctx, captured_dispatch):
    register(db, manager_ctx, consent=False)
    [msg] = messages(db)
    assert msg.status == MessageStatus.SKIPPED and "consent" in msg.last_error
    assert captured_dispatch == []


def test_whatsapp_disabled_restaurant_skips_messages(db):
    r = make_restaurant(db, whatsapp_enabled=False)
    m = make_staff(db, r, StaffRole.QUEUE_MANAGER)
    register(db, ctx_for(r, m, StaffRole.QUEUE_MANAGER))
    [msg] = messages(db)
    assert msg.status == MessageStatus.SKIPPED


def test_allocation_queues_table_ready_message(db, restaurant, manager_ctx, captured_dispatch):
    make_table(db, restaurant, "T5", 4)
    entry = register(db, manager_ctx, size=4)
    [ready] = messages(db, MessageType.TABLE_READY)
    params = [p["text"] for p in ready.payload["template"]["components"][0]["parameters"]]
    assert params == ["Arun", entry.queue_number, "T5", "4"]
    assert ready.allocation_id is not None
    assert ready.id in captured_dispatch


# ---------------------------------------------------------------------------
# Delivery and retries
# ---------------------------------------------------------------------------


def test_successful_delivery_records_wamid(db, manager_ctx):
    register(db, manager_ctx)
    [msg] = messages(db)
    client, calls = client_returning(ok("wamid.ABC"))
    assert whatsapp_service.deliver_message(db, msg.id, client) == MessageStatus.SENT
    [msg] = messages(db)
    assert msg.wa_message_id == "wamid.ABC" and msg.sent_at is not None and msg.attempt_count == 1
    assert calls[0].url.path == "/v23.0/1234567890/messages"
    assert calls[0].headers["Authorization"] == "Bearer test-token"
    # Delivering again is a no-op (no duplicate sends)
    assert whatsapp_service.deliver_message(db, msg.id, client) == MessageStatus.SENT
    assert len(calls) == 1


def test_temporary_failure_is_retried_with_backoff_then_succeeds(db, manager_ctx):
    register(db, manager_ctx)
    [msg] = messages(db)
    client, _ = client_returning(meta_error(500, 131000), ok())
    assert whatsapp_service.deliver_message(db, msg.id, client) == MessageStatus.PENDING
    [msg] = messages(db)
    assert msg.attempt_count == 1 and "131000" in msg.last_error
    assert msg.next_attempt_at > msg.created_at
    # Not due yet: the sweep does not pick it up
    assert msg.id not in whatsapp_service.due_message_ids(db)

    # Time passes (simulate by moving the retry time into the past)
    msg.next_attempt_at = msg.created_at
    db.commit()
    assert msg.id in whatsapp_service.due_message_ids(db)
    assert whatsapp_service.deliver_message(db, msg.id, client) == MessageStatus.SENT


def test_network_errors_are_retryable(db, manager_ctx):
    register(db, manager_ctx)
    [msg] = messages(db)
    client, _ = client_returning(httpx.ConnectError("boom"))
    assert whatsapp_service.deliver_message(db, msg.id, client) == MessageStatus.PENDING


def test_failure_after_max_attempts_alerts_staff_and_keeps_allocation(db, restaurant, manager_ctx):
    make_table(db, restaurant, "T2", 2)
    entry = register(db, manager_ctx)
    [ready] = messages(db, MessageType.TABLE_READY)
    client, _ = client_returning(*[meta_error(503, 131016)] * 5)
    for _ in range(5):
        m = db.get(WhatsAppMessage, ready.id)
        m.next_attempt_at = m.created_at
        db.commit()
        whatsapp_service.deliver_message(db, ready.id, client)
    [ready] = messages(db, MessageType.TABLE_READY)
    assert ready.status == MessageStatus.FAILED and ready.attempt_count == 5
    assert db.scalar(select(ActivityLog).where(ActivityLog.action == "WHATSAPP_DELIVERY_FAILED")) is not None
    # The committed allocation is untouched by the notification failure
    assert db.get(QueueEntry, entry.id).status == QueueStatus.ASSIGNED
    alloc = db.scalar(select(TableAllocation).where(TableAllocation.queue_entry_id == entry.id))
    assert alloc.status == AllocationStatus.ACTIVE and alloc.table.status == TableStatus.OCCUPIED


def test_permanent_error_fails_immediately(db, manager_ctx):
    register(db, manager_ctx)
    [msg] = messages(db)
    client, _ = client_returning(meta_error(400, 132001, "Template name does not exist"))
    assert whatsapp_service.deliver_message(db, msg.id, client) == MessageStatus.FAILED
    assert "132001" in messages(db)[0].last_error


def test_missing_server_credentials_fail_honestly(db, manager_ctx, monkeypatch):
    from app.core.config import get_settings

    register(db, manager_ctx)
    [msg] = messages(db)
    monkeypatch.setattr(get_settings(), "whatsapp_access_token", "")
    assert whatsapp_service.deliver_message(db, msg.id) == MessageStatus.FAILED
    assert "not configured" in messages(db)[0].last_error


def test_staff_can_retry_a_failed_message(db, manager_ctx, captured_dispatch):
    register(db, manager_ctx)
    [msg] = messages(db)
    client, _ = client_returning(meta_error(400, 132001))
    whatsapp_service.deliver_message(db, msg.id, client)
    captured_dispatch.clear()
    whatsapp_service.retry_failed_message(db, manager_ctx, msg.id)
    [msg] = messages(db)
    assert msg.status == MessageStatus.PENDING and msg.attempt_count == 0
    assert captured_dispatch == [msg.id]


def test_undone_allocation_does_not_send_stale_notification(db, restaurant, manager_ctx, waiter_ctx):
    t2 = make_table(db, restaurant, "T2", 2)
    register(db, manager_ctx, name="Diner", phone="+919800000001")
    register(db, manager_ctx, name="Next", phone="+919800000002")
    table_service.mark_available(db, waiter_ctx, t2.id)  # Next gets T2, notification pending
    table_service.undo_mark_available(db, manager_ctx, t2.id)
    next_ready = [m for m in messages(db, MessageType.TABLE_READY) if m.to_phone == "+919800000002"]
    assert [m.status for m in next_ready] == [MessageStatus.SKIPPED]


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------


def sign(body: bytes, secret="test-app-secret") -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def status_payload(wamid, status, errors=None):
    s = {"id": wamid, "status": status, "timestamp": "1764261000", "recipient_id": "919876543210"}
    if errors:
        s["errors"] = errors
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {
            "messaging_product": "whatsapp", "metadata": {"phone_number_id": "1234567890"}, "statuses": [s]}}]}],
    }


def test_webhook_verification_handshake(client):
    ok_ = client.get("/api/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "test-verify-token", "hub.challenge": "42"})
    assert ok_.status_code == 200 and ok_.text == "42"
    bad = client.get("/api/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42"})
    assert bad.status_code == 403


def test_webhook_rejects_unsigned_or_forged_requests(client):
    body = json.dumps(status_payload("wamid.X", "delivered")).encode()
    assert client.post("/api/webhooks/whatsapp", content=body).status_code == 401
    forged = client.post("/api/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": sign(body, "wrong")})
    assert forged.status_code == 401


def test_webhook_updates_delivery_status(client, db, manager_ctx):
    register(db, manager_ctx)
    [msg] = messages(db)
    whatsapp_service.deliver_message(db, msg.id, client_returning(ok("wamid.D1"))[0])

    for st in ("delivered", "read", "delivered"):  # out-of-order update must not go backwards
        body = json.dumps(status_payload("wamid.D1", st)).encode()
        r = client.post("/api/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": sign(body), "Content-Type": "application/json"})
        assert r.status_code == 200
    [msg] = messages(db)
    assert msg.status == MessageStatus.READ and msg.delivered_at is not None and msg.read_at is not None


def test_webhook_failed_status_alerts_staff(client, db, manager_ctx):
    register(db, manager_ctx)
    [msg] = messages(db)
    whatsapp_service.deliver_message(db, msg.id, client_returning(ok("wamid.F1"))[0])
    body = json.dumps(status_payload("wamid.F1", "failed", [{"code": 131026, "title": "Message undeliverable"}])).encode()
    client.post("/api/webhooks/whatsapp", content=body, headers={"X-Hub-Signature-256": sign(body)})
    [msg] = messages(db)
    assert msg.status == MessageStatus.FAILED and "131026" in msg.last_error
    assert db.scalar(select(ActivityLog).where(ActivityLog.action == "WHATSAPP_DELIVERY_FAILED")) is not None
