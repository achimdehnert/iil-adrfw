"""Regression tests for bug-fixes ported from the adr-doctor review (2026-05-08).

These verify the same edge-cases that broke in the wild on the 156 real
platform ADRs, but applied to the iil-adrfw loader/auditor stack.

Bug references trace back to the adr-doctor review:
- Bug #2: legacy hyphenated field names ('decision-makers', 'superseded-by')
- Bug #3: string-form supersedes ('ADR-110 (Legacy) — replaced by modern format')
- Bug #4: dangling supersedes target (cross-repo or typo)
- Bug #5: self-reference in supersedes (revision marker, not real supersession)
"""

import os  # noqa: E402
import shutil  # noqa: E402
from pathlib import Path  # noqa: E402

BASE = Path(__file__).resolve().parent
ADRS_DIR = BASE / "_test_adrs_regression"
SCHEMAS_DIR = BASE.parent / "schemas"

if ADRS_DIR.exists():
    shutil.rmtree(ADRS_DIR)
ADRS_DIR.mkdir(parents=True)

# Always include the canonical ADR-099 so we have at least one normal ADR
shutil.copy(BASE / "ADR-099-multi-tenancy.md", ADRS_DIR)
shutil.copy(BASE / "ADR-099-multi-tenancy.rules.yaml", ADRS_DIR)


# --- Test fixtures: deliberately-quirky ADRs reproducing real-world drift ---


_LEGACY_HYPHENS = """---
id: ADR-410
title: Legacy hyphenated field names
status: accepted
decision_date: "2024-08-15"
decision-makers: Achim Dehnert
superseded-by: []
domains:
  - test/legacy
rationale_summary: This ADR uses the old hyphenated field convention seen in real ADRs.
---

# ADR-410 — Legacy field names

This is a fixture for testing alias normalization.
"""


_FREETEXT_SUPERSEDES = """---
id: ADR-411
title: Freetext supersedes string
status: accepted
decision_date: "2025-03-01"
deciders:
  - "Achim Dehnert"
supersedes: ADR-410 (Legacy field names) — replaced by modern format
domains:
  - test/legacy
rationale_summary: This fixture has supersedes as a freetext string instead of a list.
---

# ADR-411 — Freetext supersedes
"""


_DANGLING_TARGET = """---
id: ADR-420
title: Supersedes a non-existent ADR
status: accepted
decision_date: "2025-09-01"
deciders:
  - "Achim Dehnert"
supersedes:
  - ADR-9999
domains:
  - test/dangling
rationale_summary: This fixture references ADR-9999 which doesn't exist.
---

# ADR-420
"""


_SELF_REFERENCE = """---
id: ADR-430
title: Self-reference in supersedes
status: accepted
decision_date: "2025-10-01"
deciders:
  - "Achim Dehnert"
supersedes:
  - ADR-430
domains:
  - test/self-ref
rationale_summary: This fixture self-references in supersedes (real-world ADR-167 case).
---

# ADR-430
"""


def _stage_fixture(name: str, content: str) -> Path:
    p = ADRS_DIR / name
    p.write_text(content, encoding="utf-8")
    return p


# Stage all four
_stage_fixture("ADR-410-legacy-hyphens.md", _LEGACY_HYPHENS)
_stage_fixture("ADR-411-freetext-supersedes.md", _FREETEXT_SUPERSEDES)
_stage_fixture("ADR-420-dangling.md", _DANGLING_TARGET)
_stage_fixture("ADR-430-self-ref.md", _SELF_REFERENCE)


os.environ["IIL_ADRFW_ADRS_DIR"] = str(ADRS_DIR)
os.environ["IIL_ADRFW_SCHEMAS_DIR"] = str(SCHEMAS_DIR)


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


from iil_adrfw.audit import run_audit  # noqa: E402
from iil_adrfw.graph import ConstitutionGraph  # noqa: E402
from iil_adrfw.persistence import load_adrs  # noqa: E402


def test_should_normalize_legacy_hyphenated_field_names():
    """Bug #2: 'decision-makers', 'superseded-by' must be normalized."""
    print("=" * 70)
    print("TEST: Bug #2 — legacy hyphenated field names load successfully")
    print("=" * 70)
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    by_id = {a.id: a for a in adrs}
    assert "ADR-410" in by_id, "legacy-hyphens ADR did not load"
    adr = by_id["ADR-410"]
    print(f"  ADR-410 loaded:       {adr.title}")
    print(f"  deciders:             {adr.deciders}")
    print(f"  superseded_by:        {adr.superseded_by}")
    assert adr.deciders == ("Achim Dehnert",), (
        f"decision-makers should normalize to deciders=['Achim Dehnert'], got {adr.deciders}"
    )
    assert adr.superseded_by == (), "superseded-by should normalize to empty tuple"
    print("\nPASS: legacy hyphenated fields normalized correctly\n")


def test_should_extract_adr_id_from_freetext_supersedes_string():
    """Bug #3: supersedes given as a plain string with parenthetical comment."""
    print("=" * 70)
    print("TEST: Bug #3 — freetext supersedes string is parsed")
    print("=" * 70)
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    by_id = {a.id: a for a in adrs}
    assert "ADR-411" in by_id, "freetext-supersedes ADR did not load"
    adr = by_id["ADR-411"]
    print(f"  ADR-411 supersedes:   {adr.supersedes}")
    assert adr.supersedes == ("ADR-410",), (
        f"freetext 'ADR-410 (Legacy ...)' should extract to ('ADR-410',), got {adr.supersedes}"
    )
    print("\nPASS: freetext string supersedes correctly extracted\n")


def test_should_flag_dangling_supersedes_target_as_warning_not_error():
    """Bug #4: dangling target should be WARNING (cross-repo possible) not ERROR."""
    print("=" * 70)
    print("TEST: Bug #4 — dangling supersedes is WARNING, not ERROR")
    print("=" * 70)
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    graph = ConstitutionGraph.build(adrs)
    report = run_audit(graph, auditors=["supersession_hygiene"])

    dangling_findings = [f for f in report.findings if "ADR-420" in f.affected_adrs and "ADR-9999" in f.description]
    print(f"  Dangling findings for ADR-420: {len(dangling_findings)}")
    for f in dangling_findings:
        print(f"    [{f.severity.value}] {f.description[:110]}")
    assert dangling_findings, "dangling supersedes should produce a finding"
    severities = {f.severity.value for f in dangling_findings}
    assert "warning" in severities, f"dangling supersedes should be WARNING, got severities {severities}"
    assert "error" not in severities, "dangling should NOT be ERROR — target may live in another repo"
    print("\nPASS: dangling supersedes correctly flagged as warning\n")


def test_should_detect_self_reference_in_supersedes_as_warning():
    """Bug #5: ADR that supersedes itself (revision marker) is flagged."""
    print("=" * 70)
    print("TEST: Bug #5 — self-reference in supersedes is detected")
    print("=" * 70)
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    graph = ConstitutionGraph.build(adrs)
    report = run_audit(graph, auditors=["supersession_hygiene"])

    self_ref_findings = [
        f for f in report.findings if "ADR-430" in f.affected_adrs and "self-reference" in f.description.lower()
    ]
    print(f"  Self-reference findings for ADR-430: {len(self_ref_findings)}")
    for f in self_ref_findings:
        print(f"    [{f.severity.value}] {f.description[:120]}")
        if f.proposed_resolution:
            print(f"       resolution: {f.proposed_resolution[:100]}")
    assert self_ref_findings, "self-reference must be detected"
    assert all(f.severity.value == "warning" for f in self_ref_findings), (
        "self-reference is WARNING (not ERROR — could be revision marker)"
    )
    # Resolution should mention 'amended' as the right field
    assert any("amended" in (f.proposed_resolution or "") for f in self_ref_findings), (
        "resolution should suggest using 'amended' field instead"
    )
    print("\nPASS: self-reference detected with appropriate severity and resolution\n")


def test_should_produce_coherent_audit_across_combined_edge_case_adrs():
    """All four edge-case ADRs + ADR-099 + the proposed-supersession rule
    must produce a coherent audit report."""
    print("=" * 70)
    print("TEST: combined constitution with all edge cases produces sensible audit")
    print("=" * 70)
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    graph = ConstitutionGraph.build(adrs)
    report = run_audit(graph)

    print(f"  ADRs loaded:       {len(adrs)}")
    print(f"  Findings:          {len(report.findings)}")
    print(f"  Health score:      {report.health.score}")
    print(f"  Issue counts:      {report.health.issue_counts}")

    # ADR-411 supersedes ADR-410 — that creates a back-ref expectation
    # ADR-410 is loaded, so we expect a 'missing back-reference' finding
    missing_backref = [f for f in report.findings if "ADR-410" in f.affected_adrs and "ADR-411" in f.affected_adrs]
    print(f"\n  Missing back-ref ADR-411→ADR-410: {len(missing_backref)} finding(s)")
    assert missing_backref, "should find missing back-ref from freetext supersedes"
    # This is the killer demonstration: even with freetext supersedes, the
    # auditor sees the relation correctly.
    print("\nPASS: combined audit on real-world-like ADR set works end-to-end\n")


if __name__ == "__main__":
    test_should_normalize_legacy_hyphenated_field_names()
    test_should_extract_adr_id_from_freetext_supersedes_string()
    test_should_flag_dangling_supersedes_target_as_warning_not_error()
    test_should_detect_self_reference_in_supersedes_as_warning()
    test_should_produce_coherent_audit_across_combined_edge_case_adrs()
    print("=" * 70)
    print("ALL REGRESSION TESTS PASSED")
    print("=" * 70)
    print()
    print("Bugs 2/3/4/5 from adr-doctor review correctly ported into iil-adrfw.")
    print("Loader and auditor handle real-world ADR variations.")
