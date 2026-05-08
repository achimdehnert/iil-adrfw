"""Audience-tailored narratives over a constitution subset.

adr_narrate composes a coherent textual summary of a set of ADRs, adapted to
one of four audiences (new_dev, senior, architect, auditor).

Design principle (same as adr_explain and adr_propose): the tool itself
makes NO LLM calls. It produces structured, deterministic prose; consumers
can refine with their own LLM if needed.

Selection modes:
  - domain     : all ADRs that carry a given domain tag
  - id_set     : explicit list of ADR ids
  - path_filter: all ADRs whose scope.include_paths or drift_check_paths
                 match the given path glob
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable

from iil_adrfw.domain import ADR, Status


class Audience(str, Enum):
    NEW_DEV = "new_dev"
    SENIOR = "senior"
    ARCHITECT = "architect"
    AUDITOR = "auditor"


@dataclass(frozen=True)
class NarrativeSection:
    heading: str
    body: str


@dataclass
class Narrative:
    audience: Audience
    title: str
    intro: str
    sections: list[NarrativeSection] = field(default_factory=list)
    adr_ids_covered: tuple[str, ...] = ()
    runtime_ms: int = 0

    def render_markdown(self) -> str:
        """Render as a single Markdown document."""
        out: list[str] = [f"# {self.title}", "", self.intro, ""]
        for s in self.sections:
            out.append(f"## {s.heading}")
            out.append("")
            out.append(s.body)
            out.append("")
        return "\n".join(out)


# ─── Audience-specific framing ──────────────────────────────────


def _intro_for(audience: Audience, n_adrs: int, scope_label: str) -> str:
    if audience == Audience.NEW_DEV:
        return (
            f"This narrative walks through {n_adrs} architectural decisions for "
            f"{scope_label}. It's intended as onboarding material — read it linearly "
            f"to understand how the architecture got here. Where decisions reference "
            f"other ADRs, follow the links to fill in detail."
        )
    if audience == Audience.SENIOR:
        return (
            f"Technical retrospective covering {n_adrs} decisions for {scope_label}. "
            f"Focus is on tradeoffs, supersession patterns, and lessons learned. "
            f"Drivers and rejected alternatives are surfaced where they exist."
        )
    if audience == Audience.ARCHITECT:
        return (
            f"Strategic overview of {n_adrs} decisions for {scope_label}. "
            f"Highlights consolidation moves, open questions still in flight, "
            f"and dependency clusters. Status lifecycle and per-repo rollout state "
            f"are tracked where applicable."
        )
    if audience == Audience.AUDITOR:
        return (
            f"Compliance trail for {n_adrs} decisions on {scope_label}. "
            f"Each entry shows status, deciders, decision date, regulatory drivers, "
            f"and supersession history. Open compliance questions are flagged."
        )
    return ""


def _adr_one_liner(adr: ADR, audience: Audience) -> str:
    """A single-line summary tailored to audience."""
    if audience == Audience.NEW_DEV:
        return f"**{adr.id}** ({adr.status.value}) — {adr.title}"
    if audience == Audience.SENIOR:
        impl = f", impl: {adr.implementation_status}" if adr.implementation_status != "none" else ""
        return f"**{adr.id}** ({adr.status.value}{impl}) — {adr.title}"
    if audience == Audience.ARCHITECT:
        repo = f" [{adr.repo}]" if adr.repo else ""
        n_consumers = len(adr.consumers)
        consumers_part = f", {n_consumers} consumer-repo(s)" if n_consumers else ""
        return f"**{adr.id}**{repo} ({adr.status.value}{consumers_part}) — {adr.title}"
    if audience == Audience.AUDITOR:
        deciders = ", ".join(adr.deciders[:2])
        more = f" +{len(adr.deciders)-2}" if len(adr.deciders) > 2 else ""
        date = adr.decision_date.date().isoformat() if adr.decision_date else "?"
        return f"**{adr.id}** ({adr.status.value}, {date}, deciders: {deciders}{more}) — {adr.title}"
    return f"**{adr.id}** — {adr.title}"


def _tradeoff_summary(adr: ADR) -> str:
    """Extract trade-offs / drivers / open questions for senior+architect+auditor narratives."""
    parts: list[str] = []
    if adr.decision_drivers:
        critical = [d for d in adr.decision_drivers if d.weight == "critical"]
        if critical:
            parts.append(
                "**Critical drivers:** "
                + "; ".join(f"{d.id} {d.driver}" for d in critical[:3])
            )
    if adr.open_questions:
        open_qs = [q for q in adr.open_questions if q.status == "open"]
        if open_qs:
            parts.append(f"**{len(open_qs)} open question(s)** — see ADR for details.")
    if adr.supersedes:
        parts.append(f"**Supersedes:** {', '.join(adr.supersedes[:3])}")
    if adr.consolidates:
        parts.append(f"**Consolidates:** {', '.join(adr.consolidates[:3])}")
    return "  \n  ".join(parts) if parts else ""


# ─── Section builders by audience ───────────────────────────────


def _section_overview(adrs: list[ADR], audience: Audience) -> NarrativeSection:
    statuses: dict[str, int] = {}
    for a in adrs:
        statuses[a.status.value] = statuses.get(a.status.value, 0) + 1
    status_line = ", ".join(f"{k}: {v}" for k, v in sorted(statuses.items()))
    body = (
        f"This set contains {len(adrs)} ADR(s). "
        f"Status distribution: {status_line}.\n\n"
    )
    if audience == Audience.AUDITOR:
        with_critical_drivers = sum(
            1 for a in adrs
            if any(d.weight == "critical" for d in a.decision_drivers)
        )
        if with_critical_drivers:
            body += f"{with_critical_drivers} ADR(s) carry at least one CRITICAL decision driver. "
        with_open_questions = sum(
            1 for a in adrs
            if any(q.status == "open" for q in a.open_questions)
        )
        if with_open_questions:
            body += f"{with_open_questions} ADR(s) have open questions tracked. "
    return NarrativeSection(heading="Overview", body=body)


def _section_decisions(adrs: list[ADR], audience: Audience) -> NarrativeSection:
    # Order: by decision_date ascending so it reads as a story
    ordered = sorted(adrs, key=lambda a: a.decision_date)
    lines: list[str] = []
    for a in ordered:
        line = _adr_one_liner(a, audience)
        lines.append(f"- {line}")
        if audience in (Audience.SENIOR, Audience.ARCHITECT, Audience.AUDITOR):
            tradeoff = _tradeoff_summary(a)
            if tradeoff:
                lines.append(f"  {tradeoff}")
        if audience == Audience.NEW_DEV and a.rationale_summary:
            # Trim long rationales
            rat = a.rationale_summary.strip().split("\n")[0]
            lines.append(f"  *{rat[:160]}*")
    return NarrativeSection(heading="Decisions in order", body="\n".join(lines))


def _section_supersessions(adrs: list[ADR], audience: Audience) -> NarrativeSection:
    """Always emitted. If no supersessions in scope, body is '(none)'."""
    chains: list[str] = []
    for a in adrs:
        if a.supersedes:
            for ref in a.supersedes:
                chains.append(f"- {ref} → **{a.id}** ({a.title[:80]})")
        if a.superseded_by:
            for ref in a.superseded_by:
                chains.append(f"- **{a.id}** → {ref} (superseded)")
    body = "Supersession chains in this scope:\n\n" + "\n".join(chains) if chains else "(none)"
    return NarrativeSection(heading="Supersession chains", body=body)


def _section_open_questions(adrs: list[ADR], audience: Audience) -> NarrativeSection:
    """Always emitted. If no open questions, body is '(none)'."""
    items: list[str] = []
    for a in adrs:
        for q in a.open_questions:
            if q.status == "open":
                owner = f" (owner: {q.owner})" if q.owner else ""
                deadline = f" — decide by: {q.decide_by}" if q.decide_by else ""
                items.append(f"- **{a.id}/{q.id}**: {q.question}{owner}{deadline}")
    body = "These questions remain unanswered:\n\n" + "\n".join(items) if items else "(none)"
    return NarrativeSection(heading="Open questions", body=body)


def _section_compliance_trail(adrs: list[ADR]) -> NarrativeSection:
    """Auditor section. Always emitted. If no ADRs, body is '(none)'."""
    items: list[str] = []
    for a in sorted(adrs, key=lambda a: a.decision_date):
        date = a.decision_date.date().isoformat() if a.decision_date else "?"
        deciders = ", ".join(a.deciders) if a.deciders else "(no deciders recorded)"
        regulatory = [d for d in a.decision_drivers if d.category == "regulatory"]
        regulatory_part = ""
        if regulatory:
            regulatory_part = f"  \n  *Regulatory drivers:* " + "; ".join(d.driver for d in regulatory)
        items.append(
            f"- **{a.id}** ({a.status.value})\n"
            f"  Decision date: {date}\n"
            f"  Deciders: {deciders}"
            + regulatory_part
        )
    body = "\n".join(items) if items else "(none)"
    return NarrativeSection(
        heading="Compliance trail",
        body=body,
    )


# ─── Top-level entry point ──────────────────────────────────────


def compose_narrative(
    adrs: list[ADR],
    audience: Audience,
    scope_label: str = "the constitution",
) -> Narrative:
    """Build a narrative for the given ADRs and audience.

    Always emits the same five sections in the same order, regardless of
    audience or content. Empty sections show '(none)'. This makes the output
    structure predictable for downstream consumers.

    Sections (always present):
      1. Overview
      2. Decisions in order
      3. Supersession chains
      4. Open questions
      5. Compliance trail
    """
    import time
    start = time.monotonic()

    title_map = {
        Audience.NEW_DEV: f"Architecture onboarding — {scope_label}",
        Audience.SENIOR: f"Technical retrospective — {scope_label}",
        Audience.ARCHITECT: f"Strategic overview — {scope_label}",
        Audience.AUDITOR: f"Compliance trail — {scope_label}",
    }
    intro = _intro_for(audience, len(adrs), scope_label)
    narrative = Narrative(
        audience=audience,
        title=title_map.get(audience, f"Narrative — {scope_label}"),
        intro=intro,
        adr_ids_covered=tuple(a.id for a in adrs),
    )

    # Five sections, always present, fixed order.
    narrative.sections.append(_section_overview(adrs, audience))
    narrative.sections.append(_section_decisions(adrs, audience))
    narrative.sections.append(_section_supersessions(adrs, audience))
    narrative.sections.append(_section_open_questions(adrs, audience))
    narrative.sections.append(_section_compliance_trail(adrs))

    narrative.runtime_ms = int((time.monotonic() - start) * 1000)
    return narrative


# ─── Selection helpers ──────────────────────────────────────────


def select_adrs(
    adrs: list[ADR],
    domain: str | None = None,
    id_set: list[str] | None = None,
    path_filter: str | None = None,
) -> list[ADR]:
    """Pick a subset of the constitution to narrate over.
    At least one selector must be provided. Selectors AND-combine."""
    from fnmatch import fnmatch

    if not (domain or id_set or path_filter):
        raise ValueError("At least one of domain/id_set/path_filter must be provided")

    out = list(adrs)
    if domain:
        out = [a for a in out if domain in a.domains]
    if id_set:
        id_lookup = set(id_set)
        out = [a for a in out if a.id in id_lookup]
    if path_filter:
        def matches(a: ADR) -> bool:
            scope_globs = a.raw_frontmatter.get("scope", {}).get("include_paths") or []
            drift_globs = list(a.drift_check_paths)
            for g in scope_globs + drift_globs:
                if fnmatch(path_filter, g):
                    return True
            return False
        out = [a for a in out if matches(a)]
    return out
