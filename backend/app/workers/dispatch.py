"""Hand-off from the API process to the Celery worker (after the DB commit)."""

import logging
import uuid
from collections.abc import Iterable

logger = logging.getLogger(__name__)


def enqueue_messages(message_ids: Iterable[uuid.UUID]) -> None:
    try:
        from app.workers.whatsapp_tasks import send_whatsapp_message

        for message_id in message_ids:
            send_whatsapp_message.delay(str(message_id))
    except Exception:  # noqa: BLE001 — broker outage must never break the API request
        logger.exception("Could not enqueue WhatsApp messages; the periodic outbox sweep will deliver them")
