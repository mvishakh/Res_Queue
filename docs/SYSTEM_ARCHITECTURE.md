# System architecture

```
                ┌──────────────── Vercel ────────────────┐
 Staff browser  │ React SPA                              │        Customer phone
 ─────────────▶ │  /login  /manager/*  /waiter/*         │        (WhatsApp only)
                │  /menu/:slug  (public menu page) ◀─────┼──────── menu link
                └──────┬──────────────┬──────────────────┘              ▲
        Supabase Auth  │ REST + JWT   │ Realtime (RLS-scoped)            │ template messages
        (staff login)  ▼              ▼                                  │
                ┌──── Render ─────────────┐   ┌──── Supabase ─────────┐  │
                │ FastAPI (business logic)│──▶│ PostgreSQL            │  │
                │  allocation_service     │   │ Auth · Realtime ·     │  │
                │  queue/table/menu/...   │   │ Storage (menu images) │  │
                │  webhook (signed)  ◀────┼───┼───────────────────────┼──┤ delivery statuses
                └──────────┬──────────────┘   └───────────────────────┘  │
                           │ enqueue after commit                         │
                     ┌─────▼──────┐    ┌─────────────────────────┐        │
                     │ Upstash    │───▶│ Celery worker + beat    │────────┘
                     │ Redis      │    │ (Render background)     │  Meta Cloud API
                     └────────────┘    └─────────────────────────┘
```

## Responsibilities

| Component | Owns |
|---|---|
| React app | Two role-based dashboard layouts, login, public menu page. No business rules beyond display. |
| FastAPI | Every write: registration, cancellation, table changes, allocation, overrides, menu, settings. Verifies Supabase JWTs and enforces roles and restaurant scope. |
| PostgreSQL (Supabase) | Source of truth; transactions, row locks, constraints, allocation trigger, RLS for browser reads. |
| Supabase Auth | Staff identities and sessions. Staff profiles and roles live in our tables. |
| Supabase Realtime | Pushes change *signals* to dashboards; the dashboards re-fetch from FastAPI. |
| Celery + Redis | WhatsApp delivery, retries with backoff, periodic outbox sweep. |
| Meta Cloud API | Template message delivery; webhooks report sent / delivered / read / failed. |

## Key flows

**Registration.** The Queue Manager submits the form, then `POST /api/queue`. In one transaction FastAPI:
1. locks the restaurant row
2. normalizes the phone number to E.164
3. rejects duplicate active registrations (409 with the existing entry)
4. issues the next queue number from `queue_counters` (atomic upsert)
5. inserts the entry with the DB timestamp
6. writes the MENU message to the outbox
7. runs the allocation engine
8. commits

After commit it enqueues the Celery task. Realtime then updates every Queue Manager screen.

**Table freed.** The waiter taps the button, which calls `PATCH /api/tables/{id}/available`. In one transaction FastAPI:
1. locks the restaurant row
2. completes the current allocation and queue entry
3. sets the table to AVAILABLE
4. runs the engine; if a party fits, the table becomes OCCUPIED again with the TABLE_READY message in the outbox
5. commits

Celery then sends the WhatsApp message, and Realtime refreshes both dashboards.

**Delivery tracking.** Meta calls `POST /api/webhooks/whatsapp`. FastAPI verifies the HMAC signature and moves the message status forward only (sent → delivered → read, or failed). A failure is logged and appears as a staff alert on the dashboard.

## Reliability decisions

- **Transactional outbox:** message rows are committed atomically with the business change. Celery is triggered after commit, and a beat task re-sends anything still `PENDING` every 30 s, which covers broker outages. Delivery is at-least-once.
- **Per-restaurant serialization:** a row lock on `restaurants` orders all allocation-affecting operations. This is simple and deterministic, and at restaurant scale (tens of tables) contention is negligible.
- **Database constraints back up the service code**; violations surface as HTTP 409, never as a corrupt state.
- **Honest failure:** with no WhatsApp credentials, messages end `FAILED` with a clear reason. Nothing is reported as sent unless Meta accepted it.

## Security

- The browser holds only the Supabase anon key and the user's JWT. The service-role key, DB password, WhatsApp token and app secret exist only on Render.
- FastAPI checks every request's JWT (JWKS for asymmetric keys, or the legacy HS256 secret) and the staff member's active role in the selected restaurant (`X-Restaurant-Id`). Every query filters by that restaurant.
- RLS is enabled on every table. Browser roles get **read-only** access to just the realtime tables, scoped to their restaurant. Waiters cannot read queue or customer rows. Nothing is writable from the browser.
- Webhooks are rejected unless the `X-Hub-Signature-256` HMAC matches the app secret.
