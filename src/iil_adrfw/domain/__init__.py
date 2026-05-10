"""Pure domain types — no I/O, no MCP, no Django.

These are the types that flow through the rest of the system.
Persistence (markdown/yaml loading) is in iil_adrfw.persistence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

    def blocks_merge(self) -> bool:
        return self in (Severity.ERROR, Severity.CRITICAL)


class Status(str, Enum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    EXPERIMENTAL = "experimental"
    VOID = "void"  # Schema v4: misclassified ADR slot — content moved to correct doc type

    def is_active(self) -> bool:
        return self in (Status.ACCEPTED, Status.EXPERIMENTAL)

    def is_pre_decision(self) -> bool:
        return self in (Status.DRAFT, Status.PROPOSED)


@dataclass(frozen=True)
class TemporalRange:
    """Bi-temporal validity. Two axes: when it applied in the world, when we knew."""

    valid_from: datetime
    valid_to: datetime | None = None
    knowledge_from: datetime | None = None
    retroactive: bool = False

    def applies_at(self, world_time: datetime, known_at: datetime | None = None) -> bool:
        """Check whether the rule applies at a given world time, given what we knew at known_at."""
        if world_time < self.valid_from and not self.retroactive:
            return False
        if self.valid_to is not None and world_time > self.valid_to:
            return False
        # Knowledge-time check: if we didn't know yet at known_at, don't enforce
        if known_at is not None and self.knowledge_from is not None:
            if known_at < self.knowledge_from:
                return False
        return True


@dataclass(frozen=True)
class Scope:
    include_paths: tuple[str, ...] = ()
    exclude_paths: tuple[str, ...] = ()
    file_types: tuple[str, ...] = ()

    def matches(self, path: Path) -> bool:
        from fnmatch import fnmatch

        path_str = str(path)
        if self.file_types:
            if path.suffix not in self.file_types:
                return False
        if self.include_paths:
            if not any(fnmatch(path_str, pat) for pat in self.include_paths):
                return False
        if self.exclude_paths:
            if any(fnmatch(path_str, pat) for pat in self.exclude_paths):
                return False
        return True


@dataclass
class Rule:
    """A single executable rule extracted from a .rules.yaml file."""

    adr_id: str
    rule_id: str  # short slug, like 'tenant-id-bigint'
    title: str
    severity: Severity
    rationale: str
    temporal: TemporalRange
    scope: Scope
    checker_spec: dict[str, Any]  # raw spec; concrete checkers built lazily
    fix_suggestions: list[dict[str, Any]] = field(default_factory=list)
    audience_explanations: dict[str, str] = field(default_factory=dict)
    blast_radius: str | None = None
    examples: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @property
    def global_id(self) -> str:
        return f"{self.adr_id}/{self.rule_id}"


@dataclass(frozen=True)
class Amendment:
    version: str
    at: datetime
    by: str
    summary: str
    sections_changed: tuple[str, ...] = ()
    rationale: str = ""


@dataclass(frozen=True)
class DecisionDriver:
    id: str  # "D-1"
    driver: str
    weight: str  # critical|high|medium|low
    category: str | None = None


@dataclass(frozen=True)
class OpenQuestion:
    id: str  # "Q-1"
    question: str
    decide_by: str | None = None
    owner: str | None = None
    status: str = "open"
    resolution: str | None = None


@dataclass(frozen=True)
class DeprecationStep:
    phase: str  # "D-1"
    action: str
    state: str
    earliest: str | None = None
    completion_signal: str = ""


@dataclass(frozen=True)
class SPOFMitigation:
    component: str
    measure: str
    implementation: str = ""
    phase: str | None = None


@dataclass(frozen=True)
class PerRepoStatus:
    repo: str
    status: Status | None = None
    implementation_status: str = "none"
    planned_phase: str | None = None
    target_date: datetime | None = None
    actual_completion_date: datetime | None = None
    notes: str = ""


@dataclass
class ADR:
    """Single ADR with its frontmatter and (optionally) executable rules."""

    id: str
    title: str
    status: Status
    domains: tuple[str, ...]
    deciders: tuple[str, ...]
    decision_date: datetime
    temporal: TemporalRange
    rationale_summary: str = ""
    supersedes: tuple[str, ...] = ()
    superseded_by: tuple[str, ...] = ()
    consolidates: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    conflicts_with: tuple[str, ...] = ()
    rules: list[Rule] = field(default_factory=list)
    raw_frontmatter: dict[str, Any] = field(default_factory=dict)
    body_markdown: str = ""
    # v1.1 fields
    amendments: tuple[Amendment, ...] = ()
    decision_drivers: tuple[DecisionDriver, ...] = ()
    open_questions: tuple[OpenQuestion, ...] = ()
    deprecation_timeline: tuple[DeprecationStep, ...] = ()
    spof_mitigation: tuple[SPOFMitigation, ...] = ()
    per_repo_status: tuple[PerRepoStatus, ...] = ()
    repo: str | None = None
    consumers: tuple[str, ...] = ()
    implementation_status: str = "none"
    staleness_months: int | None = None
    drift_check_paths: tuple[str, ...] = ()
    # Schema v3 fields (added 2026-05-08, all optional)
    updated: datetime | None = None
    version: int | None = None
    review_status: str | None = None
    owner: str | None = None
    implementation_done_when: str | None = None

    def applicable_rules(self, world_time: datetime | None = None) -> list[Rule]:
        if not self.status.is_active():
            return []
        wt = world_time or datetime.now(timezone.utc)
        return [r for r in self.rules if r.temporal.applies_at(wt)]

    def status_in_repo(self, repo: str) -> tuple[Status, str]:
        """Return (status, implementation_status) for a specific repo.
        Falls back to top-level if no per_repo_status entry exists."""
        for prs in self.per_repo_status:
            if prs.repo == repo:
                return (prs.status or self.status, prs.implementation_status)
        return (self.status, self.implementation_status)

    @property
    def latest_amendment(self) -> Amendment | None:
        if not self.amendments:
            return None
        return max(self.amendments, key=lambda a: a.at)


@dataclass(frozen=True)
class DifferentialDiagnostic:
    """Structured 'how is this wrong' info — the GEPA actionable side info pattern."""

    expected_pattern: str
    actual_pattern: str
    semantic_distance: float  # 0.0 = identical, 1.0 = opposite
    likely_cause: str
    historical_pattern: str | None = None
    blast_radius: str | None = None


@dataclass(frozen=True)
class FixSuggestion:
    description: str
    confidence: float
    automated: bool
    code_transform: str | None = None
    side_effects: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuleViolation:
    rule_id: str  # global id like 'ADR-099/tenant-id-bigint'
    severity: Severity
    file: str
    line_start: int
    line_end: int
    expected: str
    actual: str
    diagnostic: DifferentialDiagnostic
    suggestions: tuple[FixSuggestion, ...] = ()
