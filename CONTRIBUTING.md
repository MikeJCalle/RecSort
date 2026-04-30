# Contributing to RecSort

Thanks for your interest in contributing. RecSort is a small, focused compiler — every part of the codebase is intentionally readable and approachable.

---

## Project layout

```
recsort/
├── recsort/
│   ├── __init__.py       # public API exports
│   ├── __main__.py       # python -m recsort entry point
│   └── compiler.py       # full pipeline: lexer → parser → semantic → codegen
├── tests/
│   ├── test_integration.py            # end-to-end compile + execute tests
│   ├── test_parser.py                 # lexer and parser unit tests
│   ├── test_semantic.py               # semantic analysis tests
│   ├── test_deep_nesting.py           # arbitrary-depth then-block tests
│   ├── test_dot_notation_and_sentinel.py  # dot-key access + null sentinel tests
│   └── test_v2_features.py            # v0.2 feature tests (stable, limit, group-by, etc.)
├── examples/
│   ├── orders.nst
│   ├── products.nst
│   └── employees.nst
├── .github/workflows/
│   └── ci.yml
├── pyproject.toml
├── README.md
└── CONTRIBUTING.md
```

---

## Setting up locally

```bash
git clone https://github.com/your-username/recsort
cd recsort
pip install -e ".[dev]"
pytest
```

---

## Compiler pipeline

Every `.nst` file passes through five stages in `compiler.py`:

1. **Lexer** — `_tokenise` / `_indent`: strips comments, splits lines into (lineno, indent, tokens)
2. **Parser** — `parse()`: iterative stack-based parser that builds a tree of `SortBlock` objects
3. **Semantic analysis** — `analyse()`: walks the tree checking for cycles, duplicate keys, missing `by` clauses, etc.
4. **Preview** — `preview()`: walks the tree and produces a plain-English description (no code emitted)
5. **Code generator** — `generate()` / `_emit_block()` / `_emit_children_only()`: emits self-contained Python

---

## Open contribution areas

Issues are labelled by area. Pick one and open a PR.

### `core` — compiler pipeline

- **Fuzz / property-based tests** — use Hypothesis to verify the output is always a valid permutation of the input and is always correctly sorted
- **Inline type hints in `.nst`** — allow `by price: float asc` to make the null sentinel explicit and reliable instead of name-heuristic-based
- **`by count(<list-key>) asc`** — sort the outer list by a derived property of an inner list (e.g. sort orders by how many items they contain)
- **Scalar inner lists** — support `then tags` when `tags` is a list of strings/ints rather than a list of dicts

### `syntax-ext` — new `.nst` keywords

- **`--watch` mode** — re-compile on file save using `watchfiles`
- **`recsort fmt`** — canonical formatter/pretty-printer for `.nst` files (normalize indentation and spacing)

### `tooling`

- **VS Code extension** — TextMate grammar for `.nst` syntax highlighting (5 keywords: `sort`, `by`, `then`, `nulls`, `on-missing`)
- **Web playground** — single-page app running the compiler via Pyodide (Python in the browser); the compiler has no third-party dependencies so it runs in Pyodide unchanged

---

## Code style

- Python 3.9+ compatible
- Standard library only in `recsort/compiler.py` — no third-party imports
- All new features need tests; aim for the same structure as existing test files
- New `.nst` keywords must be handled in: parser (`parse`), semantic analyser (`_check_block`), preview (`_preview_block`), and code generator (`_emit_block` / `generate`)

---

## Running tests

```bash
pytest                        # all tests
pytest tests/test_parser.py   # one suite
pytest -v                     # verbose
pytest --cov=recsort          # with coverage (requires pytest-cov)
```

---

## Submitting a PR

1. Fork the repo and create a branch: `git checkout -b feat/my-feature`
2. Make your changes and add tests
3. Run `pytest` — all tests must pass
4. Open a pull request with a short description of what and why

---

## Questions

Open a GitHub Discussion or drop a comment on the relevant issue.
