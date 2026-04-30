"""
Tests for arbitrary-depth nested sorting.

Previously _emit_block only handled one level of 'then' (parent → child).
These tests cover grandchildren and deeper, ensuring:
  - sorts are applied innermost-first
  - unique loop variables (_i0, _i1, _i2) prevent shadowing
  - null/empty lists at any depth are handled safely
  - multiple children at the same level all sort correctly
  - existing single-level behaviour is unchanged
"""

import copy
import pytest
from nestsort.compiler import compile_nst


def _run(nst_source, data, func_name="sort_test"):
    code = compile_nst(nst_source, func_name)
    ns = {}
    exec(code, ns)
    return ns[func_name](copy.deepcopy(data))


# ── 2-level deep (existing behaviour — must not regress) ──────────────────

def test_two_level_unchanged():
    src = (
        "sort orders\n"
        "  by status asc\n"
        "  then items\n"
        "    by price asc\n"
    )
    data = [
        {"status": "b", "items": [{"price": 9}, {"price": 2}]},
        {"status": "a", "items": [{"price": 5}, {"price": 1}]},
    ]
    result = _run(src, data)
    assert result[0]["status"] == "a"
    assert [i["price"] for i in result[0]["items"]] == [1, 5]
    assert [i["price"] for i in result[1]["items"]] == [2, 9]


# ── 3-level deep: orders → items → tags ──────────────────────────────────

THREE_LEVEL = (
    "sort orders\n"
    "  by status asc\n"
    "  then items\n"
    "    by price asc\n"
    "    then tags\n"
    "      by label asc\n"
    "  nulls last\n"
)


def test_three_level_outer_sorted():
    data = [
        {"status": "pending", "items": []},
        {"status": "active",  "items": []},
    ]
    result = _run(THREE_LEVEL, data)
    assert result[0]["status"] == "active"
    assert result[1]["status"] == "pending"


def test_three_level_middle_sorted():
    data = [
        {"status": "active", "items": [
            {"price": 9, "tags": []},
            {"price": 2, "tags": []},
            {"price": 5, "tags": []},
        ]},
    ]
    result = _run(THREE_LEVEL, data)
    assert [i["price"] for i in result[0]["items"]] == [2, 5, 9]


def test_three_level_innermost_sorted():
    data = [
        {"status": "active", "items": [
            {"price": 1, "tags": [{"label": "z"}, {"label": "a"}, {"label": "m"}]},
        ]},
    ]
    result = _run(THREE_LEVEL, data)
    tags = [t["label"] for t in result[0]["items"][0]["tags"]]
    assert tags == ["a", "m", "z"]


def test_three_level_all_levels_sorted_together():
    data = [
        {"status": "pending", "items": [
            {"price": 9, "tags": [{"label": "z"}, {"label": "a"}]},
            {"price": 2, "tags": [{"label": "b"}, {"label": "a"}]},
        ]},
        {"status": "active", "items": [
            {"price": 5, "tags": [{"label": "c"}, {"label": "a"}]},
        ]},
    ]
    result = _run(THREE_LEVEL, data)
    # outer: active before pending
    assert result[0]["status"] == "active"
    # middle: items in pending sorted by price
    pending = result[1]
    assert [i["price"] for i in pending["items"]] == [2, 9]
    # inner: tags sorted alphabetically
    assert [t["label"] for t in pending["items"][0]["tags"]] == ["a", "b"]
    assert [t["label"] for t in pending["items"][1]["tags"]] == ["a", "z"]


def test_three_level_null_inner_list_safe():
    """None at any nesting level must not raise."""
    data = [
        {"status": "active", "items": None},
        {"status": "pending", "items": [
            {"price": 1, "tags": None},
        ]},
    ]
    result = _run(THREE_LEVEL, data)
    assert result[0]["items"] == []
    assert result[1]["items"][0]["tags"] == []


def test_three_level_empty_lists_safe():
    data = [
        {"status": "x", "items": []},
        {"status": "x", "items": [{"price": 1, "tags": []}]},
    ]
    result = _run(THREE_LEVEL, data)
    assert result[0]["items"] == [] or result[1]["items"] == []


def test_three_level_nulls_in_inner_keys():
    """Null prices and labels at depth 2 and 3 sort correctly."""
    src = (
        "sort orders\n"
        "  by id asc\n"
        "  then items\n"
        "    by price asc\n"
        "    then tags\n"
        "      by label asc\n"
        "  nulls last\n"
    )
    data = [
        {"id": 1, "items": [
            {"price": None, "tags": [{"label": "b"}, {"label": None}]},
            {"price": 3,    "tags": [{"label": None}, {"label": "a"}]},
        ]},
    ]
    result = _run(src, data)
    items = result[0]["items"]
    # price asc, nulls last
    assert items[0]["price"] == 3
    assert items[1]["price"] is None
    # tags in first item (price=3): 'a' before None
    assert items[0]["tags"][0]["label"] == "a"
    assert items[0]["tags"][1]["label"] is None


# ── 4-level deep: orders → items → tags → attrs ──────────────────────────

FOUR_LEVEL = (
    "sort catalogue\n"
    "  by name asc\n"
    "  then products\n"
    "    by sku asc\n"
    "    then variants\n"
    "      by size asc\n"
    "      then attributes\n"
    "        by key asc\n"
)


def test_four_level_innermost_sorted():
    data = [
        {"name": "A", "products": [
            {"sku": "p1", "variants": [
                {"size": "M", "attributes": [
                    {"key": "z"}, {"key": "a"}, {"key": "m"},
                ]},
            ]},
        ]},
    ]
    result = _run(FOUR_LEVEL, data)
    attrs = result[0]["products"][0]["variants"][0]["attributes"]
    assert [a["key"] for a in attrs] == ["a", "m", "z"]


def test_four_level_all_levels_sorted():
    data = [
        {"name": "B", "products": [
            {"sku": "p2", "variants": [{"size": "L", "attributes": []}]},
            {"sku": "p1", "variants": [{"size": "S", "attributes": []}]},
        ]},
        {"name": "A", "products": [
            {"sku": "p3", "variants": [
                {"size": "M", "attributes": [{"key": "y"}, {"key": "b"}]},
                {"size": "A", "attributes": [{"key": "c"}]},
            ]},
        ]},
    ]
    result = _run(FOUR_LEVEL, data)
    # level 1: name asc
    assert result[0]["name"] == "A"
    # level 2: sku asc within A
    skus = [p["sku"] for p in result[0]["products"]]
    assert skus == ["p3"]
    # level 3: variants by size asc within p3
    sizes = [v["size"] for v in result[0]["products"][0]["variants"]]
    assert sizes == ["A", "M"]
    # level 4: attributes by key asc within size=M variant
    m_variant = next(v for v in result[0]["products"][0]["variants"] if v["size"] == "M")
    assert [a["key"] for a in m_variant["attributes"]] == ["b", "y"]


def test_four_level_nulls_safe():
    data = [
        {"name": "X", "products": None},
        {"name": "Y", "products": [
            {"sku": "s1", "variants": None},
        ]},
        {"name": "Z", "products": [
            {"sku": "s2", "variants": [
                {"size": "S", "attributes": None},
            ]},
        ]},
    ]
    result = _run(FOUR_LEVEL, data)   # must not raise
    assert len(result) == 3


# ── multiple children at same level ──────────────────────────────────────

def test_two_children_at_same_level():
    """A block with two 'then' children must sort both inner lists."""
    src = (
        "sort orders\n"
        "  by id asc\n"
        "  then items\n"
        "    by price asc\n"
        "  then tags\n"
        "    by label asc\n"
    )
    data = [
        {"id": 1,
         "items": [{"price": 9}, {"price": 2}, {"price": 5}],
         "tags":  [{"label": "z"}, {"label": "a"}, {"label": "m"}]},
    ]
    result = _run(src, data)
    assert [i["price"] for i in result[0]["items"]] == [2, 5, 9]
    assert [t["label"] for t in result[0]["tags"]]  == ["a", "m", "z"]


def test_two_children_outer_sorted_too():
    src = (
        "sort orders\n"
        "  by id asc\n"
        "  then items\n"
        "    by price asc\n"
        "  then tags\n"
        "    by label asc\n"
    )
    data = [
        {"id": 3, "items": [{"price": 1}], "tags": [{"label": "b"}]},
        {"id": 1, "items": [{"price": 9}], "tags": [{"label": "a"}]},
        {"id": 2, "items": [{"price": 5}], "tags": [{"label": "c"}]},
    ]
    result = _run(src, data)
    assert [r["id"] for r in result] == [1, 2, 3]
