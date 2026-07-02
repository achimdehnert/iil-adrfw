"""Headless CLI — all 8 MCP tools as subcommands.

Exit codes (consistent across subcommands):
  0   Success, no findings/violations
  1   Findings or violations present (constitution unhealthy or rules failed)
  2   Configuration or invocation error (bad args, missing files, etc.)
  3   Internal error (uncaught exception, propagated as well)

JSON output (`--json`) is intended for CI pipelines. Text output is for humans.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from iil_adrfw.server import (
    AuditRequest,
    CheckRequest,
    DiffRequest,
    ExplainRequest,
    NarrateRequest,
    ProposeRequest,
    QueryRequest,
    ValidateCrossRepoRequest,
    _do_audit,
    _do_check,
    _do_diff,
    _do_explain,
    _do_list_adrs,
    _do_narrate,
    _do_propose,
    _do_query,
    _do_validate_cross_repo,
)

# ─── Common helpers ─────────────────────────────────────────────


def _parse_iso(s: str) -> datetime:
    """Parse an ISO timestamp; assume UTC if naive."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _print_json(obj) -> None:
    if hasattr(obj, "model_dump_json"):
        print(obj.model_dump_json(indent=2))
    else:
        print(json.dumps(obj, indent=2, default=str))


# ─── adr_check ──────────────────────────────────────────────────


def _cmd_check(args: argparse.Namespace) -> int:
    as_of = _parse_iso(args.as_of) if args.as_of else None
    req = CheckRequest(
        paths=args.paths,
        rule_ids=args.rule or None,
        severity_threshold=args.severity,
        as_of=as_of,
    )
    resp = _do_check(req)
    if args.json:
        _print_json(resp)
    else:
        print(f"Scanned {resp.files_scanned} files, evaluated {resp.rules_evaluated} rules in {resp.runtime_ms}ms")
        print(f"Loaded {resp.constitution_loaded} ADRs from constitution\n")
        if not resp.violations:
            print("OK — no violations")
        else:
            print(f"FOUND {len(resp.violations)} violation(s):")
            for v in resp.violations:
                print(f"  [{v.severity}] {v.rule_id} at {v.file}:{v.line_start}")
                print(f"    expected: {v.expected}")
                print(f"    actual:   {v.actual}")
    return 1 if resp.violations else 0


# ─── adr_explain ────────────────────────────────────────────────


def _cmd_explain(args: argparse.Namespace) -> int:
    req = ExplainRequest(rule_id=args.rule_id, audience=args.audience)
    resp = _do_explain(req)
    if args.json:
        _print_json(resp)
    else:
        print(f"# {resp.rule}")
        print(f"Severity: {resp.severity}")
        print(f"Audience: {args.audience}")
        print(f"\n## Why\n{resp.why_it_exists}\n")
        print(f"## Explanation\n{resp.explanation_for_audience}\n")
        if resp.correct_examples:
            print("## Correct examples")
            for ex in resp.correct_examples:
                print(f"  {ex.strip()}")
        if resp.common_violations:
            print("\n## Common violations")
            for ex in resp.common_violations:
                print(f"  {ex.strip()}")
        if resp.blast_radius:
            print(f"\n## Blast radius\n{resp.blast_radius}")
    return 0


# ─── adr_list ───────────────────────────────────────────────────


def _cmd_list(args: argparse.Namespace) -> int:
    listing = _do_list_adrs()
    if args.json:
        _print_json(listing)
    else:
        print(f"Constitution: {len(listing['adrs'])} ADRs\n")
        for a in listing["adrs"]:
            print(f"  {a['id']}  [{a['status']:12}]  {a['title']}")
            print(f"    domains: {', '.join(a['domains'])}")
            print(f"    rules:   {a['rule_count']}")
    return 0


# ─── adr_validate_cross_repo ────────────────────────────────────


def _cmd_validate_cross_repo(args: argparse.Namespace) -> int:
    from iil_adrfw.server import ConsumerRepoSpec

    if not args.repos:
        print("error: at least one --repo NAME=PATH required", file=sys.stderr)
        return 2
    specs: list[ConsumerRepoSpec] = []
    for r in args.repos:
        if "=" not in r:
            print(f"error: --repo expects NAME=PATH, got {r!r}", file=sys.stderr)
            return 2
        name, path = r.split("=", 1)
        specs.append(ConsumerRepoSpec(name=name, root=path))
    req = ValidateCrossRepoRequest(
        adr_id=args.adr_id,
        consumer_repos=specs,
    )
    resp = _do_validate_cross_repo(req)
    if args.json:
        _print_json(resp)
    else:
        print(f"Cross-repo validation for {resp.adr_id}")
        print(f"  consumer repos scanned: {', '.join(resp.consumer_repos_scanned)}")
        if resp.repos_unreachable:
            print(f"  repos unreachable: {', '.join(resp.repos_unreachable)}")
        print(f"  conflicts: class1={resp.class1_count} class2={resp.class2_count} class3={resp.class3_count}")
        if not resp.conflicts:
            print("  OK — no conflicts")
        else:
            for c in resp.conflicts:
                print(f"  [{c.conflict_class}/{c.confidence}] {c.rule_id or '-'}: {c.claim}")
        if resp.has_blocking_conflicts:
            print("\n⚠ Has blocking conflicts.")
    return 1 if resp.has_blocking_conflicts else 0


def _add_validate_cross_repo_parser(sub):
    p = sub.add_parser("validate-cross-repo", help="Validate an ADR's rules against consumer repos")
    p.add_argument("--adr-id", required=True, dest="adr_id", help="ADR to validate, e.g. 'ADR-188'")
    p.add_argument(
        "--repo",
        action="append",
        dest="repos",
        default=[],
        help="Consumer repo as NAME=PATH (repeatable, at least 1 required)",
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_validate_cross_repo)


# ─── adr_query ──────────────────────────────────────────────────


def _cmd_query(args: argparse.Namespace) -> int:
    req = QueryRequest(
        question=args.question,
        domain=args.domain,
        path=args.path,
    )
    resp = _do_query(req)
    if args.json:
        _print_json(resp)
    else:
        print(f"Query — {len(resp.citations)} citation(s)\n")
        if resp.primary_answer:
            print(f"Primary answer:\n  {resp.primary_answer[:300]}\n")
        for c in resp.citations:
            print(f"  {c.adr_id}  [{c.status:12}]  {c.title}")
            print(f"    relevance: {c.relevance}")
            if c.matched_concepts:
                print(f"    concepts: {', '.join(c.matched_concepts)}")
    return 0


# ─── adr_audit ──────────────────────────────────────────────────


def _cmd_audit(args: argparse.Namespace) -> int:
    as_of = _parse_iso(args.as_of) if args.as_of else None
    req = AuditRequest(
        auditors=args.auditor or None,
        as_of=as_of,
    )
    resp = _do_audit(req)
    if args.json:
        _print_json(resp)
    else:
        print(f"Audit: health score {resp.health.score:.3f}")
        print(f"  internal_consistency: {resp.health.internal_consistency:.3f}")
        print(f"  supersession_hygiene: {resp.health.supersession_hygiene:.3f}")
        print(f"  coverage:             {resp.health.coverage:.3f}")
        print(f"  freshness:            {resp.health.freshness:.3f}")
        if not resp.findings:
            print("\nOK — no findings")
        else:
            print(f"\nFindings: {len(resp.findings)}")
            for f in resp.findings:
                ids = ", ".join(f.affected_adrs) if f.affected_adrs else "-"
                print(f"  [{f.severity:8}] {f.auditor}: {ids}")
                print(f"    {f.description}")
                if f.proposed_resolution:
                    print(f"    → {f.proposed_resolution}")
    return 1 if resp.findings else 0


# ─── adr_propose ────────────────────────────────────────────────


def _cmd_propose(args: argparse.Namespace) -> int:
    req = ProposeRequest(
        title=args.title,
        domains=args.domain,
        deciders=args.decider,
        rationale_summary=args.rationale,
    )
    resp = _do_propose(req)
    if args.json:
        _print_json(resp)
    else:
        import yaml as _yaml

        print(f"Proposed ADR: {resp.proposed_id}\n")
        print("--- frontmatter ---")
        print(_yaml.safe_dump(resp.frontmatter, sort_keys=False, allow_unicode=True))
        print("--- body prompt ---")
        print(resp.body_prompt)
        if resp.conflicts:
            print(f"\n⚠ {len(resp.conflicts)} conflict(s):")
            for c in resp.conflicts:
                print(f"  - {c}")
        if resp.blocks_publish:
            print("\n⚠ This proposal currently BLOCKS publish (see conflicts)")
    return 1 if resp.blocks_publish else 0


# ─── adr_diff ───────────────────────────────────────────────────


def _cmd_diff(args: argparse.Namespace) -> int:
    if args.mode == "temporal":
        req = DiffRequest(
            mode="temporal",
            left_time=_parse_iso(args.left_time),
            right_time=_parse_iso(args.right_time),
        )
    elif args.mode == "set":
        req = DiffRequest(
            mode="set",
            right_dir=args.right_dir,
            left_label=args.left_label,
            right_label=args.right_label,
        )
    else:
        print(f"unknown mode: {args.mode}", file=sys.stderr)
        return 2
    resp = _do_diff(req)
    if args.json:
        _print_json(resp)
    else:
        print(f"Diff ({resp.mode}): {resp.left_label} → {resp.right_label}")
        print(f"  +added: {resp.added_count}  -removed: {resp.removed_count}  ~modified: {resp.modified_count}")
        print(f"  runtime: {resp.runtime_ms}ms\n")
        for c in resp.changes:
            sym = {"added": "+", "removed": "-"}.get(c.kind, "~")
            print(f"  {sym} [{c.kind:22}] {c.summary}")
    return 1 if resp.changes else 0


# ─── adr_narrate ────────────────────────────────────────────────


def _cmd_narrate(args: argparse.Namespace) -> int:
    if not (args.domain or args.id_set or args.path_filter):
        print("error: at least one of --domain, --id, --path-filter required", file=sys.stderr)
        return 2
    req = NarrateRequest(
        audience=args.audience,
        domain=args.domain,
        id_set=args.id_set or None,
        path_filter=args.path_filter,
        scope_label=args.scope_label,
    )
    resp = _do_narrate(req)
    if args.json:
        _print_json(resp)
    else:
        # Default human output IS the markdown — that's the most useful form
        print(resp.markdown)
    return 0


# ─── adr_validate (frontmatter schema validation) ────────────────


def _cmd_validate(args: argparse.Namespace) -> int:
    """Validate ADR frontmatter against schema v3."""
    from iil_adrfw.persistence import (
        ADRLoadError,
        detect_legacy_aliases,
        load_adr,
        original_frontmatter,
    )
    from iil_adrfw.schemas import get_schema_dir

    adr_dir = Path(args.adr_dir)
    schema_dir = Path(args.schema_dir) if args.schema_dir else get_schema_dir()

    if not adr_dir.is_dir():
        print(f"error: {adr_dir} is not a directory", file=sys.stderr)
        return 2

    md_files = sorted(adr_dir.glob("ADR-*.md"))
    if not md_files:
        print(f"error: no ADR-*.md files found in {adr_dir}", file=sys.stderr)
        return 2

    ok, failures = [], []
    alias_warnings = []  # (file, [(legacy, canonical), ...])
    for md in md_files:
        try:
            load_adr(md, schema_dir, validate=True)
            ok.append(md.name)
        except ADRLoadError as e:
            msg = str(e).split("\n")[1] if "\n" in str(e) else str(e)[:120]
            failures.append((md.name, msg))
        except Exception as e:
            failures.append((md.name, f"{type(e).__name__}: {str(e)[:100]}"))
        # Deprecation warnings: non-canonical alias keys are accepted (normalized)
        # but should migrate to the canonical form. Never affects pass/fail.
        try:
            aliases = detect_legacy_aliases(original_frontmatter(md))
            if aliases:
                alias_warnings.append((md.name, aliases))
        except Exception:
            pass

    total = len(ok) + len(failures)
    pct = 100 * len(ok) / total if total else 0

    if args.json:
        _print_json(
            {
                "total": total,
                "passed": len(ok),
                "failed": len(failures),
                "percent": round(pct, 1),
                "failures": [{"file": f, "error": e} for f, e in failures],
                "deprecation_warnings": [
                    {"file": f, "aliases": [{"legacy": legacy, "canonical": canonical} for legacy, canonical in al]}
                    for f, al in alias_warnings
                ],
            }
        )
    else:
        print(f"ADR Frontmatter Validation: {len(ok)}/{total} ({pct:.1f}%)")
        if failures:
            print(f"\nFAILED ({len(failures)}):")
            for name, err in failures:
                print(f"  {name}: {err}")
        else:
            print("  ✓ All ADRs valid")
        if alias_warnings:
            print(
                f"\nDEPRECATION ({len(alias_warnings)}) — non-canonical frontmatter keys (normalized, please migrate):"
            )
            for name, aliases in alias_warnings:
                hint = ", ".join(f"'{legacy}' → '{canonical}'" for legacy, canonical in aliases)
                print(f"  {name}: {hint}")

    return 1 if failures else 0


# ─── adr_staleness (age + drift check) ───────────────────────────


def _cmd_staleness(args: argparse.Namespace) -> int:
    """Check ADRs for staleness (age, missing reviews, broken references)."""
    from datetime import date, timedelta

    from iil_adrfw.persistence import ADRLoadError, load_adr
    from iil_adrfw.schemas import get_schema_dir

    adr_dir = Path(args.adr_dir)
    schema_dir = Path(args.schema_dir) if args.schema_dir else get_schema_dir()
    max_months = args.months

    if not adr_dir.is_dir():
        print(f"error: {adr_dir} is not a directory", file=sys.stderr)
        return 2

    md_files = sorted(adr_dir.glob("ADR-*.md"))
    if not md_files:
        print("error: no ADR-*.md files found", file=sys.stderr)
        return 2

    today = date.today()
    threshold = today - timedelta(days=30 * max_months)
    findings = []
    all_ids = set()
    adrs_data = []

    # Phase 1: Load all ADRs and extract metadata
    for md in md_files:
        try:
            adr = load_adr(md, schema_dir, validate=False)
            adr_id = adr.id
            all_ids.add(adr_id)
            adrs_data.append(adr)

            # Staleness: check decision_date
            adr_date = None
            if hasattr(adr, "decision_date") and adr.decision_date:
                try:
                    adr_date = date.fromisoformat(str(adr.decision_date)[:10])
                except (ValueError, TypeError):
                    pass

            status = adr.status.value if hasattr(adr.status, "value") else str(adr.status)

            # Skip deprecated/superseded for staleness
            if status.lower() in ("deprecated", "superseded", "rejected"):
                continue

            if adr_date and adr_date < threshold:
                age_months = (today - adr_date).days // 30
                findings.append(
                    {
                        "adr_id": adr_id,
                        "type": "stale",
                        "severity": "warning",
                        "message": f"Last decision date {adr_date} ({age_months}mo ago, threshold: {max_months}mo)",
                    }
                )

            # Missing review_status on accepted ADRs
            review = getattr(adr, "review_status", None)
            if status.lower() == "accepted" and not review:
                findings.append(
                    {
                        "adr_id": adr_id,
                        "type": "no_review",
                        "severity": "info",
                        "message": "Accepted ADR without review_status field",
                    }
                )

        except (ADRLoadError, Exception):
            continue

    # Phase 2: Reference drift — check if referenced ADRs exist
    for adr in adrs_data:
        adr_id = adr.id
        # Check superseded_by (can be string or list)
        sup_by = getattr(adr, "superseded_by", None)
        if sup_by:
            refs = sup_by if isinstance(sup_by, (list, tuple)) else [sup_by]
            for ref in refs:
                ref_str = str(ref).strip()
                if ref_str and ref_str not in all_ids:
                    findings.append(
                        {
                            "adr_id": adr_id,
                            "type": "broken_ref",
                            "severity": "error",
                            "message": f"superseded_by references '{ref_str}' which does not exist",
                        }
                    )
        # Check depends_on
        deps = getattr(adr, "depends_on", None) or []
        for dep in deps:
            if dep not in all_ids:
                findings.append(
                    {
                        "adr_id": adr_id,
                        "type": "broken_ref",
                        "severity": "warning",
                        "message": f"depends_on references '{dep}' which does not exist",
                    }
                )
        # Check related
        related = getattr(adr, "related", None) or []
        for rel in related:
            if rel.startswith("ADR-") and rel not in all_ids:
                findings.append(
                    {
                        "adr_id": adr_id,
                        "type": "broken_ref",
                        "severity": "info",
                        "message": f"related references '{rel}' which does not exist",
                    }
                )

    # Output
    stale_count = len([f for f in findings if f["type"] == "stale"])
    ref_count = len([f for f in findings if f["type"] == "broken_ref"])
    review_count = len([f for f in findings if f["type"] == "no_review"])

    if args.json:
        _print_json(
            {
                "total_adrs": len(md_files),
                "stale_count": stale_count,
                "broken_refs": ref_count,
                "missing_reviews": review_count,
                "findings": findings,
            }
        )
    else:
        print(f"Staleness Report: {len(md_files)} ADRs scanned (threshold: {max_months}mo)\n")
        print(f"  Stale ADRs:       {stale_count}")
        print(f"  Broken refs:      {ref_count}")
        print(f"  Missing reviews:  {review_count}")
        if findings:
            print(f"\nFindings ({len(findings)}):")
            for f in sorted(findings, key=lambda x: (x["severity"], x["adr_id"])):
                print(f"  [{f['severity']:7}] {f['adr_id']}: {f['message']}")
        else:
            print("\n  ✓ No staleness or drift issues found")

    return 1 if any(f["severity"] == "error" for f in findings) else 0


# ─── Argument parser ────────────────────────────────────────────


def _add_staleness_parser(sub):
    p = sub.add_parser("staleness", help="Check ADRs for staleness and reference drift")
    p.add_argument("adr_dir", help="Directory containing ADR-*.md files")
    p.add_argument("--months", type=int, default=6, help="Staleness threshold in months (default: 6)")
    p.add_argument(
        "--schema-dir", dest="schema_dir", help="Directory containing JSON schema files (default: auto-detect)"
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_staleness)


# ─── adr_graph (dependency visualization) ────────────────────────


def _cmd_graph(args: argparse.Namespace) -> int:
    """Generate ADR dependency graph in DOT or text format."""
    from iil_adrfw.persistence import load_adr
    from iil_adrfw.schemas import get_schema_dir

    adr_dir = Path(args.adr_dir)
    schema_dir = Path(args.schema_dir) if args.schema_dir else get_schema_dir()

    if not adr_dir.is_dir():
        print(f"error: {adr_dir} is not a directory", file=sys.stderr)
        return 2

    md_files = sorted(adr_dir.glob("ADR-*.md"))
    adrs_meta: list[dict[str, Any]] = []

    for md in md_files:
        try:
            adr = load_adr(md, schema_dir, validate=False)
            adrs_meta.append(
                {
                    "id": adr.id,
                    "title": adr.title[:40],
                    "status": adr.status.value if hasattr(adr.status, "value") else str(adr.status),
                    "superseded_by": getattr(adr, "superseded_by", None),
                    "depends_on": getattr(adr, "depends_on", None) or [],
                    "related": getattr(adr, "related", None) or [],
                    "amends": getattr(adr, "amends", None) or [],
                }
            )
        except Exception:
            continue

    # Build edges
    edges = []
    for meta in adrs_meta:
        aid = meta["id"]
        sup = meta["superseded_by"]
        if sup:
            refs = sup if isinstance(sup, (list, tuple)) else [sup]
            for r in refs:
                edges.append((aid, str(r).strip(), "superseded_by"))
        for dep in meta["depends_on"]:
            edges.append((aid, dep, "depends_on"))
        for rel in meta["related"]:
            if rel.startswith("ADR-"):
                edges.append((aid, rel, "related"))
        for am in meta["amends"]:
            edges.append((aid, am, "amends"))

    if args.dot:
        # DOT format for Graphviz
        print("digraph ADR_Dependencies {")
        print("  rankdir=LR;")
        print("  node [shape=box, style=filled, fontsize=10];")
        status_colors = {
            "accepted": "#d4edda",
            "proposed": "#fff3cd",
            "draft": "#e2e3e5",
            "deprecated": "#ffeeba",
            "superseded": "#f8d7da",
            "rejected": "#f5c6cb",
        }
        for meta in adrs_meta:
            color = status_colors.get(meta["status"], "#ffffff")
            label = f"{meta['id']}\\n{meta['title']}"
            print(f'  "{meta["id"]}" [label="{label}", fillcolor="{color}"];')
        edge_styles = {
            "superseded_by": "[color=red, style=dashed, label=supersedes]",
            "depends_on": "[color=blue, label=depends]",
            "related": "[color=gray, style=dotted]",
            "amends": "[color=orange, label=amends]",
        }
        for src, dst, rel in edges:
            style = edge_styles.get(rel, "")
            print(f'  "{src}" -> "{dst}" {style};')
        print("}")
    elif args.json:
        _print_json(
            {
                "nodes": len(adrs_meta),
                "edges": len(edges),
                "adrs": [{"id": a["id"], "status": a["status"]} for a in adrs_meta],
                "relationships": [{"from": s, "to": d, "type": t} for s, d, t in edges],
            }
        )
    else:
        print(f"ADR Dependency Graph: {len(adrs_meta)} nodes, {len(edges)} edges\n")
        if not edges:
            print("  No dependencies found.")
        else:
            by_type: dict[str, list[tuple[str, str]]] = {}
            for s, d, t in edges:
                by_type.setdefault(t, []).append((s, d))
            for rel_type, rels in sorted(by_type.items()):
                print(f"  {rel_type} ({len(rels)}):")
                for s, d in sorted(rels):
                    print(f"    {s} → {d}")

    return 0


def _add_graph_parser(sub):
    p = sub.add_parser("graph", help="Generate ADR dependency graph")
    p.add_argument("adr_dir", help="Directory containing ADR-*.md files")
    p.add_argument(
        "--schema-dir", dest="schema_dir", help="Directory containing JSON schema files (default: auto-detect)"
    )
    p.add_argument("--dot", action="store_true", help="Output in Graphviz DOT format")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_graph)


# ─── adr_export (Outline-compatible markdown) ─────────────────────


def _cmd_export(args: argparse.Namespace) -> int:
    """Export all ADRs as Outline-compatible markdown registry."""
    from datetime import date

    from iil_adrfw.persistence import load_adr
    from iil_adrfw.schemas import get_schema_dir

    adr_dir = Path(args.adr_dir)
    schema_dir = Path(args.schema_dir) if args.schema_dir else get_schema_dir()

    if not adr_dir.is_dir():
        print(f"error: {adr_dir} is not a directory", file=sys.stderr)
        return 2

    md_files = sorted(adr_dir.glob("ADR-*.md"))
    adrs: list[dict[str, Any]] = []
    for md in md_files:
        try:
            adr = load_adr(md, schema_dir, validate=False)
            status = adr.status.value if hasattr(adr.status, "value") else str(adr.status)
            adrs.append(
                {
                    "id": adr.id,
                    "title": adr.title,
                    "status": status,
                    "date": str(getattr(adr, "decision_date", "") or ""),
                    "domains": getattr(adr, "domains", []) or [],
                    "scope": str(getattr(adr, "scope", "") or ""),
                }
            )
        except Exception:
            continue

    # Generate markdown
    lines = [
        "# ADR Registry",
        "",
        f"> Auto-generated by `iil-adrfw export` on {date.today()}",
        f"> Source: `{adr_dir}`",
        f"> Total: **{len(adrs)} ADRs**",
        "",
        "## Summary",
        "",
    ]

    # Status counts
    from collections import Counter

    status_counts = Counter(a["status"] for a in adrs)
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- **{status}**: {count}")
    lines.append("")

    # Table
    lines.extend(
        [
            "## Full Index",
            "",
            "| ID | Title | Status | Date | Domains |",
            "|---|---|---|---|---|",
        ]
    )
    for a in adrs:
        domains = ", ".join(a["domains"][:3]) if a["domains"] else "—"
        title = a["title"][:50] + ("…" if len(a["title"]) > 50 else "")
        lines.append(f"| {a['id']} | {title} | {a['status']} | {a['date'][:10] or '—'} | {domains} |")
    lines.append("")

    output = "\n".join(lines)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Exported {len(adrs)} ADRs to {args.output}")
    else:
        print(output)

    return 0


def _add_export_parser(sub):
    p = sub.add_parser("export", help="Export ADR registry as Outline-compatible markdown")
    p.add_argument("adr_dir", help="Directory containing ADR-*.md files")
    p.add_argument(
        "--schema-dir", dest="schema_dir", help="Directory containing JSON schema files (default: auto-detect)"
    )
    p.add_argument("-o", "--output", help="Output file path (default: stdout)")
    p.set_defaults(func=_cmd_export)


def _add_validate_parser(sub):
    p = sub.add_parser("validate", help="Validate ADR frontmatter against schema v3")
    p.add_argument("adr_dir", help="Directory containing ADR-*.md files")
    p.add_argument(
        "--schema-dir", dest="schema_dir", help="Directory containing JSON schema files (default: auto-detect)"
    )
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_validate)


def _add_check_parser(sub):
    p = sub.add_parser("check", help="Run rules against code paths")
    p.add_argument("paths", nargs="+")
    p.add_argument("--rule", action="append", default=[], help="Filter to specific rule ids (repeatable)")
    p.add_argument("--severity", default="warning", choices=["info", "warning", "error", "critical"])
    p.add_argument("--as-of", help="ISO timestamp; check constitution as of this time")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_check)


def _add_explain_parser(sub):
    p = sub.add_parser("explain", help="Explain a rule for an audience")
    p.add_argument("rule_id")
    p.add_argument("--audience", default="senior", choices=["new_dev", "senior", "architect", "auditor"])
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_explain)


def _add_list_parser(sub):
    p = sub.add_parser("list", help="List ADRs in the constitution")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_list)


def _add_query_parser(sub):
    p = sub.add_parser("query", help="Query the constitution by question/domain/path")
    p.add_argument("--question", help="Natural-language question")
    p.add_argument("--domain", help="Limit to specific domain tag")
    p.add_argument("--path", help="File path the answer should apply to")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_query)


def _add_audit_parser(sub):
    p = sub.add_parser("audit", help="Run constitution-level audit")
    p.add_argument("--auditor", action="append", default=[], help="Run only specific auditors (repeatable)")
    p.add_argument("--as-of", help="ISO timestamp; audit constitution as of this time")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_audit)


def _add_propose_parser(sub):
    p = sub.add_parser("propose", help="Propose a new ADR (returns frontmatter + body prompt)")
    p.add_argument("--title", required=True)
    p.add_argument(
        "--rationale", required=True, help="Rationale summary (min 20 chars) — drives concept matching and body prompt"
    )
    p.add_argument("--domain", action="append", required=True, help="Domain tag (repeatable, at least 1 required)")
    p.add_argument("--decider", action="append", required=True, help="Decider name (repeatable, at least 1 required)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_propose)


def _add_diff_parser(sub):
    p = sub.add_parser("diff", help="Diff constitution between times or sets")
    p.add_argument("--mode", required=True, choices=["temporal", "set"])
    p.add_argument("--left-time", help="Temporal mode: ISO timestamp (older)")
    p.add_argument("--right-time", help="Temporal mode: ISO timestamp (newer)")
    p.add_argument("--right-dir", help="Set mode: path to right-hand-side ADR directory")
    p.add_argument("--left-label", default="left")
    p.add_argument("--right-label", default="right")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_diff)


def _add_narrate_parser(sub):
    p = sub.add_parser("narrate", help="Compose audience-tailored narrative")
    p.add_argument("--audience", default="senior", choices=["new_dev", "senior", "architect", "auditor"])
    p.add_argument("--domain", help="Pick ADRs by domain tag")
    p.add_argument("--id", action="append", dest="id_set", default=[], help="Pick ADRs by id (repeatable)")
    p.add_argument("--path-filter", help="Pick ADRs whose scope matches this path")
    p.add_argument("--scope-label", default="the constitution", help="Free-text label used in the narrative title")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_narrate)


def _cmd_metrics(args: argparse.Namespace) -> int:
    """Compute and optionally write Schema v4 metrics to ADR frontmatters."""
    import os as _os

    from iil_adrfw.metrics import compute_all, controlling_report, write_metrics
    from iil_adrfw.persistence import load_adrs
    from iil_adrfw.schemas import get_schema_dir

    _adr_dir_str = args.adr_dir or _os.environ.get("IIL_ADRFW_ADRS_DIR") or "docs/adr"
    adr_dir = Path(_adr_dir_str)
    schema_dir = Path(args.schema_dir) if args.schema_dir else get_schema_dir()

    if not adr_dir.is_dir():
        print(f"error: {adr_dir} is not a directory", file=sys.stderr)
        return 2

    adrs = load_adrs(adr_dir, schema_dir)
    metrics_map = compute_all(adrs)

    if args.write:
        changed = write_metrics(adr_dir, metrics_map)
        print(f"[OK] Metrics written to {changed} ADR files")

    if args.report or not args.write:
        print(controlling_report(metrics_map))

    if args.json:
        import json

        out = {
            mid: {
                "inbound_links": m.inbound_links,
                "ttd_days": m.ttd_days,
                "ttr_days": m.ttr_days,
                "ai_interactions": m.ai_interactions,
                "ai_interactions_90d": m.ai_interactions_90d,
                "last_computed": m.last_computed,
            }
            for mid, m in metrics_map.items()
        }
        print(json.dumps(out, indent=2))

    return 0


def _add_metrics_parser(sub):
    p = sub.add_parser("metrics", help="Compute Schema v4 metrics (inbound_links, ttd, ttr, ai_interactions)")
    p.add_argument("--adr-dir", default=None, help="ADR directory (default: $IIL_ADRFW_ADRS_DIR or ./docs/adr)")
    p.add_argument("--schema-dir", default=None)
    p.add_argument("--write", action="store_true", help="Write computed metrics into ADR frontmatters")
    p.add_argument("--report", action="store_true", help="Print controlling report (always shown without --write)")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=_cmd_metrics)


def main() -> None:
    p = argparse.ArgumentParser(
        prog="iil-adrfw",
        description="Architecture Decision Record framework — headless CLI",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    _add_validate_parser(sub)
    _add_staleness_parser(sub)
    _add_graph_parser(sub)
    _add_export_parser(sub)
    _add_check_parser(sub)
    _add_explain_parser(sub)
    _add_list_parser(sub)
    _add_validate_cross_repo_parser(sub)
    _add_query_parser(sub)
    _add_audit_parser(sub)
    _add_propose_parser(sub)
    _add_diff_parser(sub)
    _add_narrate_parser(sub)
    _add_metrics_parser(sub)

    args = p.parse_args()
    try:
        sys.exit(args.func(args))
    except (FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
