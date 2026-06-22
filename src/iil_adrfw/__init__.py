"""iil-adrfw — Architectural Decision Record framework.

Schema validation, loader normalization, a cross-ADR constitution graph, audit
tooling, bi-temporal diff/narrate/propose, and a CLI (``iil-adrfw``) + FastMCP
server (``iil-adrfw-mcp``) over a directory of ``ADR-*.md`` files.

Public API is organised by submodule — import from these directly:

- ``iil_adrfw.domain``       — ADR dataclass, Status enum, temporal/relation types
- ``iil_adrfw.persistence``  — ``load_adrs()``, ``ADRLoadError``, schema validation
- ``iil_adrfw.graph``        — ``ConstitutionGraph`` (dependencies, supersession, cycles)
- ``iil_adrfw.audit``        — ``run_audit()`` and the auditor suite
- ``iil_adrfw.diff``         — ``diff_set()``, ``diff_temporal()``
- ``iil_adrfw.narrate``      — ``compose_narrative()``, ``Audience``
- ``iil_adrfw.propose``      — ADR proposal generation
- ``iil_adrfw.cross_repo``   — cross-repo claim validation
- ``iil_adrfw.freshness``    — repo-vs-ADR freshness checks
- ``iil_adrfw.metrics``      — Schema v4 controlling metrics
- ``iil_adrfw.server``       — FastMCP request models + ``_do_*`` handlers
- ``iil_adrfw.cli``          — ``iil-adrfw`` command-line entry point

``__version__`` is resolved from the installed package metadata.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("iil-adrfw")
except PackageNotFoundError:  # source checkout without an install
    __version__ = "0.0.0.dev0"

__all__ = ["__version__"]
