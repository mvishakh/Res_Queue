import logging
import uuid

from app.core.database import SessionLocal
from app.services import whatsapp_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.whatsapp_tasks.send_whatsapp_message")
def send_whatsapp_message(message_id: str) -> str | None:
    with SessionLocal() as db:
        status = whatsapp_service.deliver_message(db, uuid.UUID(message_id))
        return status.value if status else None


@celery_app.task(name="app.workers.whatsapp_tasks.dispatch_due_messages")
def dispatch_due_messages() -> int:
    """Periodic outbox sweep: sends messages whose (re)try time has come, including any
    that could not be enqueued right after their transaction committed."""
    with SessionLocal() as db:
        ids = whatsapp_service.due_message_ids(db)
    for message_id in ids:
        with SessionLocal() as db:
            try:
                whatsapp_service.deliver_message(db, message_id)
            except Exception:  # noqa: BLE001 — one bad message must not stop the sweep
                logger.exception("Outbox delivery crashed for %s", message_id)
    return len(ids)
