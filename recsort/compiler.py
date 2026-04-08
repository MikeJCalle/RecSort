# Written by: Michael Calle
# Written on: 4/5/2026

"""
RecSort — Recursive Sort Expression Compiler  (prototype v0.1)

Compiles a .nst declaration into a self-contained Python sort function.

Usage:
    python recsort.py --demo                   run built-in demo
    python recsort.py <file.nst>               compile → <file.py>
    python recsort.py <file.nst> --preview     plain-English plan only

.nst syntax:
    sort <name>
      by <key> asc|desc [, <key> asc|desc ...]
      then <list-key>
        by <subkey> asc|desc
      nulls first|last
"""

import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path


# ──────────────────────────────────────────────────────────────
#  DATA TYPES
# ──────────────────────────────────────────────────────────────

@dataclass
class SortKey:
    key: str
    direction: str  # "asc" or "desc"


@dataclass
class SortBlock:
    name: str
    keys: list
    nulls: str              # "first" or "last"
    children: list = field(default_factory=list)  # list[SortBlock]
    parent_key: str = None  # the key in the parent whose list we sort


#  LEXER  (line-by-line, indent-aware)
class ParseError(Exception):
    pass

class SemanticError(Exception):
    pass


def _tokenise(line):
    """Split a stripped line into tokens, stripping commas."""
    return [t.rstrip(",") for t in line.split() if t.rstrip(",")]


def _indent(line):
    return len(line) - len(line.lstrip(" "))


#  PARSER  (iterative stack-based, no recursion)
def parse(source):
    raw_lines = source.splitlines()

    # strip blank lines and comments, keep (lineno, indent, tokens)
    lines = []
    for i, raw in enumerate(raw_lines, 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append((i, _indent(raw), _tokenise(stripped)))

    if not lines:
        raise ParseError("Empty .nst file — nothing to parse.")

    lineno, indent, tokens = lines[0]
    if tokens[0] != "sort" or len(tokens) < 2:
        raise ParseError(f"Line {lineno}: file must begin with 'sort <name>'")

    # Build a flat list of (indent, tokens) for everything after the header
    body = lines[1:]

    # We'll use a stack to track open blocks.
    # Each stack frame = SortBlock being built.
    root = SortBlock(name=tokens[1], keys=[], nulls="last")
    stack = [(0, root)]  # (indent_level, block)

    for lineno, ind, toks in body:
        if not toks:
            continue

        # Find the parent block: deepest stack entry whose indent < current
        while len(stack) > 1 and stack[-1][0] >= ind:
            stack.pop()

        current_block = stack[-1][1]
        verb = toks[0]

        if verb == "by":
            rest = toks[1:]
            i = 0
            while i < len(rest):
                k = rest[i]
                if not k:
                    i += 1
                    continue
                d = "asc"
                if i + 1 < len(rest) and rest[i + 1] in ("asc", "desc"):
                    d = rest[i + 1]
                    i += 2
                else:
                    i += 1
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
                raise ParseError(f"Line {lineno}: 'nulls' must be followed by 'first' or 'last'")

        # unknown lines silently skipped (future syntax extensions)

    return root


#  SEMANTIC ANALYSIS
def analyse(root):
    """Walk the block tree and enforce correctness rules."""
    _check_block(root, set())


def _check_block(block, seen_names):
    # Cycle: same block name must not appear twice in the tree
    if block.name in seen_names:
        raise SemanticError(f"Cycle detected: block '{block.name}' appears more than once")
    seen_names = seen_names | {block.name}

    for child in block.children:
        if not child.keys:
            raise SemanticError(
                f"'then {child.parent_key}' block has no 'by' clause — "
                f"add at least: 'by <key> asc|desc'"
            )
        _check_block(child, seen_names)


#  PLAIN-ENGLISH PREVIEW
def preview(block, depth=0):
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

    for child in block.children:
        out.append(f"{pad}  For each item, sort the '{child.parent_key}' list:")
        out.append(preview(child, depth + 2))

    return "\n".join(out)


#  CODE GENERATOR
def _key_expr(sk, nulls, item_var="_x"):
    """Emit the sort-key tuple (null_sentinel, value) for a single SortKey.

    Tuple element 1: a boolean that pushes nulls to the right place.
      - For nulls=last:  None -> True  (sorts after False)
      - For nulls=first: None -> False (sorts before True)
    Tuple element 2: the actual value (wrapped in _Desc for desc direction).
      - For null entries we use a safe sentinel so element 2 is never compared.
    """
    null_test = f"{item_var}.get({sk.key!r}) is None"
    val       = f"{item_var}.get({sk.key!r})"
    # sentinel: True = sort last, False = sort first
    null_sentinel = "True" if nulls == "last" else "False"
    not_null_sentinel = "False" if nulls == "last" else "True"
    if sk.direction == "asc":
        # nulls push to correct side; real values sort naturally
        return (f"({null_sentinel} if {null_test} else {not_null_sentinel},"
                f" {val} if not ({null_test}) else '')")
    else:
        # descending: wrap non-null values in _Desc for inverted comparison
        return (f"({null_sentinel} if {null_test} else {not_null_sentinel},"
                f" _Desc({val}) if not ({null_test}) else '')")


def _emit_sorted_call(block, data_var, item_var, pad):
    """Emit a sorted(...) call for a block's keys."""
    if not block.keys:
        return f"{pad}{data_var} = {data_var}"
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


def _emit_block(block, data_var, pad):
    """Recursively emit sort code for a block and its children."""
    out = []
    # 1. sort children (inner lists) first
    for child in block.children:
        child_item = "_ci"
        child_list = f'{child_item}["{child.parent_key}"]'
        child_key_comment = ", ".join(f"{sk.key} {sk.direction}" for sk in child.keys)
        out.append(f"{pad}# sub-sort '{child.parent_key}' within each item → {child_key_comment}")
        out.append(f"{pad}for {child_item} in {data_var}:")
        inner_pad = pad + "    "
        # normalise None → [] so sorted() never sees a NoneType
        out.append(f'{inner_pad}if {child_item}.get("{child.parent_key}") is None: {child_item}["{child.parent_key}"] = []')
        if child.keys:
            out.append(_emit_sorted_call(child, child_list, "_si", inner_pad))
        else:
            out.append(f"{inner_pad}pass  # no keys defined for '{child.parent_key}'")

    # 2. sort this level
    out.append(_emit_sorted_call(block, data_var, "_x", pad))
    return "\n".join(out)


def generate(root, func_name=None):
    fn = func_name or f"sort_{root.name}"
    body = _emit_block(root, "data", "    ")
    key_summary = ", ".join(f"{sk.key} {sk.direction}" for sk in root.keys)

    code = textwrap.dedent(f"""\
        # ── NestSort generated function ──────────────────────────────────
        # sort {root.name}: {key_summary}  |  nulls {root.nulls}

        def {fn}(data):
            \"\"\"Sort '{root.name}' — generated by NestSort v0.1.\"\"\"
        """)
    # indent body
    code += body + "\n    return data\n"
    return code


def _runtime_header():
    return textwrap.dedent("""\
        # ── NestSort runtime helper ───────────────────────────────────────
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
    root = parse(source)
    analyse(root)
    return _runtime_header() + generate(root, func_name)


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
    print(f"\n{'NestSort v0.1 — Demo':^58}")
    print(sep)

    print("\n.nst script:\n")
    for line in DEMO_NST.splitlines():
        print(f"  {line}")

    root = parse(DEMO_NST)
    analyse(root)

    print("\nPlain-English preview:\n")
    for line in preview(root).splitlines():
        print(f"  {line}")

    code = _runtime_header() + generate(root, "sort_orders")

    print("\nGenerated Python:\n")
    for line in code.splitlines():
        print(f"  {line}")

    # execute and show results
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

def main():
    args = sys.argv[1:]

    if not args or "-h" in args or "--help" in args:
        print(__doc__)
        return

    if "--demo" in args:
        run_demo()
        return

    src = Path(args[0])
    if not src.exists():
        print(f"Error: '{src}' not found.")
        sys.exit(1)

    source = src.read_text()

    if "--preview" in args:
        try:
            root = parse(source)
            analyse(root)
            print(preview(root))
        except (ParseError, SemanticError) as e:
            print(f"Error: {e}")
            sys.exit(1)
        return

    try:
        code = compile_nst(source, f"sort_{src.stem}")
    except (ParseError, SemanticError) as e:
        print(f"Compile error: {e}")
        sys.exit(1)

    out = src.with_suffix(".py")
    out.write_text(code)
    print(f"✓ {src} → {out}  (function: sort_{src.stem})")


if __name__ == "__main__":
    main()
