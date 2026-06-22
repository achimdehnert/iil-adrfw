# AGENT_HANDOVER — iil-adrfw

> Living handover for the next agent/session. Keep this current; `NEXT.md` is an
> auto-generated cache and is **not** the source of truth — this file is.

## Current state (2026-06-22)

- Version: **0.6.0** (`pyproject` + CHANGELOG top entry aligned).
- Tests: green — `make test` → 94 passed (suite in `examples/`, order-stable).
- Lint: `ruff check .` clean. Types: `make types` (mypy) — 37 errors remain
  (advisory harness, **not** gated in CI).
- Coverage: `make test` enforces `--cov-fail-under=55`; current ~59%.
- CI: `ci.yml` (lint + full `make test` suite with coverage) + `publish.yml`
  (PyPI, `workflow_dispatch`).

## Recently landed

- Test isolation fix: per-module autouse fixture isolates `IIL_ADRFW_ADRS_DIR`,
  removing 5 order-dependent failures (#10).
- Agent-readiness: `__version__` + `__all__` + public-API docstring in
  `__init__.py`, Python classifiers, `CLAUDE.md`, `AGENT_HANDOVER.md`, Makefile.
- 0.6.0: `metrics` module + `iil-adrfw metrics` CLI (Schema v4 controlling).

## Known issues / TODO

- **PyPI drift (priority):** 0.6.0 is **not published**; PyPI is stuck at 0.5.0.
  The platform `adr-nightly-metrics.yml` pipeline needs the 0.6.0 `metrics`
  command. Publishing is a gated decision (see CLAUDE.md → Release).
- Stale duplicate checkout `~/github/iil-adrfw-repo` (same name+version, behind
  `origin/main`) — risk of editing stale code; prefer `~/github/iil-adrfw`.
- **Type backlog:** 37 genuine mypy errors across 7 files (`make types`) — these
  are real type issues, not stub noise. Good first optimization target.

## Next priorities

1. Decide/execute the gated 0.6.0 PyPI publish (unblocks the nightly pipeline).
2. Drive the 37 mypy errors to zero, then promote `make types` to a CI gate.
3. Raise the coverage floor (currently 55, actual ~59) as coverage improves;
   the heaviest gaps are `server.py` (72%) and `persistence/` (77%).

## Pointers

- Architecture + commands: `CLAUDE.md`.
- Schema source of truth: `src/iil_adrfw/schemas/`.
- Changelog: `CHANGELOG.md` (Keep a Changelog).
