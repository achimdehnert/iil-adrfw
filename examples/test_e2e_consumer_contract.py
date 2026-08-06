"""Consumer-facing contract tests (v0.8.0).

These lock in the guarantees a *consuming repo* depends on. Each one maps to a
defect that was live in the fleet before 0.8.0:

- meiki-hub and ttz-hub ran `iil-adrfw audit --adr-dir docs/adr` nightly. `audit`
  had no such flag, argparse exited 2 with empty stdout, and the workflow's
  "no JSON output" branch turned that into a green, no-op run for months.
- The pre-0.8 default ADR directory was `./adrs`, which no fleet repo uses, so an
  unset env var produced an empty constitution reporting `health score 1.000`.
- `_schemas_dir()` resolved to `<prefix>/lib/pythonX.Y/schemas`, a path that never
  exists in a pip install, breaking every env-var-driven subcommand and all 12
  MCP tools unless the caller also set IIL_ADRFW_SCHEMAS_DIR.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from iil_adrfw import api, cli

SRC_DIR = Path(__file__).resolve().parent.parent / "src"

ADR_BODY = """---
id: ADR-001
title: Probe ADR
status: accepted
decision_date: 2026-01-01
owner: probe
domains: [testing]
---
# Context
Probe.
"""

# Subcommands that used to be reachable only via $IIL_ADRFW_ADRS_DIR.
ENV_ONLY_SUBCOMMANDS = ["audit", "list", "query", "narrate", "explain", "propose"]


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Never let an ambient IIL_ADRFW_* leak in — these tests are about defaults."""
    monkeypatch.delenv("IIL_ADRFW_ADRS_DIR", raising=False)
    monkeypatch.delenv("IIL_ADRFW_SCHEMAS_DIR", raising=False)


@pytest.fixture
def adr_repo(tmp_path: Path) -> Path:
    """A minimal consumer repo laid out the way every fleet repo lays them out."""
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-001-probe.md").write_text(ADR_BODY, encoding="utf-8")
    return tmp_path


def _child_env() -> dict[str, str]:
    """Inherit the real environment, minus the IIL_ADRFW_* vars under test."""
    env = dict(os.environ)
    env.pop("IIL_ADRFW_ADRS_DIR", None)
    env.pop("IIL_ADRFW_SCHEMAS_DIR", None)
    env["PYTHONPATH"] = str(SRC_DIR)
    return env


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """Invoke the CLI the way a consumer's CI does — a real subprocess."""
    return subprocess.run(
        [sys.executable, "-m", "iil_adrfw.cli", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        env=_child_env(),
    )


@pytest.mark.parametrize("subcommand", ENV_ONLY_SUBCOMMANDS)
def test_should_accept_adr_dir_flag_on_every_subcommand(subcommand):
    """--adr-dir is the one uniform way to point any subcommand at a constitution."""
    parser_help = subprocess.run(
        [sys.executable, "-m", "iil_adrfw.cli", subcommand, "--help"],
        capture_output=True,
        text=True,
        env=_child_env(),
    )
    assert "--adr-dir" in parser_help.stdout


def test_should_exit_2_when_constitution_is_empty(tmp_path):
    """An empty constitution is a configuration error, never a clean bill of health."""
    (tmp_path / "docs" / "adr").mkdir(parents=True)

    result = _run(tmp_path, "audit")

    assert result.returncode == 2
    assert "empty constitution" in result.stderr
    assert "health score" not in result.stdout


def test_should_exit_2_when_adr_dir_does_not_exist(tmp_path):
    result = _run(tmp_path, "audit")

    assert result.returncode == 2
    assert "does not exist" in result.stderr


def test_should_allow_empty_constitution_when_opted_in(tmp_path):
    """--allow-empty is the explicit escape hatch for repos with zero ADRs yet."""
    (tmp_path / "docs" / "adr").mkdir(parents=True)

    result = _run(tmp_path, "audit", "--allow-empty")

    assert result.returncode == 0


def test_should_audit_via_adr_dir_flag(adr_repo):
    """The exact invocation the fleet nightly workflows already use."""
    result = _run(adr_repo, "audit", "--adr-dir", "docs/adr", "--json")

    assert result.returncode == 0, result.stderr
    assert "health" in result.stdout


def test_should_default_to_docs_adr(adr_repo):
    """No flag, no env var — find the layout every ADR-carrying repo uses."""
    result = _run(adr_repo, "list")

    assert result.returncode == 0, result.stderr
    assert "ADR-001" in result.stdout


def test_should_keep_positional_adr_dir_working(adr_repo):
    """Backwards compatibility: documented positional invocations still work."""
    result = _run(adr_repo, "validate", "docs/adr")

    assert result.returncode == 0, result.stderr
    assert "1/1" in result.stdout


def test_should_resolve_bundled_schemas_without_env_var():
    """A pip-installed consumer must not have to set IIL_ADRFW_SCHEMAS_DIR."""
    schemas_dir = api._schemas_dir()

    assert schemas_dir.is_dir()
    assert (schemas_dir / "adr_frontmatter.schema.json").is_file()


def test_should_honour_schemas_dir_override(tmp_path, monkeypatch):
    monkeypatch.setenv("IIL_ADRFW_SCHEMAS_DIR", str(tmp_path))

    assert api._schemas_dir() == tmp_path.resolve()


def test_should_default_adrs_dir_to_docs_adr():
    """The pre-0.8 default (./adrs) matched no repo in the fleet."""
    assert api._adrs_dir() == (Path.cwd() / "docs" / "adr").resolve()


def test_should_expose_freshness_and_impact_as_subcommands(adr_repo):
    """The CLI covers the MCP tool surface — these two had no CLI equivalent."""
    for subcommand, extra in (("freshness", ["--repo-path", "."]), ("impact", ["docs/adr/ADR-001-probe.md"])):
        result = _run(adr_repo, subcommand, *extra)
        assert result.returncode in (0, 1), f"{subcommand}: {result.stderr}"


def test_should_import_core_without_fastmcp(tmp_path):
    """`iil_adrfw.api` and the CLI must not drag the MCP transport into a CI install.

    Runs in a subprocess with `fastmcp` blocked at the import hook: reloading
    modules in-process would leave rebound pydantic classes behind and make the
    suite order-dependent, which this repo forbids (pytest-randomly).
    """
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import sys\n"
        "class _Block:\n"
        "    def find_module(self, name, path=None):\n"
        "        return self if name.split('.')[0] == 'fastmcp' else None\n"
        "    def load_module(self, name):\n"
        "        raise ImportError('fastmcp is blocked for this probe')\n"
        "sys.meta_path.insert(0, _Block())\n"
        "import iil_adrfw, iil_adrfw.api, iil_adrfw.cli\n"
        "assert 'fastmcp' not in sys.modules\n"
        "print('ok')\n",
        encoding="utf-8",
    )

    result = subprocess.run([sys.executable, str(probe)], capture_output=True, text=True, env=_child_env())

    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_should_reexport_public_api_at_top_level():
    """One import for the common case, stable across internal refactors."""
    import iil_adrfw

    for name in ("load_adrs", "load_adr", "get_schema_dir", "ConstitutionGraph", "run_audit", "ADR", "Status"):
        assert hasattr(iil_adrfw, name), name
        assert name in iil_adrfw.__all__


def test_should_ship_typing_marker():
    """py.typed makes the strict-typed internals usable by typed consumers."""
    import iil_adrfw

    assert (Path(iil_adrfw.__file__).parent / "py.typed").is_file()


def test_should_keep_server_reexports_for_backwards_compatibility():
    """Pre-0.8 code imported models and handlers from iil_adrfw.server."""
    pytest.importorskip("fastmcp")
    from iil_adrfw import server

    for name in ("AuditRequest", "ProposeRequest", "DecisionDriverIn", "_do_audit", "_do_propose"):
        assert hasattr(server, name), name


def test_should_keep_cli_exit_code_contract(adr_repo):
    """0 = clean, 2 = configuration error. CI pipelines branch on these."""
    assert _run(adr_repo, "validate", "--adr-dir", "docs/adr").returncode == 0
    assert _run(adr_repo, "validate", "--adr-dir", "nope").returncode == 2


def test_should_not_regress_cli_helper_resolution_order(tmp_path, monkeypatch):
    """Explicit flag beats positional beats env var beats default."""
    monkeypatch.setenv("IIL_ADRFW_ADRS_DIR", "from-env")

    import argparse

    flag_and_pos = argparse.Namespace(adr_dir="from-flag", adr_dir_pos="from-pos")
    assert cli._resolve_adr_dir(flag_and_pos) == Path("from-flag")

    pos_only = argparse.Namespace(adr_dir=None, adr_dir_pos="from-pos")
    assert cli._resolve_adr_dir(pos_only) == Path("from-pos")

    neither = argparse.Namespace(adr_dir=None, adr_dir_pos=None)
    assert cli._resolve_adr_dir(neither) == Path("from-env")

    monkeypatch.delenv("IIL_ADRFW_ADRS_DIR")
    assert cli._resolve_adr_dir(neither) == Path(cli.DEFAULT_ADR_DIR)


def test_should_audit_despite_invalid_adrs(tmp_path):
    """One malformed ADR must not abort the whole constitution audit.

    Before 0.8.0 a single invalid file made `audit` exit 3 ("internal error"),
    so the tool was unusable in exactly the repos whose ADR hygiene needed
    auditing (meiki-hub: 23 of 36 ADRs invalid). Unloadable files are findings.
    """
    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-001-good.md").write_text(ADR_BODY, encoding="utf-8")
    (adr_dir / "ADR-002-broken.md").write_text(
        "---\nstatus: Accepted\ndate: 2026-04-20\naccepted: 2026-04-26\n---\n# Broken\n",
        encoding="utf-8",
    )

    result = _run(tmp_path, "audit", "--adr-dir", "docs/adr")

    assert result.returncode == 1, result.stderr  # findings present, not a crash
    assert "loadability" in result.stdout
    assert "ADR-002-broken.md" in result.stdout


def test_should_keep_load_adrs_strict_by_default(tmp_path):
    """Tolerant loading is opt-in — the default still raises on a bad ADR."""
    from iil_adrfw import ADRLoadError, get_schema_dir, load_adrs

    adr_dir = tmp_path / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-002-broken.md").write_text("---\nstatus: Accepted\naccepted: x\n---\n# B\n", encoding="utf-8")

    with pytest.raises(ADRLoadError):
        load_adrs(adr_dir, get_schema_dir())

    errors: list[dict] = []
    adrs = load_adrs(adr_dir, get_schema_dir(), errors=errors)
    assert adrs == []
    assert len(errors) == 1
    assert errors[0]["file"] == "ADR-002-broken.md"
