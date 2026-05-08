# Project Facts: iil-adrfw

## Meta

- **Type**: `python-library`
- **GitHub**: `https://github.com/achimdehnert/iil-adrfw`
- **Branch**: `main`
- **PyPI**: `iil-adrfw`
- **Build**: `hatchling` (`python3 -m hatchling build`)

## Package

| Field | Value |
|-------|-------|
| **Name** | `iil-adrfw` |
| **Version** | `0.2.0` |
| **Python** | `>=3.12` |
| **Entry points** | `iil-adrfw` (CLI), `iil-adrfw-mcp` (FastMCP server) |
| **Source layout** | `src/iil_adrfw/` |

## Key modules

| Module | Purpose |
|--------|---------|
| `persistence/` | Loader: normalize → validate → construct ADR objects |
| `domain/` | ADR dataclass, Status enum, cross-repo models |
| `graph/` | Constitution graph (supersession, dependencies) |
| `audit/` | Staleness, implementation evidence checks |
| `checkers/` | AST-based Python code checkers |
| `cli.py` | CLI entry point |
| `server.py` | FastMCP MCP server |

## Schemas

- `schemas/adr_frontmatter.schema.json` — ADR frontmatter (Schema v3)
- `schemas/adr_rules.schema.json` — ADR executable rules
- `schemas/constitution.schema.json` — Constitution graph

## Tests

```bash
python3 examples/test_e2e_schema_v3.py   # 22 cases — Schema v3
python3 examples/test_e2e.py              # Core tests
python3 examples/test_e2e_v11.py          # v1.1 format tests
python3 examples/test_e2e_regression.py   # Regression tests
```

## CI/CD

- `.github/workflows/ci.yml` — ruff lint + test suites on push/PR
- `.github/workflows/publish.yml` — hatchling build + twine upload (workflow_dispatch)

## MCP Prefix (WSL Standard)

| Prefix | Server |
|--------|--------|
| `mcp0_` | deployment-mcp |
| `mcp1_` | github |
| `mcp2_` | orchestrator |
| `mcp3_` | outline-knowledge |
| `mcp4_` | paperless-docs |
| `mcp5_` | platform-context |
| `mcp6_` | playwright |
