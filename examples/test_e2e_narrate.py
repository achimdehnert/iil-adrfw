"""Tests for adr_narrate (4 audiences, 3 selection modes, fixed-section structure)."""

import os  # noqa: E402
import shutil  # noqa: E402
from pathlib import Path  # noqa: E402

BASE = Path(__file__).resolve().parent
ADRS_DIR = BASE / "_test_adrs_narrate"
SCHEMAS_DIR = BASE.parent / "schemas"

if ADRS_DIR.exists():
    shutil.rmtree(ADRS_DIR)
ADRS_DIR.mkdir(parents=True)

# Stage canonical fixtures
shutil.copy(BASE / "ADR-099-multi-tenancy.md", ADRS_DIR)
shutil.copy(BASE / "ADR-099-multi-tenancy.rules.yaml", ADRS_DIR)
shutil.copy(BASE / "ADR-188-unified-vector-store.md", ADRS_DIR)
shutil.copy(BASE / "ADR-188-unified-vector-store.rules.yaml", ADRS_DIR)

os.environ["IIL_ADRFW_ADRS_DIR"] = str(ADRS_DIR)
os.environ["IIL_ADRFW_SCHEMAS_DIR"] = str(SCHEMAS_DIR)

from iil_adrfw.narrate import Audience, compose_narrative, select_adrs  # noqa: E402
from iil_adrfw.persistence import load_adrs  # noqa: E402
from iil_adrfw.server import NarrateRequest, _do_narrate  # noqa: E402

# Common fixed-section structure expected for every narrative
EXPECTED_SECTIONS = (
    "Overview",
    "Decisions in order",
    "Supersession chains",
    "Open questions",
    "Compliance trail",
)


def _all_adrs():
    return load_adrs(ADRS_DIR, SCHEMAS_DIR)


def test_all_audiences_emit_same_section_structure():
    """Every audience must produce exactly the same 5 sections in the same order."""
    print("=" * 70)
    print("TEST: all 4 audiences emit identical fixed section structure")
    print("=" * 70)
    adrs = _all_adrs()
    for aud in Audience:
        narrative = compose_narrative(adrs, aud, scope_label="full constitution")
        section_headings = tuple(s.heading for s in narrative.sections)
        print(f"  {aud.value:10}: {section_headings}")
        assert section_headings == EXPECTED_SECTIONS, f"{aud.value} produced wrong section list: {section_headings}"
    print("  PASS: all 4 audiences have the same 5 sections in the same order\n")


def test_audience_specific_intro_text():
    """Each audience produces a distinct intro framing."""
    print("=" * 70)
    print("TEST: audience-specific intro framing")
    print("=" * 70)
    adrs = _all_adrs()
    intros = {aud: compose_narrative(adrs, aud).intro for aud in Audience}
    print(f"  new_dev intro:   {intros[Audience.NEW_DEV][:80]}...")
    print(f"  senior intro:    {intros[Audience.SENIOR][:80]}...")
    print(f"  architect intro: {intros[Audience.ARCHITECT][:80]}...")
    print(f"  auditor intro:   {intros[Audience.AUDITOR][:80]}...")
    # All four intros must be distinct
    assert len({intros[a] for a in Audience}) == 4
    # Intros must be non-empty
    for aud in Audience:
        assert intros[aud], f"{aud.value} intro is empty"
    print("  PASS: 4 distinct, non-empty intro texts\n")


def test_empty_sections_show_none_marker():
    """When there's nothing to put in a section, body is '(none)' — not omitted."""
    print("=" * 70)
    print("TEST: empty sections explicitly show '(none)'")
    print("=" * 70)
    # Pick a single ADR that has no supersessions
    adrs = _all_adrs()
    adr_099 = [a for a in adrs if a.id == "ADR-099"]
    assert adr_099, "fixture missing"
    narrative = compose_narrative(adr_099, Audience.NEW_DEV)
    sup_section = next(s for s in narrative.sections if s.heading == "Supersession chains")
    print(f"  ADR-099 alone, supersession section body: {sup_section.body!r}")
    # ADR-099 has no supersedes/superseded_by → body should be '(none)'
    assert sup_section.body == "(none)", f"expected '(none)' for empty supersession section, got {sup_section.body!r}"
    print("  PASS: empty sections marked with '(none)'\n")


def test_selection_by_domain():
    """select_adrs filters by a domain tag."""
    print("=" * 70)
    print("TEST: selection by domain tag")
    print("=" * 70)
    adrs = _all_adrs()
    print(f"  All ADRs: {[a.id for a in adrs]}")
    for a in adrs:
        print(f"    {a.id}: domains={list(a.domains)}")

    # Both ADR-099 and ADR-188 should have at least one domain — pick one
    sample_domain = adrs[0].domains[0] if adrs[0].domains else None
    if sample_domain:
        selected = select_adrs(adrs, domain=sample_domain)
        print(f"  Selected with domain='{sample_domain}': {[a.id for a in selected]}")
        assert all(sample_domain in a.domains for a in selected)
        assert len(selected) >= 1
    print("  PASS: domain selection works\n")


def test_selection_by_id_set():
    """select_adrs filters by explicit ID list."""
    print("=" * 70)
    print("TEST: selection by id_set")
    print("=" * 70)
    adrs = _all_adrs()
    selected = select_adrs(adrs, id_set=["ADR-099"])
    print(f"  Selected with id_set=['ADR-099']: {[a.id for a in selected]}")
    assert len(selected) == 1
    assert selected[0].id == "ADR-099"
    print("  PASS: id_set selection works\n")


def test_selection_requires_at_least_one_selector():
    """Calling select_adrs with no selectors raises ValueError."""
    print("=" * 70)
    print("TEST: select_adrs without any selector raises")
    print("=" * 70)
    try:
        select_adrs(_all_adrs())
        raise AssertionError("expected ValueError")
    except ValueError as e:
        print(f"  PASS: ValueError raised: {e}")
    print()


def test_selection_combined_and():
    """domain + id_set AND-combine."""
    print("=" * 70)
    print("TEST: domain + id_set selectors AND-combine")
    print("=" * 70)
    adrs = _all_adrs()
    # Use a domain ADR-099 has but ADR-188 does not (or vice versa)
    adr_099 = next(a for a in adrs if a.id == "ADR-099")
    if adr_099.domains:
        d = adr_099.domains[0]
        # Both selectors satisfied for ADR-099
        selected = select_adrs(adrs, domain=d, id_set=["ADR-099", "ADR-188"])
        print(f"  domain='{d}' + id_set=['ADR-099','ADR-188']: {[a.id for a in selected]}")
        assert all(a.id in ("ADR-099", "ADR-188") for a in selected)
        assert all(d in a.domains for a in selected)
    print("  PASS: AND combination works\n")


def test_mcp_tool_each_audience():
    """MCP tool entry point produces a NarrateResponse with markdown for each audience."""
    print("=" * 70)
    print("TEST: MCP tool — produce response for each audience")
    print("=" * 70)
    for aud in Audience:
        resp = _do_narrate(
            NarrateRequest(
                audience=aud.value,
                id_set=["ADR-099", "ADR-188"],
                scope_label="rag-mcp scope",
            )
        )
        assert resp.audience == aud.value
        assert resp.markdown.startswith("# ")
        assert len(resp.sections) == 5
        section_headings = tuple(s.heading for s in resp.sections)
        assert section_headings == EXPECTED_SECTIONS
        print(f"  {aud.value:10}: title='{resp.title[:60]}', sections={len(resp.sections)}, md={len(resp.markdown)}b")
    print("  PASS: all 4 audiences via MCP tool\n")


def test_mcp_tool_validation_errors():
    """MCP tool surfaces validation errors clearly."""
    print("=" * 70)
    print("TEST: MCP tool — validation errors")
    print("=" * 70)
    try:
        _do_narrate(NarrateRequest(audience="new_dev"))
        raise AssertionError("expected ValueError for missing selectors")
    except ValueError as e:
        assert "selector" in str(e).lower()
        print(f"  PASS: missing selectors → ValueError: {e}")

    try:
        _do_narrate(NarrateRequest(audience="new_dev", id_set=["ADR-NONEXISTENT-9999"]))
        raise AssertionError("expected ValueError for empty selection")
    except ValueError as e:
        assert "no adrs matched" in str(e).lower()
        print(f"  PASS: empty match → ValueError: {e}")
    print()


def test_auditor_compliance_trail_has_dates_and_deciders():
    """Auditor narrative's compliance trail shows decision_date and deciders."""
    print("=" * 70)
    print("TEST: auditor compliance trail contains structured metadata")
    print("=" * 70)
    adrs = _all_adrs()
    narrative = compose_narrative(adrs, Audience.AUDITOR)
    ct_section = next(s for s in narrative.sections if s.heading == "Compliance trail")
    print("  Compliance trail body (excerpt):")
    for line in ct_section.body.splitlines()[:12]:
        print(f"    {line}")
    # Must contain at least one ADR id, the keyword 'Decision date', and 'Deciders'
    assert "ADR-099" in ct_section.body or "ADR-188" in ct_section.body
    assert "Decision date:" in ct_section.body
    assert "Deciders:" in ct_section.body
    print("  PASS: auditor trail structured properly\n")


def test_markdown_render_is_valid_markdown():
    """The markdown field renders as valid, well-formed Markdown."""
    print("=" * 70)
    print("TEST: render_markdown produces well-formed output")
    print("=" * 70)
    adrs = _all_adrs()
    narrative = compose_narrative(adrs, Audience.SENIOR, scope_label="test")
    md = narrative.render_markdown()
    print(f"  Markdown length: {len(md)} bytes")
    print(f"  First 200 chars: {md[:200]!r}")
    # Must start with H1
    assert md.startswith("# ")
    # Must contain all 5 section H2s
    for heading in EXPECTED_SECTIONS:
        assert f"## {heading}" in md, f"missing H2 for '{heading}'"
    print("  PASS: markdown render is well-formed\n")


if __name__ == "__main__":
    test_all_audiences_emit_same_section_structure()
    test_audience_specific_intro_text()
    test_empty_sections_show_none_marker()
    test_selection_by_domain()
    test_selection_by_id_set()
    test_selection_requires_at_least_one_selector()
    test_selection_combined_and()
    test_mcp_tool_each_audience()
    test_mcp_tool_validation_errors()
    test_auditor_compliance_trail_has_dates_and_deciders()
    test_markdown_render_is_valid_markdown()
    print("=" * 70)
    print("ALL adr_narrate TESTS PASSED")
    print("=" * 70)
