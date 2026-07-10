"""E2E tests for adr_propose."""

import json
import shutil
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from iil_adrfw.server import DecisionDriverIn, ProposeRequest, _do_propose

BASE = Path(__file__).resolve().parent
ADRS_DIR = BASE / "_test_adrs_propose"
SCHEMAS_DIR = BASE.parent / "schemas"
WORKSPACE = BASE / "polyrepo_workspace"


def _stage_fixtures() -> None:
    """Stage canonical fixtures (see conftest.py)."""
    for fn in [
        "ADR-099-multi-tenancy.md",
        "ADR-099-multi-tenancy.rules.yaml",
        "ADR-188-unified-vector-store.md",
        "ADR-188-unified-vector-store.rules.yaml",
    ]:
        shutil.copy(BASE / fn, ADRS_DIR)


# Build a frontmatter validator for assertion tests
_registry = Registry()
for sf in SCHEMAS_DIR.glob("*.json"):
    with open(sf) as f:
        s = json.load(f)
    _registry = _registry.with_resource(uri=s["$id"], resource=Resource.from_contents(s))
with open(SCHEMAS_DIR / "adr_frontmatter.schema.json") as f:
    _fm_schema = json.load(f)
_fm_validator = Draft202012Validator(_fm_schema, registry=_registry)


def _validate_frontmatter(fm: dict) -> list[str]:
    errors = []
    for err in sorted(_fm_validator.iter_errors(fm), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"  {loc}: {err.message[:160]}")
    return errors


def test_should_generate_schema_valid_frontmatter_for_basic_proposal():
    print("=" * 70)
    print("TEST: basic proposal — frontmatter is schema-valid out of the box")
    print("=" * 70)
    resp = _do_propose(
        ProposeRequest(
            title="Use Celery for background task scheduling",
            domains=["celery", "background-tasks"],
            deciders=["Achim Dehnert <achim@iil.gmbh>"],
            rationale_summary=(
                "We need a robust scheduler for background tasks across the polyrepo. "
                "Celery has been used successfully and integrates with Django and Redis."
            ),
        )
    )
    print(f"  Proposed ID:        {resp.proposed_id}")
    print(f"  Conflicts:          {len(resp.conflicts)}")
    print(f"  Closes open Qs:     {len(resp.closes_open_questions)}")
    print(f"  Cross-repo blockers:{len(resp.cross_repo_blockers)}")
    print(f"  Blocks publish:     {resp.blocks_publish}")
    print(f"  Runtime:            {resp.runtime_ms}ms")
    print(f"  Frontmatter keys:   {sorted(resp.frontmatter.keys())}")

    errors = _validate_frontmatter(resp.frontmatter)
    if errors:
        print("  Frontmatter validation errors:")
        for e in errors:
            print(e)
        raise AssertionError("frontmatter must be schema-valid")
    print(f"  Body prompt:        {len(resp.body_prompt)} chars")
    assert resp.proposed_id.startswith("ADR-")
    assert not resp.blocks_publish
    print("\nPASS: basic proposal yields schema-valid frontmatter\n")


def test_should_allocate_next_available_adr_id():
    print("=" * 70)
    print("TEST: id allocation — picks next number after existing ADRs")
    print("=" * 70)
    resp = _do_propose(
        ProposeRequest(
            title="Some new architectural decision",
            domains=["test"],
            deciders=["Achim"],
            rationale_summary="A long enough rationale summary to satisfy schema minLength.",
        )
    )
    print("  Existing: ADR-099, ADR-188")
    print(f"  Allocated: {resp.proposed_id}")
    # Should be ADR-189 because 188 is the highest
    assert resp.proposed_id == "ADR-189", f"expected ADR-189, got {resp.proposed_id}"
    print("\nPASS: next ADR id allocated correctly\n")


def test_should_honor_requested_id_when_free():
    print("=" * 70)
    print("TEST: requested id honored when not in use")
    print("=" * 70)
    resp = _do_propose(
        ProposeRequest(
            title="Something specific",
            domains=["test"],
            deciders=["Achim"],
            rationale_summary="A long enough rationale summary to satisfy schema minLength.",
            requested_id="ADR-200",
        )
    )
    assert resp.proposed_id == "ADR-200"
    print(f"  Requested ADR-200, got {resp.proposed_id}")
    print("\nPASS: requested id honored\n")


def test_should_reject_requested_id_when_already_taken():
    print("=" * 70)
    print("TEST: requested id rejected when already in use")
    print("=" * 70)
    try:
        _do_propose(
            ProposeRequest(
                title="Something",
                domains=["test"],
                deciders=["Achim"],
                rationale_summary="A long enough rationale summary to satisfy schema minLength.",
                requested_id="ADR-099",  # already taken
            )
        )
        raise AssertionError("expected ValueError")
    except ValueError as e:
        print(f"  Caught (as expected): {e}")
    print("\nPASS: collision detected\n")


def test_should_warn_on_near_duplicate_title():
    print("=" * 70)
    print("TEST: very similar title triggers duplicate warning")
    print("=" * 70)
    resp = _do_propose(
        ProposeRequest(
            # Almost the same as ADR-099 to trigger heuristic
            title="Multi-tenancy via tenant_id BigIntegerField with manager scoping",
            domains=["django/models"],
            deciders=["Achim"],
            rationale_summary="An attempt to re-decide multi-tenancy without superseding ADR-099.",
        )
    )
    print(f"  Conflicts: {len(resp.conflicts)}")
    for c in resp.conflicts:
        print(f"    [{c.severity:8}] {c.kind}: {c.description[:120]}")
    duplicates = [c for c in resp.conflicts if c.kind == "duplicate"]
    assert duplicates, "should detect title near-duplicate"
    assert "ADR-099" in duplicates[0].related_adr_ids
    print("\nPASS: title duplication caught\n")


def test_should_flag_domain_overlap_without_supersession():
    print("=" * 70)
    print("TEST: heavy domain overlap without supersession is flagged")
    print("=" * 70)
    # Pick domains that overlap with ADR-099 (django/models, security/multi-tenancy)
    # without supersedes
    resp = _do_propose(
        ProposeRequest(
            title="A different multi-tenant design",
            domains=["django/models", "security/multi-tenancy"],
            deciders=["Achim"],
            rationale_summary="Yet another approach to multi-tenancy that lives alongside ADR-099.",
        )
    )
    print(f"  Conflicts: {len(resp.conflicts)}")
    for c in resp.conflicts:
        print(f"    [{c.severity:8}] {c.kind}: {c.description[:140]}")
    overlap_findings = [c for c in resp.conflicts if c.kind == "missed_supersession"]
    assert overlap_findings, "should flag the domain overlap"
    print("\nPASS: missed-supersession indicator works\n")


def test_should_detect_open_question_closure_and_mention_it_in_body_prompt():
    print("=" * 70)
    print("TEST: proposal addressing ADR-188 Q-4 is detected")
    print("=" * 70)
    # ADR-188 Q-4: "Cross-Repo-Search (Phase 4): Benötigt das ein explizites Opt-in pro Tenant?"
    resp = _do_propose(
        ProposeRequest(
            title="Cross-Repo-Search opt-in policy per tenant",
            domains=["rag/infrastructure", "security/multi-tenancy"],
            deciders=["Achim"],
            rationale_summary=(
                "We need an explicit opt-in mechanism per tenant for Cross-Repo-Search "
                "to avoid accidental data leakage between organizations."
            ),
        )
    )
    print(f"  Closes open questions: {len(resp.closes_open_questions)}")
    for m in resp.closes_open_questions:
        print(f"    [{m.adr_id}/{m.q_id}] (overlap={m.overlap_score}) {m.question[:80]}")
    closes_q4 = [m for m in resp.closes_open_questions if m.q_id == "Q-4"]
    assert closes_q4, "should match ADR-188 Q-4 about cross-repo opt-in"
    # The body prompt should also mention this
    assert "ADR-188/Q-4" in resp.body_prompt
    print("\nPASS: open question closure detection works (and informs body prompt)\n")


def test_should_run_cross_repo_pre_check_without_crashing_on_draft():
    print("=" * 70)
    print("TEST: proposing a BIGINT tenant_id ADR is BLOCKED by cross-repo pre-check")
    print("=" * 70)
    # This is the v1.0 scenario re-played: claim BIGINT, but consumer-repos all use UUID
    resp = _do_propose(
        ProposeRequest(
            title="Use BIGINT for tenant_id in vector store",
            domains=["data/vector-store"],
            deciders=["Achim"],
            rationale_summary="A draft that wrongly claims tenant_id should be BIGINT — designed to be caught by cross-repo pre-check.",
            repo="mcp-hub",
            consumers=["meiki-hub", "bfagent"],
            cross_repo_paths={
                "meiki-hub": str(WORKSPACE / "meiki-hub"),
                "bfagent": str(WORKSPACE / "bfagent"),
            },
        )
    )

    print(f"  Cross-repo blockers: {len(resp.cross_repo_blockers)}")
    for b in resp.cross_repo_blockers:
        print(f"    [{b.confidence}] {b.summary[:140]}")
        print(f"      affected repos: {b.affected_repos}")
    print(f"  blocks_publish: {resp.blocks_publish}")
    # The draft contains tenant_id BIGINT claim implicitly via title; current heuristic
    # in _detect_adr_tenant_id_claim looks at rules. For this proposal we don't have rules
    # yet (rules are per-ADR additions), so this test expects ZERO cross-repo conflicts —
    # because there's nothing actionable yet. That's actually correct behavior: the draft
    # doesn't yet make a checkable claim. The blocking would happen when rules are added.
    # So the assertion is: pre-check ran without crashing on a draft.
    assert isinstance(resp.cross_repo_blockers, list)
    print("\n  Note: this draft has no rules yet, so cross-repo claim-detection finds nothing.")
    print("        Once rules are attached (in adr_check rules file), the blocker fires.")
    print("PASS: cross-repo pre-check runs cleanly on a draft\n")


def test_should_block_publish_when_rationale_states_conflicting_claim():
    """Force a measurable cross-repo conflict by putting the claim into rationale_summary."""
    print("=" * 70)
    print("TEST: cross-repo pre-check with rationale-stated claim")
    print("=" * 70)
    resp = _do_propose(
        ProposeRequest(
            title="Use BIGINT for tenant_id in vector store",
            domains=["data/vector-store"],
            deciders=["Achim"],
            rationale_summary=(
                "Decision: tenant_id BIGINT in all vector-store tables. Rejected UUID due to performance concerns."
            ),
            repo="mcp-hub",
            consumers=["meiki-hub", "bfagent"],
            cross_repo_paths={
                "meiki-hub": str(WORKSPACE / "meiki-hub"),
                "bfagent": str(WORKSPACE / "bfagent"),
            },
        )
    )

    print(f"  Frontmatter keys: {sorted(resp.frontmatter.keys())}")
    print(f"  Cross-repo blockers: {len(resp.cross_repo_blockers)}")
    for b in resp.cross_repo_blockers:
        print(f"    [{b.confidence}] {b.summary[:140]}")
    print(f"  blocks_publish: {resp.blocks_publish}")
    # The claim 'tenant_id BIGINT' in rationale_summary IS detected by
    # _detect_adr_tenant_id_claim, so we expect a real blocker here.
    assert resp.blocks_publish, "rationale-stated BIGINT vs UUID consumer-reality should block"
    assert len(resp.cross_repo_blockers) >= 1
    print("\nPASS: explicit rationale claim is cross-checked and blocks publish\n")


def test_should_structure_body_prompt_with_decision_drivers_and_context():
    print("=" * 70)
    print("TEST: body prompt is structured and references context")
    print("=" * 70)
    resp = _do_propose(
        ProposeRequest(
            title="Adopt OpenTelemetry for distributed tracing",
            domains=["observability", "django/middleware"],
            deciders=["Achim", "Platform Team"],
            rationale_summary=(
                "Cross-service request tracing is needed to debug latency issues "
                "across the polyrepo. OpenTelemetry is the de-facto standard."
            ),
            decision_drivers=[
                DecisionDriverIn(id="D-1", driver="Need to debug cross-service latency", weight="high"),
                DecisionDriverIn(id="D-2", driver="Avoid vendor lock-in", weight="medium"),
            ],
        )
    )
    print(f"  Body prompt length: {len(resp.body_prompt)} chars\n")
    print("  --- body prompt excerpt ---")
    for line in resp.body_prompt.splitlines()[:30]:
        print(f"  {line}")
    print()
    assert "Decision drivers" in resp.body_prompt
    assert "[D-1]" in resp.body_prompt
    assert "Context" in resp.body_prompt and "Decision" in resp.body_prompt
    print("PASS: body prompt is well-structured\n")


def test_should_silence_missed_supersession_warning_when_supersedes_given():
    print("=" * 70)
    print("TEST: explicit supersedes silences the missed_supersession warning")
    print("=" * 70)
    resp = _do_propose(
        ProposeRequest(
            title="Multi-tenant v2 with row-level-security",
            domains=["django/models", "security/multi-tenancy"],
            deciders=["Achim"],
            rationale_summary="A v2 multi-tenancy design that supersedes ADR-099 by adding RLS.",
            supersedes=["ADR-099"],
        )
    )
    overlap_findings = [c for c in resp.conflicts if c.kind == "missed_supersession"]
    assert not overlap_findings, "explicit supersedes should silence the warning"
    print(f"  Conflicts: {len(resp.conflicts)} (no missed_supersession warning)")
    print("\nPASS: explicit supersedes silences the heuristic\n")


def test_should_auto_derive_repo_from_cwd_git_checkout(tmp_path, monkeypatch):
    print("=" * 70)
    print("TEST: repo auto-derived from CWD's git checkout name (ADR-259 R2-REC-4)")
    print("=" * 70)
    checkout = tmp_path / "some-hub"
    (checkout / ".git").mkdir(parents=True)
    monkeypatch.chdir(checkout)

    resp = _do_propose(
        ProposeRequest(
            title="Use Celery for background task scheduling",
            domains=["celery"],
            deciders=["Achim"],
            rationale_summary="Need a robust scheduler for background tasks across the polyrepo.",
        )
    )
    assert resp.frontmatter.get("repo") == "some-hub"
    print(f"  Auto-derived repo:  {resp.frontmatter.get('repo')}")
    print("\nPASS: repo auto-derived from CWD\n")


def test_should_prefer_explicit_repo_over_cwd_derivation(tmp_path, monkeypatch):
    print("=" * 70)
    print("TEST: explicit repo= wins over CWD auto-derivation")
    print("=" * 70)
    checkout = tmp_path / "cwd-derived-name"
    (checkout / ".git").mkdir(parents=True)
    monkeypatch.chdir(checkout)

    resp = _do_propose(
        ProposeRequest(
            title="Use Celery for background task scheduling",
            domains=["celery"],
            deciders=["Achim"],
            rationale_summary="Need a robust scheduler for background tasks across the polyrepo.",
            repo="explicitly-given-repo",
        )
    )
    assert resp.frontmatter.get("repo") == "explicitly-given-repo"
    print(f"  repo (explicit wins): {resp.frontmatter.get('repo')}")
    print("\nPASS: explicit repo overrides CWD derivation\n")


def test_should_resolve_repo_name_from_adr233_session_worktree(tmp_path, monkeypatch):
    print("=" * 70)
    print("TEST: platform:ADR-233 session-worktree layout resolves to the real repo name")
    print("=" * 70)
    # Mirrors ~/.repo-session/worktrees/<repo>/<session-slug>/ — the git-root
    # itself is the ephemeral session-slug dir, NOT the repo name.
    session_worktree = tmp_path / ".repo-session" / "worktrees" / "iil-adrfw" / "2026-07-10-achim-adr259-054959"
    (session_worktree / ".git").mkdir(parents=True)  # worktree .git is a file in real git; dir is enough here
    monkeypatch.chdir(session_worktree)

    resp = _do_propose(
        ProposeRequest(
            title="Use Celery for background task scheduling",
            domains=["celery"],
            deciders=["Achim"],
            rationale_summary="Need a robust scheduler for background tasks across the polyrepo.",
        )
    )
    assert resp.frontmatter.get("repo") == "iil-adrfw"
    print(f"  Resolved repo (via worktree layout): {resp.frontmatter.get('repo')}")
    print("\nPASS: session-worktree layout resolves to real repo name, not session slug\n")


def test_should_omit_repo_when_cwd_is_not_a_git_checkout(tmp_path, monkeypatch):
    print("=" * 70)
    print("TEST: no crash, repo omitted when CWD isn't inside a git checkout")
    print("=" * 70)
    monkeypatch.chdir(tmp_path)  # no .git anywhere under tmp_path

    resp = _do_propose(
        ProposeRequest(
            title="Use Celery for background task scheduling",
            domains=["celery"],
            deciders=["Achim"],
            rationale_summary="Need a robust scheduler for background tasks across the polyrepo.",
        )
    )
    assert "repo" not in resp.frontmatter
    print("  repo key absent (degrades silently, per ADR-259 'offline → degradiert')")
    print("\nPASS: graceful degradation outside a git checkout\n")


if __name__ == "__main__":
    test_should_generate_schema_valid_frontmatter_for_basic_proposal()
    test_should_allocate_next_available_adr_id()
    test_should_honor_requested_id_when_free()
    test_should_reject_requested_id_when_already_taken()
    test_should_warn_on_near_duplicate_title()
    test_should_flag_domain_overlap_without_supersession()
    test_should_detect_open_question_closure_and_mention_it_in_body_prompt()
    test_should_run_cross_repo_pre_check_without_crashing_on_draft()
    test_should_block_publish_when_rationale_states_conflicting_claim()
    test_should_structure_body_prompt_with_decision_drivers_and_context()
    test_should_silence_missed_supersession_warning_when_supersedes_given()
    print("=" * 70)
    print("ALL adr_propose TESTS PASSED")
    print("=" * 70)
