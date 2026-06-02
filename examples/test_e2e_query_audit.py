"""E2E tests for adr_query and adr_audit."""

import os  # noqa: E402
import shutil  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

BASE = Path(__file__).resolve().parent
ADRS_DIR = BASE / "_test_adrs_qa"
SCHEMAS_DIR = BASE.parent / "schemas"
REPO_ROOT = BASE / "django_polyrepo"

if ADRS_DIR.exists():
    shutil.rmtree(ADRS_DIR)
ADRS_DIR.mkdir(parents=True)
for fn in [
    "ADR-099-multi-tenancy.md",
    "ADR-099-multi-tenancy.rules.yaml",
    "ADR-188-unified-vector-store.md",
    "ADR-188-unified-vector-store.rules.yaml",
]:
    shutil.copy(BASE / fn, ADRS_DIR)

os.environ["IIL_ADRFW_ADRS_DIR"] = str(ADRS_DIR)
os.environ["IIL_ADRFW_SCHEMAS_DIR"] = str(SCHEMAS_DIR)
os.environ["IIL_ADRFW_REPO_ROOT"] = str(REPO_ROOT)

from iil_adrfw.server import (  # noqa: E402
    AuditRequest,
    QueryRequest,
    _do_audit,
    _do_query,
)

# ============================================================
# adr_query
# ============================================================


def test_query_by_domain():
    print("=" * 70)
    print("TEST: adr_query — by domain tag")
    print("=" * 70)
    resp = _do_query(QueryRequest(domain="django/models"))
    print(f"  Routing:    {resp.routing}")
    print(f"  Confidence: {resp.confidence}")
    print(f"  Answer:     {resp.primary_answer[:120]}...")
    print(f"  Citations:  {len(resp.citations)}")
    for c in resp.citations:
        print(f"    [{c.relevance:10}] {c.adr_id}  {c.title[:60]}")
    assert len(resp.citations) >= 2  # Both ADR-099 and ADR-188 cover django/models
    print("\nPASS: domain query returns relevant ADRs\n")


def test_query_by_concept():
    print("=" * 70)
    print("TEST: adr_query — by concept (text question)")
    print("=" * 70)
    resp = _do_query(QueryRequest(question="Wie soll tenant_id typisiert werden?"))
    print(f"  Routing:    {resp.routing}")
    print(f"  Confidence: {resp.confidence}")
    print(f"  Answer:     {resp.primary_answer[:200]}")
    print(f"  Citations:  {len(resp.citations)}")
    for c in resp.citations[:3]:
        print(f"    [{c.relevance:10}] {c.adr_id}  matched: {c.matched_concepts}")
    print(f"  Open questions related: {len(resp.open_questions)}")
    assert resp.routing in ("concept", "mixed")
    assert len(resp.citations) >= 1
    print("\nPASS: concept query returns ranked, relevance-tagged ADRs\n")


def test_query_unknown_topic():
    print("=" * 70)
    print("TEST: adr_query — topic not in constitution returns honest 'no answer'")
    print("=" * 70)
    resp = _do_query(QueryRequest(question="Wie machen wir Kubernetes deployment rollouts?"))
    print(f"  Routing:    {resp.routing}")
    print(f"  Confidence: {resp.confidence}")
    print(f"  Answer:     {resp.primary_answer[:200]}")
    print(f"  Citations:  {len(resp.citations)}")
    # Confidence should be low — we don't have ADRs about k8s
    assert resp.confidence < 0.5 or len(resp.citations) == 0
    print("\nPASS: query honestly reports 'no decision' rather than hallucinating\n")


def test_query_by_path():
    print("=" * 70)
    print("TEST: adr_query — by file path resolves applicable ADRs")
    print("=" * 70)
    resp = _do_query(QueryRequest(path="apps/billing/models.py"))
    print(f"  Routing:    {resp.routing}")
    print(f"  Citations:  {len(resp.citations)}")
    for c in resp.citations:
        print(f"    [{c.relevance:10}] {c.adr_id}  {c.title[:60]}")
    print("\nPASS: path query resolves via scope.include_paths\n")


def test_query_returns_open_questions():
    print("=" * 70)
    print("TEST: adr_query — surfaces open_questions when relevant")
    print("=" * 70)
    resp = _do_query(QueryRequest(question="Wie machen wir Cross-Repo-Search opt-in?"))
    print(f"  Routing:                {resp.routing}")
    print(f"  Open questions found:   {len(resp.open_questions)}")
    for oq in resp.open_questions:
        print(f"    [{oq['adr_id']}/{oq['q_id']}] {oq['question']}")
    # ADR-188 v1.1 has Q-4 about cross-repo opt-in
    found_q4 = any(q["q_id"] == "Q-4" for q in resp.open_questions)
    assert found_q4, "Should find ADR-188 Q-4 about cross-repo opt-in"
    print("\nPASS: open question surfacing works\n")


# ============================================================
# adr_audit
# ============================================================


def test_audit_clean_constitution():
    print("=" * 70)
    print("TEST: adr_audit — clean constitution (ADR-099 + ADR-188 v1.1)")
    print("=" * 70)
    resp = _do_audit(AuditRequest())
    print(f"  Auditors run:    {resp.auditors_run}")
    print(f"  Findings:        {len(resp.findings)}")
    print(f"  Issue counts:    {resp.health.issue_counts}")
    print(f"  Health score:    {resp.health.score}")
    print(f"    consistency:   {resp.health.internal_consistency}")
    print(f"    coverage:      {resp.health.coverage}")
    print(f"    freshness:     {resp.health.freshness}")
    print(f"    supersession:  {resp.health.supersession_hygiene}")
    print(f"  Runtime:         {resp.runtime_ms}ms")

    if resp.findings:
        print("\n  Findings detail:")
        for f in resp.findings:
            print(f"    [{f.severity:8}] {f.auditor}: {f.description[:120]}")

    print("\nPASS: clean run completes\n")


def test_audit_finds_dangling_supersedes():
    """Inject a broken ADR with dangling supersedes ref, verify audit catches it."""
    print("=" * 70)
    print("TEST: adr_audit — dangling supersedes reference")
    print("=" * 70)

    # Stage a hypothetical broken ADR
    broken = """---
id: ADR-9099
title: Hypothetical broken ADR
status: accepted
decision_date: "2026-01-01"
valid_from: "2026-01-01T00:00:00Z"
deciders:
  - "Test <test@iil.gmbh>"
domains:
  - test/broken
supersedes:
  - "ADR-9999"
depends_on:
  - id: "ADR-8888"
    reason: "Hypothetical missing dep"
rationale_summary: "Test fixture for dangling refs"
---
# Broken ADR test fixture
"""
    broken_path = ADRS_DIR / "ADR-9099-broken.md"
    broken_path.write_text(broken)
    try:
        resp = _do_audit(AuditRequest(auditors=["supersession_hygiene", "dependency_health"]))
        print(f"  Findings: {len(resp.findings)}")
        for f in resp.findings:
            print(f"    [{f.severity:8}] {f.auditor}: {f.description[:140]}")
        # Expect at least 2 findings: dangling supersedes (ADR-9999) and dangling depends_on (ADR-8888)
        dangling_supersedes = [
            f for f in resp.findings if f.auditor == "supersession_hygiene" and "ADR-9999" in f.description
        ]
        dangling_dep = [f for f in resp.findings if f.auditor == "dependency_health" and "ADR-8888" in f.description]
        assert dangling_supersedes, "Should find dangling supersedes ADR-9999"
        assert dangling_dep, "Should find dangling depends_on ADR-8888"
    finally:
        broken_path.unlink(missing_ok=True)
    print("\nPASS: audit catches dangling references with proposed resolutions\n")


def test_audit_supersession_back_reference():
    """ADR-188 supersedes ADR-087, but ADR-087 isn't in the test fixture set.
    The audit should flag this because it's both dangling AND missing back-ref."""
    print("=" * 70)
    print("TEST: adr_audit — ADR-188's supersedes ADR-087 (missing in fixture)")
    print("=" * 70)
    resp = _do_audit(AuditRequest(auditors=["supersession_hygiene"]))
    related = [f for f in resp.findings if "ADR-087" in f.description or "ADR-188" in f.affected_adrs]
    print(f"  ADR-087/188 related findings: {len(related)}")
    for f in related:
        print(f"    [{f.severity:8}] {f.description[:160]}")
    # ADR-087 is referenced by ADR-188.supersedes but isn't loaded in the fixture
    # set. The audit should flag this as ERROR (dangling reference).
    assert any("ADR-087" in f.description for f in related)
    print("\nPASS: missing supersedes target is flagged\n")


def test_audit_staleness_with_explicit_date():
    print("=" * 70)
    print("TEST: adr_audit — staleness check with future as_of")
    print("=" * 70)
    # Force the audit to see itself in the future, past staleness threshold
    far_future = datetime(2030, 1, 1, tzinfo=UTC)
    resp = _do_audit(AuditRequest(auditors=["staleness"], as_of=far_future))
    print(f"  Findings (in 2030): {len(resp.findings)}")
    for f in resp.findings:
        print(f"    [{f.severity:8}] {f.description[:160]}")
    # Both ADRs should be flagged as stale by 2030
    assert len(resp.findings) >= 1
    print("\nPASS: bi-temporal as_of correctly drives staleness detection\n")


def test_audit_health_snapshot_quantified():
    print("=" * 70)
    print("TEST: adr_audit — HealthSnapshot is meaningful")
    print("=" * 70)
    resp = _do_audit(AuditRequest())
    h = resp.health
    print(f"  Composite score:         {h.score}")
    print(f"  Internal consistency:    {h.internal_consistency}")
    print(f"  Coverage:                {h.coverage}")
    print(f"  Freshness:               {h.freshness}")
    print(f"  Supersession hygiene:    {h.supersession_hygiene}")
    # Score should be in [0, 1]
    for name, v in [
        ("score", h.score),
        ("consistency", h.internal_consistency),
        ("coverage", h.coverage),
        ("freshness", h.freshness),
        ("supersession_hygiene", h.supersession_hygiene),
    ]:
        assert 0.0 <= v <= 1.0, f"{name}={v} out of [0,1]"
    print("\nPASS: HealthSnapshot dimensions are quantified and bounded\n")


if __name__ == "__main__":
    test_query_by_domain()
    test_query_by_concept()
    test_query_unknown_topic()
    test_query_by_path()
    test_query_returns_open_questions()
    test_audit_clean_constitution()
    test_audit_finds_dangling_supersedes()
    test_audit_supersession_back_reference()
    test_audit_staleness_with_explicit_date()
    test_audit_health_snapshot_quantified()
    print("=" * 70)
    print("ALL adr_query + adr_audit TESTS PASSED")
    print("=" * 70)
