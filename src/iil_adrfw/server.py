"""FastMCP server exposing iil-adrfw tools.

Two tools implemented for the skeleton:
- adr_check:   run rules against code paths
- adr_explain: audience-tailored rule explanation

Six more (query, diff, audit, propose, shadow_pr, narrate) will follow.
"""

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from iil_adrfw.checkers import build_checker
from iil_adrfw.domain import ADR, Rule, RuleViolation, Severity
from iil_adrfw.persistence import load_adrs

mcp = FastMCP("iil-adrfw")


# --- Configuration via env vars ---


def _adrs_dir() -> Path:
    return Path(os.environ.get("IIL_ADRFW_ADRS_DIR", "./adrs")).resolve()


def _schemas_dir() -> Path:
    default = Path(__file__).resolve().parent.parent.parent / "schemas"
    return Path(os.environ.get("IIL_ADRFW_SCHEMAS_DIR", str(default))).resolve()


def _repo_root() -> Path:
    return Path(os.environ.get("IIL_ADRFW_REPO_ROOT", ".")).resolve()


# --- Caching ---
# Skeleton: load on every call. Production: hash adrs_dir mtime, cache.


def _load_constitution() -> list[ADR]:
    return load_adrs(_adrs_dir(), _schemas_dir(), validate=True)


# --- Tool: adr_check ---


class CheckRequest(BaseModel):
    paths: list[str] = Field(description="Files or directories (relative to repo root or absolute) to check")
    rule_ids: list[str] | None = Field(
        default=None,
        description="Filter to specific rule IDs (e.g. ['ADR-099/tenant-id-bigint']). None = all applicable.",
    )
    severity_threshold: Literal["info", "warning", "error", "critical"] = "warning"
    as_of: datetime | None = Field(
        default=None,
        description="Bi-temporal: check against the constitution as of this timestamp. None = now.",
    )


class ViolationOut(BaseModel):
    rule_id: str
    severity: str
    file: str
    line_start: int
    line_end: int
    expected: str
    actual: str
    likely_cause: str
    semantic_distance: float
    blast_radius: str | None
    suggestions: list[dict]


class CheckResponse(BaseModel):
    violations: list[ViolationOut]
    rules_evaluated: int
    files_scanned: int
    runtime_ms: int
    constitution_loaded: int  # how many ADRs were active


def _gather_files(paths: list[str], repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        path = Path(p)
        if not path.is_absolute():
            path = repo_root / path
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(path.rglob("*.py"))
    return files


def _meets_threshold(severity: Severity, threshold: Severity) -> bool:
    order = [Severity.INFO, Severity.WARNING, Severity.ERROR, Severity.CRITICAL]
    return order.index(severity) >= order.index(threshold)


def _do_check(req: CheckRequest) -> CheckResponse:
    """Pure implementation, callable directly from tests and CLI."""
    start = datetime.now(UTC)
    repo_root = _repo_root()

    adrs = _load_constitution()
    as_of = req.as_of or datetime.now(UTC)
    threshold = Severity(req.severity_threshold)

    # Collect applicable rules
    rules: list[Rule] = []
    for adr in adrs:
        for r in adr.applicable_rules(world_time=as_of):
            if req.rule_ids and r.global_id not in req.rule_ids:
                continue
            if not _meets_threshold(r.severity, threshold):
                continue
            rules.append(r)

    # Collect files
    files = _gather_files(req.paths, repo_root)

    # Run checkers
    all_violations: list[RuleViolation] = []
    for rule in rules:
        checker = build_checker(rule)
        if checker is None:
            continue
        for f in files:
            if not rule.scope.matches(f.relative_to(repo_root) if f.is_absolute() and repo_root in f.parents else f):
                # Try with raw path if relative_to fails
                if not rule.scope.matches(f):
                    continue
            try:
                source = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, FileNotFoundError):
                continue
            violations = checker.check(rule, f, source)
            all_violations.extend(violations)

    elapsed_ms = int((datetime.now(UTC) - start).total_seconds() * 1000)

    out_violations = [
        ViolationOut(
            rule_id=v.rule_id,
            severity=v.severity.value,
            file=v.file,
            line_start=v.line_start,
            line_end=v.line_end,
            expected=v.expected,
            actual=v.actual,
            likely_cause=v.diagnostic.likely_cause,
            semantic_distance=v.diagnostic.semantic_distance,
            blast_radius=v.diagnostic.blast_radius,
            suggestions=[
                {
                    "description": s.description,
                    "confidence": s.confidence,
                    "automated": s.automated,
                    "side_effects": list(s.side_effects),
                }
                for s in v.suggestions
            ],
        )
        for v in all_violations
    ]
    return CheckResponse(
        violations=out_violations,
        rules_evaluated=len(rules),
        files_scanned=len(files),
        runtime_ms=elapsed_ms,
        constitution_loaded=len(adrs),
    )


# --- Tool: adr_explain ---


class ExplainRequest(BaseModel):
    rule_id: str = Field(description="Global rule id, e.g. 'ADR-099/tenant-id-bigint'")
    audience: Literal["new_dev", "senior", "architect", "auditor"] = "senior"


class ExplainResponse(BaseModel):
    rule: str
    severity: str
    why_it_exists: str
    explanation_for_audience: str
    correct_examples: list[str]
    common_violations: list[str]
    last_changed: str
    blast_radius: str | None


@mcp.tool
def adr_check(req: CheckRequest) -> CheckResponse:
    """Run ADR rules against code paths and return structured violations."""
    return _do_check(req)


def _do_explain(req: ExplainRequest) -> ExplainResponse:
    """Pure implementation, callable directly from tests and CLI."""
    adrs = _load_constitution()
    rule: Rule | None = None
    for adr in adrs:
        for r in adr.rules:
            if r.global_id == req.rule_id:
                rule = r
                break
        if rule:
            break

    if rule is None:
        raise ValueError(f"Rule {req.rule_id!r} not found in constitution")

    audience_text = rule.audience_explanations.get(req.audience) or rule.rationale

    correct = [ex.get("code", "") for ex in rule.examples.get("good", [])]
    bad = [ex.get("code", "") for ex in rule.examples.get("bad", [])]

    return ExplainResponse(
        rule=rule.title,
        severity=rule.severity.value,
        why_it_exists=rule.rationale,
        explanation_for_audience=audience_text,
        correct_examples=correct,
        common_violations=bad,
        last_changed=rule.temporal.valid_from.isoformat(),
        blast_radius=rule.blast_radius,
    )


@mcp.tool
def adr_explain(req: ExplainRequest) -> ExplainResponse:
    """Provide pedagogical, audience-tailored explanation of a single rule."""
    return _do_explain(req)


# --- Tool: adr_validate_cross_repo ---


class ConsumerRepoSpec(BaseModel):
    name: str = Field(description="Repo name as referenced in ADR.consumers")
    root: str = Field(description="Local path to the repo checkout")


class ValidateCrossRepoRequest(BaseModel):
    adr_id: str = Field(description="The ADR to validate, e.g. 'ADR-188'")
    consumer_repos: list[ConsumerRepoSpec] = Field(
        description="Consumer repos to scan. Order does not matter.",
    )


class ConflictOut(BaseModel):
    rule_id: str | None
    conflict_class: str
    confidence: str
    claim: str
    reality: str
    affected_repos: list[str]
    suggestion: str
    blocks_publish: bool
    evidence_count: int
    evidence_preview: list[dict]  # first few samples


class ValidateCrossRepoResponse(BaseModel):
    adr_id: str
    consumer_repos_scanned: list[str]
    repos_unreachable: list[str]
    conflicts: list[ConflictOut]
    has_blocking_conflicts: bool
    class1_count: int
    class2_count: int
    class3_count: int
    runtime_ms: int


def _do_validate_cross_repo(req: ValidateCrossRepoRequest) -> ValidateCrossRepoResponse:
    """Pure implementation, callable from tests and CLI."""
    from iil_adrfw.cross_repo import ConsumerRepoLayout, validate_cross_repo

    adrs = _load_constitution()
    adr = next((a for a in adrs if a.id == req.adr_id), None)
    if adr is None:
        raise ValueError(f"ADR {req.adr_id!r} not found in constitution")

    layouts = [ConsumerRepoLayout(name=r.name, root=Path(r.root)) for r in req.consumer_repos]

    report = validate_cross_repo(adr, layouts)

    out_conflicts = [
        ConflictOut(
            rule_id=c.rule_id,
            conflict_class=c.conflict_class.value,
            confidence=c.confidence.value,
            claim=c.claim,
            reality=c.reality,
            affected_repos=list(c.affected_repos),
            suggestion=c.suggestion,
            blocks_publish=c.blocks_publish,
            evidence_count=len(c.evidence),
            evidence_preview=[
                {
                    "repo": s.repo,
                    "file": s.file,
                    "line": s.line_start,
                    "snippet": s.snippet,
                    "extracted_value": s.extracted_value,
                }
                for s in c.evidence[:5]
            ],
        )
        for c in report.conflicts
    ]
    return ValidateCrossRepoResponse(
        adr_id=report.adr_id,
        consumer_repos_scanned=list(report.consumer_repos_scanned),
        repos_unreachable=list(report.repos_unreachable),
        conflicts=out_conflicts,
        has_blocking_conflicts=report.has_blocking_conflicts,
        class1_count=report.class1_count,
        class2_count=report.class2_count,
        class3_count=report.class3_count,
        runtime_ms=report.runtime_ms,
    )


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


# --- Tool: adr_query ---


class QueryRequest(BaseModel):
    question: str | None = Field(
        default=None,
        description="Natural-language question about architectural rules",
    )
    domain: str | None = Field(
        default=None,
        description="Limit to a specific domain tag, e.g. 'django/models'",
    )
    path: str | None = Field(
        default=None,
        description="File path the answer should apply to, e.g. 'apps/billing/models.py'",
    )


class CitationOut(BaseModel):
    adr_id: str
    title: str
    status: str
    relevance: str
    excerpt: str
    matched_concepts: list[str]


class QueryResponse(BaseModel):
    primary_answer: str
    citations: list[CitationOut]
    open_questions: list[dict]  # adr_id, q_id, question
    confidence: float
    routing: str


def _do_query(req: QueryRequest) -> QueryResponse:
    from iil_adrfw.graph import ConstitutionGraph, execute_query

    if not (req.question or req.domain or req.path):
        raise ValueError("At least one of question/domain/path must be provided")

    adrs = _load_constitution()
    graph = ConstitutionGraph.build(adrs)
    result = execute_query(graph, question=req.question, domain=req.domain, path=req.path)

    return QueryResponse(
        primary_answer=result.primary_answer,
        citations=[
            CitationOut(
                adr_id=c.adr_id,
                title=c.title,
                status=c.status,
                relevance=c.relevance,
                excerpt=c.excerpt,
                matched_concepts=list(c.matched_concepts),
            )
            for c in result.citations
        ],
        open_questions=[{"adr_id": adr_id, "q_id": q_id, "question": q} for adr_id, q_id, q in result.open_questions],
        confidence=result.confidence,
        routing=result.routing,
    )


@mcp.tool
def adr_query(req: QueryRequest) -> QueryResponse:
    """Query the constitution: find which ADRs apply, what they say, and what
    open questions are related. Deterministic — no LLM call.

    Drives by question (text), domain tag, file path, or any combination.
    Returns 'open_questions' when the query touches an unanswered area —
    enabling consumers to escalate rather than guess.
    """
    return _do_query(req)


# --- Tool: adr_audit ---


class AuditRequest(BaseModel):
    auditors: list[str] | None = Field(
        default=None,
        description=(
            "Subset of auditors to run. Available: supersession_hygiene, "
            "dependency_health, staleness, coverage, open_question_aging, conflict. "
            "None = all."
        ),
    )
    as_of: datetime | None = Field(
        default=None,
        description="Timestamp for staleness/open_question_aging checks. None = now.",
    )


class FindingOut(BaseModel):
    auditor: str
    severity: str
    affected_adrs: list[str]
    description: str
    proposed_resolution: str | None
    evidence: list[str]


class HealthOut(BaseModel):
    score: float
    internal_consistency: float
    code_alignment: float
    coverage: float
    freshness: float
    supersession_hygiene: float
    issue_counts: dict[str, int]


class AuditResponse(BaseModel):
    auditors_run: list[str]
    findings: list[FindingOut]
    health: HealthOut
    runtime_ms: int


def _do_audit(req: AuditRequest) -> AuditResponse:
    from iil_adrfw.audit import run_audit
    from iil_adrfw.graph import ConstitutionGraph

    adrs = _load_constitution()
    graph = ConstitutionGraph.build(adrs)
    report = run_audit(graph, auditors=req.auditors, now=req.as_of)

    return AuditResponse(
        auditors_run=list(report.auditors_run),
        findings=[
            FindingOut(
                auditor=f.auditor,
                severity=f.severity.value,
                affected_adrs=list(f.affected_adrs),
                description=f.description,
                proposed_resolution=f.proposed_resolution,
                evidence=list(f.evidence),
            )
            for f in report.findings
        ],
        health=HealthOut(
            score=report.health.score,
            internal_consistency=report.health.internal_consistency,
            code_alignment=report.health.code_alignment,
            coverage=report.health.coverage,
            freshness=report.health.freshness,
            supersession_hygiene=report.health.supersession_hygiene,
            issue_counts=report.health.issue_counts,
        ),
        runtime_ms=report.runtime_ms,
    )


@mcp.tool
def adr_audit(req: AuditRequest) -> AuditResponse:
    """Self-audit the ADR set itself — meta-level consistency check.

    Composed of small specialized auditors: supersession_hygiene, dependency_health,
    staleness, coverage, open_question_aging, conflict. Each can be run alone
    or together. Returns aggregated findings PLUS a quantified HealthSnapshot
    so trends over time are measurable.
    """
    return _do_audit(req)


# --- Tool: adr_propose ---


class DecisionDriverIn(BaseModel):
    id: str = Field(description="Local id like 'D-1'")
    driver: str = Field(description="One-sentence driver statement")
    weight: Literal["critical", "high", "medium", "low"] = "medium"
    category: str | None = None


class ProposeRequest(BaseModel):
    title: str = Field(description="Decision-stating title in imperative voice")
    domains: list[str] = Field(min_length=1, description="Domain tags this ADR applies to")
    deciders: list[str] = Field(min_length=1, description="Accountable decision-makers")
    rationale_summary: str = Field(
        min_length=20,
        description="One paragraph of 'why'. Drives concept matching and body prompt.",
    )
    repo: str | None = None
    consumers: list[str] | None = None
    supersedes: list[str] | None = None
    consolidates: list[str] | None = None
    depends_on: list[str] | None = None
    decision_drivers: list[DecisionDriverIn] | None = None
    requested_id: str | None = Field(
        default=None,
        description="Specific ADR id to use. If omitted, the next available number is allocated.",
    )
    cross_repo_paths: dict[str, str] | None = Field(
        default=None,
        description=(
            "Map from consumer-repo name to local checkout path. If provided, "
            "the proposal is validated against actual consumer-repo state — "
            "the lesson from ADR-188 v1.1."
        ),
    )


class ProposalConflictOut(BaseModel):
    kind: str
    severity: str
    related_adr_ids: list[str]
    description: str
    suggestion: str


class OpenQuestionMatchOut(BaseModel):
    adr_id: str
    q_id: str
    question: str
    overlap_score: float


class CrossRepoBlockerOut(BaseModel):
    conflict_class: str
    confidence: str
    claim: str
    reality: str
    affected_repos: list[str]
    blocks_publish: bool
    summary: str


class ProposeResponse(BaseModel):
    proposed_id: str
    frontmatter: dict
    body_prompt: str
    conflicts: list[ProposalConflictOut]
    closes_open_questions: list[OpenQuestionMatchOut]
    cross_repo_blockers: list[CrossRepoBlockerOut]
    blocks_publish: bool
    runtime_ms: int


def _do_propose(req: ProposeRequest) -> ProposeResponse:
    from iil_adrfw.graph import ConstitutionGraph
    from iil_adrfw.propose import ProposalRequest, propose_adr

    adrs = _load_constitution()
    graph = ConstitutionGraph.build(adrs)

    drivers = [d.model_dump() for d in req.decision_drivers] if req.decision_drivers else None

    proposal_req = ProposalRequest(
        title=req.title,
        domains=req.domains,
        deciders=req.deciders,
        rationale_summary=req.rationale_summary,
        repo=req.repo,
        consumers=req.consumers,
        supersedes=req.supersedes,
        consolidates=req.consolidates,
        depends_on=req.depends_on,
        decision_drivers=drivers,
        requested_id=req.requested_id,
        cross_repo_paths=req.cross_repo_paths,
    )
    result = propose_adr(graph, proposal_req)

    return ProposeResponse(
        proposed_id=result.proposed_id,
        frontmatter=result.frontmatter,
        body_prompt=result.body_prompt,
        conflicts=[
            ProposalConflictOut(
                kind=c.kind,
                severity=c.severity,
                related_adr_ids=list(c.related_adr_ids),
                description=c.description,
                suggestion=c.suggestion,
            )
            for c in result.conflicts
        ],
        closes_open_questions=[
            OpenQuestionMatchOut(
                adr_id=m.adr_id,
                q_id=m.q_id,
                question=m.question,
                overlap_score=m.overlap_score,
            )
            for m in result.closes_open_questions
        ],
        cross_repo_blockers=[CrossRepoBlockerOut(**b) for b in result.cross_repo_blockers],
        blocks_publish=result.blocks_publish,
        runtime_ms=result.runtime_ms,
    )


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


# --- Tool: adr_diff ---


class DiffRequest(BaseModel):
    mode: Literal["temporal", "set"] = Field(
        description=(
            "'temporal': same ADR set at two world times. Requires left_time + right_time. "
            "'set': two distinct ADR sets/repos. Requires right_dir."
        ),
    )
    left_time: datetime | None = Field(
        default=None,
        description="Temporal mode: left side world time (older).",
    )
    right_time: datetime | None = Field(
        default=None,
        description="Temporal mode: right side world time (newer).",
    )
    right_dir: str | None = Field(
        default=None,
        description="Set mode: path to the right-hand-side ADR directory. Left is the configured constitution.",
    )
    left_label: str = "left"
    right_label: str = "right"


class FieldChangeOut(BaseModel):
    field_path: str
    before: object | None = None
    after: object | None = None


class ADRChangeOut(BaseModel):
    adr_id: str
    kind: str
    summary: str
    field_changes: list[FieldChangeOut] = []


class DiffResponse(BaseModel):
    mode: str
    left_label: str
    right_label: str
    added_count: int
    removed_count: int
    modified_count: int
    changes: list[ADRChangeOut]
    runtime_ms: int


def _do_diff(req: DiffRequest) -> DiffResponse:
    from iil_adrfw.diff import diff_set, diff_temporal

    if req.mode == "temporal":
        if req.left_time is None or req.right_time is None:
            raise ValueError("temporal mode requires left_time and right_time")
        adrs = _load_constitution()
        result = diff_temporal(adrs, req.left_time, req.right_time)
    elif req.mode == "set":
        if not req.right_dir:
            raise ValueError("set mode requires right_dir")
        from iil_adrfw.persistence import load_adrs

        right_path = Path(req.right_dir)
        if not right_path.is_dir():
            raise ValueError(f"right_dir does not exist: {right_path}")
        left = _load_constitution()
        right = load_adrs(right_path, _schemas_dir(), validate=True)
        result = diff_set(
            left,
            right,
            left_label=req.left_label,
            right_label=req.right_label,
        )
    else:
        raise ValueError(f"unknown mode: {req.mode}")

    return DiffResponse(
        mode=result.mode.value,
        left_label=result.left_label,
        right_label=result.right_label,
        added_count=result.added_count,
        removed_count=result.removed_count,
        modified_count=result.modified_count,
        changes=[
            ADRChangeOut(
                adr_id=c.adr_id,
                kind=c.kind.value,
                summary=c.summary,
                field_changes=[
                    FieldChangeOut(field_path=fc.field_path, before=fc.before, after=fc.after) for fc in c.field_changes
                ],
            )
            for c in result.changes
        ],
        runtime_ms=result.runtime_ms,
    )


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


# --- Tool: adr_narrate ---


class NarrateRequest(BaseModel):
    audience: Literal["new_dev", "senior", "architect", "auditor"] = Field(
        description=(
            "new_dev: onboarding story. senior: technical retrospective with tradeoffs. "
            "architect: strategic overview with consolidation/dependencies. "
            "auditor: compliance trail with deciders/dates/regulatory drivers."
        ),
    )
    domain: str | None = Field(
        default=None,
        description="Pick all ADRs carrying this domain tag (e.g. 'data/database').",
    )
    id_set: list[str] | None = Field(
        default=None,
        description="Pick an explicit list of ADR ids (e.g. ['ADR-099', 'ADR-188']).",
    )
    path_filter: str | None = Field(
        default=None,
        description="Pick ADRs whose scope.include_paths or drift_check_paths match this path.",
    )
    scope_label: str = Field(
        default="the constitution",
        description="Free-text label used in the narrative title and intro.",
    )


class NarrativeSectionOut(BaseModel):
    heading: str
    body: str


class NarrateResponse(BaseModel):
    audience: str
    title: str
    intro: str
    sections: list[NarrativeSectionOut]
    adr_ids_covered: list[str]
    markdown: str = Field(description="Full markdown rendering for direct use or refinement.")
    runtime_ms: int


def _do_narrate(req: NarrateRequest) -> NarrateResponse:
    from iil_adrfw.narrate import Audience, compose_narrative, select_adrs

    if not (req.domain or req.id_set or req.path_filter):
        raise ValueError("At least one selector required: domain, id_set, or path_filter")
    adrs = _load_constitution()
    selected = select_adrs(
        adrs,
        domain=req.domain,
        id_set=req.id_set,
        path_filter=req.path_filter,
    )
    if not selected:
        raise ValueError("No ADRs matched the given selectors")

    audience = Audience(req.audience)
    narrative = compose_narrative(selected, audience, scope_label=req.scope_label)

    return NarrateResponse(
        audience=narrative.audience.value,
        title=narrative.title,
        intro=narrative.intro,
        sections=[NarrativeSectionOut(heading=s.heading, body=s.body) for s in narrative.sections],
        adr_ids_covered=list(narrative.adr_ids_covered),
        markdown=narrative.render_markdown(),
        runtime_ms=narrative.runtime_ms,
    )


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


# --- Resource: list ADRs ---


def _do_list_adrs() -> dict:
    adrs = _load_constitution()
    return {
        "adrs": [
            {
                "id": a.id,
                "title": a.title,
                "status": a.status.value,
                "domains": list(a.domains),
                "rule_count": len(a.rules),
            }
            for a in adrs
        ]
    }


@mcp.resource("adr://list")
def list_adrs() -> dict:
    return _do_list_adrs()


# --- Tool: adr_validate (schema validation) ---


class ValidateRequest(BaseModel):
    adr_dir: str | None = Field(
        default=None,
        description="Directory containing ADR-*.md files. Defaults to IIL_ADRFW_ADRS_DIR env.",
    )


class ValidateResponse(BaseModel):
    total: int
    passed: int
    failed: int
    percent: float
    failures: list[dict]


def _do_validate(req: ValidateRequest) -> ValidateResponse:
    from iil_adrfw.persistence import ADRLoadError, load_adr
    from iil_adrfw.schemas import get_schema_dir

    adr_dir = Path(req.adr_dir) if req.adr_dir else _adrs_dir()
    schema_dir = get_schema_dir()

    md_files = sorted(adr_dir.glob("ADR-*.md"))
    ok, failures = [], []
    for md in md_files:
        try:
            load_adr(md, schema_dir, validate=True)
            ok.append(md.name)
        except ADRLoadError as e:
            msg = str(e).split("\n")[1] if "\n" in str(e) else str(e)[:120]
            failures.append({"file": md.name, "error": msg})
        except Exception as e:
            failures.append({"file": md.name, "error": f"{type(e).__name__}: {str(e)[:100]}"})

    total = len(ok) + len(failures)
    return ValidateResponse(
        total=total,
        passed=len(ok),
        failed=len(failures),
        percent=round(100 * len(ok) / total, 1) if total else 0,
        failures=failures,
    )


@mcp.tool
def adr_validate(req: ValidateRequest) -> ValidateResponse:
    """Validate all ADR frontmatters against schema v3. Returns pass/fail count and failures."""
    return _do_validate(req)


# --- Tool: adr_staleness ---


class StalenessRequest(BaseModel):
    adr_dir: str | None = Field(
        default=None,
        description="Directory containing ADR-*.md files. Defaults to IIL_ADRFW_ADRS_DIR env.",
    )
    months: int = Field(default=6, description="Staleness threshold in months")


class StalenessResponse(BaseModel):
    total_adrs: int
    stale_count: int
    broken_refs: int
    missing_reviews: int
    findings: list[dict]


@mcp.tool
def adr_staleness(req: StalenessRequest) -> StalenessResponse:
    """Check ADRs for staleness (age > threshold) and reference drift (broken superseded_by, depends_on)."""
    from datetime import date, timedelta

    from iil_adrfw.persistence import load_adr
    from iil_adrfw.schemas import get_schema_dir

    adr_dir = Path(req.adr_dir) if req.adr_dir else _adrs_dir()
    schema_dir = get_schema_dir()
    today = date.today()
    threshold = today - timedelta(days=30 * req.months)

    md_files = sorted(adr_dir.glob("ADR-*.md"))
    findings = []
    all_ids = set()
    adrs_data = []

    for md in md_files:
        try:
            adr = load_adr(md, schema_dir, validate=False)
            all_ids.add(adr.id)
            adrs_data.append(adr)

            adr_date = None
            if hasattr(adr, "decision_date") and adr.decision_date:
                try:
                    adr_date = date.fromisoformat(str(adr.decision_date)[:10])
                except (ValueError, TypeError):
                    pass

            status = adr.status.value if hasattr(adr.status, "value") else str(adr.status)
            if status.lower() in ("deprecated", "superseded", "rejected"):
                continue

            if adr_date and adr_date < threshold:
                age_months = (today - adr_date).days // 30
                findings.append(
                    {
                        "adr_id": adr.id,
                        "type": "stale",
                        "severity": "warning",
                        "message": f"Decision date {adr_date} ({age_months}mo ago)",
                    }
                )

            review = getattr(adr, "review_status", None)
            if status.lower() == "accepted" and not review:
                findings.append(
                    {
                        "adr_id": adr.id,
                        "type": "no_review",
                        "severity": "info",
                        "message": "Accepted ADR without review_status",
                    }
                )
        except Exception:
            continue

    for adr in adrs_data:
        sup_by = getattr(adr, "superseded_by", None)
        if sup_by:
            refs = sup_by if isinstance(sup_by, (list, tuple)) else [sup_by]
            for ref in refs:
                ref_str = str(ref).strip()
                if ref_str and ref_str not in all_ids:
                    findings.append(
                        {
                            "adr_id": adr.id,
                            "type": "broken_ref",
                            "severity": "error",
                            "message": f"superseded_by '{ref_str}' not found",
                        }
                    )

    return StalenessResponse(
        total_adrs=len(md_files),
        stale_count=len([f for f in findings if f["type"] == "stale"]),
        broken_refs=len([f for f in findings if f["type"] == "broken_ref"]),
        missing_reviews=len([f for f in findings if f["type"] == "no_review"]),
        findings=findings,
    )


# --- Tool: adr_impact (Code → ADR mapping) ---


class ImpactRequest(BaseModel):
    file_path: str = Field(description="File path to check (e.g. 'apps/billing/models.py')")
    repo: str | None = Field(default=None, description="Repo name for scope filtering")


class ImpactADR(BaseModel):
    adr_id: str
    title: str
    status: str
    relevance: str  # "direct" | "domain" | "general"
    matched_by: str  # what triggered the match


class ImpactResponse(BaseModel):
    file_path: str
    applicable_adrs: list[ImpactADR]
    total_applicable: int


@mcp.tool
def adr_impact(req: ImpactRequest) -> ImpactResponse:
    """Given a file path, find which ADRs apply. Matches on scope patterns, domains, and repo references."""
    import fnmatch

    adrs = _load_constitution()
    file_p = req.file_path
    applicable = []

    # Infer domain from path
    path_domains = set()
    if "models" in file_p:
        path_domains.update(["django/models", "database"])
    if "views" in file_p:
        path_domains.update(["django/views", "htmx"])
    if "service" in file_p:
        path_domains.update(["django/services", "service-layer"])
    if "template" in file_p or ".html" in file_p:
        path_domains.update(["htmx", "templates"])
    if "docker" in file_p.lower() or "compose" in file_p.lower():
        path_domains.update(["deployment", "docker"])
    if "test" in file_p:
        path_domains.update(["testing"])
    if ".github" in file_p or "ci" in file_p.lower():
        path_domains.update(["ci-cd", "deployment"])
    if "migration" in file_p:
        path_domains.update(["database", "migrations"])

    for adr in adrs:
        adr_id = adr.id
        title = adr.title
        status = adr.status.value if hasattr(adr.status, "value") else str(adr.status)

        # Skip non-active ADRs
        if status.lower() in ("deprecated", "superseded", "rejected"):
            continue

        # Check scope patterns
        scope = getattr(adr, "scope", None)
        if scope:
            scope_str = str(scope) if not hasattr(scope, "glob_patterns") else ""
            patterns = getattr(scope, "glob_patterns", []) or []
            if not patterns and scope_str:
                patterns = [p.strip() for p in scope_str.split(",") if p.strip()]

            for pattern in patterns:
                if fnmatch.fnmatch(file_p, pattern) or fnmatch.fnmatch(file_p, f"**/{pattern}"):
                    applicable.append(
                        ImpactADR(
                            adr_id=adr_id,
                            title=title,
                            status=status,
                            relevance="direct",
                            matched_by=f"scope: {pattern}",
                        )
                    )
                    break

        # Check domain overlap
        adr_domains = set(getattr(adr, "domains", []) or [])
        overlap = path_domains & adr_domains
        if overlap and not any(a.adr_id == adr_id for a in applicable):
            applicable.append(
                ImpactADR(
                    adr_id=adr_id,
                    title=title,
                    status=status,
                    relevance="domain",
                    matched_by=f"domains: {', '.join(overlap)}",
                )
            )

        # Check repo reference
        if req.repo:
            consumers = getattr(adr, "consumers", []) or []
            if req.repo in consumers or req.repo in str(getattr(adr, "scope", "")):
                if not any(a.adr_id == adr_id for a in applicable):
                    applicable.append(
                        ImpactADR(
                            adr_id=adr_id,
                            title=title,
                            status=status,
                            relevance="general",
                            matched_by=f"repo: {req.repo}",
                        )
                    )

    # Sort: direct first, then domain, then general
    order = {"direct": 0, "domain": 1, "general": 2}
    applicable.sort(key=lambda a: order.get(a.relevance, 9))

    return ImpactResponse(
        file_path=file_p,
        applicable_adrs=applicable,
        total_applicable=len(applicable),
    )


class FreshnessRequest(BaseModel):
    adr_id: str | None = Field(
        default=None,
        description="Check a specific ADR. If None, checks all active ADRs.",
    )
    repo_path: str = Field(
        description="Path to the repo root to compare against",
    )
    compose_files: list[str] | None = Field(
        default=None,
        description="Compose files to check (default: docker-compose.prod.yml, docker-compose.yml)",
    )
    requirements_files: list[str] | None = Field(
        default=None,
        description="Requirements files (default: requirements.txt, pyproject.toml)",
    )


class FreshnessClaimOut(BaseModel):
    adr_id: str
    claim_type: str
    subject: str
    claimed_value: str
    actual_value: str
    source_file: str
    severity: str


class FreshnessResponse(BaseModel):
    total_claims: int
    stale_claims: list[FreshnessClaimOut]
    verified_claims: int
    unverifiable_claims: int
    runtime_ms: int


@mcp.tool()
def adr_freshness(req: FreshnessRequest) -> FreshnessResponse:
    """Check ADR content claims against actual repo state (versions, ports, images).

    Phase 1+2: deterministic, no LLM. Extracts version/port/image claims from
    ADR markdown body and compares against docker-compose and requirements files.
    """
    from iil_adrfw.freshness import check_freshness, extract_claims

    adrs = _load_constitution()
    repo_root = Path(req.repo_path).resolve()

    # Derive repo name from path for relevance filtering
    repo_name = repo_root.name  # e.g. "dev-hub"

    def _is_relevant(adr) -> bool:
        """ADR is relevant if it targets this repo, or is platform-wide."""
        if req.adr_id and adr.id == req.adr_id:
            return True
        # Explicit repo match
        if adr.repo and adr.repo == repo_name:
            return True
        # Listed as consumer
        if repo_name in adr.consumers:
            return True
        # Platform-wide (no specific repo/consumers = applies to all)
        if not adr.repo and not adr.consumers:
            return True
        # "platform" repo ADRs apply broadly
        if adr.repo == "platform" and not adr.consumers:
            return True
        return False

    all_claims = []
    if req.adr_id:
        for adr in adrs:
            if adr.id == req.adr_id:
                all_claims = extract_claims(adr.id, adr.body_markdown)
                break
    else:
        for adr in adrs:
            if adr.status.is_active() and adr.body_markdown and _is_relevant(adr):
                all_claims.extend(extract_claims(adr.id, adr.body_markdown))

    report = check_freshness(
        all_claims,
        repo_root,
        compose_files=req.compose_files,
        requirements_files=req.requirements_files,
    )

    return FreshnessResponse(
        total_claims=report.total_claims,
        stale_claims=[
            FreshnessClaimOut(
                adr_id=f.adr_id,
                claim_type=f.claim.claim_type,
                subject=f.claim.subject,
                claimed_value=f.claim.value,
                actual_value=f.actual_value,
                source_file=f.source_file,
                severity=f.severity,
            )
            for f in report.stale_claims
        ],
        verified_claims=report.verified_claims,
        unverifiable_claims=report.unverifiable_claims,
        runtime_ms=report.runtime_ms,
    )


def main() -> None:
    """Entry point for `iil-adrfw-mcp`."""
    mcp.run()


if __name__ == "__main__":
    main()
