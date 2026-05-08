# iil-adrfw — Sprint-Plan nach Iter 3

**Stand:** 2026-05-08, Ende von Iter 3 (8 MCP-Tools, 71 Tests grün, Schema v3 live, Constitution geheilt)
**Zweck:** Was kommt als nächstes — sowohl als Tool-Roadmap als auch als praktische Anwendung im Stack.

---

## Teil 1 — Tool-Roadmap (Iter 4 — Iter 7)

Drei Themenfelder mit unterschiedlicher Priorität:

### Iter 4 — Audit-Erweiterungen (höchste Priorität)

Die echten 156-ADR-Daten zeigen, dass die jetzigen 6 Auditoren nur einen Teil dessen sehen, was wirklich anliegt. Drei neue Auditoren mit konkretem Nachweis-Use-Case:

| Auditor | Findet | Use-Case-Trigger |
|---|---|---|
| `implementation_evidence_check` | ADRs mit `implementation_status: complete` aber leerer `implementation_evidence` | 87/141 ADRs nutzen das Feld bereits — bei `complete`-Status muss es belegt sein |
| `circular_dependency` | Zyklen in `depends_on` und `consolidates` über alle ADRs | Polyrepo-Risiko: ADR-A depends_on ADR-B depends_on ADR-A |
| `orphaned_adr` | ADRs ohne irgendeine eingehende Referenz aus anderen ADRs/Code | Tote Beschlüsse — geringer Wert, halten aber den Health-Score |

**Aufwand:** ~600 LOC + 15 Tests, ~3h.
**Risiko:** Niedrig — alle drei sind reine Reader, kein Schema-Change.
**Output-Wert:** Health-Score wird differenzierter, aktuelle 1.000 fallen wahrscheinlich auf 0.85-0.92 — das ist **gut**, weil ehrlicher.

### Iter 5 — `adr_shadow_pr` (deferred, see ADR_SHADOW_PR_DEFERRED.md)

Wird gebaut, **wenn** drei Bedingungen zusammenkommen:
1. Iter 4 produziert eine wiederkehrende Klasse von Findings
2. Das gleiche Fix-Pattern taucht über mehrere Repos auf
3. Der Fix ist mechanisch (kein Design-Urteil nötig)

Bevor diese Bedingungen alle erfüllt sind, ist das Tool spekulativ. Iter 4 Audit-Daten werden zeigen, ob es Sinn macht.

### Iter 6 — Schema-Evolution / Migration-Tools

Wenn Schema v4 nötig wird (z.B. neue Compliance-Anforderungen, neue Domain-Konzepte), brauchen wir:

| Komponente | Was |
|---|---|
| `adr_migrate` | Tool das ADRs von Schema vN nach vN+1 transformiert, generiert Patches via `adr-doctor`-Modell |
| `adr_schema_diff` | CLI-Subcommand das zwei Schema-Versionen visuell vergleicht |
| `versioned constitution` | Schema-Versions-Marker in Frontmatter (`adr_schema_version: 4`) |

**Aufwand:** Hoch (~5-7h), aber nur sinnvoll **bei konkretem Schema-v4-Bedarf**. Spekulativ verschoben.

### Iter 7 — Constitution-as-Service

Falls die internen Tools sich bewähren: API um den MCP-Server, sodass andere Cascade-Workflows oder Drittanbieter-Tools die Constitution abfragen können.

| Komponente | Was |
|---|---|
| HTTP/REST-Wrapper | um die 8 MCP-Tools, mit OpenAPI-Doku |
| Multi-Constitution-Support | mehrere Constitutions parallel (per-tenant, per-environment) |
| Webhook-Notifications | bei ADR-Änderungen → Cascade/Discord/Slack |

**Aufwand:** Hoch (~10h+). Nur wenn echte externe Konsumenten existieren.

---

## Teil 2 — Anwendungs-Plan (was läuft jetzt produktiv?)

### Phase A — Smoke-Test mit echten Daten (sofort, ~1h Cascade-Aufwand)

```bash
# 1. Loading-Rate gegen Schema v3 messen
iil-adrfw list --json | jq '.adrs | length'   # erwartet: ~150

# 2. Audit-Run gegen die 156 platform-ADRs
iil-adrfw audit --json > /tmp/audit-after-v3.json

# 3. Vergleich mit dem letzten Audit (Iter 3 Anfang: Health 1.000, 0 Findings)
jq '{score: .health.score, findings: (.findings | length)}' /tmp/audit-after-v3.json
```

**Ziel:** Bestätigen dass die Schema-v3-Aliase wirklich greifen. Erwartung: alle 152 ADRs laden strikt (vorher 102).

### Phase B — CI-Integration in platform/ (Woche 1)

```yaml
# .github/workflows/adr-gate.yml
name: ADR Constitution Gate
on: [push, pull_request]
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install /path/to/iil-adrfw
      - run: |
          export IIL_ADRFW_ADRS_DIR=$PWD/docs/adr
          iil-adrfw audit --json > audit.json
        continue-on-error: false  # Health-Score-Drop blockt PR
      - uses: actions/upload-artifact@v4
        with: { name: audit-report, path: audit.json }
```

**Effekt:** Jeder PR der ADRs ändert wird gegen die Constitution validiert.

### Phase C — Cross-Repo-Workflow für mcp-hub & meiki-hub (Woche 2-3)

Cascade ruft auf jedem PR der diese Repos berührt:

```bash
iil-adrfw validate-cross-repo \
  --adr-id ADR-099 \
  --repo mcp-hub=$PWD/repos/mcp-hub \
  --repo meiki-hub=$PWD/repos/meiki-hub \
  --json > /tmp/cross-repo.json

# Block PR wenn class1 oder class2 Konflikte
jq -e '.has_blocking_conflicts | not' /tmp/cross-repo.json
```

**Erwarteter Erstlauf:** 1-3 Konflikte, weil meiki-hub historisch von Platform-Standards abweicht. Diese explizit machen → in beide Richtungen entscheiden (anpassen ODER Ausnahme dokumentieren).

### Phase D — Onboarding-Doc-Generierung (Woche 4)

Nightly Cron:

```bash
iil-adrfw narrate --audience new_dev --domain "django/models" \
    --scope-label "data layer" \
    > docs/onboarding/data-layer.md

iil-adrfw narrate --audience auditor --domain "security/dsgvo" \
    --scope-label "DSGVO-Trail" \
    > docs/compliance/dsgvo-trail.md

git add docs/onboarding/ docs/compliance/
git diff --cached --quiet || git commit -m "auto: refresh ADR narratives [skip ci]"
git push
```

**Effekt:** Onboarding-Docs sind immer synchron mit der aktuellen Constitution, ohne manuellen Pflegeaufwand.

### Phase E — Quartals-Retro (alle 3 Monate)

```bash
LEFT=$(date -d '90 days ago' -Iseconds)
RIGHT=$(date -Iseconds)
iil-adrfw diff --mode temporal --left-time "$LEFT" --right-time "$RIGHT" \
    > /tmp/quarterly-diff.txt
```

**Effekt:** "Was haben wir architektonisch im letzten Quartal entschieden?" mechanisch generiert.

---

## Teil 3 — Risiken und Stop-Bedingungen

| Risiko | Wahrscheinlichkeit | Mitigation |
|---|---|---|
| Audit-Erweiterungen produzieren zu viele False-Positives | Mittel | Severity-Thresholds zunächst auf `error` setzen, schrittweise lockern |
| Cross-Repo-Validation blockiert legitime Drift | Hoch | Konflikte als WARNING starten, erst nach 2 Wochen auf ERROR hochstufen |
| Nightly-Narrative-Cron erzeugt git-Noise | Niedrig | `--no-changes`-Filter implementieren oder Diff-only-Commit |
| Schema-v3-Edge-Case in echten Daten | Mittel | Phase A ist genau der Smoke-Test dafür |

**Stop-Signal für die Iter 4 Audit-Erweiterungen:** Wenn Phase A zeigt dass Schema v3 die Loading-Rate **nicht** auf ≥95% hebt, dann ist ein nicht-verstandenes Phänomen in den Daten — keine neuen Auditoren dazu schalten, sondern erst diagnostizieren.

---

## Empfohlene nächste konkrete Schritte (in Reihenfolge)

1. **Phase A ausführen** — 1h Cascade-Arbeit, klare Validierung von Schema v3
2. **Iter 4 Audit-Erweiterungen** — falls Phase A grün, sonst pausiert
3. **Phase B CI-Integration** — sobald Iter 4 stabil

Schritte 1 und 2 sind die direkte Fortsetzung. Phase B ist der "Produktiv-Schalter".
