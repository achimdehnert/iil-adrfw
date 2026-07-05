# AGENT_HANDOVER — iil-adrfw

> Living handover for the next agent/session. Keep this current; `NEXT.md` is an
> auto-generated cache and is **not** the source of truth — this file is.

## Current state (2026-07-05)

- Version: **0.7.0** (`pyproject` + CHANGELOG top entry aligned) — **published
  to PyPI** 2026-07-05 via Trusted Publishing (OIDC, `publish.yml`; verified live:
  `iil_adrfw-0.7.0-py3-none-any.whl` in the simple index with provenance
  attestation). `[Unreleased]` is empty again — the next release needs a fresh
  version bump + CHANGELOG cut (enforced by the `publish.yml` version-check gate).
- Tests: green — `make test` → **196 passed** (suite in `examples/`, order-stable).
- Lint: `make lint` (`ruff check .`) clean, **gated** in CI. Types: `make types`
  (mypy) — **0 errors, gated** in CI (`types` job), now with
  **`disallow_untyped_defs = true`** so new untyped code can't slip in.
- Coverage: `make test` enforces `--cov-fail-under=80`; current ~87.5%.
- CI: `ci.yml` (least-privilege `permissions`, `concurrency`, pip-cache;
  lint + types + full `make test` + `SAST` bandit + `Security Scan` pip-audit) +
  `publish.yml` (PyPI via OIDC, `workflow_dispatch`, gated on `version-check`
  + tests). The `ci / SAST (bandit)` check is **green** but still
  **non-blocking** (advisory) — promoting it to blocking is a next priority.

## Recently landed (session 2026-07-05 — 0.7.0 release)

- **Released 0.7.0 to PyPI** — cut `[Unreleased]` → `[0.7.0]`, consolidated the
  split Fixed/Changed subsections (#51).
- **Bandit SAST → green (#51, closes #50):** the 4 Low findings from the #49
  reactivation are fixed, not suppressed — `contextlib.suppress(Exception)` for
  the three best-effort `try/except` loops in `cli.py`; the `assert health is
  not None` in `server.py` `_do_audit` became an explicit `RuntimeError` guard
  (correct under `python -O`, still narrows for mypy).
- **mypy tightened to `disallow_untyped_defs` (#51):** 17 previously-untyped
  functions (CLI `_add_*_parser` builders, `_print_json`, `_is_relevant`) annotated.
- Dependabot: GitHub Actions group bump merged (#47).

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

1. Promote the `ci / SAST (bandit)` check from advisory to **blocking** now that
   it is green (#50 cleared all findings) — a permanently-green advisory check is
   ripe to gate, and removes the alert-fatigue risk that a future finding goes
   unnoticed. Same for the `pip-audit` scan once its findings stay clean.
2. Keep ratcheting `--cov-fail-under` (currently 80, actual ~87.5%) as coverage
   improves.
3. Optional further mypy strictness (e.g. `disallow_any_generics`,
   `warn_return_any`, or full `strict = true` per module) now that
   `disallow_untyped_defs` is in and the baseline is zero.

## Pointers

- Architecture + commands: `CLAUDE.md`.
- Schema source of truth: `src/iil_adrfw/schemas/`.
- Changelog: `CHANGELOG.md` (Keep a Changelog).
