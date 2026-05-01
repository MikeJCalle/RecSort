"""
Tests for two new _key_expr features:
  1. Dot-notation key access  (e.g. ``by customer.name asc``)
  2. Type-aware null sentinel  (numeric keys use 0, string keys use '')
"""

import copy
import pytest
from recsort.compiler import compile_nst, _dot_access, _type_sentinel


# ── helpers ────────────────────────────────────────────────────────────────

def _run(nst_source, data, func_name="sort_test"):
    code = compile_nst(nst_source, func_name)
    ns = {}
    exec(code, ns)
    return ns[func_name](copy.deepcopy(data))


# ══════════════════════════════════════════════════════════════════════════
#  1.  DOT-NOTATION ACCESS
# ══════════════════════════════════════════════════════════════════════════

class TestDotAccess:
    """Unit tests for the _dot_access code-emitter."""

    def test_simple_key_unchanged(self):
        assert _dot_access("_x", "price") == "_x.get('price')"

    def test_two_level_dot(self):
        expr = _dot_access("_x", "customer.name")
        assert expr == "(_x.get('customer') or {}).get('name')"

    def test_three_level_dot(self):
        expr = _dot_access("_x", "a.b.c")
        assert expr == "((_x.get('a') or {}).get('b') or {}).get('c')"

    def test_custom_item_var(self):
        expr = _dot_access("_si", "meta.score")
        assert "_si.get('meta')" in expr
        assert ".get('score')" in expr


class TestDotNotationSorting:
    """Integration tests: compile + execute sorts using dot-notation keys."""

    def test_sort_by_nested_string_asc(self):
        src = "sort people\n  by contact.city asc\n"
        data = [
            {"contact": {"city": "Paris"}},
            {"contact": {"city": "Berlin"}},
            {"contact": {"city": "Amsterdam"}},
        ]
        result = _run(src, data)
        cities = [r["contact"]["city"] for r in result]
        assert cities == ["Amsterdam", "Berlin", "Paris"]

    def test_sort_by_nested_string_desc(self):
        src = "sort people\n  by contact.city desc\n"
        data = [
            {"contact": {"city": "Amsterdam"}},
            {"contact": {"city": "Paris"}},
            {"contact": {"city": "Berlin"}},
        ]
        result = _run(src, data)
        cities = [r["contact"]["city"] for r in result]
        assert cities == ["Paris", "Berlin", "Amsterdam"]

    def test_sort_by_nested_numeric_asc(self):
        src = "sort orders\n  by meta.priority asc\n"
        data = [
            {"meta": {"priority": 3}},
            {"meta": {"priority": 1}},
            {"meta": {"priority": 2}},
        ]
        result = _run(src, data)
        assert [r["meta"]["priority"] for r in result] == [1, 2, 3]

    def test_missing_parent_key_treated_as_null(self):
        """A record missing the parent dict should sort as None (nulls last by default)."""
        src = "sort people\n  by contact.city asc\n"
        data = [
            {"contact": {"city": "Zurich"}},
            {},                              # no 'contact' key at all
            {"contact": {"city": "Athens"}},
        ]
        result = _run(src, data)
        # nulls last: the record with no contact goes to the end
        assert result[-1] == {}
        assert result[0]["contact"]["city"] == "Athens"

    def test_missing_leaf_key_treated_as_null(self):
        """A record with the parent dict but missing the leaf key sorts as null."""
        src = "sort people\n  by contact.city asc\n"
        data = [
            {"contact": {"city": "Rome"}},
            {"contact": {}},                 # parent exists, leaf missing
            {"contact": {"city": "Athens"}},
        ]
        result = _run(src, data)
        assert result[-1]["contact"] == {}   # null last

    def test_three_level_dot_notation(self):
        src = "sort records\n  by a.b.c asc\n"
        data = [
            {"a": {"b": {"c": 30}}},
            {"a": {"b": {"c": 10}}},
            {"a": {"b": {"c": 20}}},
        ]
        result = _run(src, data)
        assert [r["a"]["b"]["c"] for r in result] == [10, 20, 30]

    def test_multi_key_with_dot_and_plain(self):
        """Mix a dotted key with a plain key in the same by-clause."""
        src = "sort employees\n  by department asc, meta.level desc\n"
        data = [
            {"department": "eng",  "meta": {"level": 1}},
            {"department": "eng",  "meta": {"level": 3}},
            {"department": "hr",   "meta": {"level": 2}},
            {"department": "eng",  "meta": {"level": 2}},
        ]
        result = _run(src, data)
        eng_levels = [r["meta"]["level"] for r in result if r["department"] == "eng"]
        assert eng_levels == [3, 2, 1]   # desc within eng

    def test_dot_key_nulls_first(self):
        src = "sort items\n  by meta.score asc\n  nulls first\n"
        data = [
            {"meta": {"score": 5}},
            {"meta": {}},
            {"meta": {"score": 2}},
        ]
        result = _run(src, data)
        assert result[0]["meta"] == {}   # null first


# ══════════════════════════════════════════════════════════════════════════
#  2.  TYPE-AWARE NULL SENTINEL
# ══════════════════════════════════════════════════════════════════════════

class TestTypeSentinel:
    """Unit tests for the _type_sentinel heuristic."""

    # --- numeric keys ---
    def test_price_is_numeric(self):       assert _type_sentinel("price")      == "0"
    def test_amount_is_numeric(self):      assert _type_sentinel("amount")     == "0"
    def test_total_is_numeric(self):       assert _type_sentinel("total")      == "0"
    def test_weight_is_numeric(self):      assert _type_sentinel("weight")     == "0"
    def test_rating_is_numeric(self):      assert _type_sentinel("rating")     == "0"
    def test_suffix_id_is_numeric(self):   assert _type_sentinel("product_id") == "0"
    def test_suffix_count_is_numeric(self):assert _type_sentinel("item_count") == "0"
    def test_suffix_num_is_numeric(self):  assert _type_sentinel("page_num")   == "0"
    def test_suffix_age_is_numeric(self):  assert _type_sentinel("user_age")   == "0"
    def test_suffix_rank_is_numeric(self): assert _type_sentinel("rank")       == "0"  # in numeric_exact set
    def test_suffix_score_is_numeric(self):assert _type_sentinel("raw_score")  == "0"
    def test_suffix_date_is_numeric(self): assert _type_sentinel("created_at") == "0"
    def test_lat_is_numeric(self):         assert _type_sentinel("latitude")   == "0"
    def test_lon_is_numeric(self):         assert _type_sentinel("longitude")  == "0"

    # --- string keys ---
    def test_name_is_string(self):   assert _type_sentinel("name")   == "''"
    def test_status_is_string(self): assert _type_sentinel("status") == "''"
    def test_city_is_string(self):   assert _type_sentinel("city")   == "''"
    def test_email_is_string(self):  assert _type_sentinel("email")  == "''"

    # --- dotted keys use leaf segment ---
    def test_dotted_price_leaf(self):  assert _type_sentinel("meta.price")  == "0"
    def test_dotted_name_leaf(self):   assert _type_sentinel("meta.name")   == "''"
    def test_dotted_id_leaf(self):     assert _type_sentinel("order.item_id") == "0"


class TestTypeSentinelRuntime:
    """Verify that all-null lists of numeric keys don't raise TypeError."""

    def test_all_null_numeric_key_no_type_error(self):
        """Two records with None price must not raise TypeError during sort."""
        src = "sort items\n  by price asc\n"
        data = [{"price": None}, {"price": None}]
        result = _run(src, data)   # must not raise
        assert len(result) == 2

    def test_all_null_id_key_no_type_error(self):
        src = "sort rows\n  by item_id asc\n"
        data = [{"item_id": None}, {"item_id": None}, {"item_id": None}]
        result = _run(src, data)
        assert len(result) == 3

    def test_mixed_null_and_int_price_asc(self):
        src = "sort items\n  by price asc\n"
        data = [{"price": 10}, {"price": None}, {"price": 5}, {"price": None}]
        result = _run(src, data)
        non_null = [r["price"] for r in result if r["price"] is not None]
        assert non_null == [5, 10]
        # both nulls are last
        assert result[-1]["price"] is None
        assert result[-2]["price"] is None

    def test_mixed_null_and_int_price_desc(self):
        src = "sort items\n  by price desc\n"
        data = [{"price": None}, {"price": 3}, {"price": 7}, {"price": None}]
        result = _run(src, data)
        non_null = [r["price"] for r in result if r["price"] is not None]
        assert non_null == [7, 3]

    def test_null_sentinel_string_key_no_type_error(self):
        src = "sort items\n  by status asc\n"
        data = [{"status": None}, {"status": None}]
        result = _run(src, data)
        assert len(result) == 2

    def test_dot_notation_all_null_numeric_no_type_error(self):
        src = "sort items\n  by meta.price asc\n"
        data = [{"meta": {"price": None}}, {"meta": {"price": None}}]
        result = _run(src, data)
        assert len(result) == 2

    def test_dot_notation_mixed_null_numeric(self):
        src = "sort items\n  by meta.price asc\n"
        data = [
            {"meta": {"price": 9}},
            {"meta": {"price": None}},
            {"meta": {"price": 3}},
        ]
        result = _run(src, data)
        assert result[0]["meta"]["price"] == 3
        assert result[1]["meta"]["price"] == 9
        assert result[2]["meta"]["price"] is None
