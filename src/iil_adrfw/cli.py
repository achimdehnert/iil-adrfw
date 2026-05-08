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
from datetime import datetime, timezone


def _parse_iso(s: str) -> datetime:
    """Parse an ISO timestamp; assume UTC if naive."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
from pathlib import Path

from iil_adrfw.server import (
    _do_check, _do_explain, _do_list_adrs,
    _do_validate_cross_repo, _do_query, _do_audit, _do_propose,
    _do_diff, _do_narrate,
    CheckRequest, ExplainRequest, ValidateCrossRepoRequest,
    QueryRequest, AuditRequest, ProposeRequest,
    DiffRequest, NarrateRequest,
)


# ─── Common helpers ─────────────────────────────────────────────


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
        print(f"Scanned {resp.files_scanned} files, "
              f"evaluated {resp.rules_evaluated} rules in {resp.runtime_ms}ms")
        print(f"Loaded {resp.constitution_loaded} ADRs from constitution\n")
        if not resp.violations:
            print("OK — no violations")
        else:
            print(f"FOUND {len(resp.violations)} violation(s):")
            for v in resp.violations:
                print(f"  [{v.severity}] {v.rule_id} at {v.file_path}:{v.line_number or '?'}")
                print(f"    {v.message}")
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
                print(f"  [{c.severity}] {c.rule_id or '-'}: {c.description}")
        if resp.has_blocking_conflicts:
            print("\n⚠ Has blocking conflicts.")
    return 1 if resp.has_blocking_conflicts else 0


def _add_validate_cross_repo_parser(sub):
    p = sub.add_parser("validate-cross-repo",
                       help="Validate an ADR's rules against consumer repos")
    p.add_argument("--adr-id", required=True, dest="adr_id",
                   help="ADR to validate, e.g. 'ADR-188'")
    p.add_argument("--repo", action="append", dest="repos", default=[],
                   help="Consumer repo as NAME=PATH (repeatable, at least 1 required)")
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
        print(f"--- frontmatter ---")
        print(_yaml.safe_dump(resp.frontmatter, sort_keys=False, allow_unicode=True))
        print(f"--- body prompt ---")
        print(resp.body_prompt)
        if resp.conflicts:
            print(f"\n⚠ {len(resp.conflicts)} conflict(s):")
            for c in resp.conflicts:
                print(f"  - {c}")
        if resp.blocks_publish:
            print(f"\n⚠ This proposal currently BLOCKS publish (see conflicts)")
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
        print("error: at least one of --domain, --id, --path-filter required",
              file=sys.stderr)
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
    from iil_adrfw.persistence import load_adr, ADRLoadError

    adr_dir = Path(args.adr_dir)
    schema_dir = Path(args.schema_dir) if args.schema_dir else adr_dir.parent.parent / "schemas"

    if not adr_dir.is_dir():
        print(f"error: {adr_dir} is not a directory", file=sys.stderr)
        return 2

    md_files = sorted(adr_dir.glob("ADR-*.md"))
    if not md_files:
        print(f"error: no ADR-*.md files found in {adr_dir}", file=sys.stderr)
        return 2

    ok, failures = [], []
    for md in md_files:
        try:
            load_adr(md, schema_dir, validate=True)
            ok.append(md.name)
        except ADRLoadError as e:
            msg = str(e).split('\n')[1] if '\n' in str(e) else str(e)[:120]
            failures.append((md.name, msg))
        except Exception as e:
            failures.append((md.name, f"{type(e).__name__}: {str(e)[:100]}"))

    total = len(ok) + len(failures)
    pct = 100 * len(ok) / total if total else 0

    if args.json:
        _print_json({
            "total": total, "passed": len(ok), "failed": len(failures),
            "percent": round(pct, 1),
            "failures": [{"file": f, "error": e} for f, e in failures],
        })
    else:
        print(f"ADR Frontmatter Validation: {len(ok)}/{total} ({pct:.1f}%)")
        if failures:
            print(f"\nFAILED ({len(failures)}):")
            for name, err in failures:
                print(f"  {name}: {err}")
        else:
            print("  ✓ All ADRs valid")

    return 1 if failures else 0


# ─── Argument parser ────────────────────────────────────────────


def _add_validate_parser(sub):
    p = sub.add_parser("validate", help="Validate ADR frontmatter against schema v3")
    p.add_argument("adr_dir", help="Directory containing ADR-*.md files")
    p.add_argument("--schema-dir", dest="schema_dir",
                   help="Directory containing JSON schema files (default: auto-detect)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_validate)


def _add_check_parser(sub):
    p = sub.add_parser("check", help="Run rules against code paths")
    p.add_argument("paths", nargs="+")
    p.add_argument("--rule", action="append", default=[],
                   help="Filter to specific rule ids (repeatable)")
    p.add_argument("--severity", default="warning",
                   choices=["info", "warning", "error", "critical"])
    p.add_argument("--as-of", help="ISO timestamp; check constitution as of this time")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_check)


def _add_explain_parser(sub):
    p = sub.add_parser("explain", help="Explain a rule for an audience")
    p.add_argument("rule_id")
    p.add_argument("--audience", default="senior",
                   choices=["new_dev", "senior", "architect", "auditor"])
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
    p.add_argument("--auditor", action="append", default=[],
                   help="Run only specific auditors (repeatable)")
    p.add_argument("--as-of", help="ISO timestamp; audit constitution as of this time")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_audit)


def _add_propose_parser(sub):
    p = sub.add_parser("propose", help="Propose a new ADR (returns frontmatter + body prompt)")
    p.add_argument("--title", required=True)
    p.add_argument("--rationale", required=True,
                   help="Rationale summary (min 20 chars) — drives concept matching and body prompt")
    p.add_argument("--domain", action="append", required=True,
                   help="Domain tag (repeatable, at least 1 required)")
    p.add_argument("--decider", action="append", required=True,
                   help="Decider name (repeatable, at least 1 required)")
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
    p.add_argument("--audience", default="senior",
                   choices=["new_dev", "senior", "architect", "auditor"])
    p.add_argument("--domain", help="Pick ADRs by domain tag")
    p.add_argument("--id", action="append", dest="id_set", default=[],
                   help="Pick ADRs by id (repeatable)")
    p.add_argument("--path-filter", help="Pick ADRs whose scope matches this path")
    p.add_argument("--scope-label", default="the constitution",
                   help="Free-text label used in the narrative title")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_narrate)


def main() -> None:
    p = argparse.ArgumentParser(
        prog="iil-adrfw",
        description="Architecture Decision Record framework — headless CLI",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    _add_validate_parser(sub)
    _add_check_parser(sub)
    _add_explain_parser(sub)
    _add_list_parser(sub)
    _add_validate_cross_repo_parser(sub)
    _add_query_parser(sub)
    _add_audit_parser(sub)
    _add_propose_parser(sub)
    _add_diff_parser(sub)
    _add_narrate_parser(sub)

    args = p.parse_args()
    try:
        sys.exit(args.func(args))
    except (FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
