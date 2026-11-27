# Database schema

PostgreSQL on Supabase, defined by SQLAlchemy 2.0 models ([`backend/app/models`](../backend/app/models)) and Alembic migrations ([`backend/alembic/versions`](../backend/alembic/versions)). UUID primary keys, `timestamptz` everywhere, and every restaurant-owned row carries `restaurant_id`.

## Tables

| Table | Purpose | Notable constraints |
|---|---|---|
| `restaurants` | Tenant. Name, `slug` (menu URL), timezone, default phone region, currency, menu settings | `slug` unique |
| `staff_profiles` | One per Supabase Auth user (`id` = `auth.users.id`) | `email` unique |
| `restaurant_staff` | Membership + role (`OWNER`, `QUEUE_MANAGER`, `WAITER`), active flag | unique (restaurant, staff) |
| `customers` | Name, phone in E.164, WhatsApp consent + timestamp of the decision | unique (restaurant, phone) |
| `queue_counters` | Daily counter for queue numbers | PK (restaurant, business_date) |
| `queue_entries` | One visit: queue number, party size, notes, status, arrival (`created_at`), assigned/completed/cancelled times | unique (restaurant, business_date, sequence); **one active entry per customer** (partial unique); party size 1–50 |
| `dining_tables` | Table number, capacity, status (`AVAILABLE`/`OCCUPIED`), `current_allocation_id`, `archived_at` | unique number per restaurant among non-archived; check: allocation ⇒ OCCUPIED |
| `table_allocations` | Allocation history (never deleted): table, entry, status, type, timestamps, end reason, staff | **one ACTIVE per table**, **one ACTIVE per entry** (partial uniques); guard trigger |
| `menu_categories` | Category name, description, order, visibility | unique (restaurant, name) |
| `menu_items` | Name, description, price, image URL/path, `dietary_type` (VEG/NON_VEG), availability | price ≥ 0 |
| `whatsapp_configurations` | Per restaurant: enabled flag, phone number id override, template names, language | PK restaurant_id |
| `whatsapp_messages` | Outbox + delivery record: type, payload, status, `wa_message_id`, attempts, next attempt, error, sent/delivered/read/failed times | wamid unique; one MENU per entry; one TABLE_READY per allocation |
| `activity_logs` | Action, entity, actor (NULL = system), JSON details, time | index (restaurant, time) |

`archived_at` on tables is configuration ("removed from the floor plan"), not a table status. It keeps allocation history intact.

## Enums

| Enum | Values |
|---|---|
| `table_status` | `AVAILABLE`, `OCCUPIED` — **only these two** |
| `queue_status` | `WAITING`, `ASSIGNED`, `COMPLETED`, `CANCELLED` |
| `allocation_status` | `ACTIVE`, `COMPLETED`, `RELEASED` |
| `allocation_type` | `AUTOMATIC`, `MANUAL_OVERRIDE` |
| `allocation_end_reason` | `TABLE_FREED`, `NO_SHOW`, `REVERTED`, `REASSIGNED` |
| `staff_role` | `OWNER`, `QUEUE_MANAGER`, `WAITER` |
| `whatsapp_message_type` | `MENU`, `TABLE_READY` |
| `whatsapp_message_status` | `PENDING`, `SENT`, `DELIVERED`, `READ`, `FAILED`, `SKIPPED` |
| `dietary_type` | `VEG`, `NON_VEG` |

## Relationships

```
restaurants 1─* restaurant_staff *─1 staff_profiles
restaurants 1─* customers 1─* queue_entries 1─* table_allocations *─1 dining_tables
dining_tables.current_allocation_id ─▶ table_allocations   (circular FK, added after both tables)
queue_entries / table_allocations 1─* whatsapp_messages
restaurants 1─* menu_categories 1─* menu_items
restaurants 1─1 whatsapp_configurations ; restaurants 1─* activity_logs
```

## Migrations

| Revision | Contents |
|---|---|
| `0001` | All tables, enums, indexes and constraints |
| `0002` | `smartqueue_check_allocation()` trigger: capacity ≥ party size and same-restaurant references |
| `0003` | RLS on every table. **On Supabase only:** `smartqueue_staff_role()` helper, read-only policies for realtime tables, revoke of anon/authenticated privileges, Realtime publication |

```bash
alembic upgrade head      # apply
alembic check             # verify models and migrations agree
alembic downgrade base    # full rollback (tested)
```
