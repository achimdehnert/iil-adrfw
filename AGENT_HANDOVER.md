# AGENT_HANDOVER — iil-adrfw

> Living handover for the next agent/session. Keep this current; `NEXT.md` is an
> auto-generated cache and is **not** the source of truth — this file is.

## Current state (2026-08-06)

- Version: **0.8.0** (`pyproject` + CHANGELOG top entry aligned) — **not yet
  published to PyPI**. Consumer-ergonomics release; see CHANGELOG 0.8.0 for the
  four fleet-visible defects it fixes. Publishing is the gated next step
  (`publish.yml`, `workflow_dispatch`).
  - *Handover drift note:* this file claimed 0.7.0 until 2026-08-06 while `main`
    had shipped 0.7.1 and 0.7.2. Keep it current — the session-start
    reconciliation check compares against it.
- Tests: green — `make test` → **222 passed**, coverage ~86.8% (gate 85).
- Lint `make lint` clean; types `make types` 0 errors. Both gated in CI.
- Runtime install: **12 packages** (was 69). `fastmcp` → `[mcp]` extra,
  `libcst` → `[checkers]`, `[all]` restores the old footprint.
- `iil_adrfw.server` was split into `api.py` (transport-neutral core, no MCP
  import) + `server.py` (FastMCP transport). All pre-0.8 `server` imports are
  re-exported, so nothing downstream breaks.

## Fleet impact of 0.8.0 (open follow-through)

The nightly ADR audits in **meiki-hub** and **ttz-hub** have been silently
auditing nothing — they call `iil-adrfw audit --adr-dir docs/adr`, a flag that
did not exist, and their workflow turns the resulting empty output into a green
run. Evidence: meiki-hub run 31072337200 (2026-08-06) logs
`[INFO] Audit produced no JSON output`, conclusion success.

0.8.0 fixes the framework side (the flag now exists; an empty constitution exits
2). The consumer side still needs:

1. Publish 0.8.0 to PyPI — both repos pin `iil-adrfw>=0.5.0`, so they pick it up.
2. Repoint both nightly workflows at the reusable
   `iil-adrfw/.github/workflows/_adr-validate.yml`, and drop the
   `sys.exit(0)`-on-empty-output branch that masked the failure.
3. Optional: migrate `platform/.github/workflows/adr-validate.yml` onto the same
   reusable workflow so the remaining ~36 ADR-carrying repos can adopt it in six
   lines. Needs @wirdigital review (platform codeowner model).

## Recently landed (session 2026-08-06 — consumer ergonomics, 0.8.0)

- Uniform `--adr-dir` on all 17 subcommands; empty/missing ADR dir → exit 2.
- `server._schemas_dir()` fixed (pointed outside the package in any pip install,
  breaking all 12 MCP tools).
- `freshness` + `impact` promoted to CLI subcommands.
- Reusable `_adr-validate.yml`, `.pre-commit-hooks.yaml`, `py.typed`, LICENSE,
  top-level API re-exports, `--version`.
- `examples/test_e2e_consumer_contract.py` (22 tests) pins all of it.

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
- **Quality ratchet (#53):** coverage gate 80→85; mypy strict subset enabled
  (7 flags, all zero-cost) + one `warn_return_any` fix in `_infer_title`.
- **Bandit SAST → blocking (#54 + platform#938):** added a `bandit_blocking`
  input to the shared `_ci-pypi.yml` (mirrors `mypy_blocking`, opt-in,
  backward-compatible) and flipped iil-adrfw to `bandit_blocking: true`. A
  future finding now fails CI + the gate. NOTE: a cosmetic follow-up
  (**platform#941**) fixes the job name still rendering "non-blocking" — a
  GitHub Actions `&& '' ||` empty-string ternary footgun; the job is genuinely
  blocking regardless of the label.

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

1. Cut the next release (0.8.0) when enough has accumulated in `[Unreleased]` —
   the post-0.7.0 quality work (coverage 85, mypy strict subset, bandit blocking)
   is currently unreleased on `main`. Same drill: bump `pyproject.version`, cut
   `[Unreleased]` → `[0.8.0]`, dispatch `publish.yml`.
2. Promote the `pip-audit` (`Security Scan`) job to blocking once its findings
   stay clean — same rationale as the bandit promotion just done.
3. Keep ratcheting `--cov-fail-under` (currently 85, actual ~87.5%) as coverage
   improves.
4. Optional deeper mypy strictness: `disallow_any_generics` (measured: **45
   errors** across 5 files — a focused effort, not a quick pass) and
   `warn_unreachable` (2 hits, both *defensive* fallbacks after exhaustive
   `Audience` enum chains in `narrate/` — decide keep-guard vs delete-dead-code).

## Pointers

- Architecture + commands: `CLAUDE.md`.
- Schema source of truth: `src/iil_adrfw/schemas/`.
- Changelog: `CHANGELOG.md` (Keep a Changelog).
