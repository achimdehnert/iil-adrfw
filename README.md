# iil-adrfw

**ADR Framework for the IIL Platform** — schema validation, loader normalization, constitution graph, audit tooling.

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

Tested against **156 real platform ADRs**:

| Mode | Result |
|---|---|
| Strict load (validate=True) | **152/156 (97.4%)** |
| Unit tests | **22/22 green** |
| Remaining failures | 4x broken YAML (unfixable) |

## Installation

```bash
pip install -e .

# With dev dependencies:
pip install -e ".[dev]"
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
# Validate ADRs
iil-adrfw validate docs/adr/ --schemas schemas/

# Audit for staleness, missing evidence
iil-adrfw audit docs/adr/ --schemas schemas/
```

### MCP Server

```bash
iil-adrfw-mcp
```

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
python examples/test_e2e_schema_v3.py   # Schema v3 tests (22 cases)
python examples/test_e2e.py              # Core tests
python examples/test_e2e_v11.py          # v1.1 format tests
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
