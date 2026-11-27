"""Meta WhatsApp Cloud API webhook.

GET  — verification handshake (hub.mode / hub.verify_token / hub.challenge).
POST — event notifications. Every request must carry a valid X-Hub-Signature-256
       (HMAC-SHA256 of the raw body with the Meta App Secret); unsigned or wrongly
       signed requests are rejected.
"""

import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.services import whatsapp_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def verify_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> bool:
    if not app_secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


@router.get("/whatsapp", response_class=PlainTextResponse)
def verify_webhook(
    mode: str | None = Query(default=None, alias="hub.mode"),
    token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    expected = get_settings().whatsapp_webhook_verify_token
    if mode == "subscribe" and expected and token and hmac.compare_digest(token, expected) and challenge:
        return challenge
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/whatsapp")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    if not verify_signature(raw, request.headers.get("X-Hub-Signature-256"), get_settings().whatsapp_app_secret):
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    updated = 0
    if payload.get("object") == "whatsapp_business_account":
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for status_update in value.get("statuses", []):
                    if whatsapp_service.apply_status_update(db, status_update):
                        updated += 1
                # Inbound customer messages are not part of the workflow; they are ignored.
    db.commit()
    return {"received": True, "updated": updated}
