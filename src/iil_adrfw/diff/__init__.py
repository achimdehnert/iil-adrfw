"""Constitution diff — temporal and set modes.

Two snapshots of a constitution can differ in two ways:

- **Temporal**: same ADR set viewed at different times. Uses the bi-temporal
  schema (valid_from / valid_to / knowledge_from / amendments) to materialize
  what each ADR looked like at a given point in world-time.
- **Set**: two distinct ADR sets (e.g. two repos, two branches, two
  directories). Compared by ID overlap and per-ADR field differences.

Both produce the same ConstitutionDiff structure with categorized changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from iil_adrfw.domain import ADR


class ChangeKind(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    STATUS_CHANGED = "status_changed"
    SUPERSESSION_CHANGED = "supersession_changed"
    RULES_CHANGED = "rules_changed"
    FRONTMATTER_CHANGED = "frontmatter_changed"


class DiffMode(str, Enum):
    TEMPORAL = "temporal"
    SET = "set"


@dataclass(frozen=True)
class FieldChange:
    field_path: str
    before: object | None
    after: object | None


@dataclass(frozen=True)
class ADRChange:
    adr_id: str
    kind: ChangeKind
    field_changes: tuple[FieldChange, ...] = ()
    summary: str = ""


@dataclass
class ConstitutionDiff:
    mode: DiffMode
    left_label: str
    right_label: str
    changes: list[ADRChange] = field(default_factory=list)
    runtime_ms: int = 0

    @property
    def added_count(self) -> int:
        return sum(1 for c in self.changes if c.kind == ChangeKind.ADDED)

    @property
    def removed_count(self) -> int:
        return sum(1 for c in self.changes if c.kind == ChangeKind.REMOVED)

    @property
    def modified_count(self) -> int:
        return sum(1 for c in self.changes if c.kind not in (ChangeKind.ADDED, ChangeKind.REMOVED))

    def changes_for(self, adr_id: str) -> list[ADRChange]:
        return [c for c in self.changes if c.adr_id == adr_id]


# ─── Temporal materialization ───────────────────────────────────


def _adr_effective_at(adr: ADR, world_time: datetime) -> ADR | None:
    """Return the ADR as it appeared at world_time, or None if it didn't
    exist yet."""
    if adr.decision_date > world_time:
        return None
    effective_amendments = tuple(a for a in adr.amendments if a.at <= world_time)
    return ADR(
        id=adr.id,
        title=adr.title,
        status=adr.status,
        domains=adr.domains,
        deciders=adr.deciders,
        decision_date=adr.decision_date,
        temporal=adr.temporal,
        rationale_summary=adr.rationale_summary,
        supersedes=adr.supersedes,
        superseded_by=adr.superseded_by,
        consolidates=adr.consolidates,
        depends_on=adr.depends_on,
        conflicts_with=adr.conflicts_with,
        rules=[r for r in adr.rules if r.temporal.applies_at(world_time)],
        raw_frontmatter=adr.raw_frontmatter,
        body_markdown=adr.body_markdown,
        amendments=effective_amendments,
        decision_drivers=adr.decision_drivers,
        open_questions=adr.open_questions,
        deprecation_timeline=adr.deprecation_timeline,
        spof_mitigation=adr.spof_mitigation,
        per_repo_status=adr.per_repo_status,
        repo=adr.repo,
        consumers=adr.consumers,
        implementation_status=adr.implementation_status,
        staleness_months=adr.staleness_months,
        drift_check_paths=adr.drift_check_paths,
    )


def _materialize_at(adrs: list[ADR], world_time: datetime) -> dict[str, ADR]:
    out: dict[str, ADR] = {}
    for adr in adrs:
        snap = _adr_effective_at(adr, world_time)
        if snap is not None:
            out[adr.id] = snap
    return out


# ─── Per-ADR diff (used by both modes) ──────────────────────────


def _diff_adr_pair(left: ADR, right: ADR) -> ADRChange | None:
    field_changes: list[FieldChange] = []

    if left.status != right.status:
        field_changes.append(
            FieldChange(
                field_path="status",
                before=left.status.value,
                after=right.status.value,
            )
        )

    for fname in ("supersedes", "superseded_by", "consolidates"):
        l_val = getattr(left, fname)
        r_val = getattr(right, fname)
        if l_val != r_val:
            field_changes.append(
                FieldChange(
                    field_path=fname,
                    before=list(l_val),
                    after=list(r_val),
                )
            )

    left_rules = {r.rule_id: r for r in left.rules}
    right_rules = {r.rule_id: r for r in right.rules}
    rules_added = set(right_rules) - set(left_rules)
    rules_removed = set(left_rules) - set(right_rules)
    rules_changed_ids: list[str] = []
    for rid in set(left_rules) & set(right_rules):
        l_rule = left_rules[rid]
        r_rule = right_rules[rid]
        if l_rule.severity != r_rule.severity or l_rule.title != r_rule.title:
            rules_changed_ids.append(rid)
    if rules_added or rules_removed or rules_changed_ids:
        field_changes.append(
            FieldChange(
                field_path="rules",
                before={
                    "rule_ids": sorted(left_rules.keys()),
                    "count": len(left_rules),
                },
                after={
                    "rule_ids": sorted(right_rules.keys()),
                    "count": len(right_rules),
                    "added": sorted(rules_added),
                    "removed": sorted(rules_removed),
                    "modified": sorted(rules_changed_ids),
                },
            )
        )

    for fname in ("title", "rationale_summary", "implementation_status", "owner"):
        l_val = getattr(left, fname, None)
        r_val = getattr(right, fname, None)
        if l_val != r_val:
            field_changes.append(FieldChange(field_path=fname, before=l_val, after=r_val))

    if not field_changes:
        return None

    paths = {fc.field_path for fc in field_changes}
    if paths == {"status"}:
        kind = ChangeKind.STATUS_CHANGED
    elif paths and paths.issubset({"supersedes", "superseded_by", "consolidates"}):
        kind = ChangeKind.SUPERSESSION_CHANGED
    elif paths == {"rules"}:
        kind = ChangeKind.RULES_CHANGED
    else:
        kind = ChangeKind.FRONTMATTER_CHANGED

    return ADRChange(
        adr_id=left.id,
        kind=kind,
        field_changes=tuple(field_changes),
        summary=_summarize_change(left.id, kind, field_changes),
    )


def _summarize_change(adr_id: str, kind: ChangeKind, fcs: list[FieldChange]) -> str:
    parts: list[str] = []
    for fc in fcs:
        if fc.field_path == "status":
            parts.append(f"status: {fc.before} → {fc.after}")
        elif fc.field_path == "rules":
            after = fc.after if isinstance(fc.after, dict) else {}
            n_add = len(after.get("added", []))
            n_rem = len(after.get("removed", []))
            n_mod = len(after.get("modified", []))
            ops = []
            if n_add:
                ops.append(f"+{n_add}")
            if n_rem:
                ops.append(f"-{n_rem}")
            if n_mod:
                ops.append(f"~{n_mod}")
            parts.append(f"rules: {' '.join(ops)}")
        elif fc.field_path in ("supersedes", "superseded_by", "consolidates"):
            l_count = len(fc.before) if isinstance(fc.before, (list, tuple)) else 0
            r_count = len(fc.after) if isinstance(fc.after, (list, tuple)) else 0
            parts.append(f"{fc.field_path}: {l_count} → {r_count} refs")
        else:
            parts.append(f"{fc.field_path} changed")
    return f"{adr_id}: " + "; ".join(parts)


# ─── Top-level functions ────────────────────────────────────────


def diff_temporal(
    adrs: list[ADR],
    left_time: datetime,
    right_time: datetime,
) -> ConstitutionDiff:
    """Compare the same ADR set as it appeared at two world times.
    Always oriented from past to future."""
    import time

    start = time.monotonic()
    if left_time > right_time:
        left_time, right_time = right_time, left_time

    left_snap = _materialize_at(adrs, left_time)
    right_snap = _materialize_at(adrs, right_time)

    diff = ConstitutionDiff(
        mode=DiffMode.TEMPORAL,
        left_label=left_time.isoformat(),
        right_label=right_time.isoformat(),
    )

    all_ids = sorted(set(left_snap) | set(right_snap))
    for adr_id in all_ids:
        if adr_id in right_snap and adr_id not in left_snap:
            adr = right_snap[adr_id]
            diff.changes.append(
                ADRChange(
                    adr_id=adr_id,
                    kind=ChangeKind.ADDED,
                    summary=f"{adr_id} added: {adr.title[:60]}",
                )
            )
        elif adr_id in left_snap and adr_id not in right_snap:
            adr = left_snap[adr_id]
            diff.changes.append(
                ADRChange(
                    adr_id=adr_id,
                    kind=ChangeKind.REMOVED,
                    summary=f"{adr_id} removed: {adr.title[:60]}",
                )
            )
        else:
            change = _diff_adr_pair(left_snap[adr_id], right_snap[adr_id])
            if change is not None:
                diff.changes.append(change)

    diff.runtime_ms = int((time.monotonic() - start) * 1000)
    return diff


def diff_set(
    left_adrs: list[ADR],
    right_adrs: list[ADR],
    left_label: str = "left",
    right_label: str = "right",
) -> ConstitutionDiff:
    """Compare two ADR sets by id and field content."""
    import time

    start = time.monotonic()

    left_by_id = {a.id: a for a in left_adrs}
    right_by_id = {a.id: a for a in right_adrs}

    diff = ConstitutionDiff(
        mode=DiffMode.SET,
        left_label=left_label,
        right_label=right_label,
    )

    all_ids = sorted(set(left_by_id) | set(right_by_id))
    for adr_id in all_ids:
        if adr_id in right_by_id and adr_id not in left_by_id:
            adr = right_by_id[adr_id]
            diff.changes.append(
                ADRChange(
                    adr_id=adr_id,
                    kind=ChangeKind.ADDED,
                    summary=f"{adr_id} only in {right_label}: {adr.title[:60]}",
                )
            )
        elif adr_id in left_by_id and adr_id not in right_by_id:
            adr = left_by_id[adr_id]
            diff.changes.append(
                ADRChange(
                    adr_id=adr_id,
                    kind=ChangeKind.REMOVED,
                    summary=f"{adr_id} only in {left_label}: {adr.title[:60]}",
                )
            )
        else:
            change = _diff_adr_pair(left_by_id[adr_id], right_by_id[adr_id])
            if change is not None:
                diff.changes.append(change)

    diff.runtime_ms = int((time.monotonic() - start) * 1000)
    return diff
