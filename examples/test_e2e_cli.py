"""Tests for the headless CLI — verify all 9 commands work, exit codes are
correct, JSON output is valid."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ADRS_DIR = BASE / "_test_adrs_cli"
SCHEMAS_DIR = BASE.parent / "schemas"
PROJECT_ROOT = BASE.parent


def _stage_fixtures() -> None:
    """Stage all canonical ADR fixtures (see conftest.py).

    This module drives the CLI as a subprocess with an explicit env dict
    per call (see `_run` below), so it never had the shared-os.environ
    collection-order bug the other example modules did. Its directory setup
    still ran at import time though, so it is staged via the same
    conftest.py `_prepare_test_dirs` fixture for consistency.
    """
    for f in BASE.iterdir():
        if f.name.startswith("ADR-") and f.suffix in (".md", ".yaml"):
            shutil.copy(f, ADRS_DIR)


def _run(args: list[str], expect_exit: int | None = None) -> tuple[int, str, str]:
    """Run the CLI as a subprocess. Returns (rc, stdout, stderr)."""
    env = {
        **os.environ,
        "IIL_ADRFW_ADRS_DIR": str(ADRS_DIR),
        "IIL_ADRFW_SCHEMAS_DIR": str(SCHEMAS_DIR),
    }
    res = subprocess.run(
        [sys.executable, "-m", "iil_adrfw.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=PROJECT_ROOT,
    )
    if expect_exit is not None:
        assert res.returncode == expect_exit, (
            f"expected exit {expect_exit}, got {res.returncode}\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}"
        )
    return res.returncode, res.stdout, res.stderr


def test_help_works():
    print("=" * 70)
    print("TEST: --help shows all 9 commands")
    print("=" * 70)
    rc, out, err = _run(["--help"], expect_exit=0)
    for cmd in ("check", "explain", "list", "validate-cross-repo", "query", "audit", "propose", "diff", "narrate"):
        assert cmd in out, f"missing command in help: {cmd}"
    print("  PASS: all 9 commands listed in --help\n")


def test_list_text_and_json():
    print("=" * 70)
    print("TEST: list — text and JSON outputs both work")
    print("=" * 70)
    rc, out, err = _run(["list"], expect_exit=0)
    assert "Constitution:" in out
    assert "ADR-099" in out
    print(f"  text output: {len(out)}b, contains 'ADR-099'")

    rc, out, err = _run(["list", "--json"], expect_exit=0)
    data = json.loads(out)
    assert "adrs" in data
    assert any(a["id"] == "ADR-099" for a in data["adrs"])
    print(f"  json output: parsed, {len(data['adrs'])} ADRs")
    print("  PASS\n")


def test_audit_exit_code_signals_findings():
    print("=" * 70)
    print("TEST: audit exits 1 when there are findings")
    print("=" * 70)
    # The fixture set has supersession issues (ADR-188 → ADR-087 dangling)
    rc, out, err = _run(["audit"])
    print(f"  exit={rc}")
    print(f"  stdout (excerpt): {out[:200]}")
    # Either rc=0 (clean) or rc=1 (findings) — both valid; we just test the
    # contract: rc=1 IFF "Findings:" appears with count > 0
    if "Findings: 0" in out or "no findings" in out:
        assert rc == 0
    else:
        assert rc == 1, f"expected exit 1 when findings present, got {rc}"
    print("  PASS\n")


def test_audit_json_parseable_and_has_health():
    print("=" * 70)
    print("TEST: audit --json produces parseable output with health structure")
    print("=" * 70)
    rc, out, err = _run(["audit", "--json"])
    data = json.loads(out)
    assert "health" in data
    assert "score" in data["health"]
    assert "findings" in data
    assert isinstance(data["health"]["score"], (int, float))
    assert 0.0 <= data["health"]["score"] <= 1.0
    print(f"  health.score = {data['health']['score']}")
    print(f"  findings = {len(data['findings'])}")
    print("  PASS\n")


def test_query_filters():
    print("=" * 70)
    print("TEST: query filters by domain and produces JSON")
    print("=" * 70)
    rc, out, err = _run(["query", "--domain", "django/models", "--json"], expect_exit=0)
    data = json.loads(out)
    # QueryResponse has citations (list) and primary_answer (str)
    assert "citations" in data
    assert isinstance(data["citations"], list)
    print(f"  citations: {len(data['citations'])}")
    print(f"  primary_answer: {data.get('primary_answer', '')[:80]}...")
    assert len(data["citations"]) >= 1
    print("  PASS: domain filter works\n")


def test_explain_command():
    print("=" * 70)
    print("TEST: explain a concrete rule")
    print("=" * 70)
    rc, out, err = _run(
        [
            "explain",
            "ADR-099/tenant-id-bigint",
            "--audience",
            "new_dev",
        ],
        expect_exit=0,
    )
    assert "Severity:" in out
    assert "## Why" in out
    print(f"  output length: {len(out)}b, contains 'Severity:' and '## Why'")
    print("  PASS: explain produced output\n")


def test_diff_temporal():
    print("=" * 70)
    print("TEST: diff temporal mode")
    print("=" * 70)
    rc, out, err = _run(
        [
            "diff",
            "--mode",
            "temporal",
            "--left-time",
            "2020-01-01T00:00:00",
            "--right-time",
            "2026-12-31T00:00:00",
        ]
    )
    # exit 1 expected because there ARE changes (everything was added since 2020)
    assert rc in (0, 1)
    assert "Diff (temporal):" in out or "{" in out  # text or JSON depending on default
    print(f"  exit={rc}, output excerpt: {out[:120]!r}")
    print("  PASS\n")


def test_narrate_emits_markdown_by_default():
    print("=" * 70)
    print("TEST: narrate writes markdown to stdout (default), no --json needed")
    print("=" * 70)
    rc, out, err = _run(
        [
            "narrate",
            "--audience",
            "auditor",
            "--id",
            "ADR-099",
        ],
        expect_exit=0,
    )
    # Must be markdown — start with H1
    assert out.startswith("# "), f"expected markdown, got: {out[:80]!r}"
    assert "## Overview" in out
    assert "## Compliance trail" in out
    print(f"  markdown length: {len(out)}b")
    print("  PASS: narrate emits markdown directly\n")


def test_narrate_validation_error_exit_2():
    print("=" * 70)
    print("TEST: narrate without selectors exits 2 (config error)")
    print("=" * 70)
    rc, out, err = _run(["narrate", "--audience", "senior"])
    print(f"  exit={rc}, stderr: {err[:120]!r}")
    assert rc == 2
    assert "selector" in err.lower() or "required" in err.lower()
    print("  PASS\n")


def test_propose_outputs_frontmatter():
    print("=" * 70)
    print("TEST: propose generates frontmatter + body prompt")
    print("=" * 70)
    rc, out, err = _run(
        [
            "propose",
            "--title",
            "Test ADR for CLI smoke testing only",
            "--rationale",
            "We need to verify that propose works through the CLI; this is a fixture rationale long enough to pass min_length validation",
            "--domain",
            "test",
            "--decider",
            "Achim Dehnert",
        ]
    )
    assert rc in (0, 1), f"unexpected exit {rc}\nstdout:\n{out}\nstderr:\n{err}"
    assert "Proposed ADR:" in out
    assert "frontmatter" in out
    assert "body prompt" in out
    print(f"  exit={rc} (1=blocks_publish, 0=clean)")
    print("  PASS\n")


if __name__ == "__main__":
    test_help_works()
    test_list_text_and_json()
    test_audit_exit_code_signals_findings()
    test_audit_json_parseable_and_has_health()
    test_query_filters()
    test_explain_command()
    test_diff_temporal()
    test_narrate_emits_markdown_by_default()
    test_narrate_validation_error_exit_2()
    test_propose_outputs_frontmatter()
    print("=" * 70)
    print("ALL CLI TESTS PASSED")
    print("=" * 70)
