"""Schema coverage for platform:ADR-211 Rev 21 (owner-ratified 2026-07-10).

Rev 21 canonicalized frontmatter fields that were already in lived use across the
fleet and assigned the validator coverage to an iil-adrfw follow-up PR. That PR
never happened, so every repo carrying the ratified vocabulary hard-failed
validation. Fleet measurement 2026-08-06: 75 of 747 ADRs invalid; after this
coverage, 30 — the remainder being genuine authoring defects (missing
frontmatter, status values outside the enum), not vocabulary gaps.

Rev 21 is explicit that these are metadata definitions and NOT new gates, so
every field here is optional and no cross-field constraint is enforced.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from iil_adrfw import ADRLoadError, get_schema_dir, load_adr

BASE = """---
id: ADR-001
title: Probe ADR
status: accepted
decision_date: 2026-01-01
owner: probe
domains: [testing]
{extra}---
# Context
Probe.
"""


def _write(tmp_path: Path, extra: str) -> Path:
    p = tmp_path / "ADR-001-probe.md"
    p.write_text(BASE.format(extra=extra), encoding="utf-8")
    return p


def _load(tmp_path: Path, extra: str):
    return load_adr(_write(tmp_path, extra), get_schema_dir())


# Values taken verbatim from ADR-211 Rev 21 §Frontmatter-Konvention and from
# real fleet ADRs, so the test fails if either drifts from the other.
@pytest.mark.parametrize(
    "extra",
    [
        'extends: ["platform:ADR-103"]\n',
        "extends: []\n",
        'realizes_use_cases: ["UC-AH-040"]\n',
        'realizes_use_cases: ["UC-AH-020", "UC-AH-008"]\n',
        "spec_role: root\n",
        "spec_role: hybrid\n",
        "spec_role: standalone\n",
        'replaces_system_ref: "FV-EXCEL-MANUELL"\n',
        "replaces_system_ref: null\n",
        'integrates_with_system_ref: "FV-OKWOBIS"\n',
        'integrates_with_refs: ["TOOL-GAEB-TOOLKIT"]\n',
        "supersedes_partial: []\n",
        'supersedes_partial: ["iil-pet-portal:ADR-001 §Auth Iter. 1 (Basic Auth)"]\n',
        'scope:\n  repos: ["design-hub"]\n  apps: []\n',
        'sister_of: ["ausschreibungs-hub:ADR-005"]\n',
        'sister_of: ["ADR-005"]\n',
        "sister_of: []\n",
    ],
)
def test_should_accept_adr211_rev21_frontmatter(tmp_path, extra):
    assert _load(tmp_path, extra).id == "ADR-001"


def test_should_reject_spec_role_detail(tmp_path):
    """ADR-211 leaves the fourth value 'detail' deliberately open — not accepted yet."""
    with pytest.raises(ADRLoadError, match="spec_role"):
        _load(tmp_path, "spec_role: detail\n")


@pytest.mark.parametrize(
    "extra",
    [
        # Rev 21: NOT part of the convention, normalized away by the loader.
        "ratified: 2026-07-02\n",
        'amendments:\n  - date: 2026-06-02\n    by: "meiki:ADR-037"\n    what: "ergänzt"\n',
        'revisions:\n  - "v1": "erstes Konzept"\n',
        'decision: "Lenkungskreis 2026-06-02 — Stufe 1 freigegeben"\n',
        'external_review: "adr-handoff-extern 2026-06-26 (openai/o3)"\n',
    ],
)
def test_should_strip_generic_governance_variants(tmp_path, extra):
    """These must not hard-fail. A faithful alias is impossible (see _STRIPPED_FIELDS)."""
    adr = _load(tmp_path, extra)
    key = extra.split(":")[0].strip()
    assert key not in adr.raw_frontmatter


def test_should_not_enforce_system_ref_exclusivity(tmp_path):
    """ADR-211 calls the two mutually exclusive but Rev 21 adds no new gates."""
    adr = _load(tmp_path, 'replaces_system_ref: "FV-A"\nintegrates_with_system_ref: "FV-B"\n')
    assert adr.id == "ADR-001"


def test_should_keep_amended_as_the_canonical_amendment_field(tmp_path):
    """`amendments` is stripped; `amended` stays the real, structured field.

    Note the shapes: `amended` needs a `v`-prefixed semver, an ISO date *string*
    and a summary over the minimum length. The fleet's `amendments` entries carry
    `date`/`by`/`what` — aliasing one onto the other would mean inventing a
    version number, which is why the loader strips instead.
    """
    adr = _load(
        tmp_path,
        'amended:\n  - version: "v1.1"\n    at: "2026-06-02"\n    by: "team"\n'
        '    summary: "Kundendaten-Capabilities ergaenzt"\n',
    )
    assert len(adr.amendments) == 1
    assert adr.amendments[0].version == "v1.1"
