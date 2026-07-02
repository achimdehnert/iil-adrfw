"""Security regression tests for MCP path-parameter containment (issue #22).

The MCP server tools accept free-form path strings from the client
(`CheckRequest.paths`, `ValidateRequest.adr_dir`, `DiffRequest.right_dir`).
Without validation a malicious/buggy client could point them outside the
sanctioned repo root and make the server read arbitrary files. These tests
assert that traversal / absolute-escape now raises ValueError, while legitimate
in-root paths keep working.

Env-configured defaults (`_adrs_dir()` when no `adr_dir` is supplied) are
operator-trusted and intentionally NOT constrained — covered by the "default"
regression test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import iil_adrfw.server as server

_MINIMAL_FM = """\
---
id: ADR-0001
title: Path Containment
status: accepted
decision_date: 2026-01-01
deciders:
  - "tester <t@example.com>"
domains:
  - general
---

# ADR-0001

Body.
"""


def _make_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "adrs").mkdir(parents=True)
    (root / "adrs" / "ADR-0001-x.md").write_text(_MINIMAL_FM, encoding="utf-8")
    return root


# ─── _require_within_root helper ────────────────────────────────


def test_should_reject_absolute_path_outside_root(tmp_path):
    root = _make_root(tmp_path)
    with pytest.raises(ValueError, match="outside the sanctioned root"):
        server._require_within_root("/etc/hostname", root=root, what="adr_dir")


def test_should_reject_parent_traversal_outside_root(tmp_path):
    root = _make_root(tmp_path)
    with pytest.raises(ValueError, match="outside the sanctioned root"):
        server._require_within_root("../../etc", root=root, what="adr_dir")


def test_should_accept_relative_path_within_root(tmp_path):
    root = _make_root(tmp_path)
    resolved = server._require_within_root("adrs", root=root, what="adr_dir")
    assert resolved == (root / "adrs").resolve()


def test_should_accept_absolute_path_within_root(tmp_path):
    root = _make_root(tmp_path)
    inside = root / "adrs"
    resolved = server._require_within_root(str(inside), root=root, what="adr_dir")
    assert resolved == inside.resolve()


# ─── adr_validate (adr_dir sink) ────────────────────────────────


def test_should_reject_validate_adr_dir_outside_root(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    monkeypatch.setenv("IIL_ADRFW_REPO_ROOT", str(root))
    req = server.ValidateRequest(adr_dir="/etc")
    with pytest.raises(ValueError, match="adr_dir"):
        server._do_validate(req)


def test_should_validate_adr_dir_within_root(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    monkeypatch.setenv("IIL_ADRFW_REPO_ROOT", str(root))
    resp = server._do_validate(server.ValidateRequest(adr_dir=str(root / "adrs")))
    assert resp.total == 1


# ─── adr_check (paths sink via _gather_files) ───────────────────


def test_should_reject_check_path_outside_root(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    monkeypatch.setenv("IIL_ADRFW_REPO_ROOT", str(root))
    monkeypatch.setenv("IIL_ADRFW_ADRS_DIR", str(root / "adrs"))
    with pytest.raises(ValueError, match="check path"):
        server._gather_files(["../../../etc/passwd"], root)


def test_should_gather_files_within_root(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    (root / "src.py").write_text("x = 1\n", encoding="utf-8")
    files = server._gather_files(["src.py"], root)
    assert (root / "src.py").resolve() in {f.resolve() for f in files}


# ─── diff set mode (right_dir sink) ─────────────────────────────


def test_should_reject_diff_right_dir_outside_root(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    monkeypatch.setenv("IIL_ADRFW_REPO_ROOT", str(root))
    monkeypatch.setenv("IIL_ADRFW_ADRS_DIR", str(root / "adrs"))
    req = server.DiffRequest(mode="set", right_dir="/etc")
    with pytest.raises(ValueError, match="right_dir"):
        server._do_diff(req)
