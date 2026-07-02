"""In-process tests for `iil_adrfw.cli` `_cmd_*` handlers (issue #20).

`examples/test_e2e_cli.py` drives the CLI via `subprocess.run(...)`, which is
correct for smoke-testing the entry point but leaves `cli.py` itself at 0%
coverage (the subprocess is a separate interpreter, invisible to `coverage`).

These tests call the `_cmd_*` functions directly, in-process, so `cli.py`'s
argument-handling, formatting and exit-code logic are actually measured.

Two fixture styles are used, whichever is the cheaper way to exercise a given
handler:
  - `_cmd_validate` / `_cmd_staleness` / `_cmd_graph` / `_cmd_export` /
    `_cmd_metrics` read ADR files straight off disk via `args.adr_dir`, so
    they get real `tmp_path` copies of the canonical fixtures
    (`ADR-099-multi-tenancy.md`, `ADR-188-unified-vector-store.md`).
  - `_cmd_list` (and friends already covered by `test_e2e_cli_findings.py`
    once that lands) go through `server._do_*`, so they are monkeypatched —
    see `test_e2e_cli_findings.py` for that pattern.

Also covers the documented error paths (`raise ADRLoadError` /
`raise ValueError`) that had no `pytest.raises` coverage anywhere in the
suite before this file.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pytest

import iil_adrfw.cli as cli
from iil_adrfw.persistence import ADRLoadError, load_adr, load_adrs
from iil_adrfw.schemas import get_schema_dir

FIXTURES_DIR = Path(__file__).resolve().parent
SCHEMA_DIR = get_schema_dir()


def _stage_fixtures(dest: Path, *names: str) -> Path:
    """Copy canonical ADR fixtures (+ sibling .rules.yaml) into dest."""
    dest.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy(FIXTURES_DIR / f"{name}.md", dest / f"{name}.md")
        rules = FIXTURES_DIR / f"{name}.rules.yaml"
        if rules.exists():
            shutil.copy(rules, dest / f"{name}.rules.yaml")
    return dest


def _ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


# ─── validate ───────────────────────────────────────────────────


def test_should_report_all_adrs_valid_in_text_mode(tmp_path, capsys):
    adr_dir = _stage_fixtures(tmp_path, "ADR-099-multi-tenancy")
    args = _ns(adr_dir=str(adr_dir), schema_dir=None, json=False)

    assert cli._cmd_validate(args) == 0
    out = capsys.readouterr().out
    assert "ADR Frontmatter Validation: 1/1 (100.0%)" in out
    assert "✓ All ADRs valid" in out


def test_should_emit_valid_json_with_percent_field(tmp_path, capsys):
    adr_dir = _stage_fixtures(tmp_path, "ADR-099-multi-tenancy")
    args = _ns(adr_dir=str(adr_dir), schema_dir=str(SCHEMA_DIR), json=True)

    assert cli._cmd_validate(args) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["passed"] == 1
    assert data["failed"] == 0
    assert data["percent"] == 100.0


def test_should_exit_2_when_adr_dir_is_not_a_directory(tmp_path, capsys):
    missing = tmp_path / "does-not-exist"
    args = _ns(adr_dir=str(missing), schema_dir=None, json=False)

    assert cli._cmd_validate(args) == 2
    assert "is not a directory" in capsys.readouterr().err


def test_should_exit_2_when_no_adr_files_found(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    args = _ns(adr_dir=str(empty), schema_dir=None, json=False)

    assert cli._cmd_validate(args) == 2
    assert "no ADR-*.md files found" in capsys.readouterr().err


def test_should_list_failure_when_frontmatter_is_missing(tmp_path, capsys):
    adr_dir = tmp_path / "adrs"
    adr_dir.mkdir()
    (adr_dir / "ADR-001-broken.md").write_text("# No frontmatter here\n", encoding="utf-8")
    args = _ns(adr_dir=str(adr_dir), schema_dir=None, json=False)

    assert cli._cmd_validate(args) == 1
    out = capsys.readouterr().out
    assert "FAILED (1)" in out
    assert "ADR-001-broken.md" in out


# ─── staleness ──────────────────────────────────────────────────


def test_should_flag_broken_depends_on_reference(tmp_path, capsys):
    # ADR-099 depends_on ADR-087, which is not part of this fixture set.
    adr_dir = _stage_fixtures(tmp_path, "ADR-099-multi-tenancy")
    args = _ns(adr_dir=str(adr_dir), schema_dir=None, months=6, json=False)

    rc = cli._cmd_staleness(args)
    out = capsys.readouterr().out
    assert "Staleness Report: 1 ADRs scanned" in out
    assert "ADR-087" in out
    # depends_on broken refs are severity=warning, so exit stays 0
    assert rc == 0


def test_should_emit_staleness_findings_as_json(tmp_path, capsys):
    adr_dir = _stage_fixtures(tmp_path, "ADR-099-multi-tenancy")
    args = _ns(adr_dir=str(adr_dir), schema_dir=None, months=6, json=True)

    cli._cmd_staleness(args)
    data = json.loads(capsys.readouterr().out)
    assert data["total_adrs"] == 1
    assert any(f["type"] == "broken_ref" and "ADR-087" in f["message"] for f in data["findings"])


def test_should_exit_1_when_superseded_by_reference_is_broken(tmp_path, capsys):
    adr_dir = tmp_path / "adrs"
    _stage_fixtures(adr_dir, "ADR-099-multi-tenancy")
    text = (adr_dir / "ADR-099-multi-tenancy.md").read_text(encoding="utf-8")
    text = text.replace("superseded_by: []", "superseded_by:\n  - ADR-999-does-not-exist")
    (adr_dir / "ADR-099-multi-tenancy.md").write_text(text, encoding="utf-8")
    args = _ns(adr_dir=str(adr_dir), schema_dir=None, months=6, json=False)

    # superseded_by broken refs are severity=error -> exit code 1
    assert cli._cmd_staleness(args) == 1


def test_should_exit_2_when_staleness_adr_dir_missing(tmp_path, capsys):
    missing = tmp_path / "nope"
    args = _ns(adr_dir=str(missing), schema_dir=None, months=6, json=False)

    assert cli._cmd_staleness(args) == 2
    assert "is not a directory" in capsys.readouterr().err


# ─── graph ──────────────────────────────────────────────────────


def test_should_print_text_graph_with_depends_on_edge(tmp_path, capsys):
    adr_dir = _stage_fixtures(tmp_path, "ADR-099-multi-tenancy")
    args = _ns(adr_dir=str(adr_dir), schema_dir=None, dot=False, json=False)

    assert cli._cmd_graph(args) == 0
    out = capsys.readouterr().out
    assert "ADR Dependency Graph: 1 nodes" in out
    assert "depends_on" in out
    assert "ADR-099 → ADR-087" in out


def test_should_emit_dot_format_when_dot_flag_set(tmp_path, capsys):
    adr_dir = _stage_fixtures(tmp_path, "ADR-099-multi-tenancy")
    args = _ns(adr_dir=str(adr_dir), schema_dir=None, dot=True, json=False)

    assert cli._cmd_graph(args) == 0
    out = capsys.readouterr().out
    assert out.startswith("digraph ADR_Dependencies {")
    assert '"ADR-099" -> "ADR-087"' in out


def test_should_emit_graph_as_json_with_node_and_edge_counts(tmp_path, capsys):
    adr_dir = _stage_fixtures(tmp_path, "ADR-099-multi-tenancy")
    args = _ns(adr_dir=str(adr_dir), schema_dir=None, dot=False, json=True)

    cli._cmd_graph(args)
    data = json.loads(capsys.readouterr().out)
    assert data["nodes"] == 1
    assert data["edges"] >= 1
    assert any(r["from"] == "ADR-099" and r["to"] == "ADR-087" for r in data["relationships"])


# ─── export ─────────────────────────────────────────────────────


def test_should_print_markdown_registry_to_stdout(tmp_path, capsys):
    adr_dir = _stage_fixtures(tmp_path, "ADR-099-multi-tenancy")
    args = _ns(adr_dir=str(adr_dir), schema_dir=None, output=None)

    assert cli._cmd_export(args) == 0
    out = capsys.readouterr().out
    assert "# ADR Registry" in out
    assert "ADR-099" in out
    assert "| ID | Title | Status | Date | Domains |" in out


def test_should_write_markdown_registry_to_output_file(tmp_path, capsys):
    adr_dir = _stage_fixtures(tmp_path, "ADR-099-multi-tenancy")
    out_file = tmp_path / "registry.md"
    args = _ns(adr_dir=str(adr_dir), schema_dir=None, output=str(out_file))

    assert cli._cmd_export(args) == 0
    assert "Exported 1 ADRs to" in capsys.readouterr().out
    assert out_file.exists()
    assert "# ADR Registry" in out_file.read_text(encoding="utf-8")


def test_should_exit_2_when_export_adr_dir_missing(tmp_path, capsys):
    missing = tmp_path / "nope"
    args = _ns(adr_dir=str(missing), schema_dir=None, output=None)

    assert cli._cmd_export(args) == 2
    assert "is not a directory" in capsys.readouterr().err


# ─── metrics ────────────────────────────────────────────────────


def test_should_print_controlling_report_without_write_flag(tmp_path, capsys):
    adr_dir = _stage_fixtures(tmp_path, "ADR-099-multi-tenancy")
    args = _ns(adr_dir=str(adr_dir), schema_dir=None, write=False, report=False, json=False)

    assert cli._cmd_metrics(args) == 0
    out = capsys.readouterr().out
    assert "ADR-099" in out


def test_should_write_metrics_into_frontmatter_when_write_flag_set(tmp_path, capsys):
    adr_dir = _stage_fixtures(tmp_path, "ADR-099-multi-tenancy")
    args = _ns(adr_dir=str(adr_dir), schema_dir=None, write=True, report=False, json=False)

    assert cli._cmd_metrics(args) == 0
    out = capsys.readouterr().out
    assert "Metrics written to" in out
    updated = (adr_dir / "ADR-099-multi-tenancy.md").read_text(encoding="utf-8")
    assert "metrics:" in updated


def test_should_emit_metrics_as_json(tmp_path, capsys):
    adr_dir = _stage_fixtures(tmp_path, "ADR-099-multi-tenancy")
    args = _ns(adr_dir=str(adr_dir), schema_dir=None, write=False, report=False, json=True)

    cli._cmd_metrics(args)
    captured = capsys.readouterr().out
    # The controlling report (markdown, no braces) is printed first, then the
    # JSON blob — so the first '{' on its own line marks where JSON starts.
    json_start = captured.index("{")
    data = json.loads(captured[json_start:])
    assert "ADR-099" in data


def test_should_exit_2_when_metrics_adr_dir_missing(tmp_path, capsys):
    missing = tmp_path / "nope"
    args = _ns(adr_dir=str(missing), schema_dir=None, write=False, report=False, json=False)

    assert cli._cmd_metrics(args) == 2
    assert "is not a directory" in capsys.readouterr().err


# ─── list ───────────────────────────────────────────────────────


def test_should_print_adr_count_and_domains_in_text_mode(tmp_path, monkeypatch, capsys):
    adr_dir = _stage_fixtures(tmp_path, "ADR-099-multi-tenancy")
    monkeypatch.setenv("IIL_ADRFW_ADRS_DIR", str(adr_dir))
    args = _ns(json=False)

    assert cli._cmd_list(args) == 0
    out = capsys.readouterr().out
    assert "Constitution: 1 ADRs" in out
    assert "ADR-099" in out
    assert "domains:" in out


def test_should_print_adr_list_as_parseable_json(tmp_path, monkeypatch, capsys):
    adr_dir = _stage_fixtures(tmp_path, "ADR-099-multi-tenancy")
    monkeypatch.setenv("IIL_ADRFW_ADRS_DIR", str(adr_dir))
    args = _ns(json=True)

    assert cli._cmd_list(args) == 0
    data = json.loads(capsys.readouterr().out)
    assert any(a["id"] == "ADR-099" for a in data["adrs"])


# ─── check / explain / query / audit / propose / narrate: presentation
#     layer only, `_do_*` handlers monkeypatched (see PR #17's
#     test_e2e_cli_findings.py for the pattern this follows) ────────


def test_should_print_check_violation_and_exit_1(monkeypatch, capsys):
    from iil_adrfw.server import CheckResponse, ViolationOut

    violation = ViolationOut.model_construct(
        rule_id="ADR-099§R1",
        severity="error",
        file="src/x.py",
        line_start=5,
        line_end=7,
        expected="use TenantManager",
        actual="raw Manager",
        likely_cause="drift",
        semantic_distance=0.5,
        blast_radius=None,
        suggestions=[],
    )
    resp = CheckResponse.model_construct(
        violations=[violation], rules_evaluated=1, files_scanned=1, runtime_ms=2, constitution_loaded=1
    )
    monkeypatch.setattr(cli, "_do_check", lambda req: resp)
    args = _ns(paths=["src/"], rule=None, severity="warning", as_of=None, json=False)

    assert cli._cmd_check(args) == 1
    out = capsys.readouterr().out
    assert "FOUND 1 violation(s):" in out
    assert "[error] ADR-099§R1 at src/x.py:5" in out


def test_should_exit_0_when_check_finds_no_violations(monkeypatch, capsys):
    from iil_adrfw.server import CheckResponse

    resp = CheckResponse.model_construct(
        violations=[], rules_evaluated=3, files_scanned=2, runtime_ms=1, constitution_loaded=1
    )
    monkeypatch.setattr(cli, "_do_check", lambda req: resp)
    args = _ns(paths=["src/"], rule=None, severity="warning", as_of="2024-01-01T00:00:00", json=False)

    assert cli._cmd_check(args) == 0
    assert "OK — no violations" in capsys.readouterr().out


def test_should_print_check_as_json(monkeypatch, capsys):
    from iil_adrfw.server import CheckResponse

    resp = CheckResponse.model_construct(
        violations=[], rules_evaluated=0, files_scanned=0, runtime_ms=0, constitution_loaded=0
    )
    monkeypatch.setattr(cli, "_do_check", lambda req: resp)
    args = _ns(paths=["src/"], rule=["ADR-099§R1"], severity="info", as_of=None, json=True)

    assert cli._cmd_check(args) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["violations"] == []


def test_should_print_explain_output_in_text_mode(monkeypatch, capsys):
    from iil_adrfw.server import ExplainResponse

    resp = ExplainResponse.model_construct(
        rule="Tenant-owned models use TenantManager",
        severity="error",
        why_it_exists="prevents cross-tenant leaks",
        explanation_for_audience="explain me like I'm new",
        correct_examples=["good_code()"],
        common_violations=["bad_code()"],
        last_changed="2024-09-15T00:00:00+00:00",
        blast_radius="high",
    )
    monkeypatch.setattr(cli, "_do_explain", lambda req: resp)
    args = _ns(rule_id="ADR-099/tenant-manager", audience="new_dev", json=False)

    assert cli._cmd_explain(args) == 0
    out = capsys.readouterr().out
    assert "# Tenant-owned models use TenantManager" in out
    assert "## Why" in out
    assert "## Correct examples" in out
    assert "## Common violations" in out
    assert "## Blast radius" in out


def test_should_print_query_citations_in_text_mode(monkeypatch, capsys):
    from iil_adrfw.server import CitationOut, QueryResponse

    citation = CitationOut.model_construct(
        adr_id="ADR-099",
        title="Multi-tenancy",
        status="accepted",
        relevance="high",
        excerpt="...",
        matched_concepts=["tenant_id"],
    )
    resp = QueryResponse.model_construct(
        primary_answer="Use tenant_id as BigIntegerField.",
        citations=[citation],
        open_questions=[],
        confidence=0.9,
        routing="direct",
    )
    monkeypatch.setattr(cli, "_do_query", lambda req: resp)
    args = _ns(question="how do we scope tenants?", domain=None, path=None, json=False)

    assert cli._cmd_query(args) == 0
    out = capsys.readouterr().out
    assert "1 citation(s)" in out
    assert "ADR-099" in out
    assert "concepts: tenant_id" in out


def test_should_print_audit_health_and_exit_1_when_findings_present(monkeypatch, capsys):
    from iil_adrfw.server import AuditResponse, FindingOut, HealthOut

    finding = FindingOut.model_construct(
        auditor="supersession_hygiene",
        severity="warning",
        affected_adrs=["ADR-099"],
        description="dangling reference",
        proposed_resolution="fix the link",
        evidence=[],
    )
    health = HealthOut.model_construct(
        score=0.8,
        internal_consistency=0.9,
        code_alignment=0.7,
        coverage=0.85,
        freshness=0.75,
        supersession_hygiene=0.6,
        issue_counts={"warning": 1},
    )
    resp = AuditResponse.model_construct(auditors_run=["all"], findings=[finding], health=health, runtime_ms=3)
    monkeypatch.setattr(cli, "_do_audit", lambda req: resp)
    args = _ns(auditor=None, as_of=None, json=False)

    assert cli._cmd_audit(args) == 1
    out = capsys.readouterr().out
    assert "health score 0.800" in out
    assert "Findings: 1" in out
    assert "→ fix the link" in out


def test_should_print_propose_frontmatter_and_exit_1_when_blocking(monkeypatch, capsys):
    from iil_adrfw.server import ProposeResponse

    resp = ProposeResponse.model_construct(
        proposed_id="ADR-500",
        frontmatter={"id": "ADR-500", "title": "New rule"},
        body_prompt="Write about X.",
        conflicts=["overlaps with ADR-099"],
        closes_open_questions=[],
        cross_repo_blockers=[],
        blocks_publish=True,
        runtime_ms=1,
    )
    monkeypatch.setattr(cli, "_do_propose", lambda req: resp)
    args = _ns(title="New rule", rationale="a" * 25, domain=["test"], decider=["Achim"], json=False)

    assert cli._cmd_propose(args) == 1
    out = capsys.readouterr().out
    assert "Proposed ADR: ADR-500" in out
    assert "BLOCKS publish" in out


def test_should_print_narrate_markdown_by_default(monkeypatch, capsys):
    from iil_adrfw.server import NarrateResponse

    resp = NarrateResponse.model_construct(
        audience="senior",
        title="Multi-tenancy",
        intro="intro text",
        sections=[],
        adr_ids_covered=["ADR-099"],
        markdown="# Multi-tenancy\n\nSome narrative body.",
        runtime_ms=1,
    )
    monkeypatch.setattr(cli, "_do_narrate", lambda req: resp)
    args = _ns(audience="senior", domain=None, id_set=["ADR-099"], path_filter=None, scope_label="x", json=False)

    assert cli._cmd_narrate(args) == 0
    assert capsys.readouterr().out == "# Multi-tenancy\n\nSome narrative body.\n"


def test_should_exit_2_when_narrate_has_no_selectors(capsys):
    args = _ns(audience="senior", domain=None, id_set=[], path_filter=None, scope_label="x", json=False)

    assert cli._cmd_narrate(args) == 2
    assert "at least one of --domain, --id, --path-filter required" in capsys.readouterr().err


# ─── diff: unknown mode (cli-level branch, server.py raise is exercised
#     separately below via _do_diff directly) ─────────────────────


def test_should_exit_2_on_unknown_diff_mode(capsys):
    args = _ns(mode="bogus", json=False)

    assert cli._cmd_diff(args) == 2
    assert "unknown mode: bogus" in capsys.readouterr().err


# ─── documented raise sites: persistence.load_adr / load_adrs ──


def test_should_raise_adrloaderror_when_frontmatter_block_is_missing(tmp_path):
    md = tmp_path / "ADR-001-no-frontmatter.md"
    md.write_text("# Just a heading, no --- frontmatter ---\n", encoding="utf-8")

    with pytest.raises(ADRLoadError, match="missing YAML frontmatter"):
        load_adr(md, SCHEMA_DIR)


def test_should_raise_adrloaderror_when_frontmatter_fails_schema_validation(tmp_path):
    md = tmp_path / "ADR-002-invalid.md"
    # 'id' and 'decision_date' are present but required fields like 'status',
    # 'title', 'deciders' etc. are missing -> Draft202012Validator must fail.
    md.write_text(
        "---\nid: ADR-002\ndecision_date: '2024-01-01'\n---\n\n# ADR-002\n",
        encoding="utf-8",
    )

    with pytest.raises(ADRLoadError, match="frontmatter validation failed"):
        load_adr(md, SCHEMA_DIR)


def test_should_raise_adrloaderror_when_rules_file_adr_id_mismatches_parent(tmp_path):
    adr_dir = _stage_fixtures(tmp_path, "ADR-099-multi-tenancy")
    rules_path = adr_dir / "ADR-099-multi-tenancy.rules.yaml"
    text = rules_path.read_text(encoding="utf-8")
    assert "adr_id: ADR-099" in text
    rules_path.write_text(text.replace("adr_id: ADR-099", "adr_id: ADR-777"), encoding="utf-8")

    with pytest.raises(ADRLoadError, match="does not match parent ADR"):
        load_adrs(adr_dir, SCHEMA_DIR, validate=True)


# ─── documented raise sites: server._do_diff (ValueError) ──────


def test_should_raise_valueerror_when_diff_mode_is_unknown():
    from iil_adrfw.server import DiffRequest, _do_diff

    req = DiffRequest.model_construct(mode="bogus", left_time=None, right_time=None, right_dir=None)
    with pytest.raises(ValueError, match="unknown mode: bogus"):
        _do_diff(req)


def test_should_raise_valueerror_when_temporal_diff_missing_times():
    from iil_adrfw.server import DiffRequest, _do_diff

    req = DiffRequest.model_construct(mode="temporal", left_time=None, right_time=None, right_dir=None)
    with pytest.raises(ValueError, match="temporal mode requires left_time and right_time"):
        _do_diff(req)


def test_should_raise_valueerror_when_set_diff_right_dir_missing(tmp_path, monkeypatch):
    from iil_adrfw.server import DiffRequest, _do_diff

    monkeypatch.setenv("IIL_ADRFW_ADRS_DIR", str(_stage_fixtures(tmp_path, "ADR-099-multi-tenancy")))
    req = DiffRequest.model_construct(
        mode="set", right_dir=None, left_time=None, right_time=None, left_label="left", right_label="right"
    )
    with pytest.raises(ValueError, match="set mode requires right_dir"):
        _do_diff(req)


def test_should_raise_valueerror_when_set_diff_right_dir_does_not_exist(tmp_path, monkeypatch):
    from iil_adrfw.server import DiffRequest, _do_diff

    monkeypatch.setenv("IIL_ADRFW_ADRS_DIR", str(_stage_fixtures(tmp_path, "ADR-099-multi-tenancy")))
    req = DiffRequest(mode="set", right_dir=str(tmp_path / "nonexistent-right-side"))
    with pytest.raises(ValueError, match="right_dir does not exist"):
        _do_diff(req)


# ─── documented raise sites: server._do_explain / _do_validate_cross_repo /
#     _do_query (ValueError) ─────────────────────────────────────


def test_should_raise_valueerror_when_explain_rule_id_unknown(tmp_path, monkeypatch):
    from iil_adrfw.server import ExplainRequest, _do_explain

    monkeypatch.setenv("IIL_ADRFW_ADRS_DIR", str(_stage_fixtures(tmp_path, "ADR-099-multi-tenancy")))
    req = ExplainRequest(rule_id="ADR-999/no-such-rule", audience="senior")
    with pytest.raises(ValueError, match="not found in constitution"):
        _do_explain(req)


def test_should_raise_valueerror_when_validate_cross_repo_adr_id_is_invalid(tmp_path, monkeypatch):
    from iil_adrfw.server import ValidateCrossRepoRequest, _do_validate_cross_repo

    monkeypatch.setenv("IIL_ADRFW_ADRS_DIR", str(_stage_fixtures(tmp_path, "ADR-099-multi-tenancy")))
    req = ValidateCrossRepoRequest(adr_id="ADR-9999-invalid", consumer_repos=[])
    with pytest.raises(ValueError, match="not found in constitution"):
        _do_validate_cross_repo(req)


def test_should_raise_valueerror_when_query_has_no_selectors(tmp_path, monkeypatch):
    from iil_adrfw.server import QueryRequest, _do_query

    monkeypatch.setenv("IIL_ADRFW_ADRS_DIR", str(_stage_fixtures(tmp_path, "ADR-099-multi-tenancy")))
    req = QueryRequest(question=None, domain=None, path=None)
    with pytest.raises(ValueError, match="At least one of question/domain/path must be provided"):
        _do_query(req)
