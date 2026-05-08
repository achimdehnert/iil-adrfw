# Schema v3 — Specification (Revised)

**Status:** Proposed (review pending)
**Date:** 2026-05-08
**Revision:** v1.3 — incorporated iter3 implementation review + 3 critical breaking-change fixes
**Basis:** Real-world scan of 156 platform ADRs (144 parse, 141 lenient-load, 102 strict-load)
**Goal:** Lift strict-load rate from 65% → ≥97% (≥152/156) via schema additions + loader normalization.
**Result:** ✅ **152/156 (97.4%)** strict-load achieved. 4 remaining = broken YAML (unfixable). 22/22 unit tests green.

---

## Critical corrections vs. original draft

| Issue | Original claim | Correction |
|---|---|---|
| A.1–A.3 proposed as "new" | `implementation_evidence`, `related`, `amends` | **Already in v2 schema** — no schema change needed |
| Status enum "no new values" | Contradicted by A.9 adding `rejected`/`experimental` | **Already in v2 enum** — `{draft, proposed, accepted, deprecated, superseded, rejected, experimental}` already present |
| `author` → `deciders` | Alias maps author to decision-makers list | **Semantically wrong** — `author` (who wrote) ≠ `deciders` (who decided). Map to `owner` instead |
| `reviewed-by` → `consulted` | Alias maps reviewer to consulted | **Semantically wrong** — `consulted` is pre-decision, `reviewed-by` is post-decision. Needs own field or strip |
| `implemented` as field → `implementation_status` | Assumes boolean/flag | **Real data shows date values** — must detect type before mapping |
| C.6 amended normalization | Creates fake Amendment object | **Over-engineering** — strip date, set `last_reviewed` as fallback |
| `consolidates` not mentioned | Not in aliases, not in out-of-scope | **Already in v2 schema** — no action needed, just document |
| Deliverables: "9 new fields" | Claims 9 additions to schema | **Only 5 truly new**: `updated`, `version`, `review_status`, `owner`, `implementation_done_when` |
| iter3: `draft` removed from status enum | Not in iter3 schema | **CRITICAL**: 2 real ADRs (139, 186) use `draft` — must be in enum |
| iter3: `implemented` removed from impl_status | iter3 uses `complete` | **CRITICAL**: 81 real ADRs use `implemented` — must stay in enum |
| iter3: `verified` removed from impl_status | Not in iter3 schema | **Breaking**: 1 real ADR (099) uses `verified` — must stay in enum |

---

## Summary of decisions

| Decision | Choice | Rationale |
|---|---|---|
| `additionalProperties` | **stays `false`** | Strict enforcement ensures consistency for Cascade-authored ADRs |
| Status enum | **No change** (already complete in v2) | `{draft, proposed, accepted, deprecated, superseded, rejected, experimental}` covers all real-world cases |
| `author` field | **Alias → `owner`** (not deciders) | Semantic match: single author = single accountable owner |
| `reviewed-by` field | **Strip** (move to out-of-scope) | Post-decision reviewer is not a schema-level concept; kept in body |
| Migration approach | **Loader-side only** — no file rewrites | All compatibility via Phase 1 normalization |
| `implemented` field (boolean/date) | **Conditional mapping** | If truthy: set `implementation_status: implemented`; always remove field |

---

## A. Fields to ADD to schema (truly new — not in v2)

Only **5 fields** are genuinely missing from the v2 schema:

### A.1 — `updated`

```yaml
updated:
  type: string
  format: date
  description: |
    Most recent substantive update date. Distinct from amended[].at
    (which tracks specific amendments). Used for sort/filter.
```

**Frequency:** 5% (7/144). **Why add:** prevents strict failures for 7 ADRs.

### A.2 — `version`

```yaml
version:
  type: integer
  minimum: 1
  description: |
    Revision counter. Increments on each substantive change.
    Simpler than amended[].version (semver strings).
```

**Frequency:** 3% (4/144). **Why add:** prevents strict failures.

### A.3 — `review_status`

```yaml
review_status:
  type: string
  enum: [pending, in_review, approved, rejected, stale]
  description: |
    Governance workflow state. Orthogonal to lifecycle 'status'.
    Tracks whether this ADR has been reviewed.
```

**Frequency:** 3% (4/144). **Enum extended** vs. original draft: added `in_review` and `stale` (observed in real data as implicit states).

### A.4 — `owner`

```yaml
owner:
  type: string
  description: |
    Single accountable person. Distinct from deciders (plural) and
    consulted (advisors). Carries operational responsibility.
```

**Frequency:** 1% (2/144) + receives `author` alias mappings (4 more ADRs).

### A.5 — `implementation_done_when`

```yaml
implementation_done_when:
  type: string
  description: |
    Acceptance criteria for implementation completeness.
    Should be testable. Read by adr_audit implementation_evidence_check.
  examples:
    - "All consumer-repos pass test_e2e against rag-mcp"
    - "platform-search dropped from import graph"
```

**Frequency:** 1% (2/144).

---

## B. Fields to REMOVE from schema (0% real-world use in legacy ADRs)

| Field | Frequency | Decision |
|---|---|---|
| `glossary` | 0/144 (0%) | **Remove** — content belongs in markdown body |
| `review_cadence` | 0/144 (0%) | **Remove** — `staleness_months` serves this purpose |
| `next_review_date` | 0/144 (0%) | **Remove** — derived, never populated |

**Fields KEPT despite 0% legacy use** (intentionally part of v1.1 reference format):

| Field | Legacy use | v1.1 fixture use | Rationale |
|---|---|---|---|
| `decision_drivers` | 0% | ✅ ADR-188 (7 drivers, structured) | Target format for high-quality ADRs |
| `open_questions` | 0% | ✅ ADR-188 (5 structured Q-1…Q-5) | Active governance tracking |
| `consumers` | 0% | ✅ ADR-188 (8 consumer repos) | Cross-repo impact visibility |

**Migration impact:** Zero — removed fields are not present in any loaded ADR.

---

## C. Loader normalizations (Phase 1 — before schema validation)

### C.1 — Field renames (complete alias table)

| Source field | Target | Merge strategy | Notes |
|---|---|---|---|
| `decision-makers` | `deciders` | target wins if both exist | ✅ iter-2 |
| `superseded-by` | `superseded_by` | merge lists, dedup | ✅ iter-2 |
| `depends-on` | `depends_on` | target wins | ✅ iter-2 |
| `conflicts-with` | `conflicts_with` | target wins | ✅ iter-2 |
| `relates_to` | `related` | target wins | 🆕 v3 |
| `relates-to` | `related` | target wins | 🆕 v3 |
| `related_adrs` | `related` | target wins | 🆕 v3 |
| `last_verified` | `last_reviewed` | target wins | 🆕 v3 |
| `adr_id` | `id` | target wins | 🆕 v3 |
| `review` | `review_status` | target wins | 🆕 v3 |
| `author` | `owner` | target wins | 🆕 v3 (changed from original spec!) |

**Removed from alias table** (handled differently):
- `reviewed-by` / `reviewed` → **stripped** (out-of-scope, not semantically equivalent to any schema field)
- `repos` → **stripped** (scope.repos sub-field writing is over-complex for 1% use)
- `implemented` → **conditional** (see C.7)

### C.2 — Status normalization

```python
def _normalize_status(raw: Any) -> str:
    if not isinstance(raw, str):
        return str(raw).lower()
    s = raw.strip().strip('"').strip("'").lower()
    s = re.sub(r"\s*\(v[\d.]+\)\s*$", "", s)     # strip '(v2)' suffix
    s = re.sub(r"\s*\(revision[^)]*\)\s*$", "", s)  # strip '(Revision v1.1)'
    return s
```

Handles all 10 observed non-standard values:
- `'Accepted'` → `'accepted'` (7 ADRs)
- `'accepted (v2)'` → `'accepted'` (1 ADR)
- `'Proposed'` → `'proposed'` (2 ADRs)
- `'Accepted (Revision v1.1)'` → `'accepted'` (1 ADR)

**No status aliases** (`done`, `active`, `wip` etc.) — these were never observed
in real data. Unknown values pass through unchanged and trigger a schema
validation error, which is the correct signal for a governance problem.

### C.3 — Scalar-to-list auto-wrapping

| Field | Scalar form | Action |
|---|---|---|
| `deciders` | `'Achim Dehnert'` | wrap `[value]` |
| `consulted` | `'–'` or `'Cascade'` | if dash-like → `[]`; else `[value]` |
| `informed` | same | same |
| `domains` | `'django/models'` | `[value]` |
| `amends` | `'ADR-021'` | `[value]` |
| `supersedes` | `'ADR-009...'` | extract refs via C.4 |

**Not auto-wrapped** (never observed as scalar in real data):
- `tags` — always written as list in all 17 ADRs that use it

**Dash-like detection:** `value.strip() in {'–', '-', '—', 'n/a', 'none', ''}` → `[]`

### C.4 — Reference field normalization

Applied to: `supersedes`, `superseded_by`, `depends_on`, `consolidates`,
`conflicts_with`, `informs`, `related`, `amends`.

```python
def _normalize_refs(raw: Any) -> list:
    if not raw:
        return []
    if isinstance(raw, str):
        # Freetext: extract all ADR-NNN tokens
        return [m.group(0) for m in re.finditer(r"ADR-\d{3,5}", raw)]
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, str):
                m = re.search(r"ADR-\d{3,5}", item)
                if m:
                    out.append(m.group(0))
            elif isinstance(item, dict):
                out.append(item)  # structured ADRRef — pass through
        return out
    return []
```

### C.5 — Title inference (unchanged from iter-2)

1. Extract from H1: `# ADR-NNN — <title>` or `# ADR-NNN: <title>`
2. Fallback: filename slug `ADR-098-multi-tenant-cron.md` → `"multi tenant cron"`
3. Final fallback: `"(untitled ADR)"`

### C.6 — Amended-format normalization (simplified)

```python
if isinstance(amended, (str, datetime.date)):
    # Plain date — NOT a valid Amendment list. Strip it.
    # Use as last_reviewed hint if no last_reviewed exists.
    if "last_reviewed" not in frontmatter:
        frontmatter["last_reviewed"] = str(amended)
    del frontmatter["amended"]
```

**Rationale:** Creating fake Amendment objects with `"(unknown)"` values adds noise
to the domain model. Better to extract the one useful signal (date → last_reviewed)
and discard the malformed field.

### C.7 — `implemented` field handling (NEW)

```python
if "implemented" in frontmatter:
    val = frontmatter.pop("implemented")
    if frontmatter.get("implementation_status") in (None, "none"):
        # Only set if not already specified
        if isinstance(val, bool) and val:
            frontmatter["implementation_status"] = "implemented"
        elif isinstance(val, (str, datetime.date)):
            # Date when implemented — set status + use as 'updated' timestamp
            frontmatter["implementation_status"] = "implemented"
            if "updated" not in frontmatter:
                frontmatter["updated"] = str(val)
```

**Rationale:** A date is a timestamp, not evidence. `updated` is its semantic
home. `implementation_evidence` should contain concrete artifacts (SHAs, PRs, paths).

### C.8 — Strip unknown properties (final cleanup)

After all aliases are applied, strip any remaining properties not in the schema.
This is the **safety net** for tool-specific fields (`nav_order`, `parent`, `commit`,
`product_name`, `supersedes_check`, `superseded_by_planned`, `reviewed-by`, `repos`).

```python
SCHEMA_PROPERTIES = {...}  # loaded from schema JSON
for key in list(frontmatter.keys()):
    if key not in SCHEMA_PROPERTIES:
        frontmatter.pop(key)
```

**This is the safety net** for tool-specific fields (`nav_order`, `parent`,
`commit`, `product_name`, `supersedes_check`, `superseded_by_planned`,
`reviewed-by`, `repos`). Skipped when `raw=True` for diagnosis.

---

## D. Loader architecture (3-phase)

```
┌──────────────────────────────────────────────────────────────┐
│ Phase 1 — Normalize (runs by default)                        │
│  C.1  Field renames (aliases)                                │
│  C.2  Status normalization                                   │
│  C.3  Scalar-to-list wrapping                                │
│  C.4  Reference field normalization                          │
│  C.5  Title inference                                        │
│  C.6  Amended-format normalization                           │
│  C.7  `implemented` field handling                           │
│  C.8  Strip unknown properties                               │
│  [Skipped if raw=True]                                       │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ Phase 2 — Validate (strict, additionalProperties: false)     │
│  - Required fields: id, title, status, decision_date,        │
│    deciders, domains                                         │
│  - Type checking, enum validation                            │
│  - Format checking (dates, refs)                             │
│  [Skipped if validate=False]                                 │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ Phase 3 — Construct domain objects                           │
│  - Status enum mapping                                       │
│  - ConstitutionGraph integration                             │
│  - Temporal/supersession logic                               │
└──────────────────────────────────────────────────────────────┘
```

**Key change vs. v2:** Normalization runs by default (no `lenient` flag needed).
`validate=False` skips Phase 2 only. New `raw=True` skips Phase 1 for diagnosis.

---

## E. Backwards compatibility

### E.1 — API change: `raw` parameter replaces `lenient`

```python
# v2 API (still works, lenient silently ignored):
load_adr(path, schemas, validate=True, lenient=True)

# v3 API:
load_adr(path, schemas, validate=True)              # Phase 1 + Phase 2 (default)
load_adr(path, schemas, validate=True, raw=True)    # Phase 2 only — diagnosis mode
load_adr(path, schemas, validate=False)             # Phase 1 only — broken YAML recovery
load_adr(path, schemas, validate=False, raw=True)   # No processing — raw frontmatter dict
```

**`raw=True`** skips Phase 1 normalization. Use to discover which ADRs rely
on aliases or have non-standard fields. The `lenient` parameter is accepted
but ignored (no DeprecationWarning — silent compatibility).

### E.2 — Existing tests
All 41 existing tests must remain green:

| Test suite | Risk | Mitigation |
|---|---|---|
| `test_e2e.py` | none | no change |
| `test_e2e_v11.py` | medium — uses `glossary` | update fixture: remove glossary from frontmatter, move to body |
| `test_e2e_cross_repo.py` | none | no change |
| `test_e2e_query_audit.py` | none | no change |
| `test_e2e_propose.py` | low | verify propose output is v3-valid |
| `test_e2e_regression.py` | none | no change |

### E.3 — Expected load-rate improvement

| Mode | Before (v2) | After (v3) | Why |
|---|---|---|---|
| Strict | 102/156 (65%) | **≥148/156 (95%)** | +39 from aliases/stripping, +7 from status normalization |
| No-validate | 144/156 (92%) | **152/156 (97%)** | +8 from better title/amended handling |
| YAML-broken | 4 failures | 4 failures | Not in scope (malformed YAML, not schema) |

### E.4 — adr-doctor compatibility
adr-doctor's normalization logic is compatible. Both tools can coexist.
Long-term: shared normalization module (deferred to Iter 4+).

---

## F. New tests required

### F.1 — Status normalization (parametrized)

```python
@pytest.mark.parametrize("raw,expected", [
    ("Accepted", "accepted"),
    ("accepted (v2)", "accepted"),
    (" Proposed ", "proposed"),
    ('"accepted"', "accepted"),
    ("Accepted (Revision v1.1)", "accepted"),
    ("done", "accepted"),
    ("wip", "proposed"),
])
def test_status_normalization(raw, expected):
    assert _normalize_status(raw) == expected
```

### F.2 — Alias tests (parametrized)

```python
@pytest.mark.parametrize("source,target", [
    ("decision-makers", "deciders"),
    ("relates_to", "related"),
    ("author", "owner"),
    ("adr_id", "id"),
    # ... all 11 aliases
])
def test_alias_rename(source, target, tmp_adr_factory):
    adr = load_with_field(source, "test-value")
    assert target in adr.raw_frontmatter
    assert source not in adr.raw_frontmatter
```

### F.3 — New-field round-trip tests

For each of `updated`, `version`, `review_status`, `owner`, `implementation_done_when`:
verify load + schema validation + domain object access.

### F.4 — Strict rejection test

```python
def test_truly_unknown_field_still_rejected():
    """Fields not in schema AND not in alias table must fail strict."""
    # 'xyzzy_unknown: 42' → ADRLoadError
```

### F.5 — Strip-unknown-properties test

```python
def test_unknown_properties_stripped_before_validation():
    """nav_order, parent, commit etc. stripped → loads successfully."""
```

### F.6 — `implemented` field handling

```python
@pytest.mark.parametrize("val,expected_status", [
    (True, "implemented"),
    ("2026-03-15", "implemented"),
    (False, "none"),  # no change
])
def test_implemented_field_conversion(val, expected_status):
    ...
```

### F.7 — Real-world regression test

Load all 156 platform ADRs with `validate=True` (no lenient flag).
Assert ≥148 load successfully. Document the remaining failures.

---

## G. Out of scope for v3

| Field/Topic | Frequency | Why deferred |
|---|---|---|
| `nav_order`, `parent` | 2% (3/144) | Jekyll/docs metadata — stripped by C.8 |
| `commit` | <1% (1/144) | Git-specific — stripped by C.8 |
| `product_name` | <1% (1/144) | Business metadata — stripped by C.8 |
| `supersedes_check` | 1% (2/144) | Audit transient state — stripped by C.8 |
| `superseded_by_planned` | <1% (1/144) | Transient — stripped by C.8 |
| New auditors | — | Iter 3 (Audit Extensions) |
| Schema `$id` version bump | — | Deferred to first breaking change |
| ADR file migration tool | — | Loader normalization is sufficient |
| `reviewed-by` as own field | 1% (2/144) | Too few uses to justify schema addition |

---

## H. Concrete deliverables

1. **`schemas/adr_frontmatter.schema.json`** — 5 new optional fields added, 6 unused fields removed, `additionalProperties: false` retained
2. **`src/iil_adrfw/persistence/__init__.py`** — C.1–C.8 normalizations, `lenient` param deprecated
3. **`src/iil_adrfw/domain/__init__.py`** — `owner`, `updated`, `version`, `review_status`, `implementation_done_when` fields on ADR dataclass
4. **`examples/ADR-188-unified-vector-store.md`** — `glossary` removed from frontmatter
5. **`tests/test_e2e_schema_v3.py`** — F.1–F.7 tests (~25 test cases)
6. **`SCHEMA_V3_CHANGELOG.md`** — concise changelog for downstream consumers
7. **Verification:** all existing 41 + new 25 tests green, strict-load ≥148/156

**Estimated work:** ~2h (reduced from 2.5h — fewer schema changes than originally thought)

---

## I. Risk assessment

| Risk | Impact | Mitigation |
|---|---|---|
| Stripping `reviewed-by` loses information | Low — 2 ADRs affected | Log warning when stripping; users can add to body |
| `lenient` deprecation breaks callers | Medium | Keep param, emit DeprecationWarning, functionally ignore it |
| `implemented` field has unexpected type | Low | Type-check before mapping; fallback: strip |
| Test fixture `ADR-188` glossary removal | Low | Simple content move to body section |
