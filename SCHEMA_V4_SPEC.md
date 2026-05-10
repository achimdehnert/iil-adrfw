# ADR Schema v4 — Specification

**Released**: 2026-05-10
**Supersedes**: SCHEMA_V3_SPEC.md
**Package**: `iil-adrfw>=0.5.0`

---

## Summary of Changes (v3 → v4)

### New Status: `void`

```yaml
status: void
```

Marks an ADR slot as misclassified. The ADR number is **retained** for reference
integrity, but the content has been moved to the correct document type (`plan`,
`review`, etc.). Void ADRs do not appear in health metrics (staleness, coverage).

**Trigger**: Deliberate reclassification — not a lifecycle state of a real decision.

---

### New Field: `doc_type`

```yaml
doc_type: adr  # default
# enum: adr | standard | runbook | plan | review | rfc
```

**Discriminator** for document-type governance. Files in `docs/adr/` MUST have
`doc_type: adr`. Prevents ADR-181/182 class of misclassification.

**Migration**: Optional field. Defaults to `adr` if absent.

---

### New Field: `reviewed_by` — Human reviewers only

```yaml
reviewed_by:
  - name: achim-dehnert          # human identifier — NOT an AI tool name
    date: 2026-03-15
    verdict: approved             # approved | changes-requested | rejected
    note: "LGTM after section 3 clarification"  # optional, max 280 chars
```

**Critical governance rule**: AI tool names MUST NOT appear here. AI contributions
go to `ai_sparring_by` (see below). This separation is the core Bus Factor fix.

**Migration**: Legacy `reviewed-by: "string"` and `reviewed-by: ["string", ...]`
are **stripped** during normalization (Karenzzeit until 2026-11-10). Stripped
`reviewed_by` → empty → Bus Factor warning fires.

**Validation**: WARNING when `status: accepted` and `reviewed_by` is empty.

---

### New Field: `ai_sparring_by` — AI tool contributions

```yaml
ai_sparring_by:
  - tool: cascade                 # cascade | claude-code | copilot | other
    date: 2026-05-09
    role: adversarial-review      # compliance-check | adversarial-review | drafting
    summary: "Reviewed structure and dependency chains"  # optional, max 500 chars
  - tool: claude-code
    date: 2026-03-15
    role: compliance-check
    summary: "Checked for ADR-009 service layer violations"
```

**Explicit non-accountability**: AI tools are explicitly named here to provide
**transparency without false accountability**. An ADR with only `ai_sparring_by`
entries and no `reviewed_by` entries has **Bus Factor = 1**.

This makes the knowledge concentration risk **visible** instead of hiding it by
counting AI tools as human reviewers.

---

### New Field: `metrics` (auto-computed)

```yaml
metrics:
  references_90d: 3       # how often this ADR was queried in the last 90 days
  inbound_links: 5        # number of other ADRs that depend-on or relate-to this one
  ttd_days: 14            # time-to-decision (draft → accepted)
  ttr_days: 7             # time-to-review (accepted → first reviewed_by entry)
  last_computed: "2026-05-10T00:00:00Z"
```

**Do NOT edit manually.** Populated by `adrfw nightly` or `mcp2_adr_audit`.

---

## Migration Path for 161 existing ADRs

### Phase 1 — Karenzzeit (2026-05-10 to 2026-11-10)

- Schema v4 is **additive** — all new fields are optional.
- Legacy `reviewed-by: "string"` and `reviewed-by: ["AI (role, date)"]` are
  stripped by the persistence layer (normalization step C.v4-migration).
- Result: these ADRs get `reviewed_by: []` → Bus Factor warning fires (correct behavior).
- `doc_type` defaults to `adr` if absent.
- `void` status is only set intentionally on misclassified ADRs.

### Phase 2 — Backfill (2026-11-10 to 2027-02-10)

- ADR author adds structured `reviewed_by` entries for accepted ADRs.
- AI contributions are moved from `reviewed_by` to `ai_sparring_by`.
- `adr_audit` staleness check starts enforcing `reviewed_by` for `status: accepted`.

### Phase 3 — Enforcement (2027-02-10+)

- ADR validate raises `error` (not warning) for `status: accepted` + empty `reviewed_by`.

---

## Validator Rules (new in v4)

| Rule ID | Severity | Condition |
|---------|----------|-----------|
| `v4/bus-factor` | WARNING | `status: accepted` and `reviewed_by` is empty/absent |
| `v4/ai-in-reviewed-by` | ERROR | `reviewed_by[].name` matches known AI tool pattern |
| `v4/doc-type-mismatch` | ERROR | `doc_type != "adr"` for files in `docs/adr/` (unless `status: void`) |
| `v4/void-no-content` | WARNING | `status: void` but body length > 500 chars (should be tombstone only) |

---

## Backwards Compatibility

All changes are additive. Existing v3 ADRs load without modification.

The persistence normalization handles:
- `reviewed-by` (hyphen) → `reviewed_by` (underscore) via `_FIELD_ALIASES`
- `ai-sparring-by` (hyphen) → `ai_sparring_by` via `_FIELD_ALIASES`
- `doc-type` (hyphen) → `doc_type` via `_FIELD_ALIASES`
- Legacy string/string-array `reviewed_by` → stripped (C.v4-migration step)
- Nested `date` fields (datetime.date → string) normalized in C.1b-v4

`Status.VOID` is a new member of the `Status` enum — `is_active()` returns
`False`, `is_pre_decision()` returns `False` for void ADRs.
