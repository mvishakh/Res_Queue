"""WhatsApp Business Cloud API integration (official Meta API only).

Isolated from the allocation logic. Business services only *queue* messages here
(transactional outbox). Delivery happens after commit, in a Celery worker, so a
WhatsApp failure can never roll back a registration or a committed table allocation.

Business-initiated messages to a customer who has not messaged the restaurant in the
last 24 hours must be pre-approved *template* messages, so both the menu message and the
table-ready message are sent as templates (see docs/WHATSAPP_INTEGRATION.md).
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError
from app.core.security import StaffContext
from app.models import DiningTable, QueueEntry, Restaurant, TableAllocation, WhatsAppConfiguration, WhatsAppMessage
from app.models.enums import MessageStatus, MessageType
from app.services.common import db_now, log_activity

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com"

# Meta error codes that indicate a temporary condition worth retrying
# (throttling / temporary service problems). Everything else in 4xx is permanent.
RETRYABLE_META_ERROR_CODES = {1, 2, 4, 17, 80007, 130429, 131000, 131016, 131048, 131056, 133004}

# Status precedence — webhook updates may arrive out of order; never move backwards.
_STATUS_RANK = {
    MessageStatus.PENDING: 0,
    MessageStatus.SENT: 1,
    MessageStatus.DELIVERED: 2,
    MessageStatus.READ: 3,
}


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


class WhatsAppSendError(Exception):
    def __init__(self, message: str, *, retryable: bool, code: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.code = code


class WhatsAppCloudClient:
    def __init__(self, access_token: str, api_version: str, http: httpx.Client | None = None):
        self._token = access_token
        self._version = api_version
        self._http = http or httpx.Client(timeout=15.0)

    def send(self, phone_number_id: str, payload: dict) -> str:
        """POST /{phone_number_id}/messages. Returns the WhatsApp message id (wamid)."""
        url = f"{GRAPH_API_BASE}/{self._version}/{phone_number_id}/messages"
        try:
            response = self._http.post(url, json=payload, headers={"Authorization": f"Bearer {self._token}"})
        except httpx.TransportError as exc:
            raise WhatsAppSendError(f"Network error: {exc}", retryable=True) from exc

        if response.status_code == 200:
            try:
                return response.json()["messages"][0]["id"]
            except (ValueError, KeyError, IndexError) as exc:
                raise WhatsAppSendError("Unexpected response from WhatsApp API", retryable=False) from exc

        try:
            error = response.json().get("error", {})
        except ValueError:
            error = {}
        code = error.get("code")
        detail = (error.get("error_data") or {}).get("details") or error.get("message") or response.text[:300]
        retryable = response.status_code >= 500 or response.status_code == 429 or code in RETRYABLE_META_ERROR_CODES
        raise WhatsAppSendError(f"HTTP {response.status_code} (code {code}): {detail}", retryable=retryable, code=code)


def get_client() -> WhatsAppCloudClient:
    settings = get_settings()
    return WhatsAppCloudClient(settings.whatsapp_access_token, settings.whatsapp_api_version)


# ---------------------------------------------------------------------------
# Outbox (called inside business transactions)
# ---------------------------------------------------------------------------


def get_configuration(db: Session, restaurant_id: uuid.UUID) -> WhatsAppConfiguration | None:
    return db.get(WhatsAppConfiguration, restaurant_id)


def menu_url(restaurant: Restaurant) -> str:
    return f"{get_settings().public_app_url.rstrip('/')}/menu/{restaurant.slug}"


def _template_payload(to_e164: str, template_name: str, language: str, params: list[str]) -> dict:
    return {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_e164.lstrip("+"),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in params]},
            ],
        },
    }


def _queue_message(
    db: Session,
    *,
    entry: QueueEntry,
    message_type: MessageType,
    template_attr: str,
    params: list[str],
    allocation_id: uuid.UUID | None = None,
) -> WhatsAppMessage:
    customer = entry.customer
    config = get_configuration(db, entry.restaurant_id)
    template_name = getattr(config, template_attr) if config else None
    now = db_now(db)

    status = MessageStatus.PENDING
    reason: str | None = None
    if not customer.whatsapp_consent:
        status, reason = MessageStatus.SKIPPED, "Customer did not consent to WhatsApp messages"
    elif config is None or not config.is_enabled:
        status, reason = MessageStatus.SKIPPED, "WhatsApp messaging is disabled for this restaurant"

    message = WhatsAppMessage(
        id=uuid.uuid4(),
        restaurant_id=entry.restaurant_id,
        customer_id=customer.id,
        queue_entry_id=entry.id,
        allocation_id=allocation_id,
        message_type=message_type,
        to_phone=customer.phone_e164,
        template_name=template_name,
        payload=_template_payload(customer.phone_e164, template_name, config.template_language, params)
        if config
        else {},
        status=status,
        last_error=reason,
        next_attempt_at=now if status == MessageStatus.PENDING else None,
    )
    db.add(message)
    db.flush()
    if status == MessageStatus.PENDING:
        db.info.setdefault("outbox", []).append(message.id)
    return message


def queue_menu_message(db: Session, *, restaurant: Restaurant, entry: QueueEntry) -> WhatsAppMessage:
    # Template body: Hello {{1}}! Welcome to {{2}}. Your queue number is {{3}}
    # for {{4}} guests. Browse our menu while you wait: {{5}}
    return _queue_message(
        db,
        entry=entry,
        message_type=MessageType.MENU,
        template_attr="menu_template_name",
        params=[entry.customer.full_name, restaurant.name, entry.queue_number, str(entry.party_size), menu_url(restaurant)],
    )


def queue_table_ready_message(
    db: Session, *, entry: QueueEntry, table: DiningTable, allocation: TableAllocation
) -> WhatsAppMessage:
    # Template body: Hello {{1}}! Your table is now ready. Queue Number: {{2}}
    # Allocated Table: {{3}} Number of Guests: {{4}} ...
    return _queue_message(
        db,
        entry=entry,
        message_type=MessageType.TABLE_READY,
        template_attr="table_ready_template_name",
        params=[entry.customer.full_name, entry.queue_number, table.table_number, str(entry.party_size)],
        allocation_id=allocation.id,
    )


def supersede_pending_messages(db: Session, *, allocation_id: uuid.UUID, reason: str) -> None:
    """A not-yet-sent table notification for an allocation that was undone must not go out."""
    for message in db.scalars(
        select(WhatsAppMessage)
        .where(WhatsAppMessage.allocation_id == allocation_id, WhatsAppMessage.status == MessageStatus.PENDING)
        .with_for_update(of=WhatsAppMessage)
    ):
        message.status = MessageStatus.SKIPPED
        message.last_error = reason
        message.next_attempt_at = None
    db.flush()


def commit_and_dispatch(db: Session) -> None:
    """Commit the business transaction, then hand newly queued messages to Celery.
    If the broker is unreachable the rows stay PENDING and the periodic sweep sends them."""
    message_ids: list[uuid.UUID] = db.info.pop("outbox", [])
    db.commit()
    if message_ids:
        from app.workers import dispatch  # local import: keeps workers optional for tooling

        dispatch.enqueue_messages(message_ids)


# ---------------------------------------------------------------------------
# Delivery (called by the Celery worker)
# ---------------------------------------------------------------------------


def retry_delay(attempt: int) -> timedelta:
    """Exponential backoff: 30s, 60s, 2m, 4m, ... capped at 30 minutes."""
    return timedelta(seconds=min(30 * 2 ** max(attempt - 1, 0), 1800))


def _mark_failed(db: Session, message: WhatsAppMessage, error: str, now: datetime) -> None:
    message.status = MessageStatus.FAILED
    message.failed_at = now
    message.last_error = error
    message.next_attempt_at = None
    # Staff are alerted through the dashboard (failed notifications banner) and the log.
    log_activity(
        db,
        restaurant_id=message.restaurant_id,
        action="WHATSAPP_DELIVERY_FAILED",
        entity_type="whatsapp_message",
        entity_id=message.id,
        details={"message_type": message.message_type.value, "to": message.to_phone, "error": error},
    )


def deliver_message(db: Session, message_id: uuid.UUID, client: WhatsAppCloudClient | None = None) -> MessageStatus | None:
    """Attempt to send one outbox message. Commits. Returns the resulting status."""
    settings = get_settings()
    message = db.scalar(
        select(WhatsAppMessage).where(WhatsAppMessage.id == message_id).with_for_update(of=WhatsAppMessage, skip_locked=True)
    )
    if message is None or message.status != MessageStatus.PENDING:
        db.rollback()
        return message.status if message else None
    now = db_now(db)
    if message.next_attempt_at and message.next_attempt_at > now:
        db.rollback()
        return message.status  # not due yet; the sweep will pick it up

    config = get_configuration(db, message.restaurant_id)
    phone_number_id = (config.phone_number_id if config else None) or settings.whatsapp_phone_number_id
    if config is None or not config.is_enabled:
        message.status = MessageStatus.SKIPPED
        message.last_error = "WhatsApp messaging was disabled before delivery"
        message.next_attempt_at = None
        db.commit()
        return message.status
    if not settings.whatsapp_access_token or not phone_number_id:
        _mark_failed(db, message, "WhatsApp API credentials are not configured on the server", now)
        db.commit()
        return message.status

    message.attempt_count += 1
    try:
        wamid = (client or get_client()).send(phone_number_id, message.payload)
    except WhatsAppSendError as exc:
        logger.warning("WhatsApp send failed for %s (attempt %s): %s", message.id, message.attempt_count, exc)
        if exc.retryable and message.attempt_count < settings.whatsapp_max_attempts:
            message.last_error = str(exc)
            message.next_attempt_at = now + retry_delay(message.attempt_count)
        else:
            _mark_failed(db, message, str(exc), now)
    else:
        message.status = MessageStatus.SENT
        message.wa_message_id = wamid
        message.sent_at = now
        message.last_error = None
        message.next_attempt_at = None
    db.commit()
    return message.status


def due_message_ids(db: Session, limit: int = 100) -> list[uuid.UUID]:
    now = db_now(db)
    return list(
        db.scalars(
            select(WhatsAppMessage.id)
            .where(WhatsAppMessage.status == MessageStatus.PENDING, WhatsAppMessage.next_attempt_at <= now)
            .order_by(WhatsAppMessage.next_attempt_at)
            .limit(limit)
        )
    )


def retry_failed_message(db: Session, ctx: StaffContext, message_id: uuid.UUID) -> WhatsAppMessage:
    """Staff-initiated retry of a permanently failed message."""
    message = db.scalar(
        select(WhatsAppMessage)
        .where(WhatsAppMessage.id == message_id, WhatsAppMessage.restaurant_id == ctx.restaurant_id)
        .with_for_update(of=WhatsAppMessage)
    )
    if message is None:
        raise NotFoundError("Message not found")
    if message.status != MessageStatus.FAILED:
        raise ConflictError("Only failed messages can be retried")
    if not message.payload:
        raise ConflictError("WhatsApp was not configured when this message was created")
    message.status = MessageStatus.PENDING
    message.attempt_count = 0
    message.failed_at = None
    message.next_attempt_at = db_now(db)
    db.info.setdefault("outbox", []).append(message.id)
    log_activity(
        db,
        restaurant_id=ctx.restaurant_id,
        action="WHATSAPP_RETRY_REQUESTED",
        entity_type="whatsapp_message",
        entity_id=message.id,
        actor_id=ctx.staff_id,
    )
    commit_and_dispatch(db)
    return message


# ---------------------------------------------------------------------------
# Webhook status updates
# ---------------------------------------------------------------------------


def apply_status_update(db: Session, status: dict) -> bool:
    """Apply one entry of `value.statuses[]` from a Meta webhook. Returns True if a
    tracked message was updated. Caller commits."""
    wamid = status.get("id")
    new_status = {
        "sent": MessageStatus.SENT,
        "delivered": MessageStatus.DELIVERED,
        "read": MessageStatus.READ,
        "failed": MessageStatus.FAILED,
    }.get(status.get("status", ""))
    if not wamid or new_status is None:
        return False
    message = db.scalar(
        select(WhatsAppMessage).where(WhatsAppMessage.wa_message_id == wamid).with_for_update(of=WhatsAppMessage)
    )
    if message is None:
        return False
    try:
        at = datetime.fromtimestamp(int(status.get("timestamp")), tz=UTC)  # Unix seconds, UTC
    except (TypeError, ValueError):
        at = db_now(db)

    if new_status == MessageStatus.FAILED:
        if message.status != MessageStatus.FAILED:
            errors = status.get("errors") or [{}]
            err = errors[0]
            detail = (err.get("error_data") or {}).get("details") or err.get("message") or err.get("title") or "Delivery failed"
            _mark_failed(db, message, f"Delivery failed (code {err.get('code')}): {detail}", at)
        return True

    if message.status in _STATUS_RANK and _STATUS_RANK[new_status] > _STATUS_RANK[message.status]:
        message.status = new_status
        if new_status == MessageStatus.DELIVERED:
            message.delivered_at = at
        elif new_status == MessageStatus.READ:
            message.read_at = at
            message.delivered_at = message.delivered_at or at
    return True
