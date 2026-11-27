# Supabase configuration

Supabase provides PostgreSQL, Auth, Realtime and Storage. The schema is created by **Alembic**, not by the Supabase table editor.

## 1. Project and keys

Create a project, then collect these values:

| Value | Where | Used by |
|---|---|---|
| Project URL | Settings → API | backend `SUPABASE_URL`, frontend `VITE_SUPABASE_URL` |
| anon / publishable key | Settings → API | frontend `VITE_SUPABASE_ANON_KEY` only |
| service_role / secret key | Settings → API | backend `SUPABASE_SERVICE_ROLE_KEY` only — **never in the frontend** |
| JWT secret (legacy) | Settings → API → JWT | backend `SUPABASE_JWT_SECRET`, *only* if the project still signs with HS256. Projects on asymmetric signing keys need nothing; the backend reads `/auth/v1/.well-known/jwks.json` |
| DB connection string | Connect → **Session pooler** (port 5432) | backend `DATABASE_URL` |

Use the **session pooler** URL: `postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require`. The direct `db.<ref>.supabase.co` host is IPv6-only and not reachable from Render. Prepared statements are disabled in the engine, so the transaction pooler (6543) also works.

## 2. Schema

```bash
cd backend
alembic upgrade head
```

Migration `0003` detects the `auth` schema and then:
- enables RLS on all tables
- revokes `anon`/`authenticated` privileges
- grants **read-only** `SELECT` on `restaurants`, `dining_tables`, `table_allocations`, `queue_entries`, `whatsapp_messages` through policies using `smartqueue_staff_role(restaurant_id)`; queue and message rows are visible to Owners and Queue Managers only
- adds `dining_tables`, `table_allocations`, `queue_entries`, `whatsapp_messages` to the `supabase_realtime` publication

The backend connects as the table owner, which bypasses RLS, and enforces access itself. These policies were checked against a simulated Supabase environment:

| Staff member | Can read |
|---|---|
| manager of restaurant A | A's queue |
| waiter of A | A's tables, no queue rows |
| manager of B | nothing of A |
| anon | nothing |
| any browser role | cannot write anything |

## 3. Auth

- Authentication → Providers: keep **Email** enabled. Disable public sign-ups (Authentication → Sign In / Providers → "Allow new users to sign up" off); staff accounts are created by owners.
- Authentication → URL configuration: set the Site URL to the Vercel URL.
- Create the first restaurant and owner:
  ```bash
  python -m app.scripts.bootstrap --restaurant "Spice Garden" --slug spice-garden \
      --owner-email owner@example.com --owner-name "Owner Name" --tables "T1:2,T2:4,T3:6"
  ```
  This creates the Supabase user if needed (prompting for a password), the staff profile, the restaurant, the OWNER membership and the tables. Further staff are added in **Settings → Staff & roles**, which uses the Admin API from the backend.

## 4. Realtime

Nothing to click. The publication is managed by migration `0003`. Under Realtime settings, keep "Allow public access" disabled if your project has that option; the dashboards subscribe as authenticated users and RLS filters rows.

## 5. Storage (menu photos)

Create a **public** bucket named `menu-images` (or set `SUPABASE_STORAGE_BUCKET`). Uploads happen only from the backend with the service-role key, so no storage policies for browser roles are needed. The public URLs are what the menu page shows.
