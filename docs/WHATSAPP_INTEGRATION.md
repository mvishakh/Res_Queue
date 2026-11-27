# WhatsApp integration (Meta WhatsApp Business Cloud API)

Code: [`whatsapp_service.py`](../backend/app/services/whatsapp_service.py), [`whatsapp_tasks.py`](../backend/app/workers/whatsapp_tasks.py), [`whatsapp_webhook.py`](../backend/app/webhooks/whatsapp_webhook.py). Only the official Graph API is used: `POST https://graph.facebook.com/{version}/{phone_number_id}/messages`.

## Status of this integration

The code path is complete and tested against mocked Graph API responses: send success, retryable and permanent errors, network errors, max attempts, webhook signature verification and status updates. It has **not been tested against a live Meta account**, because none was available. Activating it requires the steps below, including Meta's template approval. Until then, messages end as `FAILED` ("credentials not configured") or `SKIPPED` (WhatsApp disabled or no consent). Nothing is ever shown as sent unless Meta accepted it.

## Why templates

Both messages are **business-initiated**. The customer has not messaged the restaurant, so no 24-hour customer-service window is open. Meta only allows **pre-approved template messages** in that case. Free-form text would be rejected.

## 1. Meta setup

1. Create a Meta app (type **Business**) at developers.facebook.com and add the **WhatsApp** product.
2. Connect or create a WhatsApp Business Account (WABA) and register the restaurant's phone number. Note its **Phone number ID**.
3. Create a **System User** in Business Settings, assign the app and WABA, and generate a **permanent access token** with `whatsapp_business_messaging` and `whatsapp_business_management` permissions.
4. Verify the business in Business Manager. Unverified accounts have low messaging limits.
5. Note the **App Secret** (App settings → Basic). It is used to verify webhook signatures.

## 2. Message templates to submit (category: Utility)

Submit both in WhatsApp Manager → Message templates. Names and language must match **Settings → WhatsApp** in Smart Queue (defaults shown). Parameters are positional.

**`smartqueue_menu_link`** (language `en`):
```
Hello {{1}}! Welcome to {{2}}.

You're on our waiting list. Queue number: {{3}} ({{4}} guests).

Browse our menu while you wait: {{5}}

We'll message you here as soon as your table is ready.
```
Parameters sent: customer name, restaurant name, queue number, guests, menu URL (`{PUBLIC_APP_URL}/menu/{slug}`).

**`smartqueue_table_ready`** (language `en`):
```
Hello {{1}}!

Your table is now ready.

Queue Number: {{2}}
Allocated Table: {{3}}
Number of Guests: {{4}}

Please proceed to your table. We look forward to hosting you — enjoy your dining experience!
```
Parameters sent: customer name, queue number, table number, guests.

Meta asks for sample values when you submit. Approval can take minutes to a day.

## 3. Server configuration (Render env vars)

| Variable | Value |
|---|---|
| `WHATSAPP_ACCESS_TOKEN` | system-user permanent token |
| `WHATSAPP_PHONE_NUMBER_ID` | default sender phone number id (per-restaurant override in Settings) |
| `WHATSAPP_APP_SECRET` | app secret, for webhook signatures |
| `WHATSAPP_WEBHOOK_VERIFY_TOKEN` | any long random string you choose |
| `WHATSAPP_API_VERSION` | Graph API version, e.g. `v23.0`. Use a version Meta currently supports |

Then in Smart Queue, under **Settings → WhatsApp**, tick *Send WhatsApp messages*. The page shows whether the server credentials and webhook are configured.

## 4. Webhook

In the Meta app go to WhatsApp → Configuration → Webhook:
- Callback URL: `https://<render-api>/api/webhooks/whatsapp`
- Verify token: the `WHATSAPP_WEBHOOK_VERIFY_TOKEN` value
- Subscribe to the **messages** field. Status updates arrive in `value.statuses[]`.

Every POST is verified against `X-Hub-Signature-256` (HMAC-SHA256 of the raw body with the app secret). Unsigned or mismatched requests get 401. Statuses only move forward (sent → delivered → read). `failed` marks the message FAILED and alerts staff. Inbound customer messages are ignored, because they're not part of the workflow.

## 5. Consent

Registration records the customer's WhatsApp opt-in (`customers.whatsapp_consent` and the time it was recorded). Without consent, no message is sent; the record is kept as `SKIPPED`. Collect consent verbally at the desk, as the form's checkbox wording says, in line with Meta's opt-in policy.

## Delivery pipeline and retries

1. The business transaction inserts a `whatsapp_messages` row (`PENDING`). This is the outbox.
2. After commit, the API enqueues `send_whatsapp_message(id)` on Redis.
3. The worker locks the row (`FOR UPDATE SKIP LOCKED`, so the same message is never sent twice concurrently) and calls Meta.
   - Success → `SENT` with the `wamid`.
   - Retryable errors (HTTP 5xx/429, network, Meta codes such as 130429, 131000, 131016, 131048, 131056, 133004) → stay `PENDING` with exponential backoff (30 s, 1 min, 2 min, … capped at 30 min).
   - Permanent errors, or `WHATSAPP_MAX_ATTEMPTS` (default 5) reached → `FAILED`, activity log entry, dashboard alert with a **Retry** button.
4. Celery beat runs `dispatch_due_messages` every 30 s, which covers broker outages and scheduled retries.

A notification failure never changes the allocation. If an allocation is undone or released before its message is sent, the pending message becomes `SKIPPED`.
