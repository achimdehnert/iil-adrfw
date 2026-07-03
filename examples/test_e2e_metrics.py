"""Tests for iil_adrfw.metrics — compute_all, write_metrics, controlling_report.

In-process (no subprocess): the module takes plain objects with `.id`,
`.depends_on`, `.raw_frontmatter`, so lightweight namespaces suffice.
"""

from datetime import date
from types import SimpleNamespace

from iil_adrfw.metrics import ADRMetrics, compute_all, controlling_report, write_metrics


def _adr(adr_id: str, depends_on=None, **frontmatter):
    return SimpleNamespace(
        id=adr_id,
        depends_on=depends_on or [],
        raw_frontmatter=frontmatter,
    )


def _days_ago(n: int) -> str:
    return date.fromordinal(date.today().toordinal() - n).isoformat()


def test_should_count_inbound_links_case_insensitively():
    adrs = [
        _adr("ADR-100"),
        _adr("ADR-101", depends_on=["ADR-100"]),
        _adr("ADR-102", depends_on=["adr-100§R1", "ADR-101"]),
    ]
    m = compute_all(adrs)
    assert m["ADR-100"].inbound_links == 2
    assert m["ADR-101"].inbound_links == 1
    assert m["ADR-102"].inbound_links == 0


def test_should_compute_ttd_days_from_knowledge_from_to_decision_date():
    m = compute_all([_adr("ADR-100", decision_date="2026-01-11", knowledge_from="2026-01-01")])
    assert m["ADR-100"].ttd_days == 10


def test_should_leave_ttd_none_when_dates_missing_or_reversed():
    adrs = [
        _adr("ADR-100", decision_date="2026-01-01"),  # no knowledge_from
        _adr("ADR-101", decision_date="2026-01-01", knowledge_from="2026-02-01"),  # reversed
        _adr("ADR-102", decision_date="not-a-date", knowledge_from="2026-01-01"),  # unparseable
    ]
    m = compute_all(adrs)
    assert m["ADR-100"].ttd_days is None
    assert m["ADR-101"].ttd_days is None
    assert m["ADR-102"].ttd_days is None


def test_should_compute_ttr_days_from_first_review_after_decision():
    m = compute_all(
        [
            _adr(
                "ADR-100",
                decision_date="2026-01-01",
                reviewed_by=[
                    {"name": "b", "date": "2026-01-20"},
                    {"name": "a", "date": "2026-01-06"},
                    "not-a-dict-entry",
                ],
            )
        ]
    )
    assert m["ADR-100"].ttr_days == 5  # first (earliest) review counts


def test_should_count_ai_interactions_with_90d_window():
    m = compute_all(
        [
            _adr(
                "ADR-100",
                ai_sparring_by=[
                    {"model": "x", "date": _days_ago(10)},
                    {"model": "y", "date": _days_ago(200)},
                    {"model": "z"},  # no date → total only
                ],
            )
        ]
    )
    assert m["ADR-100"].ai_interactions == 3
    assert m["ADR-100"].ai_interactions_90d == 1


def test_should_write_metrics_into_frontmatter_and_be_idempotent(tmp_path):
    (tmp_path / "ADR-100-example.md").write_text(
        "---\nid: ADR-100\ntitle: Example\nstatus: accepted\n---\n\n# ADR-100\n\nBody.\n",
        encoding="utf-8",
    )
    (tmp_path / "not-an-adr.md").write_text("no frontmatter", encoding="utf-8")

    metrics_map = {"ADR-100": ADRMetrics(adr_id="ADR-100", inbound_links=3, ai_interactions=2)}

    assert write_metrics(tmp_path, metrics_map) == 1
    text = (tmp_path / "ADR-100-example.md").read_text(encoding="utf-8")
    assert "metrics:" in text
    assert "inbound_links: 3" in text
    assert text.endswith("Body.\n")  # body preserved

    # Second run: identical values (modulo last_computed) → no rewrite
    fresh = {"ADR-100": ADRMetrics(adr_id="ADR-100", inbound_links=3, ai_interactions=2)}
    assert write_metrics(tmp_path, fresh) == 0


def test_should_skip_files_without_frontmatter_or_unknown_ids(tmp_path):
    (tmp_path / "ADR-200-nofm.md").write_text("# ADR-200 without frontmatter\n", encoding="utf-8")
    (tmp_path / "ADR-201-unknown.md").write_text("---\nid: ADR-201\n---\nbody\n", encoding="utf-8")
    # map only knows ADR-200 (which has no frontmatter block) → nothing written
    assert write_metrics(tmp_path, {"ADR-200": ADRMetrics(adr_id="ADR-200")}) == 0


def test_should_render_controlling_report_with_totals():
    metrics_map = {
        "ADR-100": ADRMetrics(adr_id="ADR-100", inbound_links=4, ai_interactions=2, ai_interactions_90d=1, ttr_days=6),
        "ADR-101": ADRMetrics(adr_id="ADR-101", inbound_links=0, ai_interactions=0),
    }
    report = controlling_report(metrics_map)
    assert "## ADR Controlling Report" in report
    assert "| Total ADRs | 2 |" in report
    assert "| AI interactions (total) | 2 |" in report
    assert "| ADRs with human review | 1 |" in report
    assert "| Avg time-to-review | 6d |" in report
    assert "`ADR-100`" in report


def test_should_report_placeholder_when_no_adrs():
    assert controlling_report({}) == "No ADRs found."
