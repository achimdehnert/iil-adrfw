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
python3 -m venv .venv && source .venv/bin/activate   # PEP-668-managed hosts
python3 -m pip install -e ".[dev]"   # editable install with dev extras
```

Fallback if a venv isn't an option (PEP-668-managed hosts):
`pip install --user --break-system-packages -e ".[dev]"`.

`__version__` is read from installed package metadata (`iil_adrfw.__version__`).

## Test / lint / types

```bash
make test     # python3 -m pytest examples/   (the suite lives in examples/)
make lint     # python3 -m ruff check .
make types    # python3 -m mypy src/iil_adrfw   (zero errors — gated in CI, keep it green)
```

- Tests use `pytest-randomly`; they must pass in **any** order. Never configure
  shared global state (env vars, singletons) at module import time — set it
  per-test via an autouse fixture + `monkeypatch` (see `examples/test_e2e_*.py`).
- The server resolves the ADR directory from `IIL_ADRFW_ADRS_DIR` (fresh per
  call, no caching). Schema directory resolution follows the same pattern via
  `IIL_ADRFW_SCHEMAS_DIR` (defaults to the bundled `schemas/`; see
  `_schemas_dir()` in `server.py`). See `docs/CASCADE_PIPELINE.md` for how a
  CI/Cascade pipeline sets both env vars, and the exit-code contract (0/1/2/3)
  documented in the module docstring of `cli.py`.

## Security

`constraints.txt` is a `uv`-resolved, project-scoped lock of the runtime
dependency tree (regenerate with
`uv pip compile pyproject.toml -o constraints.txt --python-version 3.12`
after changing a bound in `pyproject.toml`). CI runs an advisory `security`
job (`.github/workflows/ci.yml`, `needs: lint`) that installs against it and
runs `pip-audit` + `bandit`, both `continue-on-error: true` so findings can't
redden the pipeline yet (see issue #32 for the CVE inventory + reachability
argument for going advisory-first). Reproduce locally:
`pip install -e . -c constraints.txt && pip install pip-audit && pip-audit -r constraints.txt`.

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
| `index/` | INDEX.md table renderer (ADR-138) — not yet wired into the CLI or MCP server |
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

- `make test` enforces `--cov-fail-under=55` (actual ~59%); raise as it improves.
- The main tree at `~/github/iil-adrfw` is guarded (ADR-233): start editing
  sessions via `platform/tools/repo-session.sh start <repo> --task <slug>`.
- After a version bump in `pyproject.toml`,
  `python3 -c "import iil_adrfw; print(iil_adrfw.__version__)"` can still print
  a stale version — the editable install doesn't automatically re-resolve
  package metadata. Fix: re-run
  `pip install -e . --force-reinstall --no-deps` (add
  `--user --break-system-packages` on PEP-668-managed hosts if needed).
- See `AGENT_HANDOVER.md` for current state and next priorities.
