# adr_shadow_pr — deferred (design notes only)

**Status:** Not implemented in Iter 3.
**Date deferred:** 2026-05-08
**Rationale:** No concrete use case yet that justifies the risk surface of a code-modifying tool. Will be reconsidered when there is real demand from `adr_audit` violations that need automated remediation.

## When to revisit

- `adr_audit` produces a recurring class of violations that humans manually fix the same way each time
- The same rule keeps firing across multiple repos with the same fix-pattern
- The rule's fix is mechanical (no design judgment needed)

If those three conditions hold, `adr_shadow_pr` becomes an automation worth building.

## Captured design decisions (when we do build it)

### Architecture
- Tool produces patches in a `.shadow-patches/` directory
- Tool **never** writes to source files directly
- Tool **never** calls GitHub API
- Workflow: tool generates patch → human runs `git apply --check` → human runs `git apply` → human reviews → human commits + opens PR

This mirrors the proven `adr-doctor` model where the human stays in the code-modification loop. That model caught 6 bugs in adr-doctor itself; the same review safety should apply here.

### Patch scope (combined approach)

Two complementary strategies operating in parallel:

**1. Structured patches with TODO markers**
- For mechanical fixes (add field, change type, add import): generate a real unified diff
- For complex refactors (semantic restructuring, multi-file changes): emit a `# TODO ADR-NNN: <description>` comment with rule-id and ADR-link, plus a structured suggestion in the patch metadata
- The TODO marker is itself a real diff line that humans can apply, then expand

**2. Generic pattern engine**
- Per Rule, declare a `patch_template` with regex placeholders
- Engine matches the violation site against the template, produces the diff
- Allows ADR authors to write their own patch templates alongside the rule

### What the tool needs as input

- `rule_id` (which rule to remediate)
- `target_repo_path` (where to scan/patch)
- Optional `dry_run: false` to actually emit files (default: just preview)

### What the tool produces

```python
class ShadowPatchResponse(BaseModel):
    rule_id: str
    target_repo: str
    patches_generated: int
    patch_files: list[Path]                 # paths under .shadow-patches/
    todos_inserted: int                     # complex cases marked
    files_touched: list[str]
    apply_command: str                      # e.g. 'git apply .shadow-patches/all.patch'
    runtime_ms: int
```

### What the tool does NOT do

- No semantic refactors (asyncio→asgiref, schema migrations)
- No multi-file dependency graph rewrites
- No verification that the patches actually make tests pass — that's the human's job

### Scope realism

For the iil.gmbh stack (BigAutoField+public_id, tenant_id consistency, soft-delete), the simple-case patches realistically cover ~70% of mechanical drift. The remaining 30% need a TODO marker and human attention.
