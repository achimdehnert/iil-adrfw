---
id: ADR-099
title: Multi-tenancy via tenant_id BigIntegerField with manager-level scoping
status: deprecated
status_history:
  - from: null
    to: proposed
    at: "2024-09-10T09:00:00Z"
    by: "achim <achim@iil.gmbh>"
    reason: "Initial proposal after onboarding 3rd customer"
  - from: proposed
    to: accepted
    at: "2024-09-15T14:00:00Z"
    by: "achim <achim@iil.gmbh>"
    reason: "Reviewed in arch sync, no objections"
  - from: accepted
    to: accepted
    at: "2024-12-01T10:00:00Z"
    by: "achim <achim@iil.gmbh>"
    reason: "Severity raised from warning to error after INC-2024-11-23"
    evidence: ["incidents/INC-2024-11-23.md"]
decision_date: "2024-09-15"
valid_from: "2024-09-15T00:00:00Z"
valid_to: null
knowledge_from: "2024-09-15T00:00:00Z"
retroactive: false
deciders:
  - "achim <achim@iil.gmbh>"
consulted:
  - "external-dpo <dpo@iil.gmbh>"
domains:
  - django/models
  - django/services
  - django/managers
  - security/multi-tenancy
tech_stack:
  - "python>=3.12"
  - "django>=5.0"
  - "postgres>=16"
supersedes: []
superseded_by: []
depends_on:
  - id: ADR-087
    reason: "Soft-delete via deleted_at — tenant queries must respect it"
conflicts_with: []
informs:
  - ADR-114
  - ADR-150
rules_file: "ADR-099-multi-tenancy.rules.yaml"
tags:
  - tenant
  - security
  - data-isolation
  - non-negotiable
incident_links:
  - id: "INC-2024-11-23"
    summary: "Customer A query leaked into Customer B response after orphan migration"
    relation: "motivated"
last_reviewed: "2024-09-15"
principal: "platform"
scope:
  exclude_paths:
    - "tests/factories/**"
    - "**/migrations/0*_initial.py"
rationale_summary: >
  Every tenant-owned model carries tenant_id as a BigIntegerField (not IntegerField)
  to avoid int4 overflow at scale, and uses a TenantManager whose default queryset
  filters by current tenant. Service-layer code MUST receive tenant_id explicitly;
  it MUST NOT be inferred from request state inside the model layer.
---

# ADR-099 — Multi-tenancy via tenant_id BigIntegerField with manager-level scoping

## Context

We operate a multi-tenant SaaS platform on a single PostgreSQL cluster.
Three customers were onboarded by 2024-Q3, and a partial data leak in INC-2024-11-23
revealed that an `IntegerField` tenant_id had silently overflowed in a staging
test fixture, then a developer copied that pattern into a new app.

## Decision

Three coupled constraints, applied platform-wide:

1. **`tenant_id` is `BigIntegerField`** on every tenant-owned model.
   Reason: int4 caps at 2.1B; tenant_id is composite-derived and exceeds this
   in our addressing scheme. Use BigInt always — no exceptions, no "small
   tenants will never reach that".

2. **Tenant-owned models use `TenantManager`** (subclass of `models.Manager`)
   whose default queryset is filtered by the current request's tenant.
   The current tenant is propagated via an `asgiref` context variable, never
   from `threading.local`.

3. **Service-layer functions receive `tenant_id` as an explicit parameter.**
   No "infer tenant from request" inside services. The view layer extracts
   tenant_id and passes it down. This is testable without HTTP fixtures and
   makes the boundary auditable.

## Consequences

- New models require explicit migration discipline — see ADR-087 for soft-delete.
- Cross-tenant analytics queries must use a separate `RawTenantQuerySet` that
  loudly opts out of tenant filtering and logs the access.
- Worker tasks (Celery) receive tenant_id as the first positional argument by convention.
- This makes flat queries like `Invoice.objects.all()` impossible without context.
  That is intentional.

## Alternatives considered

- **Schema-per-tenant**: rejected, ops overhead and migration complexity.
- **Row-level security (Postgres RLS)**: deferred — promising for V2 but
  requires connection-pool changes incompatible with pgbouncer in transaction
  mode.
- **`UUIDField` for tenant_id**: rejected, breaks foreign-key performance
  on large tenant tables.

## Compliance

See `ADR-099-multi-tenancy.rules.yaml` for executable rules.
Severity raised from `warning` to `error` on 2024-12-01 (INC-2024-11-23).
