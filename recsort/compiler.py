# Written by: Michael Calle
# Written on: 4/5/2026
# Updated:    4/30/2026 — v0.2

"""
RecSort — Recursive Sort Expression Compiler  v0.2

Compiles one or more .nst declarations into self-contained Python sort
functions — no runtime dependency, no boilerplate.

Usage:
    recsort <file.nst>                    compile → <file.py>
    recsort <file.nst> --preview          plain-English plan, no file written
    recsort <file.nst> --output <path>    write output to a specific path
    recsort <file.nst> --function-name <name>   override generated function name
    recsort <file.nst> --check <data.json>      validate sort against real data
    recsort --demo                        run built-in demo with sample data
    recsort --help

.nst syntax (one or more blocks per file):

    sort <name>
      by <key> asc|desc [, <key> asc|desc ...]
      then <list-key>
        by <subkey> asc|desc
      nulls first|last
      stable
      limit <N>
      group-by <key>
      on-missing skip|stop|log

    sort <another-name>
      by <key> asc
      ...

Multiple sort blocks compile to one function each, all written to the
same output file.
"""

import json
import sys
import textwrap
import warnings
from dataclasses import dataclass, field
from pathlib import Path


# ──────────────────────────────────────────────────────────────
#  EXIT CODES
# ──────────────────────────────────────────────────────────────

EXIT_OK         = 0
EXIT_PARSE_ERR  = 1
EXIT_SEM_ERR    = 2
EXIT_IO_ERR     = 3
EXIT_CHECK_FAIL = 4


# ──────────────────────────────────────────────────────────────
#  DATA TYPES
# ──────────────────────────────────────────────────────────────

@dataclass
class SortKey:
    key: str
    direction: str          # "asc" or "desc"
    key_type: str = "auto"  # "auto" | "str" | "num"  (future explicit hint)


@dataclass
class SortBlock:
    name: str
    keys: list              # list[SortKey]
    nulls: str              # "first" | "last"
    stable: bool = False
    limit: int = None       # None = no limit
    group_by: str = None    # None = return flat list
    on_missing: str = "null"  # "null" | "skip" | "stop" | "log"
    children: list = field(default_factory=list)   # list[SortBlock]
    parent_key: str = None  # key in parent whose list we sort


# ──────────────────────────────────────────────────────────────
#  ERRORS & WARNINGS
# ──────────────────────────────────────────────────────────────

class ParseError(Exception):
    pass

class SemanticError(Exception):
    pass

class SemanticWarning(UserWarning):
    pass


# ──────────────────────────────────────────────────────────────
#  LEXER  (line-by-line, indent-aware)
# ──────────────────────────────────────────────────────────────

def _tokenise(line):
    """Split a stripped line into tokens, stripping trailing commas."""
    return [t.rstrip(",") for t in line.split() if t.rstrip(",")]


def _indent(line):
    return len(line) - len(line.lstrip(" "))


# ──────────────────────────────────────────────────────────────
#  PARSER  (iterative stack-based)
# ──────────────────────────────────────────────────────────────

def parse(source):
    """Parse a .nst source string and return a list of SortBlock roots.

    A single-block file returns a one-element list.  Multi-block files
    return one root per ``sort`` header found at indent 0.
    """
    raw_lines = source.splitlines()

    lines = []
    for i, raw in enumerate(raw_lines, 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append((i, _indent(raw), _tokenise(stripped)))

    if not lines:
        raise ParseError("Empty .nst file — nothing to parse.")

    roots = []
    # We'll scan through lines, starting a new root each time we see
    # a top-level "sort <name>" token.
    i = 0
    while i < len(lines):
        lineno, indent, tokens = lines[i]
        if tokens[0] != "sort" or len(tokens) < 2:
            raise ParseError(f"Line {lineno}: expected 'sort <name>', got: {' '.join(tokens)}")

        root = SortBlock(name=tokens[1], keys=[], nulls="last")
        stack = [(indent, root)]
        i += 1

        while i < len(lines):
            lineno, ind, toks = lines[i]
            if not toks:
                i += 1
                continue

            # A new top-level "sort" starts the next block
            if toks[0] == "sort" and ind == 0:
                break

            # Pop stack to find the right parent for this indent level
            while len(stack) > 1 and stack[-1][0] >= ind:
                stack.pop()

            current_block = stack[-1][1]
            verb = toks[0]

            if verb == "by":
                rest = toks[1:]
                j = 0
                while j < len(rest):
                    k = rest[j]
                    if not k:
                        j += 1
                        continue
                    d = "asc"
                    if j + 1 < len(rest) and rest[j + 1] in ("asc", "desc"):
                        d = rest[j + 1]
                        j += 2
                    else:
                        j += 1
                    current_block.keys.append(SortKey(key=k, direction=d))

            elif verb == "then":
                if len(toks) < 2:
                    raise ParseError(f"Line {lineno}: 'then' requires a key name")
                child_key = toks[1]
                child = SortBlock(name=child_key, keys=[], nulls=current_block.nulls,
                                  parent_key=child_key)
                current_block.children.append(child)
                stack.append((ind, child))

            elif verb == "nulls":
                if len(toks) >= 2 and toks[1] in ("first", "last"):
                    current_block.nulls = toks[1]
                else:
                    raise ParseError(
                        f"Line {lineno}: 'nulls' must be followed by 'first' or 'last'")

            elif verb == "stable":
                current_block.stable = True

            elif verb == "limit":
                if len(toks) < 2 or not toks[1].isdigit():
                    raise ParseError(
                        f"Line {lineno}: 'limit' requires a positive integer, e.g. 'limit 10'")
                current_block.limit = int(toks[1])

            elif verb == "group-by":
                if len(toks) < 2:
                    raise ParseError(f"Line {lineno}: 'group-by' requires a key name")
                current_block.group_by = toks[1]

            elif verb == "on-missing":
                if len(toks) >= 2 and toks[1] in ("skip", "stop", "log", "null"):
                    current_block.on_missing = toks[1]
                else:
                    raise ParseError(
                        f"Line {lineno}: 'on-missing' must be followed by "
                        f"skip | stop | log  (got: {toks[1] if len(toks) > 1 else '?'})")

            # Unknown verbs are silently skipped for forward-compatibility.
            i += 1

        roots.append(root)

    return roots


def parse_one(source):
    """Parse source and return the single root, raising if there are multiple."""
    roots = parse(source)
    if len(roots) != 1:
        raise ParseError(
            f"Expected exactly one sort block, found {len(roots)}. "
            "Use parse() for multi-block files.")
    return roots[0]


# ──────────────────────────────────────────────────────────────
#  SEMANTIC ANALYSIS
# ──────────────────────────────────────────────────────────────

def analyse(roots):
    """Analyse a list of SortBlock roots (or a single root) for correctness.

    Raises SemanticError for hard errors.
    Emits SemanticWarning for issues that compile but are likely bugs.
    """
    if isinstance(roots, SortBlock):
        roots = [roots]

    block_names = set()
    for root in roots:
        if root.name in block_names:
            raise SemanticError(
                f"Duplicate sort block name '{root.name}' — "
                "each sort block in a file must have a unique name")
        block_names.add(root.name)
        _check_block(root, set())


def _check_block(block, seen_names):
    # Cycle detection
    if block.name in seen_names:
        raise SemanticError(
            f"Cycle detected: block '{block.name}' appears more than once in the tree")
    seen_names = seen_names | {block.name}

    # Root block with no 'by' clause produces a no-op sort — warn
    if not block.keys and block.parent_key is None:
        warnings.warn(
            f"sort '{block.name}' has no 'by' clause — the generated function "
            "will return data unsorted. Add at least: 'by <key> asc|desc'",
            SemanticWarning,
            stacklevel=4,
        )

    # Duplicate keys in the same by-clause
    seen_keys = {}
    for sk in block.keys:
        if sk.key in seen_keys:
            raise SemanticError(
                f"Duplicate sort key '{sk.key}' in block '{block.name}' — "
                f"first seen as '{sk.key} {seen_keys[sk.key]}', "
                f"then again as '{sk.key} {sk.direction}'")
        seen_keys[sk.key] = sk.direction

    # group-by key must not also appear in by-clause (would be redundant)
    if block.group_by and block.group_by in seen_keys:
        warnings.warn(
            f"'group-by {block.group_by}' in block '{block.name}' also appears "
            "in the 'by' clause — grouping by a sort key is usually redundant",
            SemanticWarning,
            stacklevel=4,
        )

    for child in block.children:
        if not child.keys:
            raise SemanticError(
                f"'then {child.parent_key}' block has no 'by' clause — "
                f"add at least: 'by <key> asc|desc'")
        _check_block(child, seen_names)


# ──────────────────────────────────────────────────────────────
#  PLAIN-ENGLISH PREVIEW
# ──────────────────────────────────────────────────────────────

def preview(roots, depth=0):
    """Return a plain-English description of what the sort(s) will do."""
    if isinstance(roots, SortBlock):
        roots = [roots]

    sections = []
    for root in roots:
        sections.append(_preview_block(root, depth))
    return "\n\n".join(sections)


def _preview_block(block, depth=0):
    pad = "  " * depth
    out = []
    if depth == 0:
        out.append(f"Sorting '{block.name}':")

    key_parts = []
    for sk in block.keys:
        arrow = "ascending ↑" if sk.direction == "asc" else "descending ↓"
        key_parts.append(f"'{sk.key}' {arrow}")

    if key_parts:
        out.append(f"{pad}  Sort by: {', then '.join(key_parts)}")
        out.append(f"{pad}  Null values: {block.nulls}")
    else:
        out.append(f"{pad}  (no sort keys — data returned as-is)")

    if block.stable:
        out.append(f"{pad}  Stable: yes (equal elements preserve original order)")
    if block.on_missing != "null":
        out.append(f"{pad}  On missing key: {block.on_missing}")
    if block.limit:
        out.append(f"{pad}  Limit: {block.limit} results")
    if block.group_by:
        out.append(f"{pad}  Group by: '{block.group_by}'")

    for child in block.children:
        out.append(f"{pad}  For each item, sort the '{child.parent_key}' list:")
        out.append(_preview_block(child, depth + 2))

    return "\n".join(out)


# ──────────────────────────────────────────────────────────────
#  CODE GENERATOR — helpers
# ──────────────────────────────────────────────────────────────

def _dot_access(item_var, key):
    """Emit a null-safe accessor for a possibly dotted key.

    "price"         ->  _x.get('price')
    "customer.name" ->  (_x.get('customer') or {}).get('name')
    "a.b.c"         ->  ((_x.get('a') or {}).get('b') or {}).get('c')
    """
    parts = key.split(".")
    expr = f"{item_var}.get({parts[0]!r})"
    for part in parts[1:]:
        expr = f"({expr} or {{}}).get({part!r})"
    return expr


def _type_sentinel(key):
    """Return a zero-value sentinel whose type matches the key's likely type.

    Used as the fallback value when a field is None, so that two null rows
    never raise TypeError when Python compares their sort-key tuples.

    Heuristic (first match wins, applied to the leaf segment of dotted keys):
      numeric exact: price, amount, total, weight, height, rating, rank  -> 0
      numeric suffix: _id _count _num _qty _age _score _date _time _at _on -> 0
      numeric prefix: lat lon                                              -> 0
      everything else                                                      -> ''
    """
    numeric_suffixes = (
        "_id", "_count", "_num", "_qty", "_age", "_rank", "_score",
        "_date", "_time", "_at", "_on",
    )
    numeric_exact   = {"price", "amount", "total", "weight", "height", "rating", "rank"}
    numeric_prefixes = ("lat", "lon")

    k = key.split(".")[-1].lower()
    if k in numeric_exact:
        return "0"
    if any(k.endswith(s) for s in numeric_suffixes):
        return "0"
    if any(k.startswith(p) for p in numeric_prefixes):
        return "0"
    return "''"


def _key_expr(sk, nulls, item_var="_x"):
    """Emit the sort-key tuple (null_sentinel, value) for one SortKey."""
    val           = _dot_access(item_var, sk.key)
    null_test     = f"{val} is None"
    sentinel      = _type_sentinel(sk.key)
    null_sent     = "True"  if nulls == "last"  else "False"
    notnull_sent  = "False" if nulls == "last"  else "True"
    if sk.direction == "asc":
        return (f"({null_sent} if {null_test} else {notnull_sent},"
                f" {val} if not ({null_test}) else {sentinel})")
    else:
        return (f"({null_sent} if {null_test} else {notnull_sent},"
                f" _Desc({val}) if not ({null_test}) else {sentinel})")


def _emit_sorted_call(block, data_var, item_var, pad):
    """Emit a sorted(...) call for a block's keys."""
    if not block.keys:
        return f"{pad}{data_var} = list({data_var})"
    if len(block.keys) == 1:
        key_lambda = _key_expr(block.keys[0], block.nulls, item_var)
    else:
        parts = ", ".join(_key_expr(sk, block.nulls, item_var) for sk in block.keys)
        key_lambda = f"({parts})"
    key_comment = ", ".join(f"{sk.key} {sk.direction}" for sk in block.keys)
    lines = [
        f"{pad}# by: {key_comment}  (nulls {block.nulls})",
        f"{pad}{data_var} = sorted(",
        f"{pad}    {data_var},",
        f"{pad}    key=lambda {item_var}: {key_lambda}",
        f"{pad})",
    ]
    return "\n".join(lines)


def _emit_on_missing_guard(block, data_var, pad):
    """Emit on-missing filter/guard lines before a sorted() call."""
    if block.on_missing == "null" or not block.keys:
        return None
    key_list = repr([sk.key for sk in block.keys])
    if block.on_missing == "skip":
        return (
            f"{pad}# on-missing: skip records where any sort key is absent\n"
            f"{pad}{data_var} = [_r for _r in {data_var}\n"
            f"{pad}    if all(_r.get(_k) is not None for _k in {key_list})]"
        )
    if block.on_missing == "stop":
        return (
            f"{pad}# on-missing: raise if any record is missing a sort key\n"
            f"{pad}for _r in {data_var}:\n"
            f"{pad}    _missing = [_k for _k in {key_list} if _r.get(_k) is None]\n"
            f"{pad}    if _missing:\n"
            f"{pad}        raise KeyError(\n"
            f"{pad}            f'RecSort on-missing=stop: record missing key(s) {{_missing}}: {{_r}}')"
        )
    if block.on_missing == "log":
        return (
            f"{pad}# on-missing: log records that are missing a sort key\n"
            f"{pad}import warnings as _w\n"
            f"{pad}for _r in {data_var}:\n"
            f"{pad}    _missing = [_k for _k in {key_list} if _r.get(_k) is None]\n"
            f"{pad}    if _missing:\n"
            f"{pad}        _w.warn(\n"
            f"{pad}            f'RecSort: record missing key(s) {{_missing}}: {{_r}}',\n"
            f"{pad}            stacklevel=2)"
        )
    return None


# ──────────────────────────────────────────────────────────────
#  CODE GENERATOR — block emitters
# ──────────────────────────────────────────────────────────────

def _emit_children_only(block, data_var, pad, depth):
    """Emit sort code for block's children only (no re-sort of block itself)."""
    out = []
    item_var = f"_i{depth}"

    for child in block.children:
        child_list = f'{item_var}["{child.parent_key}"]'
        child_key_comment = ", ".join(f"{sk.key} {sk.direction}" for sk in child.keys)
        out.append(f"{pad}# sub-sort '{child.parent_key}' → {child_key_comment}")
        out.append(f"{pad}for {item_var} in {data_var}:")
        inner_pad = pad + "    "
        out.append(
            f'{inner_pad}if {item_var}.get("{child.parent_key}") is None: '
            f'{item_var}["{child.parent_key}"] = []')
        guard = _emit_on_missing_guard(child, child_list, inner_pad)
        if guard:
            out.append(guard)
        if child.keys:
            out.append(_emit_sorted_call(child, child_list, "_x", inner_pad))
        else:
            out.append(f"{inner_pad}pass  # no keys defined for '{child.parent_key}'")
        if child.limit:
            out.append(f"{inner_pad}{child_list} = {child_list}[:{child.limit}]")
        if child.children:
            out.append(_emit_children_only(child, child_list, inner_pad, depth + 1))

    return "\n".join(out)


def _emit_block(block, data_var, pad, depth=0):
    """Emit sort code for a block and all its descendants.

    depth drives unique loop variables (_i0, _i1, ...) to prevent shadowing.
    """
    out = []
    item_var = f"_i{depth}"

    # 1. Sort children (innermost first) before sorting this level.
    for child in block.children:
        child_list = f'{item_var}["{child.parent_key}"]'
        child_key_comment = ", ".join(f"{sk.key} {sk.direction}" for sk in child.keys)
        out.append(f"{pad}# sub-sort '{child.parent_key}' → {child_key_comment}")
        out.append(f"{pad}for {item_var} in {data_var}:")
        inner_pad = pad + "    "
        out.append(
            f'{inner_pad}if {item_var}.get("{child.parent_key}") is None: '
            f'{item_var}["{child.parent_key}"] = []')
        guard = _emit_on_missing_guard(child, child_list, inner_pad)
        if guard:
            out.append(guard)
        if child.keys:
            out.append(_emit_sorted_call(child, child_list, "_x", inner_pad))
        else:
            out.append(f"{inner_pad}pass  # no keys defined for '{child.parent_key}'")
        if child.limit:
            out.append(f"{inner_pad}{child_list} = {child_list}[:{child.limit}]")
        if child.children:
            out.append(_emit_children_only(child, child_list, inner_pad, depth + 1))

    # 2. on-missing guard for this level
    guard = _emit_on_missing_guard(block, data_var, pad)
    if guard:
        out.append(guard)

    # 3. Sort this level
    out.append(_emit_sorted_call(block, data_var, "_x", pad))

    return "\n".join(out)


# ──────────────────────────────────────────────────────────────
#  CODE GENERATOR — function builder
# ──────────────────────────────────────────────────────────────

def generate(root, func_name=None):
    """Generate a single sort function for one SortBlock root."""
    fn = func_name or f"sort_{root.name}"
    body = _emit_block(root, "data", "    ")
    key_summary = ", ".join(f"{sk.key} {sk.direction}" for sk in root.keys)

    # Build return expression: limit → group-by → plain list
    if root.group_by:
        ret_expr = _emit_group_by_return(root, "    ")
    elif root.limit:
        ret_expr = f"    data = data[:{root.limit}]\n    return data"
    else:
        ret_expr = "    return data"

    # Assemble type hint comment (simple, no runtime import needed)
    type_hint = "list[dict]"
    if root.group_by:
        type_hint = "dict[str, list[dict]]"

    code = textwrap.dedent(f"""\
        # ── RecSort generated function ──────────────────────────────────
        # sort {root.name}: {key_summary}  |  nulls {root.nulls}

        def {fn}(data: list[dict]) -> {type_hint}:
            \"\"\"Sort '{root.name}' — generated by RecSort v0.2.\"\"\"
        """)
    code += body + "\n" + ret_expr + "\n"
    return code


def _emit_group_by_return(root, pad):
    """Emit the group-by dict-building return block."""
    gk = root.group_by
    lines = [
        f"{pad}# group-by '{gk}'",
        f"{pad}_groups: dict = {{}}",
        f"{pad}for _g in data:",
        f"{pad}    _gv = _g.get({gk!r})",
        f"{pad}    _groups.setdefault(_gv, []).append(_g)",
        f"{pad}return _groups",
    ]
    if root.limit:
        lines.insert(-1, f"{pad}for _gv in _groups: _groups[_gv] = _groups[_gv][:{root.limit}]")
    return "\n".join(lines)


def _runtime_header():
    return textwrap.dedent("""\
        # ── RecSort runtime helper ───────────────────────────────────────
        class _Desc:
            \"\"\"Wraps a value so it sorts descending via comparison inversion.\"\"\"
            __slots__ = ("v",)
            def __init__(self, v): self.v = v
            def __lt__(self, o):   return (self.v > o.v) if isinstance(o, _Desc) else NotImplemented
            def __eq__(self, o):   return (self.v == o.v) if isinstance(o, _Desc) else NotImplemented
            def __le__(self, o):   return self.v >= o.v
            def __gt__(self, o):   return self.v < o.v
            def __ge__(self, o):   return self.v <= o.v


    """)


def compile_nst(source, func_name=None):
    """Compile a single-block .nst source string to Python code."""
    roots = parse(source)
    analyse(roots)
    if len(roots) == 1:
        return _runtime_header() + generate(roots[0], func_name)
    # Multi-block: func_name applies only to the first block
    parts = [_runtime_header()]
    for idx, root in enumerate(roots):
        fn = func_name if idx == 0 and func_name else None
        parts.append(generate(root, fn))
    return "\n".join(parts)


def compile_nst_multi(source):
    """Compile a multi-block .nst source, returning (code, [func_names])."""
    roots = parse(source)
    analyse(roots)
    func_names = [f"sort_{r.name}" for r in roots]
    parts = [_runtime_header()] + [generate(r) for r in roots]
    return "\n".join(parts), func_names


# ──────────────────────────────────────────────────────────────
#  CHECKER  (validate sort against real JSON data)
# ──────────────────────────────────────────────────────────────

def check(roots, data):
    """Run each sort function against data and report issues.

    Returns a list of finding strings.  Empty list means all clear.
    ``data`` should be a list of dicts matching the first root's schema.
    """
    if isinstance(roots, SortBlock):
        roots = [roots]

    findings = []

    for root in roots:
        fn_name = f"sort_{root.name}"
        code = _runtime_header() + generate(root, fn_name)
        ns = {}
        try:
            exec(code, ns)
        except Exception as e:
            findings.append(f"[{root.name}] Code generation error: {e}")
            continue

        import copy
        try:
            result = ns[fn_name](copy.deepcopy(data))
        except KeyError as e:
            findings.append(f"[{root.name}] on-missing=stop raised: {e}")
            continue
        except Exception as e:
            findings.append(f"[{root.name}] Runtime error: {e}")
            continue

        # Report keys that were missing from actual records
        all_keys = _collect_keys(root)
        for key in all_keys:
            missing_count = sum(1 for r in data if r.get(key) is None)
            if missing_count:
                findings.append(
                    f"[{root.name}] Key '{key}': {missing_count}/{len(data)} "
                    f"records have null or missing value")

        # Verify output is actually sorted
        sort_issue = _verify_sorted(result, root)
        if sort_issue:
            findings.append(f"[{root.name}] {sort_issue}")
        else:
            findings.append(f"[{root.name}] ✓ output verified sorted correctly "
                            f"({len(result)} records)")

    return findings


def _collect_keys(block):
    """Collect all key names in a block tree (flat list, top level only)."""
    return [sk.key for sk in block.keys]


def _verify_sorted(result, block):
    """Return an error string if result is not sorted per block.keys, else None."""
    if not block.keys or len(result) < 2:
        return None
    for i in range(len(result) - 1):
        a, b = result[i], result[i + 1]
        for sk in block.keys:
            va = a.get(sk.key)
            vb = b.get(sk.key)
            # nulls: skip comparison if either side is null
            if va is None or vb is None:
                continue
            try:
                if sk.direction == "asc" and va > vb:
                    return (f"Output not sorted: record {i} has {sk.key}={va!r} "
                            f"but record {i+1} has {sk.key}={vb!r} (expected asc)")
                if sk.direction == "desc" and va < vb:
                    return (f"Output not sorted: record {i} has {sk.key}={va!r} "
                            f"but record {i+1} has {sk.key}={vb!r} (expected desc)")
                if va != vb:
                    break  # this key differs and is in order — stop checking keys
            except TypeError:
                continue  # incomparable types; skip
    return None


# ──────────────────────────────────────────────────────────────
#  BUILT-IN DEMO
# ──────────────────────────────────────────────────────────────

DEMO_NST = """\
sort orders
  by status asc, date desc
  then items
    by price asc
  nulls last
"""

DEMO_DATA = [
    {"id": 1, "status": "pending", "date": 20240310,
     "items": [{"name": "Widget",      "price": 9.99},
               {"name": "Gadget",      "price": None},
               {"name": "Doohickey",   "price": 4.50}]},
    {"id": 2, "status": "active",  "date": 20240401,
     "items": [{"name": "Sprocket",    "price": 19.99},
               {"name": "Cog",         "price": 2.00}]},
    {"id": 3, "status": "active",  "date": 20240315,
     "items": [{"name": "Thingamajig", "price": 7.50}]},
    {"id": 4, "status": None,      "date": 20240101,
     "items": []},
    {"id": 5, "status": "pending", "date": 20240101,
     "items": [{"name": "Bolt",        "price": 0.99}]},
]


def run_demo():
    sep = "─" * 58
    print(f"\n{'RecSort v0.2 — Demo':^58}")
    print(sep)

    print("\n.nst script:\n")
    for line in DEMO_NST.splitlines():
        print(f"  {line}")

    roots = parse(DEMO_NST)
    analyse(roots)

    print("\nPlain-English preview:\n")
    for line in preview(roots).splitlines():
        print(f"  {line}")

    code = _runtime_header() + generate(roots[0], "sort_orders")

    print("\nGenerated Python:\n")
    for line in code.splitlines():
        print(f"  {line}")

    import copy
    ns = {}
    exec(code, ns)
    result = ns["sort_orders"](copy.deepcopy(DEMO_DATA))

    print(f"\nResult ({len(result)} orders):\n")
    for o in result:
        items = ", ".join(
            f"{i['name']}(${i['price'] if i['price'] is not None else 'null'})"
            for i in o["items"]
        ) or "(empty)"
        status = o["status"] or "null"
        print(f"  id={o['id']}  status={status:10s}  date={o['date']}")
        print(f"    items: {items}")

    print(f"\n  ✓ orders: status asc, date desc, nulls last")
    print(f"  ✓ items:  price asc, nulls last\n")
    print(sep)


# ──────────────────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────────────────

def _parse_flag(args, flag, takes_value=False):
    """Extract a flag (and optionally its value) from an args list."""
    if flag not in args:
        return (False, None) if takes_value else False
    idx = args.index(flag)
    if takes_value:
        if idx + 1 >= len(args):
            print(f"Error: {flag} requires a value")
            sys.exit(EXIT_IO_ERR)
        return True, args[idx + 1]
    return True


def main():
    args = sys.argv[1:]

    if not args or "-h" in args or "--help" in args:
        print(__doc__)
        sys.exit(EXIT_OK)

    if "--demo" in args:
        run_demo()
        sys.exit(EXIT_OK)

    # Positional: first non-flag arg is the source file
    positional = [a for a in args if not a.startswith("-")]
    if not positional:
        print("Error: no .nst file specified.")
        sys.exit(EXIT_IO_ERR)

    src = Path(positional[0])
    if not src.exists():
        print(f"Error: '{src}' not found.")
        sys.exit(EXIT_IO_ERR)

    source = src.read_text()

    # --output / --function-name flags
    _, output_path  = _parse_flag(args, "--output",        takes_value=True)
    _, func_name    = _parse_flag(args, "--function-name", takes_value=True)
    _, check_data   = _parse_flag(args, "--check",         takes_value=True)

    # --preview
    if "--preview" in args:
        try:
            roots = parse(source)
            analyse(roots)
            print(preview(roots))
        except (ParseError, SemanticError) as e:
            print(f"Error: {e}")
            sys.exit(EXIT_PARSE_ERR)
        sys.exit(EXIT_OK)

    # --check
    if check_data:
        check_path = Path(check_data)
        if not check_path.exists():
            print(f"Error: data file '{check_path}' not found.")
            sys.exit(EXIT_IO_ERR)
        try:
            data = json.loads(check_path.read_text())
        except json.JSONDecodeError as e:
            print(f"Error: could not parse JSON: {e}")
            sys.exit(EXIT_IO_ERR)
        try:
            roots = parse(source)
            analyse(roots)
        except (ParseError, SemanticError) as e:
            print(f"Error: {e}")
            sys.exit(EXIT_PARSE_ERR)
        findings = check(roots, data)
        for f in findings:
            print(f)
        has_errors = any("✓" not in f for f in findings)
        sys.exit(EXIT_CHECK_FAIL if has_errors else EXIT_OK)

    # Normal compile
    try:
        code, func_names = compile_nst_multi(source)
        # If user supplied --function-name, rename the first function
        if func_name and func_names:
            old = f"def sort_{parse(source)[0].name}("
            new = f"def {func_name}("
            code = code.replace(old, new, 1)
            func_names[0] = func_name
    except (ParseError, SemanticError) as e:
        kind = "Parse" if isinstance(e, ParseError) else "Semantic"
        print(f"{kind} error: {e}")
        sys.exit(EXIT_PARSE_ERR if isinstance(e, ParseError) else EXIT_SEM_ERR)

    out = Path(output_path) if output_path else src.with_suffix(".py")
    try:
        out.write_text(code)
    except OSError as e:
        print(f"IO error: {e}")
        sys.exit(EXIT_IO_ERR)

    fns = ", ".join(func_names)
    print(f"✓ {src} → {out}  (functions: {fns})")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
