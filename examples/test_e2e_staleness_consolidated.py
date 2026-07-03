"""Tests for the consolidated staleness implementation (issue #19 / B-2 + B-18).

`_do_staleness` is now the single source of truth shared by the CLI
(`_cmd_staleness`) and the MCP tool (`adr_staleness`). These tests cover the
unified field coverage (superseded_by / depends_on / related broken refs), the
`load_errors` reporting that replaced the silent `except: continue` (B-18), and
CLI↔server output consistency.
"""

from __future__ import annotations

import argparse
import json

import iil_adrfw.cli as cli
from iil_adrfw.schemas import get_schema_dir
from iil_adrfw.server import StalenessRequest, _do_staleness, adr_staleness

SCHEMA_DIR = get_schema_dir()

_FM = """\
---
id: {id}
title: {title}
status: {status}
decision_date: {date}
deciders:
  - "t <t@example.com>"
domains:
  - general
{extra}
---

# {id}

Body.
"""


def _write(adrs, adr_id, title="X", status="accepted", date="2026-01-01", extra=""):
    (adrs / f"{adr_id}-x.md").write_text(
        _FM.format(id=adr_id, title=title, status=status, date=date, extra=extra), encoding="utf-8"
    )


def test_should_flag_broken_superseded_by_depends_on_and_related_refs(tmp_path):
    adrs = tmp_path / "adrs"
    adrs.mkdir()
    _write(adrs, "ADR-0001", extra="superseded_by:\n  - ADR-9001\ndepends_on:\n  - ADR-9002\nrelated:\n  - ADR-9003")
    resp = _do_staleness(adrs, SCHEMA_DIR, months=6)
    by_sev = {(f["severity"], f["message"].split()[0]) for f in resp.findings if f["type"] == "broken_ref"}
    # superseded_by -> error, depends_on -> warning, related -> info
    assert ("error", "superseded_by") in by_sev
    assert ("warning", "depends_on") in by_sev
    assert ("info", "related") in by_sev
    assert resp.broken_refs == 3


def test_should_include_threshold_in_stale_message(tmp_path):
    adrs = tmp_path / "adrs"
    adrs.mkdir()
    _write(adrs, "ADR-0001", date="2020-01-01")  # very old
    resp = _do_staleness(adrs, SCHEMA_DIR, months=6)
    stale = [f for f in resp.findings if f["type"] == "stale"]
    assert stale and "threshold: 6mo" in stale[0]["message"]


def test_should_report_corrupt_file_as_load_error_not_silently_skip(tmp_path):
    adrs = tmp_path / "adrs"
    adrs.mkdir()
    _write(adrs, "ADR-0001")  # valid
    (adrs / "ADR-0002-broken.md").write_text("no frontmatter here\n", encoding="utf-8")
    resp = _do_staleness(adrs, SCHEMA_DIR, months=6)
    assert resp.total_adrs == 2
    assert len(resp.load_errors) == 1
    assert resp.load_errors[0]["file"] == "ADR-0002-broken.md"


def test_should_produce_identical_findings_from_cli_and_mcp_tool(tmp_path, monkeypatch):
    adrs = tmp_path / "adrs"
    adrs.mkdir()
    _write(adrs, "ADR-0001", date="2020-01-01", extra="depends_on:\n  - ADR-9002")

    # MCP tool path
    monkeypatch.setenv("IIL_ADRFW_ADRS_DIR", str(adrs))
    monkeypatch.setenv("IIL_ADRFW_REPO_ROOT", str(tmp_path))
    mcp_resp = adr_staleness(StalenessRequest(adr_dir=str(adrs), months=6))

    # CLI path (captured JSON)
    args = argparse.Namespace(adr_dir=str(adrs), schema_dir=None, months=6, json=True)
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli._cmd_staleness(args)
    cli_json = json.loads(buf.getvalue())

    assert cli_json["findings"] == mcp_resp.findings
    assert cli_json["stale_count"] == mcp_resp.stale_count
    assert cli_json["broken_refs"] == mcp_resp.broken_refs


def test_should_exit_1_from_cli_only_on_error_severity(tmp_path, capsys):
    adrs = tmp_path / "adrs"
    adrs.mkdir()
    # depends_on broken ref is severity=warning -> exit 0
    _write(adrs, "ADR-0001", extra="depends_on:\n  - ADR-9002")
    args = argparse.Namespace(adr_dir=str(adrs), schema_dir=None, months=6, json=False)
    assert cli._cmd_staleness(args) == 0

    # superseded_by broken ref is severity=error -> exit 1
    _write(adrs, "ADR-0002", extra="superseded_by:\n  - ADR-9001")
    args2 = argparse.Namespace(adr_dir=str(adrs), schema_dir=None, months=6, json=False)
    assert cli._cmd_staleness(args2) == 1
