# Cascade Pipeline Integration Guide

How to use `iil-adrfw` from a Cascade workflow or any CI pipeline. The CLI
exposes all 8 MCP tools as subcommands with consistent JSON/text output and
exit codes.

## Setup (once per environment)

```bash
pip install /path/to/iil-adrfw  # or pip install -e if developing

# Tell iil-adrfw where the constitution lives:
export IIL_ADRFW_ADRS_DIR=/path/to/platform/docs/adr
export IIL_ADRFW_SCHEMAS_DIR=/path/to/iil-adrfw/schemas
```

## Exit code contract

Every subcommand uses these conventions:

| Exit | Meaning | When |
|---|---|---|
| `0` | Clean — no findings, no violations | All happy paths |
| `1` | Issues found | `audit` has findings, `check` has violations, `validate-cross-repo` has blocking conflicts, `diff` has changes, `propose` blocks publish |
| `2` | Configuration error | Bad arguments, missing files, invalid request |

This means CI scripts can do `iil-adrfw audit --json && echo "clean" || echo "issues"`
without parsing JSON for the common gate.

## Workflow 1 — Daily audit gate (CI)

Fail the build if the constitution is unhealthy.

```bash
#!/usr/bin/env bash
set -e
iil-adrfw audit --json > audit-report.json
if [[ $? -eq 1 ]]; then
    echo "Constitution has findings — see audit-report.json"
    jq '.findings[] | {severity, auditor, description}' audit-report.json
    exit 1
fi
echo "Constitution clean — health: $(jq '.health.score' audit-report.json)"
```

## Workflow 2 — Pre-commit rule check

Run rules against staged files only.

```bash
#!/usr/bin/env bash
staged=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.py$')
if [[ -z "$staged" ]]; then
    exit 0
fi
iil-adrfw check $staged --severity error
# rc=1 means violations found — block commit
```

## Workflow 3 — Cross-repo validation in PR check

When changing platform ADRs, verify all consumer repos still comply.

```bash
#!/usr/bin/env bash
ADR_ID="${1:-ADR-188}"

iil-adrfw validate-cross-repo \
    --adr-id "$ADR_ID" \
    --repo platform=/repos/platform \
    --repo mcp-hub=/repos/mcp-hub \
    --repo meiki-hub=/repos/meiki-hub \
    --json > cross-repo.json

# Block PR merge if any consumer has class1 (blocking) conflicts
jq -e '.has_blocking_conflicts | not' cross-repo.json > /dev/null
```

## Workflow 4 — Onboarding doc generation (nightly)

Refresh the team's onboarding markdown from the current constitution.

```bash
#!/usr/bin/env bash
iil-adrfw narrate \
    --audience new_dev \
    --domain "django/models" \
    --scope-label "data layer" \
    > docs/onboarding/data-layer-architecture.md

iil-adrfw narrate \
    --audience auditor \
    --domain "security/dsgvo" \
    --scope-label "GDPR-relevant decisions" \
    > docs/compliance/dsgvo-trail.md
```

## Workflow 5 — Quarterly architecture diff for retrospective

Generate a "what changed last quarter" report.

```bash
#!/usr/bin/env bash
LEFT="2026-02-01T00:00:00"
RIGHT="2026-05-08T00:00:00"

iil-adrfw diff --mode temporal \
    --left-time "$LEFT" \
    --right-time "$RIGHT" \
    --json > quarterly-diff.json

# Build human-readable summary
jq -r '
  "Quarter \(.left_label) → \(.right_label):
   +\(.added_count) added, -\(.removed_count) removed, ~\(.modified_count) modified

   Changes:" + (.changes | map("  \(.kind): \(.summary)") | join("\n"))
' quarterly-diff.json
```

## Workflow 6 — Compare two repos for drift

When suspecting that meiki-hub has drifted from platform standards.

```bash
#!/usr/bin/env bash
iil-adrfw diff --mode set \
    --right-dir /repos/meiki-hub/docs/adr \
    --left-label platform \
    --right-label meiki-hub
```

## Workflow 7 — Propose ADR via Cascade

When Cascade decides to author an ADR, it can call this and receive back a
schema-valid frontmatter and a body prompt to expand.

```bash
iil-adrfw propose \
    --title "Adopt OpenTelemetry for distributed tracing" \
    --rationale "We need consistent tracing across the polyrepo to debug latency in cross-service flows. OTel is the de-facto standard." \
    --domain "observability" \
    --domain "platform" \
    --decider "Achim Dehnert" \
    --json > new-adr.json

# Cascade then expands the body using new-adr.body_prompt
# and writes new-adr.frontmatter as YAML to a fresh ADR-NNN.md file
```

## Output contract for JSON consumers

All `--json` outputs are stable Pydantic models. Important top-level fields:

| Tool | Key fields |
|---|---|
| `audit` | `health.score`, `findings[].severity`, `findings[].description` |
| `check` | `violations[].rule_id`, `violations[].file_path`, `violations[].severity` |
| `query` | `primary_answer`, `citations[].adr_id`, `citations[].relevance` |
| `validate-cross-repo` | `has_blocking_conflicts`, `class1_count`, `conflicts[]` |
| `diff` | `added_count`, `removed_count`, `modified_count`, `changes[]` |
| `narrate` | `markdown`, `sections[]` (always 5 sections in fixed order) |
| `propose` | `proposed_id`, `frontmatter` (dict), `body_prompt`, `blocks_publish` |

## Notes on running headless

- The CLI loads the constitution **on every invocation** (no caching). For
  workflows that hit multiple commands in sequence, prefer the MCP server.
- All commands respect the `IIL_ADRFW_ADRS_DIR` environment variable; pipeline
  steps can use this to point at different constitutions per stage.
- Errors print to stderr; results print to stdout. JSON results go to stdout.
- `--json` is always optional; without it, output is human-readable text.
