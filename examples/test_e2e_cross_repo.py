"""Cross-repo validation E2E test.

Reconstructs the v1.1 scenario:
- ADR-188 v1.0 (hypothetical) claims tenant_id BIGINT
- Consumer-repos all use UUIDField
- Cross-repo validation should detect the conflict with PROVEN confidence
  and recommend AMENDING the ADR (which is what happened in reality on 2026-05-08)
"""

import shutil
from pathlib import Path

from iil_adrfw.server import (
    ConsumerRepoSpec,
    ValidateCrossRepoRequest,
    _do_validate_cross_repo,
)

BASE = Path(__file__).resolve().parent
ADRS_DIR = BASE / "_test_adrs_xrepo"
SCHEMAS_DIR = BASE.parent / "schemas"
WORKSPACE = BASE / "polyrepo_workspace"


def _stage_fixtures() -> None:
    """Stage the hypothetical v1.0 + corrected v1.1, plus ADR-099 (see conftest.py)."""
    for fn in [
        "ADR-099-multi-tenancy.md",
        "ADR-099-multi-tenancy.rules.yaml",
        "ADR-188-unified-vector-store.md",
        "ADR-188-unified-vector-store.rules.yaml",
        "ADR-9088-hypothetical-v10.md",
        "ADR-9088-hypothetical-v10.rules.yaml",
    ]:
        shutil.copy(BASE / fn, ADRS_DIR)

CONSUMER_REPOS = [
    ConsumerRepoSpec(name="meiki-hub", root=str(WORKSPACE / "meiki-hub")),
    ConsumerRepoSpec(name="bfagent", root=str(WORKSPACE / "bfagent")),
    ConsumerRepoSpec(name="mcp-hub", root=str(WORKSPACE / "mcp-hub")),
]


def test_v10_hypothetical_caught_by_validator():
    """The whole point: v1.0 claim of BIGINT vs consumer-repo reality of UUID
    must produce a PROVEN/HIGH-confidence conflict that blocks publish."""
    print("=" * 70)
    print("TEST: hypothetical ADR-188 v1.0 (BIGINT claim) vs UUID reality")
    print("=" * 70)
    req = ValidateCrossRepoRequest(
        adr_id="ADR-9088",
        consumer_repos=CONSUMER_REPOS,
    )
    resp = _do_validate_cross_repo(req)

    print(f"\n  ADR validated:        {resp.adr_id}")
    print(f"  Consumer repos:       {len(resp.consumer_repos_scanned)} ({', '.join(resp.consumer_repos_scanned)})")
    print(f"  Unreachable:          {len(resp.repos_unreachable)}")
    print(f"  Class 1 conflicts:    {resp.class1_count}")
    print(f"  Class 2 conflicts:    {resp.class2_count}")
    print(f"  Class 3 conflicts:    {resp.class3_count}")
    print(f"  Runtime:              {resp.runtime_ms}ms")
    print(f"  Blocking conflicts:   {resp.has_blocking_conflicts}")

    if resp.conflicts:
        print()
        for i, c in enumerate(resp.conflicts, 1):
            print(f"  --- Conflict #{i} ---")
            print(f"    Class:       {c.conflict_class}")
            print(f"    Confidence:  {c.confidence}")
            print(f"    Claim:       {c.claim}")
            print(f"    Reality:     {c.reality}")
            print(f"    Affected:    {c.affected_repos}")
            print(f"    Blocks pub:  {c.blocks_publish}")
            print(f"    Evidence ({c.evidence_count} samples, showing first {len(c.evidence_preview)}):")
            for s in c.evidence_preview:
                print(f"      [{s['repo']}] {s['file']}:{s['line']}  ({s['extracted_value']})")
                print(f"        > {s['snippet']}")
            print("    Suggestion:")
            for line in c.suggestion.split("\n"):
                print(f"      {line}")

    assert resp.has_blocking_conflicts, "v1.0 BIGINT claim MUST be flagged as blocking"
    assert resp.class1_count == 1, "should produce exactly one Class-1 conflict"
    conflict = resp.conflicts[0]
    assert conflict.confidence in ("proven", "high"), f"confidence should be high or proven, got {conflict.confidence}"
    assert "uuid" in conflict.reality.lower()
    assert "bigint" in conflict.claim.lower()
    print("\nPASS: v1.0 hypothetical correctly flagged BEFORE it could be accepted\n")


def test_v11_correct_no_conflicts():
    """The v1.1 amended ADR matches consumer-repo reality. No conflicts expected."""
    print("=" * 70)
    print("TEST: ADR-188 v1.1 (UUID claim) vs UUID reality — should be CLEAN")
    print("=" * 70)
    req = ValidateCrossRepoRequest(
        adr_id="ADR-188",
        consumer_repos=CONSUMER_REPOS,
    )
    resp = _do_validate_cross_repo(req)

    print(f"\n  Conflicts found: {len(resp.conflicts)}")
    for c in resp.conflicts:
        print(f"  - {c.conflict_class} ({c.confidence}): {c.claim}")
    print(f"  Runtime: {resp.runtime_ms}ms")

    assert not resp.has_blocking_conflicts, f"v1.1 should not have blocking conflicts, but got {len(resp.conflicts)}"
    print("\nPASS: v1.1 (corrected) ADR validates cleanly against consumer-repos\n")


def test_unreachable_repo_handled():
    """When a consumer-repo path doesn't exist, we should report it but not crash."""
    print("=" * 70)
    print("TEST: missing consumer-repo path is handled gracefully")
    print("=" * 70)
    req = ValidateCrossRepoRequest(
        adr_id="ADR-9088",
        consumer_repos=CONSUMER_REPOS
        + [
            ConsumerRepoSpec(name="nonexistent-repo", root=str(WORKSPACE / "does-not-exist")),
        ],
    )
    resp = _do_validate_cross_repo(req)
    print(f"  Scanned:     {resp.consumer_repos_scanned}")
    print(f"  Unreachable: {resp.repos_unreachable}")
    assert "nonexistent-repo" in resp.repos_unreachable
    assert len(resp.consumer_repos_scanned) == 2  # mcp-hub is now origin, excluded
    print("\nPASS: unreachable repos reported, not crashed\n")


def test_evidence_quality():
    """The evidence in a Class-1 finding should include real file paths and line numbers."""
    print("=" * 70)
    print("TEST: evidence quality — actionable for human review")
    print("=" * 70)
    req = ValidateCrossRepoRequest(
        adr_id="ADR-9088",
        consumer_repos=CONSUMER_REPOS,
    )
    resp = _do_validate_cross_repo(req)
    conflict = resp.conflicts[0]

    # Every sample should have real file/line and extracted value
    print(f"\n  Total evidence: {conflict.evidence_count} samples")
    print(f"  Preview shown:  {len(conflict.evidence_preview)}")
    for s in conflict.evidence_preview:
        assert s["file"], "file should not be empty"
        assert s["line"] > 0, "line should be > 0"
        assert s["extracted_value"], "extracted_value should not be empty"
        print(f"    {s['repo']}/{s['file']}:{s['line']}  -> {s['extracted_value']}")
    print("\nPASS: evidence is actionable\n")


if __name__ == "__main__":
    test_v10_hypothetical_caught_by_validator()
    test_v11_correct_no_conflicts()
    test_unreachable_repo_handled()
    test_evidence_quality()
    print("=" * 70)
    print("ALL CROSS-REPO TESTS PASSED")
    print("=" * 70)
    print()
    print("The thesis is demonstrated: had iil-adrfw been live on 2026-05-07,")
    print("ADR-188 v1.0 would have been BLOCKED before transitioning to 'accepted'.")
    print("The retroactive v1.1 amendment would not have been necessary.")
