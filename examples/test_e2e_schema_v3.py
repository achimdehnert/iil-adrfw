"""Schema v3 — comprehensive tests.

Tests cover all C.1-C.8 normalization steps and the schema field changes.
Each test is isolated: stages exactly the fixture it needs, then loads with
strict validation (validate=True) and verifies behavior.
"""
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
ADRS_DIR = BASE / "_test_adrs_v3"
SCHEMAS_DIR = BASE.parent / "schemas"

if ADRS_DIR.exists():
    shutil.rmtree(ADRS_DIR)
ADRS_DIR.mkdir(parents=True)

os.environ["IIL_ADRFW_ADRS_DIR"] = str(ADRS_DIR)
os.environ["IIL_ADRFW_SCHEMAS_DIR"] = str(SCHEMAS_DIR)

from iil_adrfw.persistence import (
    ADRLoadError, _normalize_status, load_adr, load_adrs,
    detect_legacy_aliases, original_frontmatter,
)


# Common minimal frontmatter — extended in each test
_BASE = """---
id: ADR-{nnn}
title: Test ADR
status: accepted
decision_date: "2026-01-01"
deciders:
  - "Achim"
domains:
  - test
{extra}---

# ADR-{nnn} — body
"""


def _stage(name: str, content: str) -> Path:
    p = ADRS_DIR / name
    p.write_text(content, encoding="utf-8")
    return p


def _cleanup():
    """Remove staged ADR files between tests."""
    for f in ADRS_DIR.glob("ADR-*.md"):
        f.unlink()


# ─────────────────────────────────────────────────────────────
# C.2 — Status normalization
# ─────────────────────────────────────────────────────────────


def test_status_normalization_unit():
    """Unit tests for _normalize_status."""
    cases = [
        ("Accepted", "accepted"),
        ("accepted", "accepted"),
        ("accepted (v2)", "accepted"),
        (" Proposed ", "proposed"),
        ('"accepted"', "accepted"),
        ("Accepted (Revision v1.1)", "accepted"),
        ("draft", "draft"),
        ("xyzzy_unknown", "xyzzy_unknown"),  # unknown values pass through
    ]
    for raw, expected in cases:
        result = _normalize_status(raw)
        assert result == expected, f"{raw!r} → {result!r}, expected {expected!r}"
    print("  PASS: 8 status normalization cases")


def test_status_uppercase_loads_strict():
    """ADR with status: 'Accepted' (uppercase) loads under strict validation."""
    _cleanup()
    _stage("ADR-501.md", _BASE.format(nnn="501", extra="").replace(
        "status: accepted", 'status: "Accepted"'))
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    assert len(adrs) == 1
    assert adrs[0].status.value == "accepted"
    print("  PASS: 'Accepted' normalized to 'accepted' before strict check")


def test_status_with_version_suffix():
    """ADR with 'accepted (v2)' loads under strict validation."""
    _cleanup()
    _stage("ADR-502.md", _BASE.format(nnn="502", extra="").replace(
        "status: accepted", 'status: "accepted (v2)"'))
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    assert len(adrs) == 1
    assert adrs[0].status.value == "accepted"
    print("  PASS: '(v2)' suffix stripped")


# ─────────────────────────────────────────────────────────────
# C.1 — Field renames
# ─────────────────────────────────────────────────────────────


def test_relates_to_aliases_to_related():
    _cleanup()
    extra = "relates_to:\n  - ADR-001\n"
    _stage("ADR-510.md", _BASE.format(nnn="510", extra=extra))
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    assert "relates_to" not in adrs[0].raw_frontmatter
    assert adrs[0].raw_frontmatter.get("related") == ["ADR-001"]
    print("  PASS: relates_to → related")


def test_author_aliases_to_owner():
    _cleanup()
    extra = 'author: "Cascade"\n'
    _stage("ADR-511.md", _BASE.format(nnn="511", extra=extra))
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    assert adrs[0].owner == "Cascade"
    assert "author" not in adrs[0].raw_frontmatter
    print("  PASS: author → owner")


def test_adr_id_aliases_to_id():
    """adr_id field is renamed to id. Combined with main id, target wins."""
    _cleanup()
    # Frontmatter has only adr_id, no id
    fm = """---
adr_id: ADR-512
title: Test fixture for adr_id alias
status: accepted
decision_date: "2026-01-01"
deciders:
  - "Achim"
domains:
  - test
---

# Body
"""
    _stage("ADR-512.md", fm)
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    assert adrs[0].id == "ADR-512"
    print("  PASS: adr_id → id")


def test_legacy_alias_is_detected_but_still_validates():
    """A non-canonical alias (adr_id) is DETECTED for deprecation warning,
    yet the ADR still validates (warn, never hard-fail)."""
    _cleanup()
    fm = """---
adr_id: ADR-513
title: Legacy alias fixture
status: accepted
decision_date: "2026-01-01"
deciders:
  - "Achim"
domains:
  - test
---

# Body
"""
    p = _stage("ADR-513.md", fm)
    # Deprecation detection works on the ORIGINAL (pre-normalize) frontmatter
    aliases = detect_legacy_aliases(original_frontmatter(p))
    assert ("adr_id", "id") in aliases, aliases
    # ...and validation still passes (alias is normalized, not rejected)
    adr = load_adr(p, SCHEMAS_DIR, validate=True)
    assert adr.id == "ADR-513"
    print("  PASS: adr_id detected as deprecated AND still valid")


def test_canonical_id_yields_no_deprecation_warning():
    """An ADR using the canonical id: key produces no alias warnings."""
    _cleanup()
    fm = _BASE.format(nnn="514", extra="")
    p = _stage("ADR-514.md", fm)
    assert detect_legacy_aliases(original_frontmatter(p)) == []
    print("  PASS: canonical id → no deprecation warning")


def test_review_aliases_to_review_status():
    _cleanup()
    extra = "review: approved\n"
    _stage("ADR-513.md", _BASE.format(nnn="513", extra=extra))
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    assert adrs[0].review_status == "approved"
    print("  PASS: review → review_status")


def test_last_verified_aliases_to_last_reviewed():
    _cleanup()
    extra = 'last_verified: "2026-04-01"\n'
    _stage("ADR-514.md", _BASE.format(nnn="514", extra=extra))
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    assert adrs[0].raw_frontmatter.get("last_reviewed") == "2026-04-01"
    print("  PASS: last_verified → last_reviewed")


# ─────────────────────────────────────────────────────────────
# C.8 — Stripped fields
# ─────────────────────────────────────────────────────────────


def test_jekyll_metadata_stripped():
    """nav_order, parent: tool-specific noise, stripped silently."""
    _cleanup()
    extra = "nav_order: 5\nparent: Architecture\n"
    _stage("ADR-520.md", _BASE.format(nnn="520", extra=extra))
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    assert "nav_order" not in adrs[0].raw_frontmatter
    assert "parent" not in adrs[0].raw_frontmatter
    print("  PASS: nav_order, parent stripped before validation")


def test_reviewed_by_stripped_not_aliased():
    """reviewed-by has different semantics from consulted — must be stripped, not aliased."""
    _cleanup()
    extra = "reviewed-by:\n  - Late Reviewer\nconsulted:\n  - Early Advisor\n"
    _stage("ADR-521.md", _BASE.format(nnn="521", extra=extra))
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    fm = adrs[0].raw_frontmatter
    assert "reviewed-by" not in fm
    # consulted is preserved separately — NOT polluted by reviewed-by
    assert fm.get("consulted") == ["Early Advisor"]
    print("  PASS: reviewed-by stripped, consulted untouched")


def test_supersedes_check_stripped():
    """supersedes_check is audit-tool transient state, not user content."""
    _cleanup()
    extra = "supersedes_check: pending\n"
    _stage("ADR-522.md", _BASE.format(nnn="522", extra=extra))
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    assert "supersedes_check" not in adrs[0].raw_frontmatter
    print("  PASS: supersedes_check stripped")


# ─────────────────────────────────────────────────────────────
# Strict mode still rejects truly-unknown fields
# ─────────────────────────────────────────────────────────────


def test_truly_unknown_field_still_rejected():
    """Unknown fields not in the strip list must fail strict validation."""
    _cleanup()
    extra = "xyzzy_unknown_field: 42\n"
    _stage("ADR-530.md", _BASE.format(nnn="530", extra=extra))
    try:
        load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
        raise AssertionError("expected ADRLoadError for xyzzy_unknown_field")
    except ADRLoadError as e:
        assert "xyzzy_unknown_field" in str(e)
    print("  PASS: truly unknown field rejected (strict mode preserved)")


def test_raw_mode_skips_phase_1():
    """raw=True skips normalization — useful for diagnosing what raw frontmatter looks like."""
    _cleanup()
    extra = 'author: "Cascade"\nrelates_to:\n  - ADR-001\n'
    _stage("ADR-531.md", _BASE.format(nnn="531", extra=extra))
    # With raw=True, validate=False, we get the frontmatter unchanged
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=False, raw=True)
    fm = adrs[0].raw_frontmatter
    assert "author" in fm  # NOT renamed to owner
    assert "relates_to" in fm  # NOT renamed to related
    print("  PASS: raw=True preserves source frontmatter for diagnosis")


# ─────────────────────────────────────────────────────────────
# C.7 — implemented field handling
# ─────────────────────────────────────────────────────────────


def test_implemented_bool_sets_status():
    """implemented: true → implementation_status: implemented"""
    _cleanup()
    extra = "implemented: true\n"
    _stage("ADR-540.md", _BASE.format(nnn="540", extra=extra))
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    assert adrs[0].implementation_status == "implemented"
    assert "implemented" not in adrs[0].raw_frontmatter
    print("  PASS: implemented:true → implementation_status:implemented")


def test_implemented_date_sets_status_and_updated():
    """implemented: '2026-03-15' → status set + date moved to 'updated' (not evidence)."""
    _cleanup()
    extra = 'implemented: "2026-03-15"\n'
    _stage("ADR-541.md", _BASE.format(nnn="541", extra=extra))
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    assert adrs[0].implementation_status == "implemented"
    # date moves to 'updated' field
    assert adrs[0].raw_frontmatter.get("updated") == "2026-03-15"
    print("  PASS: implemented:date → status + updated")


def test_implemented_false_no_change():
    """implemented: false should not flip status; field is removed silently."""
    _cleanup()
    extra = "implemented: false\n"
    _stage("ADR-542.md", _BASE.format(nnn="542", extra=extra))
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    assert adrs[0].implementation_status == "none"
    assert "implemented" not in adrs[0].raw_frontmatter
    print("  PASS: implemented:false leaves implementation_status untouched")


# ─────────────────────────────────────────────────────────────
# C.6 — amended legacy date format
# ─────────────────────────────────────────────────────────────


def test_amended_as_plain_date_normalized():
    """amended: '2026-05-08' (legacy) becomes last_reviewed and is removed from frontmatter."""
    _cleanup()
    extra = 'amended: "2026-05-08"\n'
    _stage("ADR-550.md", _BASE.format(nnn="550", extra=extra))
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    fm = adrs[0].raw_frontmatter
    assert "amended" not in fm  # malformed legacy form stripped
    assert fm.get("last_reviewed") == "2026-05-08"
    print("  PASS: amended:date legacy form → last_reviewed")


def test_amended_proper_list_preserved():
    """amended as proper list of Amendments is preserved unchanged."""
    _cleanup()
    extra = (
        'amended:\n'
        '  - version: "v1.1"\n'
        '    at: "2026-05-08"\n'
        '    by: "Achim"\n'
        '    summary: "Bug-fix amendment"\n'
    )
    _stage("ADR-551.md", _BASE.format(nnn="551", extra=extra))
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    assert len(adrs[0].amendments) == 1
    assert adrs[0].amendments[0].version == "v1.1"
    print("  PASS: proper amended list passes through unchanged")


# ─────────────────────────────────────────────────────────────
# Schema v3 new fields — round-trip
# ─────────────────────────────────────────────────────────────


def test_new_fields_load_and_appear_on_domain_object():
    _cleanup()
    extra = (
        'updated: "2026-04-15"\n'
        'version: 3\n'
        'review_status: approved\n'
        'owner: "Platform Team"\n'
        'implementation_done_when: "all consumer-repos green"\n'
    )
    _stage("ADR-560.md", _BASE.format(nnn="560", extra=extra))
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    a = adrs[0]
    assert a.version == 3
    assert a.review_status == "approved"
    assert a.owner == "Platform Team"
    assert a.implementation_done_when == "all consumer-repos green"
    assert a.updated is not None
    print("  PASS: all 5 new schema-v3 fields hydrate onto ADR object")


def test_review_status_enum_validated():
    """review_status must match enum — invalid values rejected."""
    _cleanup()
    extra = "review_status: bogus_value\n"
    _stage("ADR-561.md", _BASE.format(nnn="561", extra=extra))
    try:
        load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
        raise AssertionError("expected enum violation")
    except ADRLoadError as e:
        assert "review_status" in str(e) or "bogus_value" in str(e)
    print("  PASS: review_status enum is enforced")


# ─────────────────────────────────────────────────────────────
# Removed fields rejected in strict mode
# ─────────────────────────────────────────────────────────────


def test_glossary_field_now_rejected():
    """glossary was removed from schema in v3 — strict mode rejects it."""
    _cleanup()
    extra = "glossary:\n  - term: foo\n    definition: bar\n"
    _stage("ADR-570.md", _BASE.format(nnn="570", extra=extra))
    try:
        load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
        raise AssertionError("expected glossary rejection")
    except ADRLoadError as e:
        assert "glossary" in str(e)
    print("  PASS: glossary field now rejected (was removed in schema v3)")


# ─────────────────────────────────────────────────────────────
# Combined real-world-like scenarios
# ─────────────────────────────────────────────────────────────


def test_realistic_legacy_adr_full_chain():
    """An ADR with multiple legacy quirks loads cleanly through full Phase 1."""
    _cleanup()
    fm = """---
id: ADR-580
title: Realistic legacy ADR
status: "Accepted (Revision v1.1)"
decision_date: "2025-08-15"
decision-makers: Achim Dehnert
relates_to:
  - ADR-001
author: "Cascade"
review: approved
nav_order: 12
parent: Architecture
reviewed-by:
  - Late Reviewer
implemented: "2025-09-01"
domains:
  - infrastructure
amended: "2025-12-01"
---

# Body
"""
    _stage("ADR-580.md", fm)
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    a = adrs[0]
    assert a.status.value == "accepted"
    assert a.deciders == ("Achim Dehnert",)
    assert a.raw_frontmatter.get("related") == ["ADR-001"]
    assert a.owner == "Cascade"
    assert a.review_status == "approved"
    assert a.implementation_status == "implemented"
    # date from implemented: moved to updated
    assert a.raw_frontmatter.get("updated") == "2025-09-01"
    # amended: as date became last_reviewed
    assert a.raw_frontmatter.get("last_reviewed") == "2025-12-01"
    # tool-noise stripped
    assert "nav_order" not in a.raw_frontmatter
    assert "parent" not in a.raw_frontmatter
    assert "reviewed-by" not in a.raw_frontmatter
    print("  PASS: full Phase 1 chain works on realistic legacy fixture")


# ─────────────────────────────────────────────────────────────
# Test runner
# ─────────────────────────────────────────────────────────────


if __name__ == "__main__":
    tests = [
        ("status normalization unit", test_status_normalization_unit),
        ("status uppercase loads strict", test_status_uppercase_loads_strict),
        ("status with (v2) suffix", test_status_with_version_suffix),
        ("relates_to → related", test_relates_to_aliases_to_related),
        ("author → owner", test_author_aliases_to_owner),
        ("adr_id → id", test_adr_id_aliases_to_id),
        ("legacy alias detected + still valid", test_legacy_alias_is_detected_but_still_validates),
        ("canonical id → no warning", test_canonical_id_yields_no_deprecation_warning),
        ("review → review_status", test_review_aliases_to_review_status),
        ("last_verified → last_reviewed", test_last_verified_aliases_to_last_reviewed),
        ("Jekyll metadata stripped", test_jekyll_metadata_stripped),
        ("reviewed-by stripped not aliased", test_reviewed_by_stripped_not_aliased),
        ("supersedes_check stripped", test_supersedes_check_stripped),
        ("truly unknown field rejected", test_truly_unknown_field_still_rejected),
        ("raw=True skips Phase 1", test_raw_mode_skips_phase_1),
        ("implemented:bool", test_implemented_bool_sets_status),
        ("implemented:date", test_implemented_date_sets_status_and_updated),
        ("implemented:false", test_implemented_false_no_change),
        ("amended:date legacy", test_amended_as_plain_date_normalized),
        ("amended list preserved", test_amended_proper_list_preserved),
        ("new fields round-trip", test_new_fields_load_and_appear_on_domain_object),
        ("review_status enum", test_review_status_enum_validated),
        ("glossary now rejected", test_glossary_field_now_rejected),
        ("realistic legacy ADR", test_realistic_legacy_adr_full_chain),
    ]
    print("=" * 70)
    print(f"Schema v3 tests — {len(tests)} cases")
    print("=" * 70)
    failed = []
    for name, fn in tests:
        print(f"\n→ {name}")
        try:
            fn()
        except Exception as e:
            print(f"  FAIL: {type(e).__name__}: {e}")
            failed.append((name, e))
    print()
    print("=" * 70)
    if failed:
        print(f"FAILED: {len(failed)} of {len(tests)}")
        for name, e in failed:
            print(f"  - {name}: {e}")
        raise SystemExit(1)
    else:
        print(f"ALL {len(tests)} SCHEMA-V3 TESTS PASSED")
    print("=" * 70)
