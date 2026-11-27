"""Pure FCFS + Table Matching algorithm tests (no database)."""

import uuid
from datetime import datetime, timedelta

from app.services.allocation_service import OpenTable, WaitingParty, plan_allocations

T0 = datetime(2026, 11, 27, 19, 0)


def party(name: str, size: int, minute: int, seq: int = 0) -> WaitingParty:
    return WaitingParty(entry_id=uuid.uuid5(uuid.NAMESPACE_DNS, name), party_size=size, arrived_at=T0 + timedelta(minutes=minute), sequence_number=seq or minute)


def table(number: str, capacity: int) -> OpenTable:
    return OpenTable(table_id=uuid.uuid5(uuid.NAMESPACE_URL, number), capacity=capacity, table_number=number)


def as_pairs(plan, parties, tables):
    names = {p.entry_id: n for n, p in parties.items()}
    nums = {t.table_id: t.table_number for t in tables}
    return [(names[a.entry_id], nums[a.table_id]) for a in plan]


def test_specification_example_skips_party_that_does_not_fit():
    parties = {
        "Arun": party("Arun", 6, 0),
        "Vijay": party("Vijay", 2, 2),
        "Rohit": party("Rohit", 4, 5),
        "Karthik": party("Karthik", 2, 7),
    }
    tables = [table("T5", 4)]
    plan = plan_allocations(list(parties.values()), tables)
    assert as_pairs(plan, parties, tables) == [("Vijay", "T5")]


def test_skipped_party_keeps_priority_when_fitting_table_frees_up():
    parties = {"Arun": party("Arun", 6, 0), "Rohit": party("Rohit", 4, 5), "Karthik": party("Karthik", 2, 7)}
    tables = [table("T8", 6)]
    plan = plan_allocations(list(parties.values()), tables)
    # Arun arrived first and now fits — he gets it even though Rohit/Karthik also fit.
    assert as_pairs(plan, parties, tables) == [("Arun", "T8")]


def test_input_order_does_not_matter_only_arrival_time():
    parties = {"Late": party("Late", 2, 10), "Early": party("Early", 2, 1)}
    tables = [table("T1", 2)]
    plan = plan_allocations([parties["Late"], parties["Early"]], tables)
    assert as_pairs(plan, parties, tables) == [("Early", "T1")]


def test_prefers_smallest_fitting_table():
    parties = {"Vijay": party("Vijay", 2, 0)}
    tables = [table("T6", 6), table("T2", 2), table("T4", 4)]
    assert as_pairs(plan_allocations(list(parties.values()), tables), parties, tables) == [("Vijay", "T2")]


def test_customer_priority_beats_table_optimisation():
    # Only a 4-seat table is free. The earliest party (2 guests) gets it even though
    # the later 4-guest party would be a perfect fit.
    parties = {"Pair": party("Pair", 2, 0), "Four": party("Four", 4, 1)}
    tables = [table("T4", 4)]
    assert as_pairs(plan_allocations(list(parties.values()), tables), parties, tables) == [("Pair", "T4")]


def test_multiple_tables_seated_in_arrival_order_each_at_smallest_fit():
    parties = {"A": party("A", 4, 0), "B": party("B", 2, 1), "C": party("C", 6, 2), "D": party("D", 2, 3)}
    tables = [table("T2", 2), table("T4", 4), table("T6", 6)]
    plan = plan_allocations(list(parties.values()), tables)
    assert as_pairs(plan, parties, tables) == [("A", "T4"), ("B", "T2"), ("C", "T6")]


def test_no_eligible_customer_returns_empty_plan():
    parties = {"Big": party("Big", 8, 0), "Bigger": party("Bigger", 10, 1)}
    assert plan_allocations(list(parties.values()), [table("T4", 4)]) == []


def test_never_assigns_insufficient_capacity_or_duplicates():
    parties = {f"P{i}": party(f"P{i}", (i % 6) + 1, i) for i in range(30)}
    tables = [table(f"T{i}", (i % 5) + 2) for i in range(12)]
    plan = plan_allocations(list(parties.values()), tables)
    by_party = {p.entry_id: p for p in parties.values()}
    by_table = {t.table_id: t for t in tables}
    assert len({a.table_id for a in plan}) == len(plan)
    assert len({a.entry_id for a in plan}) == len(plan)
    for a in plan:
        assert by_table[a.table_id].capacity >= by_party[a.entry_id].party_size


def test_deterministic_tie_breaking():
    parties = {"A": party("A", 2, 0)}
    tables = [table("T10", 2), table("T2", 2), table("T3", 2)]
    for _ in range(5):
        assert as_pairs(plan_allocations(list(parties.values()), list(reversed(tables))), parties, tables) == [("A", "T2")]


def test_empty_inputs():
    assert plan_allocations([], [table("T1", 2)]) == []
    assert plan_allocations([party("A", 2, 0)], []) == []
