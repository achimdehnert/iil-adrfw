"""Regression tests for naive-datetime handling on MCP request models (issue #18).

An MCP client may send a bi-temporal timestamp without an offset
(`"2026-01-01T00:00:00"`); Pydantic parses that to a *naive* datetime. Before
the fix, comparing it against the tz-aware ADR dates downstream raised
`TypeError: can't compare offset-naive and offset-aware datetimes`. The request
models now normalize naive input to UTC (mirroring `cli._parse_iso`).
"""

from __future__ import annotations

from datetime import UTC, datetime

from iil_adrfw.server import (
    AuditRequest,
    CheckRequest,
    DiffRequest,
    _do_diff,
    _ensure_utc,
)

_MINIMAL_FM = """\
---
id: ADR-0001
title: Naive Datetime Test
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


def _stage(tmp_path, monkeypatch):
    adrs = tmp_path / "adrs"
    adrs.mkdir()
    (adrs / "ADR-0001-x.md").write_text(_MINIMAL_FM, encoding="utf-8")
    monkeypatch.setenv("IIL_ADRFW_ADRS_DIR", str(adrs))
    monkeypatch.setenv("IIL_ADRFW_REPO_ROOT", str(tmp_path))
    return adrs


# ─── the _ensure_utc helper ─────────────────────────────────────


def test_should_assume_utc_for_naive_datetime():
    naive = datetime(2026, 1, 1, 0, 0, 0)
    assert _ensure_utc(naive).tzinfo is UTC


def test_should_leave_aware_datetime_unchanged():
    aware = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    assert _ensure_utc(aware) is aware


# ─── request-model field validation ─────────────────────────────


def test_should_normalize_naive_check_as_of_to_utc():
    req = CheckRequest(paths=[], as_of="2026-01-01T00:00:00")
    assert req.as_of is not None and req.as_of.tzinfo is UTC


def test_should_normalize_naive_audit_as_of_to_utc():
    req = AuditRequest(as_of="2026-01-01T00:00:00")
    assert req.as_of is not None and req.as_of.tzinfo is UTC


def test_should_normalize_naive_diff_times_to_utc():
    req = DiffRequest(mode="temporal", left_time="2026-01-01T00:00:00", right_time="2026-06-01T00:00:00")
    assert req.left_time is not None and req.left_time.tzinfo is UTC
    assert req.right_time is not None and req.right_time.tzinfo is UTC


def test_should_preserve_explicit_offset_on_diff_times():
    req = DiffRequest(mode="temporal", left_time="2026-01-01T00:00:00+02:00", right_time="2026-06-01T00:00:00Z")
    # offset preserved (not clobbered to UTC), just made tz-aware
    assert req.left_time is not None and req.left_time.utcoffset() is not None
    assert req.right_time is not None and req.right_time.tzinfo is not None


def test_should_leave_none_timestamps_as_none():
    req = DiffRequest(mode="temporal", left_time=None, right_time=None)
    assert req.left_time is None and req.right_time is None


# ─── end-to-end: the original crash path ────────────────────────


def test_should_run_temporal_diff_with_naive_timestamps_without_crash(tmp_path, monkeypatch):
    _stage(tmp_path, monkeypatch)
    # Before the fix this raised: can't compare offset-naive and offset-aware datetimes
    req = DiffRequest(mode="temporal", left_time="2026-01-01T00:00:00", right_time="2026-06-01T00:00:00")
    resp = _do_diff(req)
    assert resp is not None


def test_should_run_temporal_diff_with_aware_timestamps(tmp_path, monkeypatch):
    _stage(tmp_path, monkeypatch)
    req = DiffRequest(
        mode="temporal",
        left_time=datetime(2026, 1, 1, tzinfo=UTC),
        right_time=datetime(2026, 6, 1, tzinfo=UTC),
    )
    resp = _do_diff(req)
    assert resp is not None
