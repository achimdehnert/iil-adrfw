# CLAUDE.md — iil-adrfw

Operating guide for an AI agent working in this repo. Repo-specific; the
user-level `~/.claude/CLAUDE.md` still applies and wins on conflicts.

## What this is

`iil-adrfw` is the platform's **Architectural Decision Record framework**: it
loads a directory of `ADR-*.md` files, normalizes + schema-validates their
frontmatter, builds a cross-ADR constitution graph, and runs audits, diffs,
narration, proposals, freshness and cross-repo checks over it. Shipped as a
PyPI library plus two entry points: the `iil-adrfw` CLI and the `iil-adrfw-mcp`
FastMCP server.

## Setup

```bash
python3 -m pip install -e ".[dev]"   # editable install with dev extras
```

`__version__` is read from installed package metadata (`iil_adrfw.__version__`).

## Test / lint / types

```bash
make test     # python3 -m pytest examples/   (the suite lives in examples/)
make lint     # python3 -m ruff check .
make types    # python3 -m mypy src/iil_adrfw   (advisory — not yet green, see Known issues)
```

- Tests use `pytest-randomly`; they must pass in **any** order. Never configure
  shared global state (env vars, singletons) at module import time — set it
  per-test via an autouse fixture + `monkeypatch` (see `examples/test_e2e_*.py`).
- The server resolves the ADR directory from `IIL_ADRFW_ADRS_DIR` (fresh per
  call, no caching).

## Architecture (module map)

| Module | Responsibility |
|---|---|
| `domain/` | `ADR` dataclass, `Status` enum, temporal + relation types |
| `persistence/` | `load_adrs()`, `ADRLoadError`, frontmatter normalization + schema validation |
| `schemas/` | JSON Schemas (`adr_frontmatter.schema.json`, Schema v3/v4) |
| `graph/` | `ConstitutionGraph` — dependency/supersession edges, cycle detection |
| `audit/` | `run_audit()` + auditor suite (staleness, supersession hygiene, …) |
| `diff/` | `diff_set()`, `diff_temporal()` |
| `narrate/` | `compose_narrative()`, `Audience` |
| `propose/` | ADR proposal generation |
| `cross_repo/` | cross-repo claim validation |
| `freshness/` | repo-vs-ADR drift checks |
| `metrics/` | Schema v4 controlling metrics (`iil-adrfw metrics`) |
| `checkers/` | AST checkers (libcst-based) |
| `server.py` | FastMCP request models + `_do_*` handlers |
| `cli.py` | `iil-adrfw` command-line entry point |

## Conventions

- Commits: `[feat|fix|refactor|docs|test|chore](scope): description`.
- Tests: `test_should_<expected_behavior>` (ADR-057; enforced via `iil-testkit`).
- ADR schema is the source of truth — change the schema + validator together.

## Release

Versioned in `pyproject.toml` + `CHANGELOG.md` (Keep a Changelog). Publish to
PyPI is a deliberate, gated step (CI `publish.yml`, `workflow_dispatch`) — not
automatic on merge. Keep `pyproject.version`, the CHANGELOG top entry, and the
published PyPI version in sync.

## Known issues / gotchas

- `make types` (mypy) has a config but is **not** yet green (37 errors) and is
  advisory — not gated in CI. Driving it to zero is a good first optimization.
- `make test` enforces `--cov-fail-under=55` (actual ~59%); raise as it improves.
- See `AGENT_HANDOVER.md` for current state and next priorities.
