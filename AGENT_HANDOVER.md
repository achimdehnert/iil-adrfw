# AGENT_HANDOVER — iil-adrfw

> Living handover for the next agent/session. Keep this current; `NEXT.md` is an
> auto-generated cache and is **not** the source of truth — this file is.

## Current state (2026-07-02)

- Version: **0.6.0** (`pyproject` + CHANGELOG top entry aligned) — **published
  to PyPI** 2026-06-22 via Trusted Publishing (OIDC, `publish.yml`).
- Tests: green — `make test` → 122 passed (suite in `examples/`, order-stable).
- Lint: `ruff check .` clean. Types: `make types` (mypy) — **0 errors, gated
  in CI** (`types` job).
- Coverage: `make test` enforces `--cov-fail-under=70`; current ~73%.
- CI: `ci.yml` (lint + types + full `make test` suite with coverage) +
  `publish.yml` (PyPI via OIDC, `workflow_dispatch`, gated on tests).

## Recently landed

- Coverage 59→73%, floor 55→70: tests for the previously untested `metrics/`,
  `index/`, `freshness/` modules (0%→96-97%) + CLI text-output regression
  tests for the two 2026-07-02 crash fixes.
- mypy 37→0 + `types` CI gate; fixed two real CLI crashes mypy surfaced
  (`check`/`validate-cross-repo` text output referenced non-existent fields, #16).
- 0.6.0 published to PyPI via Trusted Publishing (OIDC) — unblocks the platform
  `adr-nightly-metrics.yml` pipeline (#13, #15).
- Test isolation fix: per-module autouse fixture isolates `IIL_ADRFW_ADRS_DIR`,
  removing 5 order-dependent failures (#10).
- Agent-readiness: `__version__` + `__all__` + public-API docstring in
  `__init__.py`, Python classifiers, `CLAUDE.md`, `AGENT_HANDOVER.md`, Makefile.

## Known issues / TODO

- Stale duplicate checkout `~/github/iil-adrfw-repo` (same name+version, behind
  `origin/main`) — risk of editing stale code; prefer `~/github/iil-adrfw`.
- The main tree is guarded (ADR-233 main-tree-guard): editing sessions go
  through `platform/tools/repo-session.sh start <repo> --task <slug>`.

## Next priorities

1. Keep ratcheting coverage (floor 70, actual ~73): remaining gaps are
   `server.py` (72% — mostly the later `_do_*` handlers) and
   `persistence/` (77% — error/edge paths of frontmatter normalization).
2. Consider tightening mypy (e.g. `disallow_untyped_defs` per module) now that
   the baseline is zero.

## Pointers

- Architecture + commands: `CLAUDE.md`.
- Schema source of truth: `src/iil_adrfw/schemas/`.
- Changelog: `CHANGELOG.md` (Keep a Changelog).
