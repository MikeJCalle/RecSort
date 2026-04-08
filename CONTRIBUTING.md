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
│   ├── test_lexer.py
│   ├── test_parser.py
│   ├── test_semantic.py
│   └── test_integration.py
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

## Open contribution areas

Issues are labelled by area. Pick one and open a PR.

### `core` — compiler pipeline

- **Indent-aware parser edge cases** — test and fix edge cases with mixed indentation
- **Semantic: direction inconsistency** — flag when the same key is declared with conflicting directions across levels
- **Code-gen: multi-level nesting** — ensure `then` blocks nest more than one level deep

### `syntax-ext` — new `.nst` keywords

- **`stable` modifier** — emit a sort that preserves original order for equal elements (Python's `sorted` is already stable, just needs to be documented and tested)
- **`on-missing skip|stop|log`** — when a key is absent from a dict, skip the item / raise / log and continue

### `tooling`

- **`recsort check <file.nst> <data.json>`** — compile the script, run it against a JSON file, and print the first 20 results for manual inspection
- **`--watch` mode** — re-compile on file save using `watchfiles`
- **VS Code extension** — TextMate grammar for `.nst` syntax highlighting

---

## Code style

- Python 3.9+ compatible
- Standard library only in `recsort/compiler.py` — no third-party imports
- Type annotations encouraged but not required for prototypes
- All new features need at least one test

---

## Running tests

```bash
pytest                        # all tests
pytest tests/test_parser.py   # one suite
pytest -v                     # verbose
pytest --cov=recsort         # with coverage (requires pytest-cov)
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
