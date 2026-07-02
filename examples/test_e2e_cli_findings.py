"""Regression tests for CLI text output when findings exist.

Both paths crashed until 2026-07-02 because they printed non-existent response
fields (fixed in #16). In-process: the `_do_*` handlers are monkeypatched so
only the presentation layer is under test.
"""

import argparse

import iil_adrfw.cli as cli
from iil_adrfw.schemas import get_schema_dir
from iil_adrfw.server import (
    CheckResponse,
    ConflictOut,
    ValidateCrossRepoResponse,
    ViolationOut,
)


def _violation() -> ViolationOut:
    return ViolationOut.model_construct(
        rule_id="ADR-001§R1",
        severity="error",
        file="src/x.py",
        line_start=10,
        line_end=12,
        expected="use load_adrs()",
        actual="manual frontmatter parse",
        likely_cause="drift",
        semantic_distance=0.8,
        blast_radius=None,
        suggestions=[],
    )


def _conflict() -> ConflictOut:
    return ConflictOut.model_construct(
        rule_id="ADR-002§R3",
        conflict_class="class1",
        confidence="high",
        claim="all repos use structlog",
        reality="repo X uses logging",
        affected_repos=["x"],
        suggestion="migrate",
        blocks_publish=True,
        evidence_count=1,
        evidence_preview=[],
    )


def test_should_print_check_violations_in_text_mode(monkeypatch, capsys):
    resp = CheckResponse.model_construct(
        files_scanned=1,
        rules_evaluated=1,
        runtime_ms=5,
        constitution_loaded=3,
        violations=[_violation()],
    )
    monkeypatch.setattr(cli, "_do_check", lambda req: resp)
    args = argparse.Namespace(paths=["src/"], rule=None, severity="info", as_of=None, json=False)

    assert cli._cmd_check(args) == 1
    out = capsys.readouterr().out
    assert "FOUND 1 violation(s):" in out
    assert "[error] ADR-001§R1 at src/x.py:10" in out
    assert "expected: use load_adrs()" in out
    assert "actual:   manual frontmatter parse" in out


def test_should_exit_zero_and_print_ok_without_violations(monkeypatch, capsys):
    resp = CheckResponse.model_construct(
        files_scanned=2, rules_evaluated=4, runtime_ms=3, constitution_loaded=3, violations=[]
    )
    monkeypatch.setattr(cli, "_do_check", lambda req: resp)
    args = argparse.Namespace(paths=["src/"], rule=None, severity="info", as_of=None, json=False)

    assert cli._cmd_check(args) == 0
    assert "OK — no violations" in capsys.readouterr().out


def test_should_print_cross_repo_conflicts_in_text_mode(monkeypatch, capsys):
    resp = ValidateCrossRepoResponse.model_construct(
        adr_id="ADR-002",
        consumer_repos_scanned=["x"],
        repos_unreachable=["y"],
        class1_count=1,
        class2_count=0,
        class3_count=0,
        conflicts=[_conflict()],
        has_blocking_conflicts=True,
    )
    monkeypatch.setattr(cli, "_do_validate_cross_repo", lambda req: resp)
    args = argparse.Namespace(adr_id="ADR-002", repos=["x=/tmp/x", "y=/tmp/y"], json=False)

    assert cli._cmd_validate_cross_repo(args) == 1
    out = capsys.readouterr().out
    assert "[class1/high] ADR-002§R3: all repos use structlog" in out
    assert "repos unreachable: y" in out
    assert "⚠ Has blocking conflicts." in out


def test_should_reject_malformed_repo_spec_with_exit_2(capsys):
    args = argparse.Namespace(adr_id="ADR-002", repos=["missing-equals-sign"], json=False)
    assert cli._cmd_validate_cross_repo(args) == 2
    assert "expects NAME=PATH" in capsys.readouterr().err


def test_should_expose_bundled_schema_dir():
    schema_dir = get_schema_dir()
    assert schema_dir.is_dir()
    assert list(schema_dir.glob("*.json")), "bundled schemas missing"
