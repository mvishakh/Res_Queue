# Queue allocation logic — FCFS + Table Matching

Code: [`backend/app/services/allocation_service.py`](../backend/app/services/allocation_service.py)

## The rule

1. Walk the waiting list in **original arrival order** (`queue_entries.created_at`, set from the database clock at registration and never modified; the daily sequence number breaks exact ties).
2. For each waiting party, pick the **smallest available table whose capacity ≥ party size** (ties: natural table-number order, e.g. T2 before T10).
3. If no available table fits, the party is **skipped for this run only**. It stays `WAITING` with its original arrival time and queue number, so it keeps priority over everyone who arrived later.
4. Each table goes to at most one party and each party gets at most one table. Tables are never combined.

Customer priority always beats table fit. With only a 4-seat table free, an earlier party of 2 gets it before a later party of 4.

### Worked example (from the specification)

T5 (4 seats) becomes available. Waiting: Q001 Arun 6, Q002 Vijay 2, Q003 Rohit 4, Q004 Karthik 2.

| Step | Check | Result |
|---|---|---|
| 1 | Q001, 6 > 4 | skip (stays WAITING, keeps priority) |
| 2 | Q002, 2 ≤ 4 | **T5 → Q002**, table OCCUPIED, Q002 ASSIGNED, WhatsApp queued |

The waiting list is now Q001, Q003, Q004 in the same order with unchanged timestamps. When a 6-seat table frees up, Q001 gets it ahead of Q003 and Q004. This exact scenario is covered by automated tests (`test_specification_example_*`) and was replayed over HTTP against a live stack.

## When the engine runs

| Trigger | Why |
|---|---|
| Waiter marks a table available | the main path |
| Customer registered | a fitting table may already be free |
| Table created / capacity changed | new capacity may fit someone |
| No-show release, reassignment, undo | a table was freed or a party returned to WAITING |

Each run is a **sweep over all available tables**. Because every run leaves the system in a state where *no waiting party fits any available table*, freeing one table can only produce matches for that table. So the sweep gives exactly the per-table result above. When several tables are freed in one event, the sweep handles them deterministically.

## Consistency and concurrency

Every operation that touches queue entries, tables or allocations runs in **one PostgreSQL transaction** that first takes `SELECT … FOR UPDATE` on the restaurant row. Concurrent events for the same restaurant (two waiters tapping at once, a registration racing a table release) are therefore **serialized in commit order**, and each sees the previous one's result.

Database-level guards, the last line of defence:

| Guard | Prevents |
|---|---|
| partial unique index `table_allocations(table_id) WHERE status='ACTIVE'` | one table → two parties |
| partial unique index `table_allocations(queue_entry_id) WHERE status='ACTIVE'` | one party → two tables |
| trigger `trg_table_allocations_guard` | capacity < party size; cross-restaurant allocation |
| check `current_allocation_id IS NULL OR status='OCCUPIED'` | inconsistent table state |
| partial unique index `queue_entries(restaurant_id, customer_id) WHERE status IN ('WAITING','ASSIGNED')` | duplicate active registrations |

**Idempotency.** Marking an `AVAILABLE` table available again is a no-op. The waiter UI also sends the allocation it was showing (`allocation_id`). If the table already holds a *different* party (because the first tap freed the table and the engine seated the next party), the repeated tap is ignored instead of ending the new party's allocation. This is covered by a parallel-taps test.

## Notifications never undo allocations

The `TABLE_READY` WhatsApp message is written to the outbox in the same transaction as the allocation and sent by Celery after commit. A delivery failure is recorded, retried and surfaced to staff. It never touches the allocation.

## Corrections (logged manager overrides)

| Situation | Action | Who |
|---|---|---|
| Waiter tapped the wrong table, nobody seated yet | **Undo "available"** (within 15 min) restores the previous party | Waiter, Queue Manager, Owner |
| Wrong tap and the engine already seated the next party | Undo releases that allocation (`REVERTED`), returns the party to WAITING **with its original arrival time**, cancels its unsent notification, restores the previous party | Queue Manager, Owner |
| Customer did not arrive | **Release (no-show)**: allocation `RELEASED/NO_SHOW`, entry `CANCELLED`, table offered to the queue | Queue Manager, Owner |
| Party needs a different table | **Move**: to an AVAILABLE table that fits; new `MANUAL_OVERRIDE` allocation, customer re-notified, old table offered to the queue | Queue Manager, Owner |

There is deliberately **no automatic no-show timeout** in the MVP. A configurable timeout can be added later as a Celery beat task that calls the same `release_allocation` service.

## Lifecycles

```
Queue entry:   WAITING ──allocate──▶ ASSIGNED ──table freed──▶ COMPLETED
                  │                     │
                  └──cancel──▶ CANCELLED ◀──no-show release
Table:         AVAILABLE ◀──────────▶ OCCUPIED            (only these two)
Allocation:    ACTIVE ──▶ COMPLETED (TABLE_FREED) | RELEASED (NO_SHOW / REVERTED / REASSIGNED)
```
