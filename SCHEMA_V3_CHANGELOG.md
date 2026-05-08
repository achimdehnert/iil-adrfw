# Schema v3 — Changelog

**Date:** 2026-05-08
**Basis:** Real-world data on 156 platform ADRs (Cascade run)
**Goal:** Lift strict-load rate from 65% (102/156) to ≥97% via schema additions
and Phase 1 normalization.

---

## Schema additions (5 fields truly new, all optional)

| Field | Type | Real-world frequency |
|---|---|---|
| `updated` | string (date) | 5% |
| `version` | integer ≥1 | 3% |
| `review_status` | enum (`pending`, `in_review`, `approved`, `rejected`, `stale`) | 3% |
| `owner` | string | 1% direct + receives `author` alias mappings |
| `implementation_done_when` | string | 1% |

Note: `implementation_evidence`, `related`, `amends` were already in v2 schema.

## Schema removals (3 fields, 0% real-world use)

- `glossary` — content belongs in markdown body (see ADR-188 v1.1 example)
- `review_cadence` — replaced functionally by `staleness_months`
- `next_review_date` — was a derived field, never populated

## Schema unchanged (critical for backwards compatibility)

- **Status enum** — `{draft, proposed, accepted, deprecated, superseded, rejected, experimental}` — `draft` used by 2 ADRs
- **`implementation_status` enum** — `{none, planned, in_progress, partial, implemented, complete, verified, rolled_back}` — `implemented` used by 81 ADRs, `verified` by 1
- **`additionalProperties: false`** — strict mode retained for governance
- **All v1.1 strategic fields** — `decision_drivers`, `open_questions`, `consumers`, `deprecation_timeline`, `spof_mitigation`, `per_repo_status` — kept as the v1.1 reference format

---

## Loader behavior (Phase 1 normalization)

All Phase 1 transforms run by default. To bypass them for diagnostic purposes:
`load_adr(path, schemas, raw=True)`.

### Field aliases (target wins if both present)

| Source | Target |
|---|---|
| `decision-makers` | `deciders` |
| `superseded-by` | `superseded_by` |
| `depends-on` | `depends_on` |
| `conflicts-with` | `conflicts_with` |
| `relates_to`, `relates-to`, `related_adrs` | `related` |
| `last_verified` | `last_reviewed` |
| `adr_id` | `id` |
| `review` | `review_status` |
| `author` | `owner` |

### Stripped fields (low-frequency tool-noise)

`reviewed-by`, `reviewed`, `repos`, `nav_order`, `parent`, `commit`,
`product_name`, `supersedes_check`, `superseded_by_planned`

### Status normalization

Applied to the `status` value:
- Case-insensitive: `Accepted` → `accepted`
- Strip quotes: `'"accepted"'` → `accepted`
- Strip version suffix: `accepted (v2)` → `accepted`
- Strip revision suffix: `Accepted (Revision v1.1)` → `accepted`

Unknown values pass through unchanged so the schema enum check produces a
clear error message.

### Auto-wrap scalar-to-list (only on observed-as-scalar fields)

`deciders`, `consulted`, `informed`, `domains`, `amends` — string value gets
wrapped to `[value]`. Sentinel values `–`, `-`, `—`, `n/a`, `none`, `""` →
empty list `[]`.

### Reference-field normalization

For `supersedes`, `superseded_by`, `depends_on`, `consolidates`,
`conflicts_with`, `informs`, `related`, `amends`: strings have all
`ADR-NNN` tokens extracted into a list.

### `implemented` field handling

| Input | Action |
|---|---|
| `implemented: true` | set `implementation_status: implemented` |
| `implemented: "2026-03-15"` (date) | set `implementation_status: implemented` AND `updated: "2026-03-15"` |
| `implemented: false` | leave `implementation_status` unchanged |

The field is always removed from the frontmatter after processing.

### Amended-format normalization

Legacy form `amended: "2026-05-08"` (plain date) is recognized:
- The date is moved to `last_reviewed` (if not already set)
- The malformed `amended` field is dropped

Proper `amended` lists (with `version`, `at`, `by`, `summary`) pass through unchanged.

### Title inference

If `title` is missing or empty:
1. Try first H1 in body: `# ADR-NNN — <title>` or `# ADR-NNN: <title>`
2. Fallback: filename slug `ADR-098-multi-tenant-cron.md` → `"multi tenant cron"`
3. Final fallback: `"(untitled ADR)"`

---

## Migration impact

- **Existing ADR files:** No file rewrites needed. Phase 1 normalization handles
  legacy formats transparently.
- **Existing tests:** All 41 prior tests remain green.
- **adr-doctor compatibility:** unchanged — both tools share normalization
  semantics but operate independently.

## API change: `raw` parameter

```python
# Before v3 (still supported):
load_adr(path, schemas, validate=True)
load_adr(path, schemas, validate=False)

# New in v3 — diagnostic mode:
load_adr(path, schemas, validate=False, raw=True)  # see frontmatter as-written
```

`raw=True` skips Phase 1 entirely. Useful for finding ADRs that depend on
tolerance and could be migrated to canonical form.

## Test additions

- `test_e2e_schema_v3.py` — 22 tests covering all C.1–C.8 transforms,
  field renames, schema additions/removals, and combined real-world scenarios.

## Out of scope for v3

| Topic | Why deferred |
|---|---|
| `nav_order`, `parent`, `commit`, `product_name` as schema fields | <2% use, stripped instead |
| `reviewed-by` as own field | 1% use, semantically distinct from `consulted`, stripped |
| Audit auditors using new fields (`implementation_evidence_check`, `circular_dependency`, `orphaned_adr`) | Iter 3 — separate increment |
| Schema `$id` version bump | Cosmetic, deferred to first breaking change |
| Status aliases (`done`, `active`, `wip`) | Antizipativ, nicht in echten Daten beobachtet — log-warning instead |
