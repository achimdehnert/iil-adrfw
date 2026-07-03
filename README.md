# iil-adrfw

**ADR Framework for the IIL Platform** — schema validation, loader normalization, constitution graph, audit tooling.

[![PyPI](https://img.shields.io/pypi/v/iil-adrfw.svg)](https://pypi.org/project/iil-adrfw/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## What it does

- **Schema v3** — strict JSON Schema for ADR frontmatter with `additionalProperties: false`
- **Phase 1 Normalizer** — 15+ field aliases, status normalization, type coercion, reference extraction
- **Phase 2 Validator** — jsonschema validation against `adr_frontmatter.schema.json`
- **Phase 3 Domain** — typed `ADR` dataclass with `Status` enum, temporal fields, relations
- **Constitution Graph** — cross-ADR dependency/supersession graph with cycle detection
- **Audit** — staleness checks, implementation evidence verification, drift detection
- **CLI + MCP Server** — `iil-adrfw` CLI and `iil-adrfw-mcp` FastMCP server

## Real-world validation

Tested against **156 real platform ADRs** (as of v0.3.1):

| Mode | Result |
|---|---|
| Schema validation | **156/156 (100%)** |
| Staleness (>6mo) | 0 stale |
| Broken references | 0 |
| Dependency edges | 31 |

## Installation

```bash
pip install iil-adrfw

# From source with dev dependencies:
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# PEP-668-managed hosts without a venv (fallback only):
pip install --user --break-system-packages -e ".[dev]"
```

## Usage

### Python API

```python
from pathlib import Path
from iil_adrfw.persistence import load_adr, load_adrs

# Load single ADR
adr = load_adr(Path("docs/adr/ADR-099.md"), Path("schemas/"))

# Load all ADRs in directory
adrs = load_adrs(Path("docs/adr/"), Path("schemas/"))

# Diagnosis mode (skip normalization)
raw_adr = load_adr(path, schemas, raw=True)
```

### CLI

```bash
# Validate all ADR frontmatters against schema v3
iil-adrfw validate docs/adr/

# Check staleness (>6 months), broken references, missing reviews
iil-adrfw staleness docs/adr/ --months 6

# Generate dependency graph (text, DOT, or JSON)
iil-adrfw graph docs/adr/ --dot > graph.dot

# Export Outline-compatible markdown registry
iil-adrfw export docs/adr/ -o adr-registry.md

# Render the INDEX.md table (ADR-138 Impl column); --table-only for the bare block
iil-adrfw index docs/adr/ -o docs/adr/INDEX.md

# Audit constitution health
iil-adrfw audit docs/adr/

# Query ADRs by question/domain
iil-adrfw query docs/adr/ "Which ADR governs deployment?"

# Compute Schema v4 controlling metrics and print a report
iil-adrfw metrics --adr-dir docs/adr/ --report
```

### MCP Server (12 tools)

```bash
iil-adrfw-mcp  # stdio transport, register in Windsurf mcp_config.json
```

Tools: `adr_validate`, `adr_staleness`, `adr_impact`, `adr_check`, `adr_explain`, `adr_query`, `adr_audit`, `adr_validate_cross_repo`, `adr_propose`, `adr_diff`, `adr_narrate`, `adr_freshness`

## Schema v3 highlights

- **5 new fields**: `updated`, `version`, `review_status`, `owner`, `implementation_done_when`
- **3 removed fields**: `glossary`, `review_cadence`, `next_review_date`
- **Status enum**: `{draft, proposed, accepted, deprecated, superseded, rejected, experimental}`
- **Implementation status**: `{none, planned, in_progress, partial, implemented, complete, verified, rolled_back}`

### Loader normalizations (Phase 1)

| Step | What |
|---|---|
| C.1 | 12 field aliases (`date`→`decision_date`, `author`→`owner`, etc.) |
| C.2 | Status normalization (case, suffixes) |
| C.3 | Scalar-to-list auto-wrapping |
| C.4 | Reference field normalization (ADR-NNN extraction) |
| C.5 | ID inference, title inference, domains default, deciders default |
| C.6 | Amended-format normalization |
| C.7 | `implemented` field → `implementation_status` mapping |
| C.8 | Strip unknown properties |

See [SCHEMA_V3_SPEC.md](SCHEMA_V3_SPEC.md) for full specification.

## Running tests

```bash
make test   # python3 -m pytest examples/  (the full suite lives in examples/)
```

## Project structure

```
iil-adrfw/
├── schemas/                    # JSON Schema files
│   ├── adr_frontmatter.schema.json
│   ├── adr_rules.schema.json
│   └── constitution.schema.json
├── src/iil_adrfw/
│   ├── persistence/            # Loader (normalize + validate + construct)
│   ├── domain/                 # ADR dataclass, Status enum
│   ├── graph/                  # Constitution graph
│   ├── audit/                  # Staleness, evidence checks
│   ├── checkers/               # AST-based code checkers
│   ├── cli.py                  # CLI entry point
│   └── server.py               # FastMCP server
├── examples/                   # Example ADRs + test suites
├── SCHEMA_V3_SPEC.md          # Full v3 specification
└── SCHEMA_V3_CHANGELOG.md     # Changelog for downstream consumers
```
