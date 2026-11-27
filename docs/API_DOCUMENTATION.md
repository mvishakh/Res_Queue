# API documentation

Base URL: `{API}/api`. The interactive OpenAPI docs are served at `/api/docs`.

**Headers.** Every staff endpoint needs `Authorization: Bearer <Supabase access token>`. If a staff member belongs to more than one restaurant, also send `X-Restaurant-Id: <uuid>`.

**Errors** use one shape: `{"error": {"code", "message", "details"}}`.

| Status | Meaning |
|---|---|
| 401 | missing or invalid token |
| 403 | role or restaurant not permitted |
| 404 | not found in *your* restaurant |
| 409 | conflicts with current state |
| 422 | validation |
| 503 | external service (Supabase admin) not configured |

Roles: **O** Owner, **M** Queue Manager, **W** Waiter.

## Auth
| Method | Path | Roles | Description |
|---|---|---|---|
| GET | `/auth/me` | any signed-in staff | Profile + memberships, each with `dashboard`: `queue-manager` or `waiter` |

Sign-in itself happens in the browser with Supabase Auth (`signInWithPassword`).

## Queue
| Method | Path | Roles | Description |
|---|---|---|---|
| POST | `/queue` | O M | Register `{name, phone, party_size, notes?, whatsapp_consent}` → 201 entry. Issues queue number, queues menu message, runs allocation. **409 `duplicate_active_registration`** with `details.existing_entry` |
| GET | `/queue?status=WAITING&status=ASSIGNED&search=` | O M | `{server_time, items[]}`; active statuses are returned in FCFS order |
| GET | `/queue/{id}` | O M | One entry with allocation and message statuses |
| PATCH | `/queue/{id}/cancel` | O M | `{reason?}`; only WAITING entries (409 if already seated) |

## Tables
| Method | Path | Roles | Description |
|---|---|---|---|
| GET | `/tables` | O M W | Tables with current party (queue no., name, guests — no phone), `can_undo_available` |
| POST | `/tables` | O | `{table_number, capacity}` |
| PATCH | `/tables/{id}` | O | `{table_number?, capacity?}` |
| DELETE | `/tables/{id}` | O | Remove from floor plan (AVAILABLE only; history kept) |
| PATCH | `/tables/{id}/available` | W O | **Mark as Available.** Body `{allocation_id}` = the allocation shown to the waiter (guards against repeated taps). Returns `{table, freed_queue_number, new_allocation, message}` |
| POST | `/tables/{id}/undo-available` | O M W | Undo a recent mark-available (needs M/O if the table was already reallocated) |

## Allocations
| Method | Path | Roles | Description |
|---|---|---|---|
| GET | `/allocations?status=&limit=` | O M W | History, newest first, with notification status |
| POST | `/allocations/{id}/release` | O M | No-show: `{reason?}` |
| POST | `/allocations/{id}/reassign` | O M | `{table_id, reason?}` to an AVAILABLE table that fits |

## Customers, dashboard, analytics, notifications, activity
| Method | Path | Roles | Description |
|---|---|---|---|
| GET | `/customers?search=` | O M | Customers with visit counts |
| GET | `/customers/{id}` | O M | Customer + visit history |
| GET | `/dashboard/overview` | O M | Counts, recent registrations/allocations/messages, failed-notification count |
| GET | `/analytics?days=7` | O M | Registered, served, cancelled, no-shows, average wait, daily series, by hour, table usage |
| GET | `/notifications?status=FAILED` | O M | WhatsApp message records |
| POST | `/notifications/{id}/retry` | O M | Re-queue a FAILED message |
| GET | `/activity?limit=` | O M | Activity log |

## Menu
| Method | Path | Roles | Description |
|---|---|---|---|
| GET | `/menu` | O M | Full menu incl. hidden items + public `menu_url` |
| POST / PATCH / DELETE | `/menu/categories[/{id}]` | O M | Category CRUD (delete only when empty) |
| POST / PATCH / DELETE | `/menu/items[/{id}]` | O M | Item CRUD |
| POST | `/menu/items/{id}/image` | O M | multipart `file` (JPEG/PNG/WebP ≤ 5 MB) → Supabase Storage |
| GET | `/public/menu/{slug}` | public | Published categories and available items only; no customer data |

## Settings (Owner)
| Method | Path | Description |
|---|---|---|
| GET / PATCH | `/settings/restaurant` | Restaurant info, slug, timezone, phone region, currency, menu publishing (GET is open to all staff) |
| GET / PUT | `/settings/whatsapp` | Enabled flag, phone number id, template names/language; reports whether server credentials and webhook are configured |
| GET / POST | `/staff` | List; create `{email, full_name, role, temporary_password}` via the Supabase Admin API |
| PATCH | `/staff/{membership_id}` | `{role?, is_active?}`; the last active owner cannot be removed |

## Webhook and health
| Method | Path | Description |
|---|---|---|
| GET | `/webhooks/whatsapp` | Meta verification (`hub.mode`, `hub.verify_token`, `hub.challenge`) |
| POST | `/webhooks/whatsapp` | Status updates; requires a valid `X-Hub-Signature-256` |
| GET | `/health` | DB connectivity check |
