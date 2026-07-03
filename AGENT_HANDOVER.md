# AGENT_HANDOVER — iil-adrfw

> Living handover for the next agent/session. Keep this current; `NEXT.md` is an
> auto-generated cache and is **not** the source of truth — this file is.

## Current state (2026-07-03)

- Version: **0.6.0** (`pyproject` + CHANGELOG top entry aligned) — **published
  to PyPI** 2026-06-22 via Trusted Publishing (OIDC, `publish.yml`). A large
  `[Unreleased]` section has accumulated since; next release needs a version
  bump + CHANGELOG cut (now enforced by the `publish.yml` version-check gate).
- Tests: green — `make test` → **193 passed** (suite in `examples/`, order-stable).
- Lint: `make lint` (`ruff check .`) clean, **gated** in CI. Types: `make types`
  (mypy) — **0 errors, gated** in CI (`types` job).
- Coverage: `make test` enforces `--cov-fail-under=80`; current ~87%.
- CI: `ci.yml` (least-privilege `permissions`, `concurrency`, pip-cache;
  lint + types + full `make test` + advisory `security` supply-chain job) +
  `publish.yml` (PyPI via OIDC, `workflow_dispatch`, gated on `version-check`
  + tests).

## Recently landed (session 2026-07-02/03 — repo-optimize follow-through)

- Security: path containment in the ADR loader — `rules_file` traversal +
  symlink escape (#33/#31); MCP client path-parameter containment (#34/#22).
- Coverage 59→87%: cli.py in-process tests (#29), metrics/index/freshness
  module tests (#36), plus the fixes below; gate ratcheted 55→80.
- `_do_staleness` consolidation — one impl shared by CLI + MCP tool, `related`
  dead-code fixed, `load_errors` reporting (#38/#19).
- MCP naive bi-temporal timestamps normalized to UTC (#37/#18 — reproduced bug).
- Small logic/injection fixes: DOT + markdown-cell escaping, CLI exit-3,
  per-ADR matched_concepts, segment-wise version compare (#39/#25).
- conftest.py consolidation + `test_should_*` naming enforced (#30/#21, #27/#26).
- CI hygiene + publish version-check gate (#40/#24); advisory supply-chain
  `security` job with project-scoped `constraints.txt` (#35/#32).
- Docs: README/CLAUDE.md drift fixed (#28/#23).

## Known issues / TODO

- Stale duplicate checkout `~/github/iil-adrfw-repo` (same name+version, behind
  `origin/main`) — risk of editing stale code; prefer `~/github/iil-adrfw`.
- The main tree is guarded (ADR-233 main-tree-guard): editing sessions go
  through `platform/tools/repo-session.sh start <repo> --task <slug>`. Note:
  the editable install points at the MAIN tree — run tests in a worktree with
  `PYTHONPATH=$PWD/src` or you silently test the wrong code.

## Next priorities

1. Cut a release: bump `pyproject.version` (e.g. 0.7.0) and move the
   `[Unreleased]` CHANGELOG section under it, then dispatch `publish.yml`
   (the version-check gate now requires this).
2. Keep ratcheting coverage as it improves; consider promoting the advisory
   `security` (pip-audit/bandit) job to gating once findings are clean.
3. Consider tightening mypy (e.g. `disallow_untyped_defs` per module) now that
   the baseline is zero.

## Pointers

- Architecture + commands: `CLAUDE.md`.
- Schema source of truth: `src/iil_adrfw/schemas/`.
- Changelog: `CHANGELOG.md` (Keep a Changelog).
