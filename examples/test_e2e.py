"""End-to-end smoke test: load ADR-099, run adr_check on the synthetic app,
verify it finds the two drifted models and ignores the compliant one.
"""

import os  # noqa: E402
import shutil  # noqa: E402
from pathlib import Path  # noqa: E402

# Configure the server to find our test fixtures BEFORE importing it
BASE = Path(__file__).resolve().parent
ADRS_DIR = BASE / "_test_adrs"
SCHEMAS_DIR = BASE.parent / "schemas"
REPO_ROOT = BASE / "django_polyrepo"

# Stage the example ADR into a fresh adrs/ dir
if ADRS_DIR.exists():
    shutil.rmtree(ADRS_DIR)
ADRS_DIR.mkdir(parents=True)
shutil.copy(BASE / "ADR-099-multi-tenancy.md", ADRS_DIR)
shutil.copy(BASE / "ADR-099-multi-tenancy.rules.yaml", ADRS_DIR)

os.environ["IIL_ADRFW_ADRS_DIR"] = str(ADRS_DIR)
os.environ["IIL_ADRFW_SCHEMAS_DIR"] = str(SCHEMAS_DIR)
os.environ["IIL_ADRFW_REPO_ROOT"] = str(REPO_ROOT)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Re-point env to THIS module's dirs before each test.

    The module-level os.environ assignments above run once at import and get
    clobbered by whichever example module is collected last (shared env key),
    making the active ADRS dir collection-order dependent. The server reads
    these vars fresh per call, so per-test setenv fully isolates the modules.
    """
    monkeypatch.setenv("IIL_ADRFW_ADRS_DIR", str(ADRS_DIR))
    monkeypatch.setenv("IIL_ADRFW_SCHEMAS_DIR", str(SCHEMAS_DIR))
    monkeypatch.setenv("IIL_ADRFW_REPO_ROOT", str(REPO_ROOT))

# Now import — the env vars take effect on first call
from datetime import UTC  # noqa: E402

from iil_adrfw.server import (  # noqa: E402
    CheckRequest,
    ExplainRequest,
    _do_check,
    _do_explain,
    _do_list_adrs,
)


def test_check_finds_violations():
    print("=" * 70)
    print("TEST 1: adr_check on synthetic Django app")
    print("=" * 70)
    req = CheckRequest(paths=["apps/billing/models.py"], severity_threshold="warning")
    resp = _do_check(req)

    print(f"  ADRs loaded:       {resp.constitution_loaded}")
    print(f"  Rules evaluated:   {resp.rules_evaluated}")
    print(f"  Files scanned:     {resp.files_scanned}")
    print(f"  Runtime:           {resp.runtime_ms} ms")
    print(f"  Violations found:  {len(resp.violations)}")
    print()
    for v in resp.violations:
        print(f"  [{v.severity.upper()}] {v.rule_id}")
        print(f"    file:        {v.file}")
        print(f"    lines:       {v.line_start}-{v.line_end}")
        print(f"    expected:    {v.expected}")
        print(f"    actual:      {v.actual}")
        print(f"    likely:      {v.likely_cause}")
        print(f"    distance:    {v.semantic_distance}")
        print(f"    blast:       {v.blast_radius}")
        if v.suggestions:
            sug = v.suggestions[0]
            print(f"    suggest:     {sug['description']} (conf={sug['confidence']}, auto={sug['automated']})")
        print()

    assert len(resp.violations) == 2, f"expected 2 violations, got {len(resp.violations)}"
    rule_ids = {v.rule_id for v in resp.violations}
    assert rule_ids == {"ADR-099/tenant-id-bigint"}, f"unexpected rule ids: {rule_ids}"
    print("PASS: found exactly the two drifted models, ignored the compliant one\n")


def test_explain_audience_routing():
    print("=" * 70)
    print("TEST 2: adr_explain — audience-tailored explanations")
    print("=" * 70)

    for audience in ("new_dev", "senior", "architect", "auditor"):
        req = ExplainRequest(rule_id="ADR-099/tenant-id-bigint", audience=audience)
        resp = _do_explain(req)
        print(f"\n--- Audience: {audience} ---")
        print(f"  Rule: {resp.rule}")
        print(f"  Severity: {resp.severity}")
        print("  Explanation:")
        for line in resp.explanation_for_audience.strip().split("\n"):
            print(f"    {line}")

    print("\nPASS: same rule, four distinct audience-appropriate explanations\n")


def test_temporal_as_of():
    print("=" * 70)
    print("TEST 3: bi-temporal — check 'as_of' before rule existed")
    print("=" * 70)
    from datetime import datetime

    req = CheckRequest(
        paths=["apps/billing/models.py"],
        as_of=datetime(2024, 9, 1, tzinfo=UTC),  # before ADR-099 valid_from
    )
    resp = _do_check(req)
    print("  As-of: 2024-09-01 (before ADR-099 took effect on 2024-09-15)")
    print(f"  Rules evaluated: {resp.rules_evaluated}")
    print(f"  Violations:      {len(resp.violations)}")
    assert resp.rules_evaluated == 0, "rules should not be active yet"
    assert len(resp.violations) == 0
    print("PASS: bi-temporal logic correctly excludes pre-rule code\n")


def test_list_adrs_resource():
    print("=" * 70)
    print("TEST 4: adr://list resource")
    print("=" * 70)
    listing = _do_list_adrs()
    print(f"  ADRs in constitution: {len(listing['adrs'])}")
    for entry in listing["adrs"]:
        print(f"  {entry['id']}: {entry['title']}")
        print(f"    status: {entry['status']}, rules: {entry['rule_count']}, domains: {entry['domains']}")
    assert len(listing["adrs"]) == 1
    assert listing["adrs"][0]["id"] == "ADR-099"
    print("\nPASS: resource returns expected listing\n")


if __name__ == "__main__":
    test_check_finds_violations()
    test_explain_audience_routing()
    test_temporal_as_of()
    test_list_adrs_resource()
    print("=" * 70)
    print("ALL TESTS PASSED")
    print("=" * 70)
