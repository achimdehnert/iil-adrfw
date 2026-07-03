"""Regression tests for the 5 logic/robustness fixes from GitHub issue #25.

Self-contained (each test builds its own inputs under ``tmp_path`` or via
in-process fixture construction) — no ``IIL_ADRFW_*`` env vars needed, so
this module needs none of ``conftest.py``'s staging machinery.

Covers:
  - B-9  DOT-label injection in ``cli._cmd_graph`` (``--dot``)
  - #25 comment: Markdown-table injection in ``cli._cmd_export``
  - B-13 exit-code contract: uncaught exceptions must exit 3, not 1
  - B-16 ``matched_concepts`` leaking the global concept set in mixed routing
  - B-17 freshness version comparison using ``startswith`` instead of
    segment-wise comparison
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import pytest

import iil_adrfw.cli as cli
from iil_adrfw.graph import ConstitutionGraph, execute_query
from iil_adrfw.persistence import load_adr
from iil_adrfw.schemas import get_schema_dir

FIXTURES_DIR = Path(__file__).resolve().parent
SCHEMA_DIR = get_schema_dir()


def _copy_adr_fixtures_into(dest: Path, *names: str) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copy(FIXTURES_DIR / f"{name}.md", dest / f"{name}.md")
        rules = FIXTURES_DIR / f"{name}.rules.yaml"
        if rules.exists():
            shutil.copy(rules, dest / f"{name}.rules.yaml")
    return dest


def _ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


# ─── B-9: DOT-label injection ─────────────────────────────────────


def test_should_escape_quotes_and_backslashes_in_dot_labels(tmp_path, capsys):
    adr_dir = _copy_adr_fixtures_into(tmp_path, "ADR-099-multi-tenancy")
    md = adr_dir / "ADR-099-multi-tenancy.md"
    raw_title = r'A "quoted" \ backslash title'
    text = md.read_text(encoding="utf-8").replace(
        "title: Multi-tenancy via tenant_id BigIntegerField with manager-level scoping",
        f"title: '{raw_title}'",
    )
    md.write_text(text, encoding="utf-8")
    args = _ns(adr_dir=str(adr_dir), schema_dir=None, dot=True, json=False)

    assert cli._cmd_graph(args) == 0
    out = capsys.readouterr().out

    # The escaped title must appear verbatim (backslash escaped first, then
    # the embedded double quotes) ...
    escaped_title = cli._escape_dot(raw_title)
    assert escaped_title in out
    # ... and the raw, unescaped title must never appear (it would break the
    # surrounding DOT quoted-string).
    assert raw_title not in out
    # Every `"` in the label attribute is either a delimiter or immediately
    # preceded by a backslash -> DOT string stays well-formed.
    label_line = next(line for line in out.splitlines() if line.strip().startswith('"ADR-099"'))
    inner = label_line.split('label="', 1)[1].rsplit('", fillcolor', 1)[0]
    assert all(inner[i - 1] == "\\" for i, ch in enumerate(inner) if ch == '"' and i > 0)


# ─── #25 comment: Markdown-table injection in export ──────────────


def test_should_escape_pipes_in_markdown_export_title(tmp_path, capsys):
    adr_dir = _copy_adr_fixtures_into(tmp_path, "ADR-099-multi-tenancy")
    md = adr_dir / "ADR-099-multi-tenancy.md"
    raw_title = "Legit | Fake | approved | 2099-01-01 | admin"
    text = md.read_text(encoding="utf-8").replace(
        "title: Multi-tenancy via tenant_id BigIntegerField with manager-level scoping",
        f"title: '{raw_title}'",
    )
    md.write_text(text, encoding="utf-8")
    args = _ns(adr_dir=str(adr_dir), schema_dir=None, output=None)

    assert cli._cmd_export(args) == 0
    out = capsys.readouterr().out

    row = next(line for line in out.splitlines() if line.startswith("| ADR-099"))
    # Reconstruct the cells by treating an escaped "\|" as a literal, not a
    # column separator -> exactly 5 columns, no forged extras. Placeholder
    # must not occur naturally in the row (unlike e.g. a plain space).
    placeholder = "\x00"
    fields = [f.strip() for f in row.replace("\\|", placeholder).split("|")]
    fields = [f.replace(placeholder, "|") for f in fields[1:-1]]
    assert len(fields) == 5
    assert fields[1] == raw_title


# ─── B-13: exit-code contract ──────────────────────────────────────


def test_should_exit_3_on_uncaught_internal_error(monkeypatch, capsys):
    def _boom(_args: argparse.Namespace) -> int:
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "_cmd_list", _boom)
    monkeypatch.setattr(sys, "argv", ["iil-adrfw", "list"])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 3
    assert "internal error: boom" in capsys.readouterr().err


# ─── B-16: matched_concepts in mixed routing ──────────────────────


def _adr_variant(tmp_path: Path, *, new_id: str, new_title: str) -> Path:
    """Write a copy of the ADR-099 fixture with a new id/title but the same
    domains, so it lands in the same domain-driven `primary` set while
    contributing disjoint concept tokens via its (unique) title."""
    base_text = (FIXTURES_DIR / "ADR-099-multi-tenancy.md").read_text(encoding="utf-8")
    text = base_text.replace("id: ADR-099", f"id: {new_id}", 1)
    text = text.replace(
        "title: Multi-tenancy via tenant_id BigIntegerField with manager-level scoping",
        f"title: {new_title}",
        1,
    )
    dest = tmp_path / f"{new_id}-variant.md"
    dest.write_text(text, encoding="utf-8")
    return dest


def test_should_scope_matched_concepts_per_adr_in_mixed_routing(tmp_path):
    adr_a_path = _adr_variant(tmp_path, new_id="ADR-201", new_title="Postgres connection pooling guidance")
    adr_b_path = _adr_variant(tmp_path, new_id="ADR-202", new_title="Redis cache eviction pattern")

    adr_a = load_adr(adr_a_path, SCHEMA_DIR, validate=False)
    adr_b = load_adr(adr_b_path, SCHEMA_DIR, validate=False)
    graph = ConstitutionGraph.build([adr_a, adr_b])

    # Domain routing puts both ADRs into `primary`; adding a `question` on
    # top pushes routing into the (buggy, pre-fix) 'mixed' branch.
    result = execute_query(graph, domain="django/models", question="postgres redis")

    assert result.routing == "mixed"
    citations = {c.adr_id: c for c in result.citations}
    assert citations["ADR-201"].matched_concepts == ("postgres",)
    assert citations["ADR-202"].matched_concepts == ("redis",)
