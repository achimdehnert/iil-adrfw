"""ADR-188 v1.1 specific tests — exercise new schema fields end-to-end."""
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
ADRS_DIR = BASE / "_test_adrs_v11"
SCHEMAS_DIR = BASE.parent / "schemas"
REPO_ROOT = BASE / "django_polyrepo"

if ADRS_DIR.exists():
    shutil.rmtree(ADRS_DIR)
ADRS_DIR.mkdir(parents=True)

# Stage both ADR-099 and ADR-188 v1.1
for fn in ["ADR-099-multi-tenancy.md", "ADR-099-multi-tenancy.rules.yaml",
           "ADR-188-unified-vector-store.md", "ADR-188-unified-vector-store.rules.yaml"]:
    shutil.copy(BASE / fn, ADRS_DIR)

os.environ["IIL_ADRFW_ADRS_DIR"] = str(ADRS_DIR)
os.environ["IIL_ADRFW_SCHEMAS_DIR"] = str(SCHEMAS_DIR)
os.environ["IIL_ADRFW_REPO_ROOT"] = str(REPO_ROOT)

from iil_adrfw.persistence import load_adrs
from iil_adrfw.domain import Status


def test_adr188_v11_loads():
    print("=" * 70)
    print("TEST: ADR-188 v1.1 loads with all extended fields")
    print("=" * 70)
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    by_id = {a.id: a for a in adrs}
    assert "ADR-188" in by_id, "ADR-188 not loaded"
    adr = by_id["ADR-188"]

    print(f"  ID:              {adr.id}")
    print(f"  Title:           {adr.title}")
    print(f"  Status:          {adr.status.value}")
    print(f"  Origin repo:     {adr.repo}")
    print(f"  Implementation:  {adr.implementation_status}")
    print(f"  Consumers:       {len(adr.consumers)} repos")
    print(f"  Consolidates:    {list(adr.consolidates)}")
    print(f"  Amendments:      {len(adr.amendments)}")
    print(f"  Decision drivers:{len(adr.decision_drivers)}")
    print(f"  Open questions:  {len(adr.open_questions)}")
    print(f"  Deprecation:     {len(adr.deprecation_timeline)} phases")
    print(f"  SPOF mitigation: {len(adr.spof_mitigation)} measures")
    print(f"  Per-repo status: {len(adr.per_repo_status)} repos")
    print(f"  Rules:           {len(adr.rules)}")

    assert len(adr.amendments) == 1
    assert adr.amendments[0].version == "v1.1"
    assert len(adr.decision_drivers) == 7
    assert sum(1 for d in adr.decision_drivers if d.weight == "critical") == 4
    assert len(adr.open_questions) == 5
    assert all(q.status == "open" for q in adr.open_questions)
    assert len(adr.deprecation_timeline) == 4
    assert adr.deprecation_timeline[-1].phase == "D-4"
    assert len(adr.per_repo_status) == 9
    assert "ADR-187§E3" in adr.consolidates, "Section-scoped reference should round-trip"
    print("\nPASS: all v1.1 fields hydrated correctly\n")


def test_per_repo_status_query():
    print("=" * 70)
    print("TEST: per-repo status — different states across polyrepo")
    print("=" * 70)
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    adr = next(a for a in adrs if a.id == "ADR-188")

    repos_to_check = ["platform", "mcp-hub", "meiki-hub", "bfagent", "travel-beat"]
    for repo in repos_to_check:
        status, impl = adr.status_in_repo(repo)
        prs = next((p for p in adr.per_repo_status if p.repo == repo), None)
        phase = prs.planned_phase if prs else "n/a"
        notes = (prs.notes[:60] + "...") if prs and prs.notes else ""
        print(f"  {repo:14}  status={status.value:12}  impl={impl:12}  phase={phase or 'n/a':8}  {notes}")

    # Cross-check: same ADR, different states
    platform_status, platform_impl = adr.status_in_repo("platform")
    mcphub_status, mcphub_impl = adr.status_in_repo("mcp-hub")
    assert platform_status != mcphub_status or platform_impl != mcphub_impl, \
        "Polyrepo states should differ for at least one pair"
    print("\nPASS: polyrepo per-repo states correctly differ\n")


def test_decision_drivers_critical():
    print("=" * 70)
    print("TEST: Critical decision drivers — auditor's question")
    print("=" * 70)
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    adr = next(a for a in adrs if a.id == "ADR-188")

    print("Critical drivers (would block this ADR if not addressed):\n")
    for d in adr.decision_drivers:
        if d.weight == "critical":
            print(f"  [{d.id}] ({d.category}) {d.driver}")
    print("\nPASS\n")


def test_open_questions_owned():
    print("=" * 70)
    print("TEST: Open questions — accountability")
    print("=" * 70)
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    adr = next(a for a in adrs if a.id == "ADR-188")

    by_owner: dict[str, list] = {}
    for q in adr.open_questions:
        by_owner.setdefault(q.owner or "unassigned", []).append(q)

    print("Open questions by owner:\n")
    for owner, qs in by_owner.items():
        print(f"  {owner}:")
        for q in qs:
            print(f"    [{q.id}] (decide by: {q.decide_by}) {q.question}")

    assert all(q.owner for q in adr.open_questions), "All Q's should have owners"
    print("\nPASS: every open question has accountable owner\n")


def test_deprecation_timeline_chain():
    print("=" * 70)
    print("TEST: Deprecation timeline — Zero Breaking Changes story")
    print("=" * 70)
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    adr = next(a for a in adrs if a.id == "ADR-188")

    print("Migration phases for superseded ADR-087:\n")
    for step in adr.deprecation_timeline:
        print(f"  [{step.phase}] {step.action}")
        print(f"        State:    {step.state}")
        print(f"        Earliest: {step.earliest}")
        print(f"        Done at:  {step.completion_signal}")
        print()
    print("PASS\n")


def test_v11_uuid_rule_is_critical():
    print("=" * 70)
    print("TEST: v1.1 critical UUID rule — DSGVO-grade severity")
    print("=" * 70)
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)
    adr = next(a for a in adrs if a.id == "ADR-188")

    uuid_rule = next((r for r in adr.rules if r.rule_id == "tenant-id-is-uuid"), None)
    dsgvo_rule = next((r for r in adr.rules if r.rule_id == "dsgvo-restricted-collections-no-cloud"), None)

    assert uuid_rule is not None
    assert dsgvo_rule is not None
    assert uuid_rule.severity.value == "critical"
    assert dsgvo_rule.severity.value == "critical"

    print(f"  {uuid_rule.global_id:60} severity={uuid_rule.severity.value}")
    print(f"    knowledge_from: {uuid_rule.temporal.knowledge_from}")
    print(f"    rationale[..120]: {uuid_rule.rationale[:120]}...")
    print()
    print(f"  {dsgvo_rule.global_id:60} severity={dsgvo_rule.severity.value}")
    print(f"    knowledge_from: {dsgvo_rule.temporal.knowledge_from}")
    print(f"    blast_radius:   {dsgvo_rule.blast_radius}")

    # The UUID rule was learned on 2026-05-08 (the v1.1 amendment date) but
    # valid_from is 2026-05-21 (Phase 1 deployment) — different from rule itself
    assert uuid_rule.temporal.knowledge_from == datetime(2026, 5, 8, tzinfo=timezone.utc)
    print("\nPASS: v1.1 introduces critical-severity rules with bi-temporal accuracy\n")


def test_constitutional_health():
    print("=" * 70)
    print("TEST: Composite constitution view — both ADRs together")
    print("=" * 70)
    adrs = load_adrs(ADRS_DIR, SCHEMAS_DIR, validate=True)

    print(f"  Total ADRs:           {len(adrs)}")
    total_rules = sum(len(a.rules) for a in adrs)
    print(f"  Total rules:          {total_rules}")
    proposed = sum(1 for a in adrs if a.status == Status.PROPOSED)
    accepted = sum(1 for a in adrs if a.status == Status.ACCEPTED)
    print(f"  Status: proposed={proposed}, accepted={accepted}")

    consolidating = [a for a in adrs if a.consolidates]
    print(f"  ADRs that consolidate others: {len(consolidating)}")
    for a in consolidating:
        print(f"    {a.id} consolidates {list(a.consolidates)}")

    with_amendments = [a for a in adrs if a.amendments]
    print(f"  ADRs with amendments: {len(with_amendments)}")

    open_q_total = sum(len(a.open_questions) for a in adrs)
    print(f"  Total open questions in constitution: {open_q_total}")
    print("\nPASS: cross-ADR aggregation works\n")


if __name__ == "__main__":
    test_adr188_v11_loads()
    test_per_repo_status_query()
    test_decision_drivers_critical()
    test_open_questions_owned()
    test_deprecation_timeline_chain()
    test_v11_uuid_rule_is_critical()
    test_constitutional_health()
    print("=" * 70)
    print("ALL v1.1 TESTS PASSED")
    print("=" * 70)
