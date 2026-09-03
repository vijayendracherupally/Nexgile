# Nexgile-DecarbX — Functional Architecture

Backend: **Python**. Frontend: **React**. Every component below exists to satisfy a
requirement ID from [REQUIREMENTS.md](REQUIREMENTS.md). Nothing here adds scope
beyond the source document.

---

## 1. How the platform actually functions (the spine)

The whole platform is one loop. Everything else hangs off it.

```
                 ┌──────────────────────────────────────────────────────┐
                 │  1. INGEST        activity data / meter readings /    │
                 │                   transactions / supplier submissions │
                 │                   (FR-5.1, 5.2, 3.C.2)               │
                 └───────────────────────┬──────────────────────────────┘
                                         ▼
                 ┌──────────────────────────────────────────────────────┐
                 │  2. RESOLVE       pick the Emission Factor           │
                 │                   (region, year, method, version)     │
                 │                   (FR-3.A.4, 5.3, 7.3)               │
                 └───────────────────────┬──────────────────────────────┘
                                         ▼
                 ┌──────────────────────────────────────────────────────┐
                 │  3. CALCULATE     unit conversion → factor → GWP →   │
                 │                   allocation → consolidation          │
                 │                   emits an immutable Calculation      │
                 │                   (FR-3.A.4)                          │
                 └───────────────────────┬──────────────────────────────┘
                                         ▼
                 ┌──────────────────────────────────────────────────────┐
                 │  4. QUALIFY       completeness, validation, anomaly,  │
                 │                   uncertainty, confidence score       │
                 │                   (FR-7.4, 3.D.4)                     │
                 └───────────────────────┬──────────────────────────────┘
                                         ▼
                 ┌──────────────────────────────────────────────────────┐
                 │  5. APPROVE       review → approve → LOCK             │
                 │                   locked actuals are immutable        │
                 │                   (FR-7.3)                            │
                 └───────────────────────┬──────────────────────────────┘
                          ┌──────────────┴──────────────┐
                          ▼                             ▼
        ┌─────────────────────────────┐   ┌──────────────────────────────┐
        │ 6a. REPORT                  │   │ 6b. PLAN (scenario sandbox)  │
        │  dashboards, disclosures,   │   │  what-if, forecast, levers,  │
        │  CSRD/CBAM/TCFD/Taxonomy/   │   │  MACC, SBTi pathways         │
        │  SEC/CDP, evidence packs    │   │  NEVER writes to actuals     │
        │  (FR-3.E, FR-4, FR-7.7)     │   │  (FR-3.D, FR-7.8)            │
        └─────────────────────────────┘   └──────────────────────────────┘
```

**Two invariants govern the whole system:**

- **FR-7.2 — lineage is not a log, it is the value.** A `Calculation` row physically
  stores the activity id, factor id + factor version, method id + method version,
  unit-conversion chain, allocation rule, assumption set, approver, and timestamp.
  A reported number that cannot name all of these cannot be reported.
- **FR-7.8 — scenarios are a different address space.** Every table that scenarios
  touch carries a `scenario_id`. `scenario_id IS NULL` means *actual*. Scenario writes
  physically cannot target `NULL`. This is enforced in the repository layer, not by convention.

---

## 2. Backend (Python)

```
backend/
  app/
    core/            config, db session, RBAC scoping, audit middleware
    domain/          the 40 vocabulary objects as SQLAlchemy models
    engine/          calculation engine  ← the heart (FR-3.A.4)
      units.py           unit conversion graph
      factors.py         factor resolution + version locking (FR-7.3)
      gwp.py             GHG → CO2e via GWP set (AR5/AR6 selectable)
      allocation.py      mass / economic / physical allocation (FR-3.A.4, 3.B.3)
      consolidation.py   equity share / financial / operational control (FR-3.A.5)
      uncertainty.py     pedigree matrix + Monte Carlo (FR-3.A.4, 3.D.2)
      recalc.py          recalculation + impact analysis + restatement (FR-7.3)
      lineage.py         builds the trace record for every value (FR-7.2)
    modules/
      accounting/      Scope 1 / 2 / 3          (FR-3.A)
      lca/             product LCA & PCF        (FR-3.B)
      suppliers/       engagement & Scope 3     (FR-3.C)
      analytics/       AI analytics & planning  (FR-3.D)
      dashboards/      scorecards & carbon finance (FR-3.E)
      compliance/      CSRD, CBAM, TCFD, Taxonomy, SEC, CDP (FR-4)
      integrations/    connectors & admin      (FR-5)
      platform/        search, notifications, bulk ops, exports (FR-7.5–7.7)
    api/             FastAPI routers (REST) + GraphQL schema (FR-5.4)
    workers/         async jobs: imports, calc batches, campaigns, syncs, reports
```

**Framework choices** — FastAPI (REST + OpenAPI, and GraphQL via Strawberry, both
demanded by FR-5.4), SQLAlchemy + Alembic, PostgreSQL, Celery + Redis for the batch
and streaming work FR-5.4/FR-7.7 require, Pandas/NumPy for the calculation and
Monte Carlo maths, and pluggable OCR + ML services for FR-3.D.1.

### 2.1 Module → responsibility → key endpoints

| Module | Covers | Representative API |
|---|---|---|
| `accounting` | FR-3.A.1–.5 | `/activity-data`, `/meter-readings`, `/transactions`, `/emissions`, `/calculations`, `/allocations`, `/organizations`, `/entities`, `/facilities`, `/departments`, `/cost-centers`, `/reporting-boundaries`, `/baselines` |
| `lca` | FR-3.B.1–.5 | `/products`, `/boms`, `/materials`, `/processes`, `/routes`, `/packaging`, `/functional-units`, `/pcf`, `/pcf/{id}/iso14067-report`, `/pcf/{id}/exchange?format=pact\|tfs`, `/eco-design/compare`, `/declarations/qr` |
| `suppliers` | FR-3.C.1–.5 | `/suppliers`, `/questionnaires`, `/campaigns`, `/submissions`, `/evidence`, `/scorecards`, `/action-plans`, `/network/tiers`, `/network/heatmap`, `/procurement/bids`, `/procurement/tco` |
| `analytics` | FR-3.D.1–.4 | `/spend/categorize`, `/documents/extract`, `/anomalies`, `/gaps`, `/forecast`, `/scenarios`, `/scenarios/{id}/monte-carlo`, `/scenarios/{id}/sensitivity`, `/carbon-price/impact`, `/pathways/sbti`, `/hotspots/pareto`, `/levers`, `/macc`, `/roadmaps`, `/data-quality/scores` |
| `dashboards` | FR-3.E.1–.3 | `/scorecards/executive`, `/drilldown`, `/intensity`, `/targets`, `/trajectories`, `/benchmarks`, `/carbon-budgets`, `/internal-price`, `/credits`, `/credits/{id}/retirement`, `/project-economics`, `/tcfd/financial-impacts` |
| `compliance` | FR-4.1–.5 | `/frameworks`, `/disclosures`, `/data-points`, `/csrd/double-materiality`, `/csrd/xbrl`, `/cbam/declarations`, `/cbam/certificates`, `/tcfd/scenarios`, `/taxonomy/eligibility`, `/taxonomy/dnsh`, `/sec/disclosures`, `/cdp/responses`, `/assurance-requests` |
| `integrations` | FR-5.1–.5 | `/connectors`, `/connectors/{id}/sync`, `/mappings`, `/schedules`, `/credentials`, `/webhooks`, `/imports`, `/imports/{id}/errors`, `/factor-libraries`, `/sync-status`, `/transaction-logs` |
| `platform` | FR-7.1, .5, .6, .7 | `/search`, `/saved-views`, `/notifications`, `/workflows`, `/approvals`, `/bulk/*`, `/exports`, `/reports/scheduled`, `/roles`, `/permissions` |

### 2.2 The calculation engine in detail (FR-3.A.4)

A single `calculate()` call is a deterministic, reproducible pipeline:

1. **Normalize** the activity quantity to the factor's base unit (`units.py`), recording
   the full conversion chain.
2. **Resolve** the emission factor (`factors.py`) by source, region, period, method,
   and **locked library version** — never "latest" for an approved period.
3. **Apply** factor × quantity per gas, then **GWP** to CO2e (`gwp.py`), keeping the
   per-gas breakdown.
4. **Allocate** to entity / facility / cost center / product / functional unit
   (`allocation.py`).
5. **Consolidate** up the organization tree by the boundary's ownership rule
   (`consolidation.py`).
6. **Quantify uncertainty** (`uncertainty.py`) and attach a confidence score.
7. **Persist** an immutable `Calculation` with its complete lineage record and the
   human-readable **formula history** string.

Re-running against a new factor version does not mutate anything: it produces a new
calculation version and a **recalculation impact analysis** (old vs new, delta by
entity/scope/period), which drives the **restatement** workflow (FR-7.3).

### 2.3 Cross-cutting mechanisms

| Mechanism | Requirement | How it works |
|---|---|---|
| RBAC + tenant scoping | FR-7.1 | Every query passes through a scoping layer that injects the caller's permitted organization/entity/facility/supplier/product set. Applied at the repository, so no endpoint can leak by omission. External roles (supplier, auditor, customer) get their own narrowed scopes. |
| Lineage | FR-7.2 | `lineage.py` writes a trace row per calculation; `GET /calculations/{id}/lineage` returns the full chain; every dashboard number is click-through to it. |
| Governance | FR-7.3 | Factor libraries are versioned and lockable per reporting period; methods are versioned; approval transitions freeze the period. |
| Data quality | FR-7.4 | Rules engine scores completeness, runs validations, flags anomalies, marks estimated/gap-filled values, and spawns remediation tasks tied to evidence status. |
| Search | FR-7.5 | One cross-object index over entities, sources, products, suppliers, factors, calculations, disclosures, evidence, actions — with filters and persisted saved views. |
| Notifications | FR-7.6 | Event bus + rule subscriptions for missing data, supplier deadlines, validation failures, target deviations, factor updates, approvals, assurance requests, regulatory updates. |
| Bulk & export | FR-7.7 | Celery jobs for activity/factor imports, supplier campaigns, calculation batches, evidence packs, PCF exchange, disclosure tables, scheduled reports. |
| Scenario isolation | FR-7.8 | `scenario_id` partition + a repository guard that rejects any scenario-context write with a null scenario id. Comparison views surface assumptions, versions, uncertainty, and selected levers. |

---

## 3. Frontend (React)

```
frontend/src/
  app/            router, role-aware shell, providers
  roles/          view compositions per FR-2.1 / 2.2 / 2.3
  modules/
    accounting/  lca/  suppliers/  analytics/  dashboards/
    compliance/  integrations/  platform/
  components/     data grid, lineage drawer, DQ badge, scenario switcher,
                  approval bar, evidence viewer, filter + saved-view bar
  lib/            api client (REST + GraphQL), permissions, formatting, i18n (25+ locales)
```

**Stack** — React + TypeScript, Vite, TanStack Query (server state), TanStack Table
(the dense grids this domain lives on), Recharts/visx for charts, MapLibre for the
geographic heat maps and multi-tier network maps (FR-3.C.4), react-i18next for the
25+ languages of FR-3.C.1.

### 3.1 Screen map

| Area | Screens | Requirement |
|---|---|---|
| Organization | Org tree, entities, facilities, departments, cost centers, reporting boundaries, baseline years, ownership controls | FR-3.A.5 |
| Carbon accounting | Scope 1 / Scope 2 / Scope 3 workbenches, activity data grid, meter readings, factor browser, calculation detail + **lineage drawer** | FR-3.A.1–.4, 7.2 |
| Product LCA & PCF | Product list, BOM explorer (multi-level), process model editor, boundary/functional-unit setup, PCF result, ISO 14067 report, eco-design comparison, label/QR declaration, B2B exchange | FR-3.B.1–.5 |
| Suppliers | Supplier directory, campaign builder, questionnaire runner (multi-language, mobile capture), submission review, scorecards, action plans, network map, heat map, procurement decision tools | FR-3.C.1–.5 |
| Analytics & planning | Spend categorization review, document extraction review, anomaly inbox, gap list, forecast, **scenario workspace** (what-if, Monte Carlo, sensitivity, carbon price, SBTi pathways), Pareto hotspots, lever library, MACC, roadmap, ROI | FR-3.D.1–.4 |
| Dashboards & finance | Executive scorecard, drill-down explorer, carbon budgets, internal pricing, credit/offset registry + retirement evidence, project economics, TCFD financial impacts | FR-3.E.1–.3 |
| Compliance | Framework workspaces (CSRD/ESRS, CBAM, TCFD, EU Taxonomy, SEC, CDP), double-materiality matrix, data-point tracker, XBRL mapping, evidence library, review workflow, assurance requests | FR-4.1–.5 |
| Integrations | Connector catalog, credential + mapping setup, schedules, sync status, error queue, factor/data versions, reconciliation, health, transaction logs | FR-5.1–.5 |
| Platform | Global search + saved views, notification center, approval queue, bulk operations, export center, role/permission admin | FR-7.1, .5, .6, .7 |

### 3.2 Three UI elements carry the audit-grade promise

- **Lineage drawer** — click any number anywhere, see its full trace (FR-7.2).
- **Data-quality badge** — every value renders with completeness/confidence state and
  whether it is measured, estimated, or gap-filled (FR-7.4).
- **Scenario switcher** — a persistent banner making it unmistakable whether you are
  looking at approved actuals or a sandbox; sandbox mode disables every write to
  actuals (FR-7.8).

---

## 4. Traceability — no requirement left unowned

| FR | Backend | Frontend |
|---|---|---|
| 1.1 | whole platform | whole platform |
| 2.1–2.3 | `core/rbac`, role definitions | `roles/` view compositions |
| 3.A.1 | `modules/accounting/scope1` | Scope 1 workbench |
| 3.A.2 | `modules/accounting/scope2` (location + market, grid factors 150+ countries) | Scope 2 workbench |
| 3.A.3 | `modules/accounting/scope3` (15 categories) | Scope 3 workbench |
| 3.A.4 | `engine/*` | Calculation detail + lineage drawer |
| 3.A.5 | `domain/organization` | Organization screens |
| 3.B.1–.5 | `modules/lca` | Product LCA & PCF screens |
| 3.C.1–.5 | `modules/suppliers` | Supplier screens |
| 3.D.1–.4 | `modules/analytics` | Analytics & planning screens |
| 3.E.1–.3 | `modules/dashboards` | Dashboards & finance screens |
| 4.1–4.5 | `modules/compliance` | Compliance workspaces |
| 5.1–5.5 | `modules/integrations`, `workers` | Integration screens |
| 6 | `domain/` — 40 models named exactly as the vocabulary | UI labels use the same terms |
| 7.1 | `core/rbac` scoping layer | permission-aware routing/rendering |
| 7.2 | `engine/lineage` | lineage drawer |
| 7.3 | `engine/factors`, `engine/recalc` | approval bar, restatement flow |
| 7.4 | `modules/platform/data_quality` | DQ badge, remediation tasks |
| 7.5 | `modules/platform/search` | global search + saved views |
| 7.6 | `modules/platform/notifications` | notification center |
| 7.7 | `modules/platform/bulk`, `workers` | bulk ops + export center |
| 7.8 | `scenario_id` partition + repository guard | scenario switcher |
