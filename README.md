# RecSort

**Recursive sort expression compiler.** Write a short `.nst` declaration, get a clean, null-safe, self-contained Python sort function — no runtime dependency, no boilerplate.

```
sort orders
  by status asc, date desc
  then items
    by price asc
  nulls last
```

Compiles to a ready-to-use `sort_orders(data)` Python function that correctly handles every nesting level, null value, and sort direction.

---

## The problem

Sorting a flat list in Python is one line. Sorting nested data — a list of orders each containing a list of items, with mixed-direction keys and nullable fields — means writing the same fragile lambda tower from scratch every single time:

```python
# what you'd have to write manually
def sort_orders(orders):
    for o in orders:
        o["items"] = sorted(
            o.get("items") or [],
            key=lambda x: (x.get("price") is None, x.get("price"))
        )
    return sorted(orders, key=lambda o: (
        o.get("status") is None, o.get("status"),
        -(o.get("date") or 0)
    ))
```

RecSort generates that code from a short declaration — and catches errors like duplicate keys and missing `by` clauses *before* any code runs.

---

## Installation

```bash
pip install recsort          # once published to PyPI
# or from source:
git clone https://github.com/your-username/recsort
cd recsort && pip install -e .
```

---

## Quick start

**1. Write a `.nst` file**

```
# orders.nst
sort orders
  by status asc, date desc
  then items
    by price asc
  nulls last
```

**2. Compile it**

```bash
recsort orders.nst
# ✓ orders.nst → orders.py  (functions: sort_orders)
```

**3. Use the generated function**

```python
from orders import sort_orders

result = sort_orders(my_data)
```

The generated `orders.py` has zero imports and no dependency on RecSort at runtime.

---

## CLI reference

```bash
recsort <file.nst>                          # compile → <file.py>
recsort <file.nst> --preview                # plain-English plan, no file written
recsort <file.nst> --output <path>          # write output to a specific path
recsort <file.nst> --function-name <name>   # override generated function name
recsort <file.nst> --check <data.json>      # validate sort against real data
recsort --demo                              # run built-in demo with sample data
recsort --help
```

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Parse error |
| `2` | Semantic error |
| `3` | IO error (file not found, write failure) |
| `4` | Check failed (sort validation found issues) |

---

## `.nst` syntax

```
sort <name>
  by <key> asc|desc [, <key> asc|desc ...]
  then <list-key>
    by <subkey> asc|desc
  nulls first|last
  stable
  limit <N>
  group-by <key>
  on-missing skip|stop|log
```

| Keyword | Description |
|---------|-------------|
| `sort <name>` | Names the block and the generated function (`sort_<name>`) |
| `by <key> asc\|desc` | Sort key with direction. Chain multiple with commas. |
| `then <list-key>` | Sub-sort: for each item, sort the nested list at `item["list-key"]`. Nestable to any depth. |
| `nulls first\|last` | Where `None` values land. Default: `last` |
| `stable` | Documents that equal elements preserve their original order (guaranteed by Python's Timsort) |
| `limit <N>` | Truncate the result to N items after sorting |
| `group-by <key>` | Return a `dict` keyed by field instead of a flat sorted list |
| `on-missing skip\|stop\|log` | Behaviour when a sort key is absent from a record. Default: treat as `null` |

**Dot notation** is supported for nested dict keys at any level: `by customer.name asc`, `by meta.score desc`.

### Multiple sort blocks per file

A single `.nst` file can contain multiple `sort` blocks. Each compiles to its own function, all written to the same output `.py` file:

```
sort orders
  by status asc, date desc
  then items
    by price asc
  nulls last

sort products
  by category asc, rating desc
  limit 50
```

Compiles to both `sort_orders(data)` and `sort_products(data)` in one file.

---

## Preview mode

Before compiling, see exactly what will happen in plain English:

```bash
recsort orders.nst --preview
```

```
Sorting 'orders':
  Sort by: 'status' ascending ↑, then 'date' descending ↓
  Null values: last
  For each item, sort the 'items' list:
      Sort by: 'price' ascending ↑
      Null values: last
```

---

## Check mode

Compile and run the sort against a real JSON file to catch problems before production:

```bash
recsort orders.nst --check sample_data.json
```

```
[orders] Key 'status': 2/50 records have null or missing value
[orders] ✓ output verified sorted correctly (50 records)
```

---

## What gets generated

The emitted Python is readable, commented, type-annotated, and self-contained:

```python
# ── RecSort runtime helper ────────────────────────────────────
class _Desc:
    """Wraps a value so it sorts descending via comparison inversion."""
    ...

# ── RecSort generated function ────────────────────────────────
# sort orders: status asc, date desc  |  nulls last

def sort_orders(data: list[dict]) -> list[dict]:
    """Sort 'orders' — generated by RecSort v0.2."""
    # sub-sort 'items' → price asc
    for _i0 in data:
        if _i0.get("items") is None: _i0["items"] = []
        # by: price asc  (nulls last)
        _i0["items"] = sorted(
            _i0["items"],
            key=lambda _x: (True if _x.get('price') is None else False,
                            _x.get('price') if not (_x.get('price') is None) else 0)
        )
    # by: status asc, date desc  (nulls last)
    data = sorted(
        data,
        key=lambda _x: (
            (True if _x.get('status') is None else False,
             _x.get('status') if not (_x.get('status') is None) else ''),
            (True if _x.get('date') is None else False,
             _Desc(_x.get('date')) if not (_x.get('date') is None) else 0)
        )
    )
    return data
```

---

## Examples

See the [`examples/`](examples/) folder for ready-to-run `.nst` scripts:

| File | What it sorts |
|------|--------------|
| `orders.nst` | Orders by status + date, items by price |
| `products.nst` | Products by category + rating, reviews by score |
| `employees.nst` | Employees by department + hire date, skills by level |

---

## Running tests

```bash
pip install pytest
pytest
```

---

## Contributing

Contributions welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for details.

---

## Changelog

### v0.2.0

#### New language features

- **Arbitrary-depth nesting** — `then` blocks now nest to any depth (orders → items → tags → attributes). Previously only one level was supported. The code generator uses unique loop variables (`_i0`, `_i1`, ...) at each depth to prevent shadowing.
- **Dot-notation key access** — `by customer.name asc` and `by meta.score desc` now work correctly. Previously dot keys were passed as literal strings to `.get()` which always returned `None`. Each segment now emits a chained null-safe accessor: `(_x.get('customer') or {}).get('name')`.
- **`stable` keyword** — declare that a sort block preserves the original order of equal elements. Python's Timsort already guarantees this; the keyword makes it explicit and visible in `--preview` output.
- **`limit N`** — truncate the sorted result to N items. Works at any nesting level, including inside `then` blocks.
- **`group-by <key>`** — instead of returning a flat sorted list, return a `dict` keyed by the specified field. Each group contains the sorted records that share that field value.
- **`on-missing skip|stop|log`** — control what happens when a record is missing a sort key entirely (not just `null`). `skip` removes the record, `stop` raises `KeyError`, `log` emits a `warnings.warn` and keeps the record. Default behaviour (treat as `null`) is unchanged.
- **Multiple `sort` blocks per file** — a single `.nst` file can now contain any number of `sort` blocks, each compiling to its own function in the output file.

#### New CLI flags

- **`--output <path>`** — write the compiled `.py` to any path instead of always placing it next to the `.nst` file.
- **`--function-name <name>`** — override the generated function name from the command line without editing the `.nst` file.
- **`--check <data.json>`** — compile the `.nst`, run the generated sort against a real JSON file, report which keys had null or missing values, and verify the output is correctly ordered.
- **Structured exit codes** — the CLI now exits with `0` (success), `1` (parse error), `2` (semantic error), `3` (IO error), or `4` (check failure) instead of only `0` or `1`.

#### Semantic analysis improvements

- **Duplicate sort key detection** — `by value asc, value desc` in the same `by` clause now raises `SemanticError` at compile time instead of silently producing nonsense output.
- **Missing root `by` clause warning** — a `sort` block with no `by` clause now emits a `SemanticWarning` instead of silently compiling to a function that returns data unsorted.
- **Duplicate block name detection** — two `sort` blocks with the same name in one file now raises `SemanticError`.
- **`group-by` redundancy warning** — warns when the `group-by` key also appears in the `by` clause, which is almost always unintentional.

#### Code generation improvements

- **Type annotations** — generated functions now carry Python type hints: `def sort_x(data: list[dict]) -> list[dict]` for flat sorts, `-> dict[str, list[dict]]` for `group-by` sorts.
- **Type-aware null sentinels** — the fallback value used when a field is `None` is now inferred from the key name. Keys matching numeric patterns (`price`, `*_id`, `*_count`, `*_date`, `latitude`, etc.) use `0` as their sentinel; all others use `''`. Previously every key used `''`, which caused a silent `TypeError` when comparing two null rows on an integer key.
- **Unique loop variables** — nested `for` loops now use `_i0`, `_i1`, `_i2`, ... instead of the hardcoded `_ci`/`_si` pair, preventing variable shadowing at more than one level of nesting.

#### Bug fixes

- Dot-notation keys (`by a.b asc`) previously compiled to `_x.get('a.b')` — a literal string lookup that always returned `None`. Fixed to emit `(_x.get('a') or {}).get('b')`.
- All-null lists on numeric keys (e.g. `[{"price": None}, {"price": None}]`) previously raised `TypeError` during sort comparison. Fixed by the type-aware sentinel change above.
- `then` blocks deeper than one level were silently dropped by the code generator. Fixed by true recursive emission with `_emit_children_only`.

---

## License

MIT — see [`LICENSE`](LICENSE).
