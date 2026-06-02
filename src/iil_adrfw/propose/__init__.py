"""ADR proposal generation with pre-publish conflict checks.

Architecture: hybrid deterministic-frontmatter + LLM-optional-body.

The tool returns:
1. A complete, schema-valid Frontmatter
2. A structured 'body_prompt' that a consumer LLM can use to generate the body
3. Pre-publish findings: conflicts with existing ADRs, cross-repo conflicts,
   open-questions this would close
4. A clear 'blocks_publish' verdict — same semantics as adr_validate_cross_repo

Design principle: the tool itself makes NO LLM calls. It is deterministic,
testable, and fast. Body generation is delegated to the consumer LLM, which
already has context the tool doesn't.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from typing import Any

from iil_adrfw.domain import (
    ADR,
    Amendment,
    DecisionDriver,
    OpenQuestion,
    PerRepoStatus,
    Status,
    TemporalRange,
)
from iil_adrfw.graph import ConstitutionGraph, _tokenize

# --- Result types ---


@dataclass(frozen=True)
class ProposalConflict:
    """A conflict detected during pre-publish validation of a draft."""

    kind: str  # 'duplicate', 'missed_supersession', 'doc_overlap'
    severity: str  # 'info' | 'warning' | 'error'
    related_adr_ids: tuple[str, ...]
    description: str
    suggestion: str


@dataclass(frozen=True)
class OpenQuestionMatch:
    """An existing open question this proposal might close."""

    adr_id: str
    q_id: str
    question: str
    overlap_score: float  # 0..1 token overlap with proposal title/summary


@dataclass
class ProposalResult:
    """Full output of adr_propose."""

    proposed_id: str  # next available ADR-id
    frontmatter: dict[str, Any]  # complete, schema-validatable
    body_prompt: str  # what a consumer LLM should expand into the body
    conflicts: list[ProposalConflict] = field(default_factory=list)
    closes_open_questions: list[OpenQuestionMatch] = field(default_factory=list)
    cross_repo_blockers: list[dict] = field(default_factory=list)
    blocks_publish: bool = False
    runtime_ms: int = 0


# --- ID allocation ---


_ADR_FILE_RE = re.compile(r"^ADR-(\d{3,4})", re.IGNORECASE)


def _next_adr_id(graph: ConstitutionGraph, requested: str | None = None) -> str:
    """Allocate the next ADR id. If 'requested' is given and free, use it.
    Otherwise return ADR-N where N = max(existing) + 1, padded to at least 3 digits."""
    if requested:
        m = re.match(r"^ADR-(\d{3,4})$", requested)
        if not m:
            raise ValueError(f"Invalid ADR id format: {requested!r}")
        if requested in graph.by_id:
            raise ValueError(f"ADR id already exists: {requested!r}")
        return requested

    nums = []
    for adr_id in graph.by_id:
        m = re.match(r"^ADR-(\d{3,4})$", adr_id)
        if m:
            nums.append(int(m.group(1)))
    next_num = (max(nums) + 1) if nums else 1
    return f"ADR-{next_num:03d}"


# --- Conflict pre-checks ---


def _detect_duplicate_title(
    graph: ConstitutionGraph,
    title: str,
    rationale_summary: str = "",
    threshold: float = 0.7,
    block_threshold: float = 0.85,
) -> list[ProposalConflict]:
    """Heuristic: token overlap between proposed title and any active ADR title.

    - overlap >= block_threshold (default 0.85): severity='error' → blocks_publish
    - overlap >= threshold (default 0.7): severity='warning' → advisory

    Additionally checks rationale_summary overlap if provided.
    """
    findings: list[ProposalConflict] = []
    proposed_tokens = _tokenize(title)
    if not proposed_tokens:
        return findings
    proposed_rationale_tokens = _tokenize(rationale_summary) if rationale_summary else set()

    for adr in graph.adrs:
        if adr.status in (Status.SUPERSEDED, Status.DEPRECATED, Status.REJECTED):
            continue
        existing_tokens = _tokenize(adr.title)
        if not existing_tokens:
            continue
        title_overlap = len(proposed_tokens & existing_tokens) / len(proposed_tokens | existing_tokens)

        # Boost: if rationale also overlaps heavily, increase confidence
        rationale_overlap = 0.0
        if proposed_rationale_tokens and adr.rationale_summary:
            existing_rationale_tokens = _tokenize(adr.rationale_summary)
            if existing_rationale_tokens:
                union = proposed_rationale_tokens | existing_rationale_tokens
                rationale_overlap = (
                    len(proposed_rationale_tokens & existing_rationale_tokens) / len(union) if union else 0.0
                )

        # Combined score: title is primary, rationale is a boost
        combined = title_overlap + (rationale_overlap * 0.3)

        if title_overlap >= block_threshold or (title_overlap >= threshold and combined >= block_threshold):
            findings.append(
                ProposalConflict(
                    kind="duplicate",
                    severity="error",
                    related_adr_ids=(adr.id,),
                    description=(
                        f"DUPLICATE DETECTED: Proposed title overlaps {title_overlap:.0%} with "
                        f"existing {adr.id}: {adr.title!r} (combined score: {combined:.0%})"
                    ),
                    suggestion=(
                        f"This proposal appears to duplicate {adr.id}. Either supersede it "
                        f"(add to 'supersedes') or abandon this proposal."
                    ),
                )
            )
        elif title_overlap >= threshold:
            findings.append(
                ProposalConflict(
                    kind="duplicate",
                    severity="warning",
                    related_adr_ids=(adr.id,),
                    description=(f"Proposed title overlaps {title_overlap:.0%} with existing {adr.id}: {adr.title!r}"),
                    suggestion=(
                        f"If this proposal is meant to supersede {adr.id}, add it to "
                        f"'supersedes'. Otherwise rename to clarify the difference."
                    ),
                )
            )
    return findings


def _detect_domain_overlap_without_supersession(
    graph: ConstitutionGraph,
    proposed_domains: list[str],
    proposed_supersedes: list[str],
    proposed_consolidates: list[str],
) -> list[ProposalConflict]:
    """If proposed domains overlap heavily with an existing active ADR's domains,
    and that ADR is NOT in supersedes/consolidates, that may indicate a missed
    supersession decision."""
    findings: list[ProposalConflict] = []
    if not proposed_domains:
        return findings
    proposed_set = set(proposed_domains)
    handled = {ref.split("§")[0] for ref in proposed_supersedes + proposed_consolidates}

    for adr in graph.adrs:
        if adr.status not in (Status.ACCEPTED, Status.EXPERIMENTAL):
            continue
        if adr.id in handled:
            continue
        existing_set = set(adr.domains)
        if not existing_set:
            continue
        overlap = len(proposed_set & existing_set)
        if overlap >= 2 or (overlap >= 1 and len(proposed_set) == 1):
            shared = sorted(proposed_set & existing_set)
            findings.append(
                ProposalConflict(
                    kind="missed_supersession",
                    severity="info",
                    related_adr_ids=(adr.id,),
                    description=(
                        f"Proposed ADR shares {overlap} domain tag(s) {shared} with active "
                        f"{adr.id} ({adr.title!r}) but doesn't supersede or consolidate it"
                    ),
                    suggestion=(
                        f"Verify intent: should this proposal extend {adr.id}, supersede it, "
                        f"consolidate with it, or live independently? If independent, the "
                        f"overlap is fine — document why in 'depends_on' or 'informs'."
                    ),
                )
            )
    return findings


def _detect_open_question_closure(
    graph: ConstitutionGraph,
    title: str,
    rationale_summary: str,
    threshold: float = 0.3,
) -> list[OpenQuestionMatch]:
    """Find open questions that might be closed by this proposal."""
    matches: list[OpenQuestionMatch] = []
    proposal_tokens = _tokenize(title) | _tokenize(rationale_summary)
    if not proposal_tokens:
        return matches
    for adr, q in graph.all_open_questions():
        q_tokens = _tokenize(q.question)
        if not q_tokens:
            continue
        overlap = len(proposal_tokens & q_tokens) / max(1, len(q_tokens))
        if overlap >= threshold:
            matches.append(
                OpenQuestionMatch(
                    adr_id=adr.id,
                    q_id=q.id,
                    question=q.question,
                    overlap_score=round(overlap, 2),
                )
            )
    matches.sort(key=lambda m: -m.overlap_score)
    return matches


# --- Frontmatter assembly ---


def _build_frontmatter(
    adr_id: str,
    title: str,
    domains: list[str],
    deciders: list[str],
    rationale_summary: str,
    repo: str | None,
    consumers: list[str] | None,
    supersedes: list[str] | None,
    consolidates: list[str] | None,
    depends_on: list[str] | None,
    decision_drivers: list[dict] | None,
    open_questions_to_close: list[OpenQuestionMatch],
) -> dict[str, Any]:
    """Assemble a complete, schema-valid frontmatter dict."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    fm: dict[str, Any] = {
        "id": adr_id,
        "title": title,
        "status": "proposed",
        "decision_date": today,
        "valid_from": f"{today}T00:00:00Z",
        "deciders": list(deciders),
        "domains": list(domains),
        "rationale_summary": rationale_summary,
    }
    if repo:
        fm["repo"] = repo
    if consumers:
        fm["consumers"] = list(consumers)
    if supersedes:
        fm["supersedes"] = list(supersedes)
    if consolidates:
        fm["consolidates"] = list(consolidates)
    if depends_on:
        fm["depends_on"] = list(depends_on)
    if decision_drivers:
        fm["decision_drivers"] = list(decision_drivers)
    if open_questions_to_close:
        # Reference them in the body prompt; the closure happens manually
        # by amending the source ADRs after acceptance.
        fm["informs"] = list({m.adr_id for m in open_questions_to_close})
    fm["implementation_status"] = "none"
    return fm


def _build_body_prompt(
    title: str,
    rationale_summary: str,
    decision_drivers: list[dict] | None,
    related_adrs: list[ADR],
    closes: list[OpenQuestionMatch],
    cross_repo_evidence: list[dict],
) -> str:
    """A structured prompt for a consumer LLM to expand into the markdown body.

    The prompt is content-addressable (deterministic given inputs) and short
    enough to fit in any context window.
    """
    lines = [
        f"# Body prompt for {title}",
        "",
        "Generate a markdown body for this ADR with the following sections, in this order:",
        "",
        "## Required sections",
        "- **Context**: 2-4 paragraphs. State the situation that necessitates this decision. "
        "Reference concrete events, code, or repo state where possible.",
        "- **Decision**: One paragraph stating the decision. Use active voice ('We adopt X', "
        "not 'X should be considered').",
        "- **Consequences**: Bulleted positive consequences and bulleted negative consequences. "
        "Each item one short sentence.",
        "- **Alternatives considered**: 2-4 alternatives with one-line reasons for rejection.",
        "",
    ]
    if rationale_summary:
        lines += ["## Rationale (use as starting point)", rationale_summary, ""]
    if decision_drivers:
        lines.append("## Decision drivers (reflect these in the Decision section)")
        for d in decision_drivers:
            lines.append(f"- [{d.get('id', '?')}] ({d.get('weight', '?')}) {d.get('driver', '')}")
        lines.append("")
    if related_adrs:
        lines.append("## Related existing ADRs (reference where appropriate)")
        for a in related_adrs:
            lines.append(f"- {a.id}: {a.title} (status: {a.status.value})")
        lines.append("")
    if closes:
        lines.append("## Open questions this proposal addresses")
        for m in closes:
            lines.append(f"- {m.adr_id}/{m.q_id}: {m.question}")
        lines.append("Reference the resolution explicitly so consumers can update those ADRs after acceptance.")
        lines.append("")
    if cross_repo_evidence:
        lines.append("## Cross-repo reality (verified against consumer-repos)")
        lines.append("These observations were confirmed before this draft was created:")
        for e in cross_repo_evidence:
            lines.append(f"- {e.get('summary', '')}")
        lines.append("")
    lines += [
        "## Style",
        "- German or English (match rationale_summary).",
        "- No marketing language. State trade-offs honestly.",
        "- Max 800 words total.",
    ]
    return "\n".join(lines)


# --- Top-level ---


@dataclass
class ProposalRequest:
    """Inputs to adr_propose."""

    title: str
    domains: list[str]
    deciders: list[str]
    rationale_summary: str
    repo: str | None = None
    consumers: list[str] | None = None
    supersedes: list[str] | None = None
    consolidates: list[str] | None = None
    depends_on: list[str] | None = None
    decision_drivers: list[dict] | None = None
    requested_id: str | None = None
    # If set, run cross-repo pre-check using these consumer-repo paths
    cross_repo_paths: dict[str, str] | None = None


def propose_adr(
    graph: ConstitutionGraph,
    req: ProposalRequest,
) -> ProposalResult:
    """Generate a proposal with all pre-publish checks. No LLM call — body
    generation is delegated to the consumer."""
    import time
    from pathlib import Path

    from iil_adrfw.cross_repo import ConsumerRepoLayout, validate_cross_repo

    start = time.monotonic()

    proposed_id = _next_adr_id(graph, req.requested_id)

    # Pre-checks
    duplicate_findings = _detect_duplicate_title(graph, req.title, req.rationale_summary)
    overlap_findings = _detect_domain_overlap_without_supersession(
        graph,
        req.domains,
        req.supersedes or [],
        req.consolidates or [],
    )
    closes = _detect_open_question_closure(
        graph,
        req.title,
        req.rationale_summary,
    )

    conflicts = duplicate_findings + overlap_findings

    # Build the frontmatter
    fm = _build_frontmatter(
        adr_id=proposed_id,
        title=req.title,
        domains=req.domains,
        deciders=req.deciders,
        rationale_summary=req.rationale_summary,
        repo=req.repo,
        consumers=req.consumers,
        supersedes=req.supersedes,
        consolidates=req.consolidates,
        depends_on=req.depends_on,
        decision_drivers=req.decision_drivers,
        open_questions_to_close=closes,
    )

    # Cross-repo pre-check (if paths provided)
    cross_repo_evidence: list[dict] = []
    cross_repo_blockers: list[dict] = []
    if req.cross_repo_paths and req.consumers:
        # Construct an ephemeral ADR for the cross-repo validator
        draft = ADR(
            id=proposed_id,
            title=req.title,
            status=Status.PROPOSED,
            domains=tuple(req.domains),
            deciders=tuple(req.deciders),
            decision_date=datetime.now(UTC),
            temporal=TemporalRange(valid_from=datetime.now(UTC)),
            rationale_summary=req.rationale_summary,
            repo=req.repo,
            consumers=tuple(req.consumers),
            supersedes=tuple(req.supersedes or []),
            consolidates=tuple(req.consolidates or []),
            depends_on=tuple(req.depends_on or []),
            raw_frontmatter=fm,
        )
        layouts = [ConsumerRepoLayout(name=name, root=Path(root)) for name, root in req.cross_repo_paths.items()]
        report = validate_cross_repo(draft, layouts)
        for c in report.conflicts:
            entry = {
                "conflict_class": c.conflict_class.value,
                "confidence": c.confidence.value,
                "claim": c.claim,
                "reality": c.reality,
                "affected_repos": list(c.affected_repos),
                "blocks_publish": c.blocks_publish,
                "summary": f"{c.claim} — {c.reality}",
            }
            if c.blocks_publish:
                cross_repo_blockers.append(entry)
            else:
                cross_repo_evidence.append(entry)

    # Find related ADRs (concept overlap with title) for the body prompt
    related_concept_hits = graph.adrs_matching_concepts(_tokenize(req.title))
    related_adrs = [a for a, _ in related_concept_hits[:5]]

    body_prompt = _build_body_prompt(
        title=req.title,
        rationale_summary=req.rationale_summary,
        decision_drivers=req.decision_drivers,
        related_adrs=related_adrs,
        closes=closes,
        cross_repo_evidence=cross_repo_evidence,
    )

    blocks_publish = bool(cross_repo_blockers) or any(c.severity == "error" for c in conflicts)

    runtime_ms = int((time.monotonic() - start) * 1000)
    return ProposalResult(
        proposed_id=proposed_id,
        frontmatter=fm,
        body_prompt=body_prompt,
        conflicts=conflicts,
        closes_open_questions=closes,
        cross_repo_blockers=cross_repo_blockers,
        blocks_publish=blocks_publish,
        runtime_ms=runtime_ms,
    )
