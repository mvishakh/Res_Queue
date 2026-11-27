# Dashboards and roles

One React application, **exactly two staff dashboards**, and no customer dashboard.

| Route | Who | Layout |
|---|---|---|
| `/login` | all staff | shared login |
| `/` | signed-in staff | redirects by role |
| `/manager/*` | Owner, Queue Manager | **Dashboard 1 — Queue Manager** |
| `/waiter/*` | Waiter | **Dashboard 2 — Waiter** |
| `/menu/:slug` | anyone | public digital menu (not a dashboard) |

Route guards ([`frontend/src/auth/guards.tsx`](../frontend/src/auth/guards.tsx)) redirect anyone who opens the wrong dashboard to their own. The backend independently rejects any request the role is not allowed to make (403), so hiding a button is never the only protection.

## Dashboard 1 — Queue Manager

| Page | Contents | Owner only? |
|---|---|---|
| Dashboard | Waiting count, available/total tables, seated today, registered today, recent registrations/allocations/WhatsApp activity, **failed-message alert with retry** | |
| Customer Registration | Name, WhatsApp number, guests (stepper + quick picks), notes, explicit consent; shows the queue number, table (if seated immediately) and menu-message status; resolves duplicates | |
| Waiting List | FCFS order with position, queue no., name, phone, guests, arrival, live waiting time, status, WhatsApp status; filters, search, cancel with confirmation | |
| Tables Overview | Live table grid (read-only), undo control for corrections | |
| Customers | Search, visit counts, history per customer | |
| Menu Management | Categories, items, prices, descriptions, veg/non-veg, photos, availability, public link | |
| Allocation History | All allocations; **No-show release** and **Move** overrides (confirmed, logged) | |
| Analytics | Registered, served, average wait, cancellations/no-shows, daily and hourly charts, table usage | |
| Settings | Restaurant info, tables, staff & roles, WhatsApp configuration, activity log | ✔ |

The Queue Manager never picks customers for tables. Allocation is automatic, and overrides exist only for exceptions.

## Dashboard 2 — Waiter

| Page | Contents |
|---|---|
| Table Overview | Card grid: table number, seats, the party seated (queue no., name, guests, since), green **Available** badge, large **Mark as Available** button |
| Table Availability | Compact list of tables with guests, each with **Mark as Available** |
| Allocation Updates | Live feed of allocations |
| Profile | Name, role, restaurant, sign out |

There is no registration, waiting list, reordering, menu, analytics, billing or messaging settings. Waiters never see customer phone numbers; Realtime/RLS doesn't send them queue or customer rows either. A mis-tap can be undone from the card for 15 minutes.

*Wireframe note:* occupied cards show the seated party instead of a prominent "Occupied" label. The data model still uses `OCCUPIED`.

## Permission matrix (enforced in FastAPI)

| Capability | Owner | Queue Manager | Waiter |
|---|:-:|:-:|:-:|
| Register / list / cancel queue entries | ✔ | ✔ | |
| View tables and allocations | ✔ | ✔ | ✔ |
| Mark table available | ✔ | | ✔ |
| Undo mark-available (nobody reseated yet) | ✔ | ✔ | ✔ |
| Undo after reallocation, no-show release, move | ✔ | ✔ | |
| Customers, analytics, dashboard, notifications, activity | ✔ | ✔ | |
| Menu management | ✔ | ✔ | |
| Tables configuration, restaurant settings, staff, WhatsApp config | ✔ | | |

Queue Managers can't mark tables available because routine table updates belong to the Waiter Dashboard. Owners can, as administrators.
