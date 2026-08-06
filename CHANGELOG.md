# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [0.8.0] — 2026-08-06

Consumer-ergonomics release. The framework worked well for the repo that
develops it and badly for the 38 other repos that carry ADRs — this release
fixes the contract they actually depend on.

### Fixed

- **`iil-adrfw audit` silently audited nothing (fleet-wide, months).** `audit` and
  eight other subcommands took the ADR directory *only* from `$IIL_ADRFW_ADRS_DIR`,
  while `validate`/`staleness`/`graph`/`export`/`index` took it positionally and
  `metrics` took `--adr-dir`. meiki-hub and ttz-hub called
  `iil-adrfw audit --adr-dir docs/adr` nightly; argparse rejected the flag, exited 2
  with empty stdout, and their workflows' "no JSON output" branch turned that into a
  green run. Verified on
  [meiki-hub run 31072337200](https://github.com/meiki-lra/meiki-hub/actions/runs/31072337200)
  (2026-08-06): `[INFO] Audit produced no JSON output`, conclusion success.
  **Every** subcommand now accepts `--adr-dir`; positional forms still work.
- **An empty or missing ADR directory reported perfect health.** The default ADR
  directory was `./adrs`, which no repo in the fleet uses, so an unset env var
  loaded zero ADRs and printed `health score 1.000 / OK — no findings / exit 0`.
  Default is now `docs/adr`; a missing directory or an empty constitution is a
  configuration error (exit 2), with `--allow-empty` as the explicit opt-out.
- **Bundled schemas were unreachable in any `pip install`.** `server._schemas_dir()`
  resolved to `<prefix>/lib/pythonX.Y/schemas` — a path that never exists in an
  installed package — so all 12 MCP tools and every env-var-driven subcommand died
  with `FileNotFoundError` unless the caller also set `IIL_ADRFW_SCHEMAS_DIR`.
  It now resolves the packaged `iil_adrfw/schemas/`, with the env var as override.
- **`audit` died on the first malformed ADR.** A single invalid file raised out of
  the constitution load, so `audit` exited 3 ("internal error") — the tool was
  unusable in exactly the repos whose ADR hygiene most needed auditing
  (meiki-hub: 23 of 36 ADRs invalid). `load_adrs()` gained an opt-in `errors=`
  collector (default stays strict); `audit` now reports unloadable ADRs as
  `loadability` findings and audits the rest.
- **The ADR-211 Rev 21 vocabulary was never covered by the schema (75 of 747 fleet
  ADRs invalid).** platform:ADR-211 Rev 21 (owner-ratified 2026-07-10) canonicalized
  `extends`, `realizes_use_cases`, `spec_role`, `replaces_system_ref`,
  `integrates_with_system_ref`, `integrates_with_refs`, `supersedes_partial` and
  `scope.repos`/`scope.apps`, and assigned the validator coverage to an iil-adrfw
  follow-up PR that never happened. Every repo carrying the ratified vocabulary
  hard-failed validation. Added all of them as optional properties — Rev 21 is
  explicit that these are metadata definitions and **not** new gates, so the
  documented mutual exclusion of `replaces_system_ref` / `integrates_with_system_ref`
  is described but deliberately not enforced. `spec_role: detail` stays rejected,
  as ADR-211 leaves that fourth value open. Measured fleet-wide 2026-08-06:
  **75 invalid ADRs → 30**, the remainder being genuine authoring defects
  (14x missing frontmatter in bfagent, status values outside the enum) rather than
  vocabulary gaps. This is the second batch of this pattern — see 0.7.1.
- **`sister_of` rejected repo-qualified refs.** 50 of 57 qualified `sister_of`
  entries in the fleet point at the ADR's *own* repo
  (`ausschreibungs-hub:ADR-005`) — the same local tree ADR-211 describes, just
  written qualified. New `$defs/QualifiedADRRef` accepts the
  `repo:ADR-NNN` form (platform:ADR-211 C5/I4) with an optional section suffix.
- **Generic governance variants hard-failed instead of being normalized.**
  ADR-211 Rev 21 says `ratified`, `amendments`, `revisions`, `decision` and
  `external_review` are not part of the convention and should be normalized by
  iil-adrfw. A faithful alias is impossible for all of them — the fleet's
  `amendments` entries carry `date`/`by`/`what`, while the canonical `amended`
  requires a `v`-prefixed version, an ISO date string and a minimum-length
  summary; `decision`, `external_review` and `ratified` have no canonical
  counterpart at all. Inventing a mapping would record wrong metadata, so they
  are stripped (existing `_STRIPPED_FIELDS` mechanism): the frontmatter stops
  hard-failing and the content stays in the ADR body.
- **Diagnosis mode crashed with a bare `KeyError`.** `load_adr(..., raw=True)` skips
  normalization, so ADRs relying on aliases or inference reached Phase 3 incomplete.
  Now raises `ADRLoadError` naming the missing fields and why.

### Added

- **`--adr-dir` on every subcommand**, with one documented precedence:
  explicit flag → positional → `$IIL_ADRFW_ADRS_DIR` → `docs/adr`.
- **`freshness` and `impact` CLI subcommands** — both existed as MCP tools with
  their implementation inline in the tool wrapper and no CLI equivalent.
- **Reusable GitHub workflow** `.github/workflows/_adr-validate.yml`
  (`workflow_call`): a consuming repo gets ADR validation, audit and staleness in
  six lines, with no steps to copy and drift.
- **`.pre-commit-hooks.yaml`** exposing `adr-validate`, `adr-staleness`, `adr-audit`.
- **`py.typed`** — the strict-typed internals are now visible to consumers' mypy.
- **Top-level re-exports**: `load_adrs`, `load_adr`, `get_schema_dir`,
  `ConstitutionGraph`, `run_audit`, `ADR`, `ADRLoadError`, `Status`.
- **`iil-adrfw --version`**.
- **LICENSE file + `license` metadata** — the README carried an MIT badge with no
  LICENSE shipped and no license field in the package metadata.
- `MissingExtraError`, mapped to exit code 2: a missing optional extra is a
  configuration error, not an internal error, and the message carries the fix.
- `examples/test_e2e_consumer_contract.py` — 24 tests pinning the consumer-facing
  contract, each mapped to one of the defects above.
- `examples/test_e2e_adr211_rev21_schema.py` — 25 tests pinning the ADR-211 Rev 21
  vocabulary against the values ADR-211 and the fleet actually use.

### Changed

- **Runtime install shrank from 69 packages to 12.** `fastmcp` and `libcst` are now
  optional extras (`[mcp]`, `[checkers]`, or `[all]` for the pre-0.8 footprint).
  A consumer that only gates ADR frontmatter in CI no longer installs the MCP
  server stack, authlib, cryptography, keyring, opentelemetry and libcst.
- **`iil_adrfw.server` split into `iil_adrfw.api` + `iil_adrfw.server`.** `api`
  carries all request/response models and `_do_*` handlers and imports no MCP
  machinery; `server` is the FastMCP transport over it. Everything the pre-0.8
  `iil_adrfw.server` exported is re-exported there — existing imports keep working.

### Migration

- `pip install iil-adrfw` → add `[mcp]` if you run `iil-adrfw-mcp`, `[checkers]` if
  you use `iil-adrfw check` or `validate-cross-repo`. Invoking either without its
  extra now exits 2 with the exact install command.
- Pipelines relying on an empty ADR directory exiting 0 must pass `--allow-empty`.

## [0.7.2] — 2026-07-27

### Fixed

- **0.7.1 still shipped the broken schema (illustration-hub#78):** the repo carries
  two copies of `adr_frontmatter.schema.json` — `schemas/` (repo-root, used by dev
  checkouts) and `src/iil_adrfw/schemas/` (bundled into the wheel/sdist; what
  `get_schema_dir()` actually resolves to for a `pip install`ed CLI). Commit 6218675
  (#59) fixed only the repo-root copy — 0.7.1 published a package whose runtime
  schema was unchanged, `iil-adrfw validate` still rejected `class`/`conforms_to`/etc.
  Synced the packaged copy; added `test_e2e_packaged_schema_sync.py` to fail CI if
  the two copies ever diverge again.

## [0.7.1] — 2026-07-27

### Fixed

- **Klickdummy ADR-211 frontmatter keys were unreleased (illustration-hub#78):**
  `class`/`conforms_to`/`sunset_after`/`extension_review_required`/`sister_of` were
  added to the schema in commit 6218675 (#59, 2026-07-10) — behebt ~80 Fleet-Hard-Fails
  laut ADR-FLEET-AUDIT 2026-07-10 F-2 — but no version bump followed, so every
  `pip install iil-adrfw` consumer kept validating against the pre-fix schema.
  This release ships that fix.

## [0.7.0] — 2026-07-05

### Added

- **`iil-adrfw index` CLI subcommand (#43):** exposes the previously-unwired
  `index/` module (INDEX.md table renderer, ADR-138 Impl column) as a CLI
  command — `iil-adrfw index <adr_dir>` renders the full INDEX.md (H1 + legend +
  next-free preamble), `--table-only` emits just the table block, `--include-archive`
  adds non-colliding `_archive/` ADRs, `-o` writes to a file. Mirrors the
  `graph`/`export` subcommand shape.

### Changed

- **Consolidated the staleness / reference-drift logic (#19, B-2 + B-18):** the CLI
  (`_cmd_staleness`) and the MCP tool (`adr_staleness`) had drifted into two
  divergent implementations (different field coverage, different messages). Both
  now call a single `_do_staleness(adr_dir, schemas_dir, months)` in `server.py`.
  Unified coverage: broken references are flagged for `superseded_by` (error),
  `depends_on` (warning) **and** `related` (info) — the `related` check previously
  read a non-existent domain attribute (dead code) and now reads `raw_frontmatter`,
  so it actually fires. ADR files that fail to load are reported in a new
  `load_errors` field instead of being silently swallowed by `except: continue`.
  Path containment stays where it belongs: the MCP tool validates client dirs via
  `_require_within_root` (#22), the trusted CLI passes the user's dir directly.
- mypy backlog driven 37 → 0; `make types` is now a required CI gate
  (`types` job in `ci.yml`). `types-PyYAML` added to the `dev` extra.
- **mypy tightened to `disallow_untyped_defs`:** every function in
  `src/iil_adrfw` must now carry a type signature. 17 previously-untyped
  functions (the CLI `_add_*_parser` builders, `_print_json`, and the
  `_is_relevant` freshness helper) were annotated, and the flag now guards
  against new untyped code slipping in under the zero-error `types` gate.

### Fixed

- **MCP bi-temporal timestamps crashed on naive input (#18):** `CheckRequest.as_of`,
  `AuditRequest.as_of` and `DiffRequest.left_time`/`right_time` accepted an ISO
  string without an offset, which Pydantic parsed to a *naive* datetime; comparing
  it against the tz-aware ADR dates raised `TypeError: can't compare offset-naive
  and offset-aware datetimes`. These fields now normalize naive input to UTC via a
  shared `UTCDateTime` annotated type (mirroring the CLI's `_parse_iso`), so the
  MCP path behaves like the CLI. Explicit offsets are preserved.
- **`check` text output crashed on violations**: it referenced non-existent
  `ViolationOut` fields (`file_path`/`line_number`/`message`); now prints
  `file:line_start` plus `expected`/`actual`. (`--json` was unaffected.)
- **`validate-cross-repo` text output crashed on conflicts**: it referenced
  non-existent `ConflictOut` fields (`severity`/`description`); now prints
  `conflict_class`/`confidence` and the `claim`. (`--json` was unaffected.)
- Five small, independently verified logic/robustness fixes (#25): DOT-label
  injection in `graph --dot` and Markdown-table injection in `export` (both
  now escape `id`/`title`/`domains` via shared `_escape_dot`/`_escape_md_cell`
  helpers before interpolation); `main()` now honors its own documented exit
  code 3 for uncaught internal errors instead of falling through to Python's
  default exit 1 ("findings present"); `execute_query`'s mixed
  (domain+question) routing branch no longer assigns every candidate ADR the
  same global `matched_concepts` set, but filters per ADR like the
  concept-only branch already did; and `check_freshness`'s version comparison
  now compares dotted segments instead of a naive `str.startswith`, so a
  claim of `"1"` no longer false-matches an actual of `"18"`.

### Security

- MCP path-parameter containment (#22). Client-supplied path parameters on the
  MCP server (`CheckRequest.paths`, `ValidateRequest.adr_dir`,
  `DiffRequest.right_dir`) are now validated to resolve within the sanctioned
  repo root (`_require_within_root`, `resolve()` + `is_relative_to()`); a `../`
  traversal or absolute escape raises `ValueError` instead of silently reading
  outside the tree. Env-configured defaults (`_adrs_dir()` when no `adr_dir` is
  given) remain operator-trusted. The cross-repo (`consumer_repos[].root`) and
  freshness (`repo_path`) tools deliberately read *other* repos as their core
  function and are intentionally not constrained; `adr_impact.file_path` is a
  pattern-matching string, not a filesystem read.
- Advisory supply-chain gate in CI (#32): a new `security` job
  (`.github/workflows/ci.yml`) installs the project against a new
  `constraints.txt` — a `uv`-resolved, project-scoped lock of the runtime
  dependency tree — and runs `pip-audit` (project-scoped, not an ambient
  environment scan) plus a lean `bandit` pass over `src/iil_adrfw`, both
  advisory (`continue-on-error: true`) so findings can't redden the
  pipeline yet. Re-resolving the tree via `uv` already picks up patched
  versions of the transitive `fastmcp` deps (`pyjwt`, `cryptography`,
  `starlette`, `python-multipart`, …) previously flagged by an ambient
  `pip-audit` scan; those CVE paths were unreachable anyway given
  iil-adrfw's documented stdio MCP transport.
- Path containment in the ADR loader (#31). Two traversal channels are now
  rejected before any out-of-tree read: a `rules_file` frontmatter field that
  points at an absolute path or `../` escape (previously opened and YAML-parsed
  arbitrary files), and an ADR markdown file that is a symlink to a target
  outside the ADR directory (previously ingested the external file's content
  into the ADR object, surfacing it via `list`/`export`/MCP). `rules_file` must
  now be a bare filename beside the ADR, and both the ADR file and the resolved
  rules path are verified to stay within the ADR directory (`resolve()` +
  `is_relative_to()`); violations raise `ADRLoadError`.
- **Bandit SAST findings triaged to zero (#50):** the reactivated `bandit` pass
  (#49) flagged 4 Low findings, now all resolved rather than suppressed. The
  three best-effort `try/except: pass|continue` loops in `cli.py` (`validate`
  alias-warning detection, `graph`/`export` ADR loading) use
  `contextlib.suppress(Exception)` (identical semantics, no B110/B112), and the
  `assert health is not None` invariant in `server.py`'s `_do_audit` became an
  explicit `RuntimeError` guard — correct under `python -O` (where `assert` is
  stripped), still narrowing the type for mypy. The `ci / SAST` check is green
  again.

### CI

- **CI hygiene (#24, B-12):** `ci.yml` now sets a least-privilege
  `permissions: contents: read`, a `concurrency` group that cancels superseded
  runs, and `cache: pip` on every job; the lint job runs `make lint`
  (`ruff check .`) so CI matches local and covers `examples/` + root scripts
  (previously `ruff check src/` only). `publish.yml` gains a `version-check`
  gate (run before publish) that fails fast if `pyproject.version` is already
  on PyPI or doesn't match the top versioned CHANGELOG heading — no change to
  the publish mechanism itself, and it only runs on the manual publish dispatch.

### Docs

- Fixed README/CLAUDE.md drift (#23): corrected MCP tool count (11→12,
  `adr_freshness` was missing from the list), added a `metrics --report`
  CLI example, replaced ad-hoc test-script invocations with `make test`,
  documented the venv setup step for PEP-668-managed hosts, added the
  `index/` module to the CLAUDE.md module map, documented
  `IIL_ADRFW_SCHEMAS_DIR` with a pointer to `docs/CASCADE_PIPELINE.md` and
  the CLI exit-code contract, added a gotcha for stale `__version__` after
  an editable-install version bump, and refreshed the stale top-of-file
  docstrings in `server.py`/`cli.py` (skeleton wording, "8 MCP tools") to
  reflect the actual 12 MCP tools / 14 CLI subcommands. No behavior change.

### Tests

- Added dedicated tests for the previously-uncovered `metrics/`, `index/`, and
  `freshness/` modules (0%/0%/82% → 95–97%), lifting total coverage ~74% → ~82.5%
  and ratcheting the `--cov-fail-under` gate 70 → 80. (Recovers the module tests
  from the superseded coverage-raise branch, rebased onto the current suite.)

## [0.6.0] — 2026-05-30

### Added — `metrics` CLI command (Schema v4 controlling)

- **New `iil-adrfw metrics` subcommand**: computes Schema v4 controlling metrics
  (`inbound_links`, `ttd_days`, `ttr_days`, `ai_interactions`) across an ADR directory.
  Flags: `--adr-dir`, `--report` (Markdown table), `--write` (persist `metrics` object
  into each ADR frontmatter), `--json` (machine-readable for downstream steps).
  Backs the platform `adr-nightly-metrics.yml` pipeline — which pins `iil-adrfw>=0.5.0`
  but requires this command, only available from 0.6.0 onward.

### Added — frontmatter alias deprecation warnings

- **`validate` now reports non-canonical frontmatter keys** as deprecation warnings.
  Legacy aliases (e.g. `adr_id`→`id`, `date`→`decision_date`, `decision-makers`→`deciders`)
  are still accepted and normalized — the warning only nudges authors toward the canonical
  form. **Never affects pass/fail** (validation stays green; exit code unchanged).
  Surfaced in both text output (`DEPRECATION (N): …`) and `--json`
  (`deprecation_warnings: [{file, aliases:[{legacy, canonical}]}]`).
- New public helpers in `iil_adrfw.persistence`: `original_frontmatter(path)` (parse
  frontmatter pre-normalization) and `detect_legacy_aliases(fm)` (single-source against
  `_FIELD_ALIASES`).

Rationale: the alias table is a deliberate lenient-input design; a hard-fail on one alias
would be inconsistent with the other ~16 and would break the green-CI contract (e.g. 173/176
platform ADRs currently use at least one alias). A consistent, non-blocking deprecation
warning makes the drift visible without breaking anything.

## [0.5.0] — 2026-05-10

### Added — Schema v4

- **`void` status**: New lifecycle state for misclassified ADR slots. Number is retained
  for reference integrity; content is moved to the correct doc type. Not a normal lifecycle
  state — only set intentionally on reclassification.
- **`doc_type` field**: Document type discriminator (`adr|standard|runbook|plan|review|rfc`).
  Files in `docs/adr/` MUST have `doc_type: adr`. Prevents ADR-181/182 class of misclassification.
- **`reviewed_by` field**: Structured human reviewer array `[{name, date, verdict, note}]`.
  AI tool names MUST NOT appear here — use `ai_sparring_by` instead. Separates human
  accountability from AI contributions for Bus Factor transparency.
- **`ai_sparring_by` field**: Explicit AI tool contribution array `[{tool, date, role, summary}]`.
  Non-accountable — does NOT satisfy `reviewed_by`. Bus Factor = 1 if `reviewed_by` is
  empty regardless of `ai_sparring_by` content. Controlled vocabulary: `cascade`,
  `claude-code`, `copilot`, `other`.
- **`metrics` field**: Auto-computed nightly object (`references_90d`, `inbound_links`,
  `ttd_days`, `ttr_days`, `last_computed`). Do NOT edit manually.
- **`HumanReview` and `AISparring` JSON Schema `$defs`** for the above fields.
- **`Status.VOID`** in `domain.Status` enum.
- **`SCHEMA_V4_SPEC.md`**: Full specification with migration path, validator rules,
  and backwards compatibility notes.

### Changed — Persistence (backwards-compatible)

- **Aliases** added: `reviewed-by`→`reviewed_by`, `ai-sparring-by`→`ai_sparring_by`,
  `doc-type`→`doc_type`, `status-history`→`status_history`, `decision-maker`→`deciders`.
- **`reviewed-by` un-stripped**: Removed from `_STRIPPED_FIELDS` — now aliased to `reviewed_by`
  instead of being silently dropped (v3 behavior).
- **C.1b-v4 normalization**: `datetime.date` objects inside `reviewed_by[].date` and
  `ai_sparring_by[].date` converted to ISO strings (YAML auto-parse tolerance).
- **C.v4-migration normalization**: Legacy `reviewed-by: "string"` and
  `reviewed-by: ["string", ...]` formats stripped with warning. Bus Factor warning fires
  on stripped entries. Karenzzeit until 2026-11-10.

### Validated

- 161/161 ADRs in platform constitution validate against Schema v4 (0 regressions).
- 27/27 e2e tests pass.

## [0.3.1] — 2026-05-08

### Added
- `staleness` CLI: check ADR age, broken references, missing reviews
- `graph` CLI: dependency visualization (text/DOT/JSON output)
- `export` CLI: Outline-compatible markdown registry generation
- `adr_staleness` MCP tool: staleness + drift check from Cascade
- `adr_impact` MCP tool: file path → applicable ADRs mapping

### Fixed
- `superseded_by` reference parsing for list/tuple values

## [0.3.0] — 2026-05-08

### Added
- `adr_validate` MCP tool for schema validation from Cascade
- `adr_list_adrs` MCP tool for ADR listing
- Registered MCP server in Windsurf config (`mcp7_`)

### Changed
- Bumped to v0.3.0 for MCP server milestone

## [0.2.2] — 2026-05-08

### Added
- Bundled JSON schemas inside package (`iil_adrfw.schemas.get_schema_dir()`)
- No `--schema-dir` needed — auto-detection from package data

## [0.2.1] — 2026-05-08

### Added
- `validate` CLI subcommand for bulk ADR frontmatter validation
- JSON output mode (`--json`) for CI integration
- Exit code 0/1 for pass/fail in CI pipelines

## [0.1.0] — 2026-05-08

### Added
- Initial release: Schema v3 loader with 3-phase pipeline (normalize → validate → construct)
- 15+ field alias normalizations
- Status enum normalization
- Constitution graph with cycle detection
- Audit tooling (staleness, evidence)
- AST-based code checkers
- FastMCP server with 8 tools (check, explain, query, audit, propose, diff, narrate, validate_cross_repo)
- CLI entry point (`iil-adrfw`)
- MCP entry point (`iil-adrfw-mcp`)
- GitHub Actions CI workflow (lint + test)
- PyPI publish workflow

### Fixed
- `review_status` normalization for 'accepted' and freetext patterns

