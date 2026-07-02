"""Tests for adr_diff (temporal and set modes)."""

import shutil
from datetime import UTC, datetime
from pathlib import Path

from iil_adrfw.diff import ChangeKind, diff_set, diff_temporal
from iil_adrfw.persistence import load_adrs
from iil_adrfw.server import DiffRequest, _do_diff

BASE = Path(__file__).resolve().parent
ADRS_DIR = BASE / "_test_adrs_diff"
ADRS_LEFT = BASE / "_test_diff_left"
ADRS_RIGHT = BASE / "_test_diff_right"
SCHEMAS_DIR = BASE.parent / "schemas"
TEST_DIRS = (ADRS_DIR, ADRS_LEFT, ADRS_RIGHT)


def _stage_fixtures() -> None:
    """Stage ADR-099 (recent decision_date) + the v1.1 ADR-188 fixture (see conftest.py).

    ADRS_LEFT/ADRS_RIGHT are left empty here; individual tests below stage
    and clear them as needed.
    """
    shutil.copy(BASE / "ADR-099-multi-tenancy.md", ADRS_DIR)
    shutil.copy(BASE / "ADR-099-multi-tenancy.rules.yaml", ADRS_DIR)
    shutil.copy(BASE / "ADR-188-unified-vector-store.md", ADRS_DIR)
    shutil.copy(BASE / "ADR-188-unified-vector-store.rules.yaml", ADRS_DIR)


def test_temporal_pre_decision_excludes_adr():
    """Querying before any ADR existed yields zero materialized ADRs."""
    print("=" * 70)
    print("TEST: temporal — querying before all decision_dates → empty left snap")
    print("=" * 70)
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR)
    very_old = datetime(2020, 1, 1, tzinfo=UTC)
    today = datetime.now(UTC)
    diff = diff_temporal(adrs, very_old, today)
    print(f"  Mode: {diff.mode.value}")
    print(f"  added: {diff.added_count}, removed: {diff.removed_count}, modified: {diff.modified_count}")
    print("  Changes:")
    for c in diff.changes:
        print(f"    [{c.kind.value:14}] {c.summary}")
    assert diff.added_count == len(adrs), f"all {len(adrs)} ADRs should be ADDED relative to 2020"
    assert diff.removed_count == 0
    assert diff.modified_count == 0
    print("  PASS\n")


def test_temporal_amendments_visible():
    """ADR-188 has v1.1 amendment in 2026-05-08. Querying with right_time after
    that should reveal the amendment in the materialized snapshot."""
    print("=" * 70)
    print("TEST: temporal — amendments are filtered by world_time")
    print("=" * 70)
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR)
    adr_188 = next(a for a in adrs if a.id == "ADR-188")
    print(f"  ADR-188 has {len(adr_188.amendments)} amendment(s) in source")

    # Two timestamps: just before the v1.1 amendment, and just after
    early = datetime(2026, 5, 7, 23, 0, tzinfo=UTC)
    late = datetime(2026, 5, 9, 0, 0, tzinfo=UTC)

    from iil_adrfw.diff import _adr_effective_at

    early_snap = _adr_effective_at(adr_188, early)
    late_snap = _adr_effective_at(adr_188, late)

    print(f"  At {early.isoformat()}: {len(early_snap.amendments)} amendments visible")
    print(f"  At {late.isoformat()}: {len(late_snap.amendments)} amendments visible")
    assert len(early_snap.amendments) == 0
    assert len(late_snap.amendments) == 1
    print("  PASS: amendments correctly filtered by world_time\n")


def test_set_diff_identical_returns_no_changes():
    """Two identical ADR sets produce no changes."""
    print("=" * 70)
    print("TEST: set — identical sets produce empty diff")
    print("=" * 70)
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR)
    diff = diff_set(adrs, adrs, "self", "self")
    print(f"  Changes: {len(diff.changes)}")
    assert len(diff.changes) == 0
    print("  PASS\n")


def test_set_diff_added_removed():
    """Stage two different sets — left has ADR-099 only, right has ADR-099 + ADR-188."""
    print("=" * 70)
    print("TEST: set — added/removed ADRs detected")
    print("=" * 70)
    # Clear and stage
    for d in (ADRS_LEFT, ADRS_RIGHT):
        for f in d.glob("ADR-*"):
            f.unlink()

    shutil.copy(BASE / "ADR-099-multi-tenancy.md", ADRS_LEFT)
    shutil.copy(BASE / "ADR-099-multi-tenancy.rules.yaml", ADRS_LEFT)

    shutil.copy(BASE / "ADR-099-multi-tenancy.md", ADRS_RIGHT)
    shutil.copy(BASE / "ADR-099-multi-tenancy.rules.yaml", ADRS_RIGHT)
    shutil.copy(BASE / "ADR-188-unified-vector-store.md", ADRS_RIGHT)
    shutil.copy(BASE / "ADR-188-unified-vector-store.rules.yaml", ADRS_RIGHT)

    left = load_adrs(ADRS_LEFT, SCHEMAS_DIR)
    right = load_adrs(ADRS_RIGHT, SCHEMAS_DIR)
    diff = diff_set(left, right, "left", "right")

    print(f"  Left: {len(left)} ADRs, Right: {len(right)} ADRs")
    print(f"  added: {diff.added_count}, removed: {diff.removed_count}, modified: {diff.modified_count}")
    for c in diff.changes:
        print(f"    [{c.kind.value:14}] {c.summary}")
    assert diff.added_count == 1
    assert diff.removed_count == 0
    assert any(c.adr_id == "ADR-188" and c.kind == ChangeKind.ADDED for c in diff.changes)
    print("  PASS\n")


def test_set_diff_status_changed():
    """Stage two copies of ADR-099 with different status values."""
    print("=" * 70)
    print("TEST: set — status_changed kind detected")
    print("=" * 70)
    for d in (ADRS_LEFT, ADRS_RIGHT):
        for f in d.glob("ADR-*"):
            f.unlink()

    shutil.copy(BASE / "ADR-099-multi-tenancy.md", ADRS_LEFT)
    shutil.copy(BASE / "ADR-099-multi-tenancy.rules.yaml", ADRS_LEFT)

    # Right: same ADR but with status=deprecated
    src = (BASE / "ADR-099-multi-tenancy.md").read_text()
    modified = src.replace("status: accepted", "status: deprecated")
    (ADRS_RIGHT / "ADR-099-multi-tenancy.md").write_text(modified)
    shutil.copy(BASE / "ADR-099-multi-tenancy.rules.yaml", ADRS_RIGHT)

    left = load_adrs(ADRS_LEFT, SCHEMAS_DIR)
    right = load_adrs(ADRS_RIGHT, SCHEMAS_DIR)
    diff = diff_set(left, right)

    print(f"  Changes: {len(diff.changes)}")
    for c in diff.changes:
        print(f"    [{c.kind.value:18}] {c.summary}")
    assert len(diff.changes) == 1
    assert diff.changes[0].kind == ChangeKind.STATUS_CHANGED
    assert "accepted" in diff.changes[0].summary and "deprecated" in diff.changes[0].summary
    print("  PASS\n")


def test_mcp_tool_temporal():
    """Smoke test of the MCP tool entry point — temporal mode."""
    print("=" * 70)
    print("TEST: MCP tool — temporal mode end-to-end")
    print("=" * 70)
    very_old = datetime(2020, 1, 1, tzinfo=UTC)
    today = datetime.now(UTC)
    resp = _do_diff(
        DiffRequest(
            mode="temporal",
            left_time=very_old,
            right_time=today,
        )
    )
    print(f"  Mode: {resp.mode}")
    print(f"  Added: {resp.added_count}, Removed: {resp.removed_count}, Modified: {resp.modified_count}")
    print(f"  Runtime: {resp.runtime_ms}ms")
    assert resp.mode == "temporal"
    assert resp.added_count >= 2  # at least ADR-099 and ADR-188
    print("  PASS\n")


def test_mcp_tool_set():
    """Smoke test of MCP tool — set mode."""
    print("=" * 70)
    print("TEST: MCP tool — set mode end-to-end")
    print("=" * 70)
    # Re-stage so right has 1 fewer ADR than the configured constitution
    for f in ADRS_LEFT.glob("ADR-*"):
        f.unlink()
    shutil.copy(BASE / "ADR-099-multi-tenancy.md", ADRS_LEFT)
    shutil.copy(BASE / "ADR-099-multi-tenancy.rules.yaml", ADRS_LEFT)

    resp = _do_diff(
        DiffRequest(
            mode="set",
            right_dir=str(ADRS_LEFT),
            left_label="full",
            right_label="subset",
        )
    )
    print(f"  Mode: {resp.mode}")
    print(f"  Added: {resp.added_count}, Removed: {resp.removed_count}, Modified: {resp.modified_count}")
    for c in resp.changes:
        print(f"    [{c.kind:14}] {c.summary}")
    # ADR-188 should be in left but not in right (subset)
    assert resp.removed_count >= 1
    assert any(c.adr_id == "ADR-188" and c.kind == "removed" for c in resp.changes)
    print("  PASS\n")


def test_mcp_tool_validation_errors():
    """Tool raises on invalid input."""
    print("=" * 70)
    print("TEST: MCP tool — validation errors")
    print("=" * 70)
    try:
        _do_diff(DiffRequest(mode="temporal"))
        raise AssertionError("expected ValueError for missing times")
    except ValueError as e:
        assert "left_time" in str(e) or "right_time" in str(e)
        print("  PASS: temporal w/o times raises ValueError")

    try:
        _do_diff(DiffRequest(mode="set"))
        raise AssertionError("expected ValueError for missing right_dir")
    except ValueError as e:
        assert "right_dir" in str(e)
        print("  PASS: set w/o right_dir raises ValueError")
    print()


if __name__ == "__main__":
    test_temporal_pre_decision_excludes_adr()
    test_temporal_amendments_visible()
    test_set_diff_identical_returns_no_changes()
    test_set_diff_added_removed()
    test_set_diff_status_changed()
    test_mcp_tool_temporal()
    test_mcp_tool_set()
    test_mcp_tool_validation_errors()
    print("=" * 70)
    print("ALL adr_diff TESTS PASSED")
    print("=" * 70)
