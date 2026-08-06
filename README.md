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

Tested against **239 real platform ADRs** (as of v0.8.0):

| Mode | Result |
|---|---|
| Schema validation | **239/239 (100%)** |
| Staleness (>6mo) | 0 stale |
| Runtime packages installed | 12 |

## Installation

```bash
pip install iil-adrfw
```

That is the lean install — 12 runtime packages, everything needed to load,
validate, graph, audit, diff, narrate and propose ADRs. Two capabilities are
optional extras because they carry heavy dependency trees most consumers never
use:

| Extra | Install | Adds | Needed for |
|---|---|---|---|
| `mcp` | `pip install 'iil-adrfw[mcp]'` | FastMCP | the `iil-adrfw-mcp` server |
| `checkers` | `pip install 'iil-adrfw[checkers]'` | libcst | `iil-adrfw check`, `validate-cross-repo` |
| `all` | `pip install 'iil-adrfw[all]'` | both | the pre-0.8 footprint |

If you invoke something that needs an extra you don't have, the CLI says exactly
which one and exits **2** (configuration error) — it never fails silently.

```bash
# From source with dev dependencies:
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# PEP-668-managed hosts without a venv (fallback only):
pip install --user --break-system-packages -e ".[dev]"
```

## Using it from another repo

The framework assumes the layout every ADR-carrying repo already uses:
`docs/adr/ADR-*.md`. With that, nothing needs configuring.

### 1. Gate ADRs in CI

Call the reusable workflow — no copy-pasted steps to drift:

```yaml
# .github/workflows/adr-validate.yml
name: ADR Validation
on:
  pull_request:
    paths: ["docs/adr/**"]
  push:
    paths: ["docs/adr/**"]

jobs:
  adr:
    uses: achimdehnert/iil-adrfw/.github/workflows/_adr-validate.yml@main
    with:
      adr-dir: docs/adr      # optional, this is the default
      audit: true            # also run the constitution audit (non-gating)
```

### 2. Gate ADRs before the commit

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/achimdehnert/iil-adrfw
    rev: v0.8.0
    hooks:
      - id: adr-validate
```

### 3. Configuration

Everything is resolvable three ways, with this precedence:
**CLI flag → environment variable → default.**

| What | Flag | Environment variable | Default |
|---|---|---|---|
| ADR directory | `--adr-dir` | `IIL_ADRFW_ADRS_DIR` | `docs/adr` |
| JSON schemas | `--schema-dir` | `IIL_ADRFW_SCHEMAS_DIR` | bundled with the package |
| Repo root | — | `IIL_ADRFW_REPO_ROOT` | `.` |

The bundled schemas are the default, so a `pip install` is self-sufficient —
you never have to vendor a `schemas/` directory or point an env var at a checkout.

### 4. Exit codes

Every subcommand honours the same contract, so CI can branch on it:

| Code | Meaning |
|---|---|
| 0 | Success, no findings |
| 1 | Findings or violations present |
| 2 | Configuration or invocation error (bad args, missing/empty ADR dir, missing extra) |
| 3 | Internal error |

**An empty or missing ADR directory is an error (2), never a clean bill of
health.** A pipeline pointed at the wrong path fails loudly instead of reporting
`health score 1.000` over zero ADRs. Repos that legitimately have no ADRs yet
pass `--allow-empty`.

## Usage

### Python API

The common entry points are re-exported at the top level, so they stay stable
even if the internal module layout moves. The package ships `py.typed`, so these
types are visible to mypy in your repo:

```python
from pathlib import Path
from iil_adrfw import ConstitutionGraph, get_schema_dir, load_adr, load_adrs, run_audit

# The bundled schemas are the default — nothing to vendor or configure.
adrs = load_adrs(Path("docs/adr"), get_schema_dir())

graph = ConstitutionGraph(adrs)
report = run_audit(graph)          # AuditReport: .findings + .health snapshot
print(report.health.score, len(report.findings))

# Single ADR
adr = load_adr(Path("docs/adr/ADR-099.md"), get_schema_dir())

# Diagnosis mode: see what the loader sees BEFORE normalization. Pair raw=True
# with validate=False — un-normalized frontmatter will not satisfy the schema,
# and that is the point (it shows which ADRs rely on the loader's tolerance).
raw = load_adr(Path("docs/adr/ADR-099.md"), get_schema_dir(), validate=False, raw=True)
```

### CLI

**Every** subcommand accepts `--adr-dir` and falls back to `$IIL_ADRFW_ADRS_DIR`
and then `docs/adr`. Subcommands that historically took a positional directory
still accept it.

```bash
# Validate all ADR frontmatters against the schema
iil-adrfw validate                        # uses docs/adr
iil-adrfw validate --adr-dir docs/adr     # explicit
iil-adrfw validate docs/adr/              # positional, still supported

# Staleness (>6 months), broken references, missing reviews
iil-adrfw staleness --months 6

# Constitution-level health audit
iil-adrfw audit --json

# Which ADRs govern a given file?
iil-adrfw impact apps/billing/models.py

# Do the ADRs still describe the repo? (versions, ports, images)
iil-adrfw freshness --repo-path .

# Query by question, domain, or path
iil-adrfw query --question "Which ADR governs deployment?"

# Dependency graph (text, DOT, or JSON)
iil-adrfw graph --dot > graph.dot

# Outline-compatible markdown registry
iil-adrfw export -o adr-registry.md

# INDEX.md table (ADR-138 Impl column); --table-only for the bare block
iil-adrfw index -o docs/adr/INDEX.md

# Schema v4 controlling metrics
iil-adrfw metrics --report
```

Full surface: `validate`, `staleness`, `graph`, `export`, `index`, `check`,
`explain`, `list`, `validate-cross-repo`, `query`, `audit`, `propose`, `diff`,
`narrate`, `metrics`, `freshness`, `impact`.

### MCP Server (12 tools)

```bash
pip install 'iil-adrfw[mcp]'
iil-adrfw-mcp  # stdio transport
```

Register it with the ADR directory of the repo it should serve:

```json
{
  "mcpServers": {
    "iil-adrfw": {
      "type": "stdio",
      "command": "iil-adrfw-mcp",
      "env": { "IIL_ADRFW_ADRS_DIR": "/abs/path/to/repo/docs/adr" }
    }
  }
}
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
