---
id: ADR-9088
title: (Hypothetical) ADR-188 v1.0 with BIGINT tenant_id claim
status: proposed
decision_date: "2026-05-07"
valid_from: "2026-05-07T00:00:00Z"
deciders:
  - "Achim Dehnert <achim@iil.gmbh>"
domains:
  - data/vector-store
repo: "mcp-hub"
consumers:
  - "meiki-hub"
  - "bfagent"
implementation_status: none
rules_file: "ADR-9088-hypothetical-v10.rules.yaml"
rationale_summary: >
  Hypothetical pre-v1.1 version of ADR-188 that claimed tenant_id BIGINT.
  Used to demonstrate cross-repo validation catching the conflict that v1.1
  fixed retroactively.
---

# ADR-188 v1.0 (HYPOTHETICAL, pre-amendment)

This is a synthetic ADR used as a test fixture for cross-repo validation.
It deliberately makes the v1.0 claim that tenant_id should be BIGINT — the
claim that v1.1 corrected to UUID after consumer-repo audit revealed the
inconsistency.
