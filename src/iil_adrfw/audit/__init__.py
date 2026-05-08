"""ADR-set self-audit. Each auditor is a small function; results are aggregated
into a single AuditReport with a HealthSnapshot.

Auditors:
- supersession_hygiene: dangling supersedes/superseded_by, missing roundtrips
- dependency_health:    depends_on referencing missing/superseded ADRs
- staleness:            ADRs past their staleness_months
- coverage:             consumers not covered by any ADR
- open_question_aging:  questions whose decide_by deadline has passed
- conflict:             pairs of accepted ADRs whose rationale touches the same domain in opposing ways
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Iterable

from iil_adrfw.domain import ADR, Status
from iil_adrfw.graph import ConstitutionGraph


class FindingSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class AuditFinding:
    auditor: str
    severity: FindingSeverity
    affected_adrs: tuple[str, ...]
    description: str
    proposed_resolution: str | None = None
    evidence: tuple[str, ...] = ()


@dataclass
class HealthSnapshot:
    score: float
    internal_consistency: float
    code_alignment: float           # placeholder — needs adr_check integration
    coverage: float
    freshness: float
    supersession_hygiene: float
    issue_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class AuditReport:
    auditors_run: tuple[str, ...]
    findings: list[AuditFinding] = field(default_factory=list)
    health: HealthSnapshot | None = None
    runtime_ms: int = 0


# --- Helpers ---


_ADR_REF_RE = re.compile(r"^(ADR-[0-9]{3,4})(?:§([A-Za-z0-9_.-]+))?$")


def _parse_ref(ref: str) -> tuple[str, str | None]:
    m = _ADR_REF_RE.match(ref)
    if m:
        return (m.group(1), m.group(2))
    return (ref, None)


# --- Individual auditors ---


def audit_supersession_hygiene(graph: ConstitutionGraph) -> list[AuditFinding]:
    """Verify that:
    - every 'supersedes A' has a matching 'superseded_by B' on A
    - every 'superseded_by B' has a matching 'supersedes A' on B
    - dangling refs (target ADR doesn't exist) are flagged
    """
    findings: list[AuditFinding] = []

    for adr in graph.adrs:
        for ref in adr.supersedes:
            target_id, _ = _parse_ref(ref)
            # Bug #5 from adr-doctor review: self-reference is not a true
            # supersession (often a revision marker, e.g. 'supersedes: ADR-167 v1.0')
            if target_id == adr.id:
                findings.append(AuditFinding(
                    auditor="supersession_hygiene",
                    severity=FindingSeverity.WARNING,
                    affected_adrs=(adr.id,),
                    description=(
                        f"{adr.id} declares 'supersedes: {adr.id}' — self-reference "
                        f"(likely a revision note, not a true supersession)"
                    ),
                    proposed_resolution=(
                        f"Remove the self-reference from supersedes; if you meant to "
                        f"track a revision, use the 'amended' field instead"
                    ),
                ))
                continue
            target = graph.by_id.get(target_id)
            if target is None:
                # Cross-repo ADRs may legitimately not be in this graph;
                # we report as WARNING (not ERROR) since absence may be benign.
                findings.append(AuditFinding(
                    auditor="supersession_hygiene",
                    severity=FindingSeverity.WARNING,
                    affected_adrs=(adr.id,),
                    description=f"{adr.id} supersedes {ref} but {target_id} does not exist in the constitution",
                    proposed_resolution=f"Either remove the reference, fix the typo, or add {target_id} to the ADR set",
                ))
                continue
            target_back_refs = {_parse_ref(r)[0] for r in target.superseded_by}
            if adr.id not in target_back_refs:
                findings.append(AuditFinding(
                    auditor="supersession_hygiene",
                    severity=FindingSeverity.ERROR,
                    affected_adrs=(adr.id, target_id),
                    description=(
                        f"{adr.id} supersedes {target_id}, but {target_id}.superseded_by "
                        f"is missing the back-reference"
                    ),
                    proposed_resolution=f"Add '{adr.id}' to {target_id}.superseded_by",
                ))
            # Also: if A is superseded, its status should reflect that
            if adr.status.is_active() and target.status not in (Status.SUPERSEDED, Status.DEPRECATED):
                findings.append(AuditFinding(
                    auditor="supersession_hygiene",
                    severity=FindingSeverity.WARNING,
                    affected_adrs=(target_id,),
                    description=(
                        f"{target_id} is superseded by {adr.id} (active) but {target_id}.status "
                        f"is still '{target.status.value}'"
                    ),
                    proposed_resolution=f"Set {target_id}.status to 'superseded'",
                ))

        for ref in adr.superseded_by:
            target_id, _ = _parse_ref(ref)
            target = graph.by_id.get(target_id)
            if target is None:
                findings.append(AuditFinding(
                    auditor="supersession_hygiene",
                    severity=FindingSeverity.ERROR,
                    affected_adrs=(adr.id,),
                    description=f"{adr.id} declares it is superseded by {ref}, but {target_id} doesn't exist",
                ))

    return findings


def audit_dependency_health(graph: ConstitutionGraph) -> list[AuditFinding]:
    """Find dangling depends_on / consolidates / conflicts_with refs."""
    findings: list[AuditFinding] = []
    relations = ("depends_on", "consolidates", "conflicts_with")
    for adr in graph.adrs:
        if not adr.status.is_active():
            continue
        for relation in relations:
            refs = getattr(adr, relation, ())
            for ref in refs:
                target_id, section = _parse_ref(ref)
                target = graph.by_id.get(target_id)
                if target is None:
                    findings.append(AuditFinding(
                        auditor="dependency_health",
                        severity=FindingSeverity.ERROR,
                        affected_adrs=(adr.id,),
                        description=(
                            f"{adr.id}.{relation} references {ref}, but {target_id} "
                            f"is not in the constitution"
                        ),
                        proposed_resolution=f"Remove or fix the {relation} reference to {ref}",
                    ))
                elif relation == "depends_on" and target.status in (Status.DEPRECATED, Status.REJECTED):
                    findings.append(AuditFinding(
                        auditor="dependency_health",
                        severity=FindingSeverity.WARNING,
                        affected_adrs=(adr.id, target_id),
                        description=(
                            f"{adr.id} depends on {target_id}, but {target_id} is "
                            f"'{target.status.value}'"
                        ),
                        proposed_resolution=(
                            f"Either revise {adr.id} to depend on a current ADR, or accept "
                            f"the lifecycle mismatch consciously"
                        ),
                    ))
    return findings


def audit_staleness(
    graph: ConstitutionGraph,
    now: datetime | None = None,
) -> list[AuditFinding]:
    """ADRs whose last_reviewed + staleness_months has passed are stale."""
    findings: list[AuditFinding] = []
    now = now or datetime.now(timezone.utc)
    for adr in graph.adrs:
        # Check proposed and active ADRs — drafts can rot too
        if adr.status in (Status.SUPERSEDED, Status.DEPRECATED, Status.REJECTED):
            continue
        if not adr.staleness_months:
            continue
        last_reviewed_str = adr.raw_frontmatter.get("last_reviewed")
        if not last_reviewed_str:
            findings.append(AuditFinding(
                auditor="staleness",
                severity=FindingSeverity.INFO,
                affected_adrs=(adr.id,),
                description=f"{adr.id} has staleness_months={adr.staleness_months} but no last_reviewed date",
                proposed_resolution="Set last_reviewed to current date if reviewed today",
            ))
            continue
        try:
            last_reviewed = datetime.fromisoformat(str(last_reviewed_str)).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        # Approximate: 30 days per month
        threshold = last_reviewed + timedelta(days=30 * adr.staleness_months)
        if now > threshold:
            days_overdue = (now - threshold).days
            findings.append(AuditFinding(
                auditor="staleness",
                severity=FindingSeverity.WARNING,
                affected_adrs=(adr.id,),
                description=(
                    f"{adr.id} last reviewed {last_reviewed.date()} "
                    f"({days_overdue} days overdue against staleness_months={adr.staleness_months})"
                ),
                proposed_resolution=f"Schedule a review of {adr.id} within the next sprint",
            ))
    return findings


def audit_coverage(graph: ConstitutionGraph) -> list[AuditFinding]:
    """Consumer-repos referenced by any ADR but with no per_repo_status entry
    are gaps in the coverage."""
    findings: list[AuditFinding] = []
    for adr in graph.adrs:
        if not adr.consumers:
            continue
        per_repo_repos = {prs.repo for prs in adr.per_repo_status}
        missing = [c for c in adr.consumers if c not in per_repo_repos]
        if missing:
            findings.append(AuditFinding(
                auditor="coverage",
                severity=FindingSeverity.INFO,
                affected_adrs=(adr.id,),
                description=(
                    f"{adr.id} lists {len(adr.consumers)} consumer-repos but "
                    f"{len(missing)} have no per_repo_status: {', '.join(missing)}"
                ),
                proposed_resolution="Add per_repo_status entries for all consumers — even 'none' is informative",
            ))
    return findings


def audit_open_question_aging(
    graph: ConstitutionGraph,
    now: datetime | None = None,
) -> list[AuditFinding]:
    """Open questions whose decide_by is a date and has passed."""
    findings: list[AuditFinding] = []
    now = now or datetime.now(timezone.utc)
    for adr, q in graph.all_open_questions():
        if not q.decide_by:
            continue
        # decide_by may be 'Phase 1' or 'YYYY-MM-DD' — only date-form is auditable here
        try:
            deadline = datetime.fromisoformat(q.decide_by).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if now > deadline:
            findings.append(AuditFinding(
                auditor="open_question_aging",
                severity=FindingSeverity.WARNING,
                affected_adrs=(adr.id,),
                description=(
                    f"{adr.id}/{q.id} ('{q.question[:80]}') decide-by {deadline.date()} "
                    f"is overdue"
                ),
                proposed_resolution=(
                    f"Either resolve the question (set status='resolved') or extend decide_by"
                ),
            ))
    return findings


# Conflict-detection is deliberately limited in this skeleton — full semantic
# conflict detection needs an LLM and richer code-base context (Class 2/3 in
# cross-repo terms). Here we ship a deterministic check: do two active ADRs
# both list the SAME domain AND consolidate/supersede the SAME third ADR
# without one consolidating the other?
def audit_conflict_pairs(graph: ConstitutionGraph) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    active = [a for a in graph.adrs if a.status.is_active()]

    for i, a in enumerate(active):
        for b in active[i + 1:]:
            shared_domains = set(a.domains) & set(b.domains)
            shared_supersedes = (
                {_parse_ref(r)[0] for r in a.supersedes}
                & {_parse_ref(r)[0] for r in b.supersedes}
            )
            shared_consolidates = (
                {_parse_ref(r)[0] for r in a.consolidates}
                & {_parse_ref(r)[0] for r in b.consolidates}
            )
            shared = shared_supersedes | shared_consolidates
            if shared and shared_domains:
                # Either A consolidates B, B consolidates A, or they conflict
                a_cs = {_parse_ref(r)[0] for r in a.consolidates}
                b_cs = {_parse_ref(r)[0] for r in b.consolidates}
                if b.id in a_cs or a.id in b_cs:
                    continue
                findings.append(AuditFinding(
                    auditor="conflict",
                    severity=FindingSeverity.ERROR,
                    affected_adrs=(a.id, b.id),
                    description=(
                        f"{a.id} and {b.id} both supersede/consolidate {sorted(shared)} "
                        f"and share domains {sorted(shared_domains)}, with no consolidation between them"
                    ),
                    proposed_resolution=(
                        f"Consolidate {a.id} and {b.id} into one, or clarify which one "
                        f"is the authoritative supersession"
                    ),
                ))
    return findings


# --- Health snapshot ---


def compute_health(graph: ConstitutionGraph, findings: list[AuditFinding]) -> HealthSnapshot:
    """Compute a quantified HealthSnapshot from findings + ADR set state."""
    counts: dict[str, int] = {"info": 0, "warning": 0, "error": 0, "critical": 0}
    by_auditor: dict[str, list[AuditFinding]] = {}
    for f in findings:
        counts[f.severity.value] += 1
        by_auditor.setdefault(f.auditor, []).append(f)

    n_active = max(1, sum(1 for a in graph.adrs if a.status.is_active()))

    def normalize(auditor: str, weight_per_finding: float = 0.1) -> float:
        n = len(by_auditor.get(auditor, []))
        return max(0.0, 1.0 - n * weight_per_finding)

    internal_consistency = min(
        normalize("conflict", 0.2),
        normalize("dependency_health", 0.15),
    )
    supersession_hygiene = normalize("supersession_hygiene", 0.15)
    freshness = normalize("staleness", 0.05) * normalize("open_question_aging", 0.05)
    # Coverage: 1 - (info findings from coverage) / (active consumers)
    coverage_findings = by_auditor.get("coverage", [])
    consumers_total = sum(len(a.consumers) for a in graph.adrs if a.status.is_active())
    if consumers_total == 0:
        coverage = 1.0
    else:
        gap = sum(
            int(re.search(r"(\d+) have no", f.description).group(1))
            if re.search(r"(\d+) have no", f.description) else 0
            for f in coverage_findings
        )
        coverage = max(0.0, 1.0 - gap / consumers_total)

    code_alignment = 1.0  # placeholder until adr_check integration

    score = (
        internal_consistency * 0.30
        + code_alignment * 0.20
        + coverage * 0.15
        + freshness * 0.15
        + supersession_hygiene * 0.20
    )

    return HealthSnapshot(
        score=round(score, 3),
        internal_consistency=round(internal_consistency, 3),
        code_alignment=round(code_alignment, 3),
        coverage=round(coverage, 3),
        freshness=round(freshness, 3),
        supersession_hygiene=round(supersession_hygiene, 3),
        issue_counts=counts,
    )


# --- Top-level run ---


_AUDITORS = {
    "supersession_hygiene": audit_supersession_hygiene,
    "dependency_health": audit_dependency_health,
    "staleness": audit_staleness,
    "coverage": audit_coverage,
    "open_question_aging": audit_open_question_aging,
    "conflict": audit_conflict_pairs,
}


def run_audit(
    graph: ConstitutionGraph,
    auditors: Iterable[str] | None = None,
    now: datetime | None = None,
) -> AuditReport:
    """Run selected auditors (or all). Returns aggregated AuditReport with HealthSnapshot."""
    import time
    start = time.monotonic()
    chosen = list(auditors) if auditors else list(_AUDITORS.keys())
    findings: list[AuditFinding] = []
    for name in chosen:
        fn = _AUDITORS.get(name)
        if fn is None:
            continue
        if name in ("staleness", "open_question_aging"):
            findings.extend(fn(graph, now=now))
        else:
            findings.extend(fn(graph))
    health = compute_health(graph, findings)
    runtime_ms = int((time.monotonic() - start) * 1000)
    return AuditReport(
        auditors_run=tuple(chosen),
        findings=findings,
        health=health,
        runtime_ms=runtime_ms,
    )
