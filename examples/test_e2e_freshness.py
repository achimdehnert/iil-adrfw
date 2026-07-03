"""Tests for iil_adrfw.freshness — claim extraction and repo-reality comparison."""

from iil_adrfw.freshness import (
    check_adr_freshness,
    check_freshness,
    extract_claims,
)

ADR_BODY = """\
# ADR-050: Stack decisions

We standardize on PostgreSQL 16 and Redis 7.2.

```yaml
# code blocks are skipped: PostgreSQL 99
```

The app image is python:3.12-slim, exposed on port 8085.
Shorthand pg16 must normalize to the same claim as PostgreSQL 16.
"""


def test_should_extract_and_dedupe_version_image_and_port_claims():
    claims = extract_claims("ADR-050", ADR_BODY)
    by_key = {(c.claim_type, c.subject, c.value) for c in claims}
    assert ("version", "PostgreSQL", "16") in by_key
    assert ("version", "Redis", "7.2") in by_key
    assert ("image", "Python", "3.12-slim") in by_key
    assert ("port", "service", "8085") in by_key
    # pg16 deduped against "PostgreSQL 16"; code-block claim skipped
    assert ("version", "PostgreSQL", "99") not in by_key
    assert len([c for c in claims if c.subject == "PostgreSQL"]) == 1


def _repo(tmp_path):
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n"
        "  db:\n"
        "    image: postgres:15\n"
        "    ports:\n"
        '      - "5433:5432"\n'
        "  web:\n"
        "    image: python:3.12-slim\n"
        "    ports:\n"
        '      - "8085:8000"\n',
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("Django==5.1.2\ncelery>=5.4\n# comment\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('dependencies = ["redis>=7.0"]\n', encoding="utf-8")
    return tmp_path


def test_should_flag_major_version_mismatch_as_warning(tmp_path):
    report = check_adr_freshness("ADR-050", "We use PostgreSQL 16.", _repo(tmp_path))
    assert report.total_claims == 1
    assert len(report.stale_claims) == 1
    finding = report.stale_claims[0]
    assert finding.severity == "warning"  # 16 vs 15 = major mismatch
    assert finding.actual_value == "15"
    assert "ADR-050 claims PostgreSQL 16" in finding.description


def test_should_flag_minor_version_mismatch_as_info(tmp_path):
    report = check_adr_freshness("ADR-050", "Pinned to Django 5.0.", _repo(tmp_path))
    assert [f.severity for f in report.stale_claims] == ["info"]  # 5.0 vs 5.1.2


def test_should_verify_matching_claims_and_ports(tmp_path):
    body = "Runs python:3.12-slim behind port 8085; Redis 7.0 for caching."
    report = check_adr_freshness("ADR-050", body, _repo(tmp_path))
    assert report.stale_claims == []
    assert report.verified_claims == 3


def test_should_flag_unknown_port_as_info_with_found_ports(tmp_path):
    report = check_adr_freshness("ADR-050", "Listens on port 9999.", _repo(tmp_path))
    assert len(report.stale_claims) == 1
    finding = report.stale_claims[0]
    assert finding.severity == "info"
    assert "8085" in finding.actual_value


def test_should_count_unverifiable_claims_without_reality_source(tmp_path):
    # Empty repo: no compose/requirements at all
    report = check_adr_freshness("ADR-050", "We use Nginx 1.25 on port 8080.", tmp_path)
    assert report.total_claims == 2
    assert report.unverifiable_claims == 2
    assert report.stale_claims == []


def test_should_accept_custom_compose_and_requirements_file_lists(tmp_path):
    (tmp_path / "compose.staging.yml").write_text("image: redis:6\n", encoding="utf-8")
    claims = extract_claims("ADR-050", "Redis 7 everywhere.")
    report = check_freshness(claims, tmp_path, compose_files=["compose.staging.yml"], requirements_files=[])
    assert len(report.stale_claims) == 1
    assert report.stale_claims[0].actual_value == "6"


def test_should_flag_stale_when_claim_is_a_naive_string_prefix_of_actual(tmp_path):
    # Regression B-17: `actual.startswith(claim.value)` has no segment
    # boundary, so a claim of "1" wrongly matched an actual of "18" (it's a
    # substring, not the same version segment).
    (tmp_path / "docker-compose.yml").write_text("services:\n  app:\n    image: node:18\n", encoding="utf-8")
    report = check_adr_freshness("ADR-050", "We standardize on Node 1.", tmp_path)
    assert len(report.stale_claims) == 1
    assert report.stale_claims[0].actual_value == "18"


def test_should_verify_when_actual_has_extra_patch_segment_beyond_claim(tmp_path):
    (tmp_path / "docker-compose.yml").write_text("services:\n  app:\n    image: python:3.12.4\n", encoding="utf-8")
    report = check_adr_freshness("ADR-050", "Pinned to Python 3.12.", tmp_path)
    assert report.stale_claims == []
    assert report.verified_claims == 1
