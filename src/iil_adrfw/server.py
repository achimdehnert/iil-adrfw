"""FastMCP transport for the iil-adrfw core.

12 tools exposed: adr_check, adr_explain, adr_validate_cross_repo, adr_query,
adr_audit, adr_propose, adr_diff, adr_narrate, adr_validate, adr_staleness,
adr_impact, adr_freshness.

The implementations live in :mod:`iil_adrfw.api`, which imports no MCP machinery.
This module is the only place that needs FastMCP — install it with the ``[mcp]``
extra (``pip install 'iil-adrfw[mcp]'``). Everything the old single-module layout
exported from ``iil_adrfw.server`` is re-exported here, so existing imports of
request models and ``_do_*`` handlers keep working unchanged.
"""

try:
    from fastmcp import FastMCP
except ImportError as _exc:  # pragma: no cover - exercised via the extras matrix
    from iil_adrfw.errors import MissingExtraError

    raise MissingExtraError("mcp", "The MCP server") from _exc

from iil_adrfw.api import (
    ADRChangeOut,
    AuditRequest,
    AuditResponse,
    CheckRequest,
    CheckResponse,
    CitationOut,
    ConflictOut,
    ConsumerRepoSpec,
    CrossRepoBlockerOut,
    DecisionDriverIn,
    DiffRequest,
    DiffResponse,
    ExplainRequest,
    ExplainResponse,
    FieldChangeOut,
    FindingOut,
    FreshnessClaimOut,
    FreshnessRequest,
    FreshnessResponse,
    HealthOut,
    ImpactADR,
    ImpactRequest,
    ImpactResponse,
    NarrateRequest,
    NarrateResponse,
    NarrativeSectionOut,
    OpenQuestionMatchOut,
    ProposalConflictOut,
    ProposeRequest,
    ProposeResponse,
    QueryRequest,
    QueryResponse,
    StalenessRequest,
    StalenessResponse,
    UTCDateTime,
    ValidateCrossRepoRequest,
    ValidateCrossRepoResponse,
    ValidateRequest,
    ValidateResponse,
    ViolationOut,
    _adrs_dir,
    _do_audit,
    _do_check,
    _do_diff,
    _do_explain,
    _do_freshness,
    _do_impact,
    _do_list_adrs,
    _do_narrate,
    _do_propose,
    _do_query,
    _do_staleness,
    _do_validate,
    _do_validate_cross_repo,
    _ensure_utc,
    _gather_files,
    _load_constitution,
    _meets_threshold,
    _repo_root,
    _require_within_root,
    _schemas_dir,
)

# Re-exported for backwards compatibility: everything the pre-0.8 single-module
# `iil_adrfw.server` exposed is still importable from here.
__all__ = [
    "ADRChangeOut",
    "AuditRequest",
    "AuditResponse",
    "CheckRequest",
    "CheckResponse",
    "CitationOut",
    "ConflictOut",
    "ConsumerRepoSpec",
    "CrossRepoBlockerOut",
    "DecisionDriverIn",
    "DiffRequest",
    "DiffResponse",
    "ExplainRequest",
    "ExplainResponse",
    "FieldChangeOut",
    "FindingOut",
    "FreshnessClaimOut",
    "FreshnessRequest",
    "FreshnessResponse",
    "HealthOut",
    "ImpactADR",
    "ImpactRequest",
    "ImpactResponse",
    "NarrateRequest",
    "NarrateResponse",
    "NarrativeSectionOut",
    "OpenQuestionMatchOut",
    "ProposalConflictOut",
    "ProposeRequest",
    "ProposeResponse",
    "QueryRequest",
    "QueryResponse",
    "StalenessRequest",
    "StalenessResponse",
    "UTCDateTime",
    "ValidateCrossRepoRequest",
    "ValidateCrossRepoResponse",
    "ValidateRequest",
    "ValidateResponse",
    "ViolationOut",
    "_adrs_dir",
    "_do_audit",
    "_do_check",
    "_do_diff",
    "_do_explain",
    "_do_freshness",
    "_do_impact",
    "_do_list_adrs",
    "_do_narrate",
    "_do_propose",
    "_do_query",
    "_do_staleness",
    "_do_validate",
    "_do_validate_cross_repo",
    "_ensure_utc",
    "_gather_files",
    "_load_constitution",
    "_meets_threshold",
    "_repo_root",
    "_require_within_root",
    "_schemas_dir",
    "adr_audit",
    "adr_check",
    "adr_diff",
    "adr_explain",
    "adr_freshness",
    "adr_impact",
    "adr_narrate",
    "adr_propose",
    "adr_query",
    "adr_staleness",
    "adr_validate",
    "adr_validate_cross_repo",
    "list_adrs",
    "main",
    "mcp",
]

mcp = FastMCP("iil-adrfw")


@mcp.tool
def adr_check(req: CheckRequest) -> CheckResponse:
    """Run ADR rules against code paths and return structured violations."""
    return _do_check(req)


@mcp.tool
def adr_explain(req: ExplainRequest) -> ExplainResponse:
    """Provide pedagogical, audience-tailored explanation of a single rule."""
    return _do_explain(req)


@mcp.tool
def adr_validate_cross_repo(
    req: ValidateCrossRepoRequest,
) -> ValidateCrossRepoResponse:
    """Validate a draft/proposed ADR against the actual state of consumer repos.

    The killer use-case from ADR-188 v1.1: BEFORE transitioning to 'accepted',
    detect cases where the ADR contradicts what consumer-repos already do.
    Returns 'blocks_publish=True' for high-confidence conflicts that should
    prevent acceptance until resolved (either by amending the ADR or migrating
    the consumer-repos).
    """
    return _do_validate_cross_repo(req)


@mcp.tool
def adr_query(req: QueryRequest) -> QueryResponse:
    """Query the constitution: find which ADRs apply, what they say, and what
    open questions are related. Deterministic — no LLM call.

    Drives by question (text), domain tag, file path, or any combination.
    Returns 'open_questions' when the query touches an unanswered area —
    enabling consumers to escalate rather than guess.
    """
    return _do_query(req)


@mcp.tool
def adr_audit(req: AuditRequest) -> AuditResponse:
    """Self-audit the ADR set itself — meta-level consistency check.

    Composed of small specialized auditors: supersession_hygiene, dependency_health,
    staleness, coverage, open_question_aging, conflict. Each can be run alone
    or together. Returns aggregated findings PLUS a quantified HealthSnapshot
    so trends over time are measurable.
    """
    return _do_audit(req)


@mcp.tool
def adr_propose(req: ProposeRequest) -> ProposeResponse:
    """Generate a draft ADR with pre-publish validation.

    Out-of-the-box compared to mainstream ADR tools:
    - Detects duplicate titles and missed supersessions BEFORE the draft is created
    - Identifies open questions in existing ADRs that this proposal could close
    - Cross-repo pre-check: if cross_repo_paths is provided, validates the
      proposed claims against actual consumer-repo state (the ADR-188 v1.1 lesson —
      see adr_validate_cross_repo for the rationale).
    - Returns blocks_publish=True if HIGH/PROVEN-confidence cross-repo conflicts exist

    Architecture note: this tool makes NO LLM calls. It returns a complete,
    schema-valid frontmatter plus a structured body_prompt that a consumer LLM
    (Cascade, Claude Code, etc.) uses to generate the markdown body.
    """
    return _do_propose(req)


@mcp.tool
def adr_diff(req: DiffRequest) -> DiffResponse:
    """Diff a constitution between two world times (temporal mode) or
    two ADR sets (set mode).

    Temporal mode uses bi-temporal schema (decision_date, valid_from, valid_to,
    amendments) to materialize each ADR's effective state at the requested
    times. Useful for 'what changed in our architecture last quarter?'.

    Set mode compares two distinct ADR directories (repos, branches). Useful
    for 'where do platform and mcp-hub diverge?'.

    Both modes return changes categorized as added/removed/status_changed/
    supersession_changed/rules_changed/frontmatter_changed.
    """
    return _do_diff(req)


@mcp.tool
def adr_narrate(req: NarrateRequest) -> NarrateResponse:
    """Compose an audience-tailored narrative summary of a constitution subset.

    Selects ADRs by domain, id_set, or path_filter (AND-combined). Adapts the
    framing for one of four audiences: new_dev, senior, architect, auditor.

    Always emits the same five sections in the same order: Overview, Decisions
    in order, Supersession chains, Open questions, Compliance trail. Empty
    sections show '(none)' so consumers can rely on a stable structure.

    Architecture: NO LLM calls. Output is structured, deterministic prose.
    Consumer LLMs (Cascade, Claude Code) can refine if needed; the markdown
    field is also directly usable as-is.
    """
    return _do_narrate(req)


@mcp.resource("adr://list")
def list_adrs() -> dict:
    return _do_list_adrs()


@mcp.tool
def adr_validate(req: ValidateRequest) -> ValidateResponse:
    """Validate all ADR frontmatters against schema v3. Returns pass/fail count and failures."""
    return _do_validate(req)


@mcp.tool
def adr_staleness(req: StalenessRequest) -> StalenessResponse:
    """Check ADRs for staleness (age > threshold) and reference drift (broken superseded_by/depends_on/related)."""
    adr_dir = _require_within_root(req.adr_dir, what="adr_dir") if req.adr_dir else _adrs_dir()
    return _do_staleness(adr_dir, _schemas_dir(), req.months)


@mcp.tool
def adr_impact(req: ImpactRequest) -> ImpactResponse:
    """Given a file path, find which ADRs apply. Matches on scope patterns, domains, and repo references."""
    return _do_impact(req)


@mcp.tool()
def adr_freshness(req: FreshnessRequest) -> FreshnessResponse:
    """Check ADR content claims against actual repo state (versions, ports, images).

    Phase 1+2: deterministic, no LLM. Extracts version/port/image claims from
    ADR markdown body and compares against docker-compose and requirements files.
    """
    return _do_freshness(req)


def main() -> None:
    """Entry point for `iil-adrfw-mcp`."""
    mcp.run()
