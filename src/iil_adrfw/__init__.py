"""iil-adrfw — Architectural Decision Record framework.

Schema validation, loader normalization, a cross-ADR constitution graph, audit
tooling, bi-temporal diff/narrate/propose, and a CLI (``iil-adrfw``) + FastMCP
server (``iil-adrfw-mcp``) over a directory of ``ADR-*.md`` files.

The names below are the supported entry points for consuming repos — re-exported
here so the common case needs one import and stays stable even if the internal
module layout moves::

    from iil_adrfw import ConstitutionGraph, get_schema_dir, load_adrs, run_audit

    adrs = load_adrs(Path("docs/adr"), get_schema_dir())
    graph = ConstitutionGraph(adrs)

Everything else remains reachable through its submodule:

- ``iil_adrfw.domain``       — ADR dataclass, Status enum, temporal/relation types
- ``iil_adrfw.persistence``  — ``load_adrs()``, ``ADRLoadError``, schema validation
- ``iil_adrfw.graph``        — ``ConstitutionGraph`` (dependencies, supersession, cycles)
- ``iil_adrfw.audit``        — ``run_audit()`` and the auditor suite
- ``iil_adrfw.diff``         — ``diff_set()``, ``diff_temporal()``
- ``iil_adrfw.narrate``      — ``compose_narrative()``, ``Audience``
- ``iil_adrfw.propose``      — ADR proposal generation
- ``iil_adrfw.cross_repo``   — cross-repo claim validation (needs the ``[checkers]`` extra)
- ``iil_adrfw.freshness``    — repo-vs-ADR freshness checks
- ``iil_adrfw.metrics``      — Schema v4 controlling metrics
- ``iil_adrfw.index``        — INDEX.md table renderer
- ``iil_adrfw.api``          — request/response models + ``_do_*`` handlers (no MCP import)
- ``iil_adrfw.server``       — FastMCP transport over ``api`` (needs the ``[mcp]`` extra)
- ``iil_adrfw.cli``          — ``iil-adrfw`` command-line entry point

``__version__`` is resolved from the installed package metadata.
"""

from importlib.metadata import PackageNotFoundError, version

from iil_adrfw.audit import run_audit
from iil_adrfw.domain import ADR, Status
from iil_adrfw.graph import ConstitutionGraph
from iil_adrfw.persistence import ADRLoadError, load_adr, load_adrs
from iil_adrfw.schemas import get_schema_dir

try:
    __version__ = version("iil-adrfw")
except PackageNotFoundError:  # source checkout without an install
    __version__ = "0.0.0.dev0"

__all__ = [
    "ADR",
    "ADRLoadError",
    "ConstitutionGraph",
    "Status",
    "__version__",
    "get_schema_dir",
    "load_adr",
    "load_adrs",
    "run_audit",
]
