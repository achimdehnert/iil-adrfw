"""Security regression tests for path containment in the ADR loader (issue #31).

Two confirmed traversal channels are covered:
  - a ``rules_file`` frontmatter field pointing at an absolute path or ``../``
    escape (arbitrary file opened + YAML-parsed), and
  - an ADR markdown file that is a symlink to a target outside the ADR
    directory (external file content ingested into the ADR object).

Both must now raise ADRLoadError before any read of the out-of-tree file.
These use ``tmp_path`` directly and are independent of the shared conftest
staging fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from iil_adrfw.persistence import ADRLoadError, load_adr, load_adrs
from iil_adrfw.schemas import get_schema_dir

SCHEMA_DIR = get_schema_dir()

_MINIMAL_FM = """\
---
id: ADR-0001
title: Containment Test
status: accepted
decision_date: 2026-01-01
deciders:
  - "tester <t@example.com>"
domains:
  - general
{extra}
---

# ADR-0001: Containment Test

Body.
"""


def _write_adr(path: Path, extra: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_MINIMAL_FM.format(extra=extra), encoding="utf-8")
    return path


def test_should_reject_rules_file_with_absolute_path(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET\n", encoding="utf-8")
    adr = _write_adr(tmp_path / "adrs" / "ADR-0001-x.md", extra=f'rules_file: "{secret}"')

    with pytest.raises(ADRLoadError, match="rules_file"):
        load_adr(adr, SCHEMA_DIR, validate=False)


def test_should_reject_rules_file_with_parent_traversal(tmp_path):
    (tmp_path / "outside.rules.yaml").write_text("adr_id: ADR-0001\nrules: []\n", encoding="utf-8")
    adr = _write_adr(tmp_path / "adrs" / "ADR-0001-x.md", extra='rules_file: "../outside.rules.yaml"')

    with pytest.raises(ADRLoadError, match="rules_file"):
        load_adr(adr, SCHEMA_DIR, validate=False)


def test_should_reject_symlinked_adr_pointing_outside_dir(tmp_path):
    outside = _write_adr(tmp_path / "outside.md")
    outside.write_text(_MINIMAL_FM.format(extra="").replace("Containment Test", "EXFILTRATED"), encoding="utf-8")
    adrs_dir = tmp_path / "adrs"
    adrs_dir.mkdir()
    link = adrs_dir / "ADR-0002-symlink.md"
    link.symlink_to(outside)

    with pytest.raises(ADRLoadError, match="outside the ADR directory"):
        load_adr(link, SCHEMA_DIR, validate=False)


def test_should_not_ingest_symlinked_adr_content_via_load_adrs(tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text(_MINIMAL_FM.format(extra="").replace("Containment Test", "EXFILTRATED"), encoding="utf-8")
    adrs_dir = tmp_path / "adrs"
    adrs_dir.mkdir()
    (adrs_dir / "ADR-0003-symlink.md").symlink_to(outside)

    # load_adrs iterates the directory; the symlink must raise rather than
    # silently surface the external file's title.
    with pytest.raises(ADRLoadError, match="outside the ADR directory"):
        load_adrs(adrs_dir, SCHEMA_DIR, validate=False)


def test_should_load_legitimate_adr_with_bare_rules_file(tmp_path):
    adrs_dir = tmp_path / "adrs"
    adr = _write_adr(adrs_dir / "ADR-0001-x.md", extra='rules_file: "ADR-0001-x.rules.yaml"')
    (adrs_dir / "ADR-0001-x.rules.yaml").write_text("adr_id: ADR-0001\nrules: []\n", encoding="utf-8")

    # Regression: a normal bare-filename rules_file beside the ADR still loads.
    loaded = load_adr(adr, SCHEMA_DIR, validate=False)
    assert loaded.id == "ADR-0001"
    assert loaded.rules == []


def test_should_load_plain_adr_without_rules_file(tmp_path):
    adr = _write_adr(tmp_path / "adrs" / "ADR-0001-x.md")
    loaded = load_adr(adr, SCHEMA_DIR, validate=False)
    assert loaded.id == "ADR-0001"
