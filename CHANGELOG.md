# CHANGELOG

## [0.3.1] — 2026-05-08

- **Added**
  - CLI command for exporting Outline-compatible ADR registry markdown.
  - Staleness, graph, and impact tools (CLI + MCP).
  - `adr_validate` MCP tool for frontmatter validation.
  - Bundled schemas in the package, eliminating the need for a `--schema-dir`.
  - `validate` CLI subcommand for bulk ADR frontmatter validation.
  
- **Changed**
  - Comprehensive README with usage instructions, schema highlights, and project structure was added.

- **Fixed**
  - Normalization for `review_status` to handle 'accepted' and freetext patterns.

