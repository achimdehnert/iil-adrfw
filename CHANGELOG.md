# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

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

