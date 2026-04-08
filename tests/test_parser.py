"""
Tests for RecSort lexer and parser stages.
"""

import pytest
from recsort.compiler import parse, ParseError, SortKey


# ── Parser: valid inputs ───────────────────────────────────────

def test_parse_flat_single_key():
    src = "sort orders\n  by date asc\n"
    root = parse(src)
    assert root.name == "orders"
    assert len(root.keys) == 1
    assert root.keys[0] == SortKey(key="date", direction="asc")
    assert root.nulls == "last"  # default


def test_parse_flat_multi_key():
    src = "sort orders\n  by status asc, date desc\n"
    root = parse(src)
    assert len(root.keys) == 2
    assert root.keys[0] == SortKey("status", "asc")
    assert root.keys[1] == SortKey("date", "desc")


def test_parse_nulls_first():
    src = "sort items\n  by price desc\n  nulls first\n"
    root = parse(src)
    assert root.nulls == "first"


def test_parse_nulls_last_explicit():
    src = "sort items\n  by price asc\n  nulls last\n"
    root = parse(src)
    assert root.nulls == "last"


def test_parse_then_child():
    src = (
        "sort orders\n"
        "  by status asc\n"
        "  then items\n"
        "    by price asc\n"
    )
    root = parse(src)
    assert len(root.children) == 1
    child = root.children[0]
    assert child.parent_key == "items"
    assert child.keys[0] == SortKey("price", "asc")


def test_parse_child_inherits_nulls():
    src = (
        "sort orders\n"
        "  by date asc\n"
        "  then items\n"
        "    by price desc\n"
        "  nulls first\n"
    )
    root = parse(src)
    assert root.nulls == "first"


def test_parse_comments_ignored():
    src = (
        "# this is a comment\n"
        "sort products\n"
        "  # another comment\n"
        "  by name asc\n"
    )
    root = parse(src)
    assert root.name == "products"
    assert len(root.keys) == 1


def test_parse_direction_default_asc():
    """Key without explicit direction defaults to asc."""
    src = "sort things\n  by name\n"
    root = parse(src)
    assert root.keys[0].direction == "asc"


# ── Parser: error cases ────────────────────────────────────────

def test_parse_empty_raises():
    with pytest.raises(ParseError, match="Empty"):
        parse("")


def test_parse_missing_sort_header():
    with pytest.raises(ParseError):
        parse("by name asc\n")


def test_parse_then_without_key_raises():
    src = "sort orders\n  by status asc\n  then\n"
    with pytest.raises(ParseError, match="then"):
        parse(src)


def test_parse_nulls_invalid_value():
    src = "sort orders\n  by date asc\n  nulls sideways\n"
    with pytest.raises(ParseError, match="nulls"):
        parse(src)
