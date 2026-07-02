# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

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

### Fixed

- **`check` text output crashed on violations**: it referenced non-existent
  `ViolationOut` fields (`file_path`/`line_number`/`message`); now prints
  `file:line_start` plus `expected`/`actual`. (`--json` was unaffected.)
- **`validate-cross-repo` text output crashed on conflicts**: it referenced
  non-existent `ConflictOut` fields (`severity`/`description`); now prints
  `conflict_class`/`confidence` and the `claim`. (`--json` was unaffected.)

### Changed

- mypy backlog driven 37 → 0; `make types` is now a required CI gate
  (`types` job in `ci.yml`). `types-PyYAML` added to the `dev` extra.

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

