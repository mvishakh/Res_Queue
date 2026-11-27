# Smart Queue

**Restaurant waiting list & automated table allocation.** Smart Queue replaces the handwritten waiting list: reception registers a guest, the guest instantly receives the digital menu on WhatsApp, and when a waiter marks a table available the system seats the earliest waiting party that fits and tells them their table number on WhatsApp.

## Problem → solution

| Today (paper list) | With Smart Queue |
|---|---|
| Receptionist writes names by hand | 10-second registration form issues a queue number (Q001, Q002…) with a server timestamp |
| Staff keep walking the floor to find free tables | Waiters tap **Mark as Available**; every dashboard updates live |
| Staff shout names / phone guests | The guest gets a WhatsApp message with their table number |
| Ad-hoc table matching | Deterministic **FCFS + Table Matching** — no party is skipped permanently |
| No menu while waiting | Menu link sent on WhatsApp the moment they register |

## Features

- **Exactly two staff dashboards** in one React app, chosen by role at login:
  - **Queue Manager Dashboard** — overview, customer registration, waiting list, tables overview, customers, menu management, allocation history (with logged manager overrides), analytics, and owner-only settings.
  - **Waiter Dashboard** — table grid, one-tap *Mark as Available*, allocation updates, profile. Nothing else.
- **No customer dashboard, login or app.** Customers interact only through WhatsApp and a public, mobile-friendly menu page.
- **Automatic allocation** in a PostgreSQL transaction with row locks, partial unique indexes and a capacity trigger.
- **Exactly two table statuses:** `AVAILABLE`, `OCCUPIED`.
- **WhatsApp via the official Meta Cloud API** — template messages, transactional outbox, Celery retries with backoff, signed webhooks for delivery tracking, staff alerts on failure.
- **Supabase** for PostgreSQL, Auth (staff login) and Realtime (live dashboards, RLS-scoped).
- Activity log of every registration, cancellation, table change, allocation, override and delivery failure.

## Technology

React 19 + TypeScript + Vite + Tailwind CSS · Python 3.12 + FastAPI · SQLAlchemy 2.0 + Alembic · Supabase (PostgreSQL, Auth, Realtime, Storage) · Celery + Redis (Upstash) · Meta WhatsApp Business Cloud API · Vercel (frontend) · Render (API + worker).

## Repository layout

```
backend/            FastAPI app, Alembic migrations, Celery worker, tests
  app/api/routes/   thin HTTP handlers
  app/services/     business logic (allocation_service.py holds the algorithm)
  app/workers/      Celery app + WhatsApp tasks
  app/webhooks/     Meta webhook (signature-verified)
  alembic/versions/ schema, allocation guard trigger, Supabase RLS/Realtime
  tests/            pytest suite (runs against real PostgreSQL)
frontend/           single React app: /login, /manager/*, /waiter/*, /menu/:slug
docs/               architecture, schema, API, allocation logic, roles, setup guides
render.yaml         Render Blueprint (API + worker)
docker-compose.dev.yml  local Postgres + Redis for tests / offline worker runs
```

## Roles

| Role | Dashboard | Can do |
|---|---|---|
| Owner / Administrator | Queue Manager | Everything a Queue Manager can, plus settings, tables, staff, WhatsApp config |
| Queue Manager | Queue Manager | Register, waiting list, cancellations, menu, overrides, analytics |
| Waiter | Waiter | View tables, mark tables available, undo a mis-tap, view allocations |

Permissions are enforced in FastAPI on every request; the UI only mirrors them. Details: [docs/DASHBOARD_ROLES.md](docs/DASHBOARD_ROLES.md).

## Local development

Prerequisites: Python 3.12, Node 20+, Docker (for the local test database), a Supabase project for login.

```bash
# 1. Local Postgres + Redis (tests and offline worker runs)
docker compose -f docker-compose.dev.yml up -d

# 2. Backend
cd backend
python -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                                  # fill in Supabase + other values
alembic upgrade head
python -m app.scripts.bootstrap --restaurant "Spice Garden" --slug spice-garden \
    --owner-email you@example.com --owner-name "Your Name" --tables "T1:2,T2:2,T3:4,T4:4,T5:6"
uvicorn app.main:app --reload                         # http://localhost:8000/api/docs

# 3. Worker (separate terminal)
celery -A app.workers.celery_app worker --loglevel=info    # add -B on Linux/macOS;
celery -A app.workers.celery_app beat --loglevel=info      # on Windows run beat separately (and use --pool=solo)

# 4. Frontend
cd frontend
cp .env.example .env.local                            # Supabase URL + anon key, API URL
npm install
npm run dev                                           # http://localhost:5173
```

### Tests

```bash
cd backend && pytest            # 80 tests; needs the docker Postgres on port 54329 (or set TEST_DATABASE_URL)
cd frontend && npm test         # route protection & role redirection
cd frontend && npm run build    # type-check + production build
```

## Environment variables

Backend: [backend/.env.example](backend/.env.example) · Frontend: [frontend/.env.example](frontend/.env.example). The frontend only ever receives the Supabase URL, the public anon key and the API URL. The service-role key, database password and WhatsApp token stay on the server. Never commit `.env` files (they are git-ignored).

## Setup guides

- [Supabase configuration](docs/SUPABASE_CONFIGURATION.md) — project, connection string, Auth, Realtime, Storage bucket
- [WhatsApp integration](docs/WHATSAPP_INTEGRATION.md) — Meta app, templates to submit, webhook
- [Deployment guide](docs/DEPLOYMENT_GUIDE.md) — Vercel, Render, Upstash

## Documentation

[System architecture](docs/SYSTEM_ARCHITECTURE.md) · [Database schema](docs/DATABASE_SCHEMA.md) · [API](docs/API_DOCUMENTATION.md) · [Queue allocation logic](docs/QUEUE_ALLOCATION_LOGIC.md) · [Dashboard roles](docs/DASHBOARD_ROLES.md)

## Out of scope (by design)

Billing, payments, online ordering, kitchen, inventory, reservations, delivery, loyalty, customer accounts, AI-based allocation, table combining.
