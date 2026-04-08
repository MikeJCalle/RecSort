"""
Integration tests: compile a .nst source, execute the generated function,
assert ordering at every nesting level.
"""

import copy
import pytest
from recsort.compiler import compile_nst


def _run(nst_source, data, func_name="sort_test"):
    """Compile source, execute against data, return sorted result."""
    code = compile_nst(nst_source, func_name)
    ns = {}
    exec(code, ns)
    return ns[func_name](copy.deepcopy(data))


# ── Flat sorts ─────────────────────────────────────────────────

def test_flat_asc():
    src = "sort items\n  by value asc\n"
    data = [{"value": 3}, {"value": 1}, {"value": 2}]
    result = _run(src, data)
    assert [r["value"] for r in result] == [1, 2, 3]


def test_flat_desc():
    src = "sort items\n  by value desc\n"
    data = [{"value": 1}, {"value": 3}, {"value": 2}]
    result = _run(src, data)
    assert [r["value"] for r in result] == [3, 2, 1]


def test_flat_multi_key():
    src = "sort items\n  by group asc, value desc\n"
    data = [
        {"group": "b", "value": 1},
        {"group": "a", "value": 2},
        {"group": "a", "value": 5},
        {"group": "b", "value": 3},
    ]
    result = _run(src, data)
    groups = [r["group"] for r in result]
    assert groups == ["a", "a", "b", "b"]
    # within group a: value desc
    a_vals = [r["value"] for r in result if r["group"] == "a"]
    assert a_vals == [5, 2]


# ── Null handling ──────────────────────────────────────────────

def test_nulls_last_default():
    src = "sort items\n  by value asc\n"
    data = [{"value": 2}, {"value": None}, {"value": 1}]
    result = _run(src, data)
    assert result[-1]["value"] is None


def test_nulls_first():
    src = "sort items\n  by value asc\n  nulls first\n"
    data = [{"value": 2}, {"value": None}, {"value": 1}]
    result = _run(src, data)
    assert result[0]["value"] is None


def test_all_nulls():
    src = "sort items\n  by value asc\n"
    data = [{"value": None}, {"value": None}]
    result = _run(src, data)
    assert all(r["value"] is None for r in result)


def test_empty_list():
    src = "sort items\n  by value asc\n"
    result = _run(src, [])
    assert result == []


# ── Nested sorts ───────────────────────────────────────────────

def test_nested_items_sorted():
    src = (
        "sort orders\n"
        "  by id asc\n"
        "  then items\n"
        "    by price asc\n"
    )
    data = [
        {"id": 1, "items": [{"price": 9}, {"price": 2}, {"price": 5}]},
        {"id": 2, "items": [{"price": 1}, {"price": 3}]},
    ]
    result = _run(src, data)
    assert [i["price"] for i in result[0]["items"]] == [2, 5, 9]
    assert [i["price"] for i in result[1]["items"]] == [1, 3]


def test_nested_items_null_price_last():
    src = (
        "sort orders\n"
        "  by id asc\n"
        "  then items\n"
        "    by price asc\n"
        "  nulls last\n"
    )
    data = [
        {"id": 1, "items": [{"price": 5}, {"price": None}, {"price": 2}]},
    ]
    result = _run(src, data)
    prices = [i["price"] for i in result[0]["items"]]
    assert prices[-1] is None


def test_nested_empty_items_list():
    src = (
        "sort orders\n"
        "  by id asc\n"
        "  then items\n"
        "    by price asc\n"
    )
    data = [{"id": 1, "items": []}, {"id": 2, "items": None}]
    result = _run(src, data)
    # should not raise; empty/None lists stay empty
    assert result[0]["items"] == []


# ── Full demo scenario ────────────────────────────────────────

def test_full_demo_scenario():
    src = (
        "sort orders\n"
        "  by status asc, date desc\n"
        "  then items\n"
        "    by price asc\n"
        "  nulls last\n"
    )
    data = [
        {"id": 1, "status": "pending", "date": 20240310,
         "items": [{"price": 9.99}, {"price": None}, {"price": 4.50}]},
        {"id": 2, "status": "active",  "date": 20240401,
         "items": [{"price": 19.99}, {"price": 2.00}]},
        {"id": 3, "status": "active",  "date": 20240315,
         "items": [{"price": 7.50}]},
        {"id": 4, "status": None,      "date": 20240101, "items": []},
        {"id": 5, "status": "pending", "date": 20240101,
         "items": [{"price": 0.99}]},
    ]
    result = _run(src, data, "sort_orders")

    statuses = [r["status"] for r in result]
    # active before pending before null
    assert statuses.index("active") < statuses.index("pending")
    assert statuses[-1] is None

    # active group: date desc → id=2 (20240401) before id=3 (20240315)
    active = [r for r in result if r["status"] == "active"]
    assert active[0]["id"] == 2
    assert active[1]["id"] == 3

    # items within order id=1: price asc, null last
    order1 = next(r for r in result if r["id"] == 1)
    prices = [i["price"] for i in order1["items"]]
    assert prices[-1] is None
    assert prices[0] < prices[1]
