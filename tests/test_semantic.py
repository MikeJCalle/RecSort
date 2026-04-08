"""
Tests for NestSort semantic analysis stage.
"""

import pytest
from nestsort.compiler import parse, analyse, SemanticError


def test_valid_flat_passes():
    src = "sort orders\n  by status asc\n"
    analyse(parse(src))  # should not raise


def test_valid_nested_passes():
    src = (
        "sort orders\n"
        "  by status asc, date desc\n"
        "  then items\n"
        "    by price asc\n"
        "  nulls last\n"
    )
    analyse(parse(src))  # should not raise


def test_child_without_by_raises():
    """A 'then' block with no 'by' clause should fail semantic analysis."""
    src = (
        "sort orders\n"
        "  by status asc\n"
        "  then items\n"  # no 'by' inside
    )
    root = parse(src)
    with pytest.raises(SemanticError, match="no 'by' clause"):
        analyse(root)


def test_multi_child_passes():
    src = (
        "sort products\n"
        "  by category asc, rating desc\n"
        "  then reviews\n"
        "    by score desc\n"
        "  nulls first\n"
    )
    analyse(parse(src))  # should not raise


def test_multiple_sort_keys_passes():
    src = "sort employees\n  by department asc, salary desc, name asc\n"
    analyse(parse(src))
