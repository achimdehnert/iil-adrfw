---
id: ADR-188
title: Adopt ADR-171 schema with multilingual-e5-large as platform-wide unified vector store
status: proposed
status_history:
  - from: null
    to: proposed
    at: "2026-05-07T00:00:00Z"
    by: "Achim Dehnert <achim@iil.gmbh>"
    reason: "Konsolidiert ADR-087, ADR-171 und ADR-187§E3 nach Recherche-Ergebnis"
amended:
  - version: "v1.1"
    at: "2026-05-08"
    by: "Achim Dehnert <achim@iil.gmbh>"
    summary: "Review-Fixes: UUID-Klarstellung, Decision Drivers, Open Questions, Glossar, Deprecation-Timeline, SPOF-Mitigation, DSGVO-Policy"
    sections_changed: ["E6", "E7", "3", "4", "8", "10"]
    rationale: >
      Konsistenz-Audit gegen Consumer-Repos zeigte, dass tenant_id dort durchgehend als
      UUID modelliert ist. ADR-022 betrifft nur Primary Keys; tenant_id ist kein PK.
      Zusätzlich: explizite Deprecation-Timeline für ADR-087 (Zero Breaking Changes),
      collection-spezifische DSGVO-Fallback-Policy, SPOF-Mitigation für mcp_hub_db.
decision_date: "2026-05-07"
valid_from: "2026-05-07T00:00:00Z"
valid_to: null
knowledge_from: "2026-05-07T00:00:00Z"
retroactive: false
deciders:
  - "Achim Dehnert <achim@iil.gmbh>"
consulted:
  - "AI Engineering Squad"
informed:
  - "Repo-Owner risk-hub"
  - "Repo-Owner meiki-hub"
  - "Repo-Owner bfagent"
  - "Repo-Owner coach-hub"
  - "Repo-Owner weltenhub"
domains:
  - data/vector-store
  - data/embeddings
  - rag/infrastructure
  - django/models
  - security/dsgvo
tech_stack:
  - "python>=3.12"
  - "postgres>=16"
  - "pgvector>=0.8"
  - "django>=5.0"
decision_drivers:
  - id: D-1
    driver: "Kein Schema-Wildwuchs — Consumer-Repos sollen genau eine API nutzen"
    weight: critical
    category: strategic
  - id: D-2
    driver: "DSGVO — personenbezogene Daten (meiki-hub Fallakten, risk-hub SDS) dürfen nicht an Cloud-APIs"
    weight: critical
    category: regulatory
  - id: D-3
    driver: "Temporal-Semantik — Gültigkeitsdaten bei Gesetzen und SDS-Versionen"
    weight: critical
    category: regulatory
  - id: D-4
    driver: "Tenant-Isolation — jeder Tenant sieht nur eigene Daten, UUID-basiert"
    weight: critical
    category: security
  - id: D-5
    driver: "Bestehende Infra nutzen — pgvector bereits deployed (kein neuer Service)"
    weight: high
    category: operational
  - id: D-6
    driver: "Cross-Repo-Suche perspektivisch möglich (ein Embedding-Modell für alle)"
    weight: medium
    category: strategic
  - id: D-7
    driver: "Kosten — kein laufender API-Verbrauch für Embeddings"
    weight: medium
    category: cost
supersedes:
  - id: ADR-087
    reason: "search_chunks-Schema wird durch rag_chunks ersetzt (Phase D-4)"
superseded_by: []
consolidates:
  - id: ADR-087
    reason: "Hybrid Search Architecture — Schema-Anteil"
  - id: ADR-171
    reason: "rag_collections / rag_documents / rag_chunks — wird zur Single Source of Truth"
  - id: ADR-187
    section: "E3"
    reason: "VectorStore-Schema-Anteil der Document Intelligence Pipeline"
depends_on:
  - id: ADR-087
    reason: "Hybrid Search Architecture — platform-search Package bleibt als Thin Client"
  - id: ADR-113
    reason: "pgvector Agent Memory Store — separate Tabelle, gleiche Engine"
  - id: ADR-022
    reason: "BigAutoField PK convention (nur PKs, nicht tenant_id)"
conflicts_with: []
informs:
  - ADR-172
  - ADR-170
rules_file: "ADR-188-unified-vector-store.rules.yaml"
tags:
  - rag
  - vector-store
  - consolidation
  - cross-repo
  - dsgvo
incident_links: []
last_reviewed: "2026-05-08"
principal: "platform"
scope:
  include_paths:
    - "**/db/schema.sql"
    - "**/models/**.py"
    - "**/rag/**"
    - "packages/platform-search/**"
repo: "platform"
consumers:
  - "meiki-hub"
  - "risk-hub"
  - "bfagent"
  - "coach-hub"
  - "weltenhub"
  - "travel-beat"
  - "dms-hub"
  - "mcp-hub"
implementation_status: none
per_repo_status:
  platform:
    status: proposed
    implementation_status: none
    planned_phase: "Phase 1"
    target_date: "2026-05-21"
    notes: "ADR-171 Schema deployen (mcp_hub_db) mit UUID tenant_id"
  mcp-hub:
    status: accepted
    implementation_status: planned
    planned_phase: "Phase 1"
    target_date: "2026-05-21"
    notes: "rag-mcp implementieren (MVP: ingest + search) + Backup-Cron + Health-Endpoints"
  meiki-hub:
    status: accepted
    implementation_status: planned
    planned_phase: "Phase 2"
    target_date: "2026-06-15"
    notes: "Pilot: BayBO + BayArchivG (ADR-006), DSGVO-Policy meiki:fallakten allow_cloud=False"
  risk-hub:
    status: accepted
    implementation_status: planned
    planned_phase: "Phase 2"
    target_date: "2026-06-15"
    notes: "SDS + Bibliothek via rag-mcp, ProjectDocumentLink Phase 3"
  bfagent:
    status: accepted
    implementation_status: planned
    planned_phase: "Phase 2"
    target_date: "2026-06-15"
    notes: "Migration search_chunks -> rag_chunks (Dual-Read in Phase D-2)"
  weltenhub:
    status: accepted
    implementation_status: planned
    planned_phase: "Phase 2"
    target_date: "2026-06-15"
    notes: "Migration search_chunks -> rag_chunks (Dual-Read in Phase D-2)"
  coach-hub:
    status: accepted
    implementation_status: none
    planned_phase: "Phase 3"
    notes: "RAG-Prefill via Bibliothek"
  travel-beat:
    status: proposed
    implementation_status: none
    planned_phase: null
    notes: "Konsumiert RAG, kein eigener Storage"
  dms-hub:
    status: proposed
    implementation_status: none
    planned_phase: null
staleness_months: 6
drift_check_paths:
  - "mcp-hub/rag_mcp/db/schema.sql"
  - "platform/packages/platform-search/**"
  - "**/models/document_chunk*.py"
  - "**/models/search_chunk*.py"
  - "**/models/rag_*.py"
deprecation_timeline:
  - phase: "D-1"
    action: "rag-mcp deployed, rag_chunks parallel verfügbar"
    state: "ADR-087 aktiv, ADR-188 parallel"
    earliest: "Phase 1 done"
    completion_signal: "rag_list(tenant_id=<uuid>) gibt leere Liste zurück, search_chunks unverändert"
  - phase: "D-2"
    action: "Consumer migrieren einzeln (bfagent, weltenhub)"
    state: "Dual-Read: SearchService fragt rag-mcp, Fallback auf search_chunks"
    earliest: "Phase 2"
    completion_signal: "search_chunks Treffer-Anteil < 5% in bfagent/weltenhub Logs"
  - phase: "D-3"
    action: "platform-search Package: Deprecation-Warning in Logs"
    state: "Alle Consumer auf rag-mcp"
    earliest: "Phase 2 + 4 Wochen"
    completion_signal: "Keine Deprecation-Warnings in 7 aufeinanderfolgenden Tagen"
  - phase: "D-4"
    action: "search_chunks Tabelle: read-only, dann DROP"
    state: "ADR-087 Status -> Superseded by ADR-188"
    earliest: "Phase 3 (frühestens 8 Wochen nach D-3)"
    completion_signal: "DROP TABLE search_chunks committed; ADR-087.status = superseded"
spof_mitigation:
  - component: "mcp_hub_db (zentrale Vector-DB)"
    measure: "Automated Backup"
    implementation: "pg_dump --format=custom via Cron, täglich, 30 Tage Retention"
    phase: "Phase 1"
  - component: "rag-mcp Service"
    measure: "Graceful Degradation"
    implementation: "rag-mcp unavailable -> Consumer-Apps degradieren auf FTS-only (keyword-basiert, ohne Embeddings)"
    phase: "Phase 1"
  - component: "rag-mcp Service"
    measure: "Health Monitoring"
    implementation: "rag-mcp /livez/ + /healthz/ (DB-Connection + Embedding-Service)"
    phase: "Phase 1"
  - component: "mcp_hub_db"
    measure: "Read-Replica (optional)"
    implementation: "Streaming Replication für Search-Queries bei >500k Chunks"
    phase: "Phase 4"
open_questions:
  - id: Q-1
    question: "Soll ADR-171 separat akzeptiert werden oder inline in ADR-188 aufgehen?"
    decide_by: "Phase 0"
    owner: "Achim Dehnert"
    status: open
  - id: Q-2
    question: "Embedder-Service: eigener Container oder Sidecar im mcp-hub Compose?"
    decide_by: "Phase 1"
    owner: "Platform"
    status: open
  - id: Q-3
    question: "Embedding-Modell-Upgrade-Strategie: Parallele Columns oder vollständiges Re-Embedding?"
    decide_by: "Phase 2"
    owner: "Platform"
    status: open
  - id: Q-4
    question: "Cross-Repo-Search (Phase 4): Benötigt das ein explizites Opt-in pro Tenant?"
    decide_by: "Phase 4"
    owner: "Achim Dehnert"
    status: open
  - id: Q-5
    question: "SLA für rag-mcp: Welche Verfügbarkeit/Latenz wird garantiert?"
    decide_by: "Phase 1"
    owner: "Platform"
    status: open
rationale_summary: >
  Drei parallele Vector-Store-Definitionen (ADR-087, ADR-171, ADR-187) mit zwei
  Embedding-Modellen werden zu einem einzigen Schema (ADR-171 mit UUID tenant_id)
  und einem primären Embedding-Modell (multilingual-e5-large, 1024 Dim, lokal)
  konsolidiert. Single API: rag-mcp. DSGVO-Vorteil: lokales Embedding für
  meiki-hub Fallakten und risk-hub Betriebsgeheimnisse. Collection-spezifische
  Fallback-Policy. Zero Breaking Changes durch 4-phasige Deprecation-Timeline.
---

# ADR-188 v1.1 — Adopt ADR-171 schema with multilingual-e5-large as platform-wide unified vector store

## Executive Summary

Drei parallele Vector-Store-Definitionen (ADR-087 `search_chunks` 1536 Dim OpenAI,
ADR-171 `rag_chunks` 1024 Dim multilingual-e5-large, ADR-187 §E3 `document_chunks`
1536 Dim OpenAI) werden zu einem **Unified Vector Store** konsolidiert mit:
- einheitlichem Schema (ADR-171: `rag_collections` / `rag_documents` / `rag_chunks`)
- einer API (`rag-mcp`, ADR-172)
- einem Embedding-Modell (multilingual-e5-large, 1024 Dim) — OpenAI als optionaler
  Fallback nur für Collections ohne DSGVO-Restriktion (siehe E7)

## E6: tenant_id ist UUID — Klarstellung

ADR-022 betrifft Primary Keys. `tenant_id` ist **kein** Primary Key, sondern
Referenzfeld auf externe Identität (Organization). Alle Consumer-Repos nutzen
bereits `tenant_id = models.UUIDField(db_index=True)`. ADR-171-Schema wird
entsprechend korrigiert (BIGINT -> UUID für tenant_id).

## E7: DSGVO-Fallback-Policy (collection-spezifisch)

Der OpenAI-Fallback darf NICHT automatisch für alle Collections greifen.
Collection-spezifische Policy:
- DSGVO-kritisch (NUR lokales Embedding, kein Cloud-Fallback): `meiki:fallakten`,
  `meiki:gesetze`, `risk:sds`, `risk:gbu`
- Cloud-Fallback erlaubt wenn lokaler Embedder unavailable: `bfagent:stories`,
  `welten:lore`, `platform:adrs`, `coach:materials`

Verhalten bei Embedder-Ausfall:
- `allow_cloud: False` -> `EmbeddingUnavailableError`, Ingest schlägt fehl,
  Search degradiert auf FTS-only
- `allow_cloud: True` -> Transparenter Fallback auf OpenAI API

## Migration siehe deprecation_timeline (D-1 .. D-4)

## Open Questions siehe open_questions (Q-1 .. Q-5)

## Glossar

| Begriff | Erläuterung |
|---|---|
| Chunk | Ein Textabschnitt (100-500 Wörter), der als kleinste Sucheinheit im Vector Store liegt |
| Collection | Logische Gruppierung von Dokumenten (z.B. alle Gesetze eines Repos) — siehe E4 |
| Embedding | Numerische Repräsentation (Zahlenvektor) eines Textes, die dessen Bedeutung codiert |
| FTS | Full-Text Search — klassische Keyword-Suche über PostgreSQL `tsvector` |
| HNSW | Hierarchical Navigable Small World — schneller Nearest-Neighbor-Index für Vektoren |
| Hybrid Search | Kombination aus semantischer Vektorsuche und klassischer Keyword-Suche |
| pgvector | PostgreSQL-Extension für Vektor-Ähnlichkeitssuche |
| rag-mcp | MCP-Server der die Vector-Store-API bereitstellt (ingest, search, supersede) |
| RRF | Reciprocal Rank Fusion — Algorithmus der Ergebnisse aus zwei Suchverfahren zusammenführt (Cormack et al. 2009) |
| Supersession Chain | Versionskette: Neues Dokument ersetzt altes, altes bleibt für historische Queries erhalten |
| Temporal | Zeitbezogene Suche: "Was galt am Stichtag X?" statt nur "Was gilt jetzt?" |
| tenant_id | Eindeutige Kennung (UUID) eines Mandanten — isoliert Daten zwischen Organisationen |
