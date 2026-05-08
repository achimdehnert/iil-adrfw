# Changelog

All notable changes to this project will be documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

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

