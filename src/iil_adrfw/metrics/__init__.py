"""
iil_adrfw.metrics — ADR Constitution Metrics

Computes Schema v4 `metrics` field values for each ADR:
  - inbound_links:   number of other ADRs that depend_on this one
  - ttd_days:        time-to-decision (decision_date - knowledge_from, if available)
  - ttr_days:        time-to-review (first reviewed_by.date - decision_date)
  - ai_interactions: count of ai_sparring_by entries
  - ai_cost_90d_usd: estimated cost of AI reviews in last 90 days (if tokens tracked)
  - last_computed:   ISO timestamp of this computation

Usage:
  from iil_adrfw.metrics import compute_all, write_metrics

  adrs = load_adrs(adrs_dir, schemas_dir)
  metrics_map = compute_all(adrs)
  changed = write_metrics(adrs_dir, metrics_map)
  print(f"{changed} ADRs updated")
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------
@dataclass
class ADRMetrics:
    adr_id: str
    inbound_links: int = 0
    ttd_days: int | None = None
    ttr_days: int | None = None
    ai_interactions: int = 0
    ai_interactions_90d: int = 0
    last_computed: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------
def compute_all(adrs: list[Any]) -> dict[str, ADRMetrics]:
    """Compute metrics for all ADRs. Returns map adr_id → ADRMetrics."""

    # Pass 1: inbound_links — count how many ADRs depend_on each ADR
    inbound: dict[str, int] = defaultdict(int)
    for adr in adrs:
        for dep in adr.depends_on or []:
            dep_str = dep if isinstance(dep, str) else str(dep)
            # Normalize: extract "ADR-NNN"
            m = re.search(r"ADR-\d+", dep_str, re.IGNORECASE)
            if m:
                inbound[m.group().upper()] += 1

    today = date.today()
    metrics_map: dict[str, ADRMetrics] = {}

    for adr in adrs:
        adr_id = str(adr.id) if hasattr(adr, "id") else "unknown"
        m = re.search(r"ADR-\d+", adr_id, re.IGNORECASE)
        canonical_id = m.group().upper() if m else adr_id

        metrics = ADRMetrics(adr_id=canonical_id)
        metrics.inbound_links = inbound.get(canonical_id, 0)

        fm = adr.raw_frontmatter if hasattr(adr, "raw_frontmatter") else {}

        # ttd_days: knowledge_from → decision_date (or amended)
        decision_date = _parse_date(fm.get("decision_date") or fm.get("date"))
        knowledge_from = _parse_date(fm.get("knowledge_from"))
        if decision_date and knowledge_from and decision_date >= knowledge_from:
            metrics.ttd_days = (decision_date - knowledge_from).days

        # ttr_days: decision_date → first reviewed_by.date
        reviewed_by = fm.get("reviewed_by") or []
        if isinstance(reviewed_by, list):
            review_dates = []
            for entry in reviewed_by:
                if isinstance(entry, dict):
                    d = _parse_date(entry.get("date"))
                    if d:
                        review_dates.append(d)
            if review_dates and decision_date:
                first_review = min(review_dates)
                if first_review >= decision_date:
                    metrics.ttr_days = (first_review - decision_date).days

        # ai_interactions: count + 90d count
        sparring = fm.get("ai_sparring_by") or []
        if isinstance(sparring, list):
            metrics.ai_interactions = len(sparring)
            # Simple 90-day cutoff
            cutoff_date = date.fromordinal(today.toordinal() - 90)
            for entry in sparring:
                if isinstance(entry, dict):
                    d = _parse_date(entry.get("date"))
                    if d and d >= cutoff_date:
                        metrics.ai_interactions_90d += 1

        metrics_map[canonical_id] = metrics

    return metrics_map


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except (ValueError, IndexError):
            return None
    return None


# ---------------------------------------------------------------------------
# Write metrics back into ADR frontmatter files
# ---------------------------------------------------------------------------
def write_metrics(adrs_dir: Path, metrics_map: dict[str, ADRMetrics]) -> int:
    """Update metrics field in each ADR file. Returns count of changed files."""
    changed = 0
    for md_path in sorted(adrs_dir.glob("ADR-*.md")):
        m = re.search(r"ADR-\d+", md_path.name, re.IGNORECASE)
        if not m:
            continue
        canonical_id = m.group().upper()
        if canonical_id not in metrics_map:
            continue

        metrics = metrics_map[canonical_id]
        metrics_dict = {
            "inbound_links": metrics.inbound_links,
            "ttd_days": metrics.ttd_days,
            "ttr_days": metrics.ttr_days,
            "ai_interactions": metrics.ai_interactions,
            "ai_interactions_90d": metrics.ai_interactions_90d,
            "last_computed": metrics.last_computed,
        }

        text = md_path.read_text(encoding="utf-8")
        match = re.match(r"^(---\n)(.*?)(\n---\n)(.*)", text, re.DOTALL)
        if not match:
            continue

        fm = yaml.safe_load(match.group(2)) or {}
        old_metrics = fm.get("metrics", {})
        if isinstance(old_metrics, dict):
            # Skip update if only last_computed changed and values are identical
            compare_old = {k: v for k, v in old_metrics.items() if k != "last_computed"}
            compare_new = {k: v for k, v in metrics_dict.items() if k != "last_computed"}
            if compare_old == compare_new:
                continue

        fm["metrics"] = metrics_dict
        new_fm = yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=False)
        new_text = f"---\n{new_fm}---\n{match.group(4)}"
        md_path.write_text(new_text, encoding="utf-8")
        changed += 1

    return changed


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------
def controlling_report(metrics_map: dict[str, ADRMetrics]) -> str:
    """Human-readable controlling summary for Job Summary / CLI output."""
    all_m = list(metrics_map.values())
    if not all_m:
        return "No ADRs found."

    total_ai = sum(m.ai_interactions for m in all_m)
    total_ai_90d = sum(m.ai_interactions_90d for m in all_m)
    reviewed = sum(1 for m in all_m if m.ttr_days is not None)
    avg_ttr = sum(m.ttr_days for m in all_m if m.ttr_days is not None) / reviewed if reviewed else None

    top_inbound = sorted(all_m, key=lambda m: m.inbound_links, reverse=True)[:5]
    top_ai = sorted(all_m, key=lambda m: m.ai_interactions, reverse=True)[:5]

    lines = [
        "## ADR Controlling Report",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total ADRs | {len(all_m)} |",
        f"| AI interactions (total) | {total_ai} |",
        f"| AI interactions (last 90d) | {total_ai_90d} |",
        f"| ADRs with human review | {reviewed} |",
        f"| Avg time-to-review | {f'{avg_ttr:.0f}d' if avg_ttr else 'n/a (Coverage=0%)'} |",
        "",
        "### Critical Nodes (highest inbound_links)",
        "| ADR | Inbound | AI Reviews |",
        "|-----|---------|------------|",
    ]
    for m in top_inbound:
        lines.append(f"| `{m.adr_id}` | {m.inbound_links} | {m.ai_interactions} |")

    lines += [
        "",
        "### Most AI-Reviewed ADRs (last 90d)",
        "| ADR | Total | 90d |",
        "|-----|-------|-----|",
    ]
    for m in top_ai:
        lines.append(f"| `{m.adr_id}` | {m.ai_interactions} | {m.ai_interactions_90d} |")

    return "\n".join(lines)
