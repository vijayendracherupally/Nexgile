# Nexgile-DecarbX Environmental Intelligence Platform
## Functional Requirements (Condensed) — transcribed source of truth

> Source: 2-page scanned functional overview supplied by the client.
> Scope note carried from the source: *"Single 2-page functional overview (no timelines, no security standards)."*
> Every bullet below is preserved from the source. Nothing added, nothing dropped.
> Requirement IDs (FR-n.n) are added purely for traceability to code.

---

## 1. Purpose & Outcomes

**FR-1.1** Provide enterprises with **one** environmental intelligence platform for:
1. audit-grade carbon accounting
2. product footprinting
3. supply-chain decarbonization
4. reduction planning
5. regulatory reporting

---

## 2. Primary Users & Role-Based Views

**FR-2.1 Sustainability roles** — Chief Sustainability Officers, ESG teams, carbon accountants, environmental managers, assurance teams.

**FR-2.2 Business roles** — Supply Chain/Procurement, Product/R&D, Manufacturing/Operations, Finance, Compliance, Risk, C-suite leaders.

**FR-2.3 External roles** — suppliers, data providers, auditors/verifiers, consultants, customers, regulatory-reporting stakeholders.

*Each role gets a distinct role-based view (see FR-7.1 for the segregation rule).*

---

## 3. Functional Scope (Modules & Key Capabilities)

### A) Enterprise Carbon Accounting

**FR-3.A.1 Scope 1** — stationary combustion, mobile combustion, fleet, process, and fugitive emissions; with meter, sensor, and telematics data capture.

**FR-3.A.2 Scope 2** — facility electricity/energy; location-based **and** market-based calculations; renewable instruments; grid factors for **150+ countries**.

**FR-3.A.3 Scope 3** — **all 15 GHG Protocol categories**, computed from spend-, activity-, supplier-, asset-, travel-, logistics-, use-, and end-of-life data.

**FR-3.A.4 Calculation engine** — emission-factor selection, unit conversion, allocation, consolidation, recalculation, uncertainty, and auditable formula history.

**FR-3.A.5 Organization model** — entities, facilities, departments, cost centers, products, reporting boundaries, baseline years, and ownership controls.

### B) Product LCA & PCF

**FR-3.B.1** PLM/ERP and **multi-level BOM** integration with material composition, component-supplier mapping, and alternative-material scenarios.

**FR-3.B.2** Process modeling for energy, emissions, scrap, defects, batch/continuous production, packaging, warehousing, and multimodal logistics.

**FR-3.B.3** Cradle-to-gate, gate-to-gate, and cradle-to-grave boundaries; functional units; allocation; end-of-life, recycling, and circularity scenarios.

**FR-3.B.4** ISO 14067-ready reports, assumptions, source evidence, uncertainty/sensitivity analysis, peer review, verification, and certification packs.

**FR-3.B.5** SKU-level PCFs, eco-design comparisons, environmental labels, QR declarations, marketing-claim evidence, and B2B exchange formats.

### C) Supplier Engagement & Scope 3

**FR-3.C.1 Supplier onboarding** — invitations, **25+ languages**, reminders, progress tracking, and materiality-based questionnaires.

**FR-3.C.2 Primary-data collection** — forms, documents/OCR, APIs, mobile capture, validations, attestations, evidence, and submission workflows.

**FR-3.C.3** Supplier scorecards, maturity assessments, rankings, year-over-year performance, improvement plans, assistance, and joint reduction projects.

**FR-3.C.4** Multi-tier network maps, geographic heat maps, supplier/category hotspots, outliers, alternative sourcing, and resilience/emissions scenarios.

**FR-3.C.5 Procurement decisions** — carbon-weighted bids, carbon-inclusive TCO, category strategies, contract clauses, KPIs, audits, and data agreements.

### D) AI Analytics & Reduction Planning

**FR-3.D.1** Automated spend categorization, invoice/document extraction, emissions anomaly detection, gap identification, and predictive forecasting.

**FR-3.D.2** What-if modeling, Monte Carlo uncertainty, sensitivity analysis, internal carbon price impacts, and SBTi-aligned pathway optimization.

**FR-3.D.3** Hotspot Pareto analysis, reduction levers, technology roadmaps, marginal abatement comparisons, investment priority, ROI, and progress tracking.

**FR-3.D.4** Data-quality scores, factor confidence, completeness, lineage, validation/cleansing, calculation versions, approvals, and change history.

### E) Dashboards & Carbon Finance

**FR-3.E.1 Executive scorecards** — total emissions, intensity, targets, trajectories, peer benchmarks, exposure, risks, and reduction performance.

**FR-3.E.2 Operational drill-down** — by entity, facility, cost center, product, supplier, project, category, geography, period, and data-quality status.

**FR-3.E.3 Carbon finance** — carbon budgets, internal pricing, credit/offset registry, retirement evidence, project economics, TCFD financial impacts, and investment prioritization.

> *Source note: the final phrase of this bullet is cut off at the page edge in the scan — it reads "…and investment p…". Read here as "investment prioritization"; to be confirmed with the client.*

---

## 4. Regulatory Compliance & Disclosure

**FR-4.1 CSRD/ESRS** — double materiality, entity consolidation, value-chain disclosures, transition plans, data-point verification, XBRL mapping, approvals, and assurance readiness.

**FR-4.2 CBAM** — imported-product mappings, embedded emissions, default/actual data, supplier requests, quarterly reports, certificates, payments, adjustments, and evidence.

**FR-4.3 TCFD and climate risk** — governance, scenarios, risks/opportunities, financial impacts, metrics, targets, controls, and disclosure documentation.

**FR-4.4 EU Taxonomy** — activity eligibility/alignment, technical criteria, DNSH checks, safeguards, CapEx/OpEx/revenue allocation, and reporting.

**FR-4.5 SEC climate and CDP** — Scope disclosures, attestation evidence, materiality, questionnaires, evidence library, review workflow, benchmarks, and response history.

---

## 5. Integrations & Data Sources (Functional)

**FR-5.1 Enterprise systems** — SAP, Oracle, Microsoft Dynamics, NetSuite, custom ERP, PLM, MES, WMS, TMS, procurement, finance, expense, and travel platforms.

**FR-5.2 Operational sources** — utilities, meters, IoT/sensors, fleet telematics, manufacturing, warehouses, logistics, waste, assets, HR, surveys, invoices, and receipts.

**FR-5.3 External data** — ecoinvent/GaBi and other factor libraries, grid data, weather/climate services, commodity indices, benchmarks, and regulatory updates.

**FR-5.4 Exchange** — REST/GraphQL APIs, webhooks, batch/streaming, JSON/XML/CSV, **PACT** and **TfS** PCF formats, schema mapping, import validation, and error queues.

**FR-5.5 Integration administration** — credentials, mappings, schedules, factor/data versions, sync status, retries, reconciliation, health monitoring, and transaction logs.

---

## 6. Core Data Objects (Platform Vocabulary)

| Column A | Column B |
|---|---|
| Organization, Entity, Facility, Department, Cost Center, Reporting Boundary | Activity Data, Meter Reading, Transaction, Emission Factor, Calculation, Allocation |
| Scope, Category, Source, Emission, Intensity, Baseline, Target, Reduction Initiative | Product/SKU, BOM, Material, Process, Route, Packaging, Functional Unit, PCF/LCA |
| Supplier, Questionnaire, Submission, Evidence, Scorecard, Action Plan | Framework, Disclosure, Data Point, Report, Assurance Request, Credit/Offset |

**Full object list (40):** Organization, Entity, Facility, Department, Cost Center, Reporting Boundary, Activity Data, Meter Reading, Transaction, Emission Factor, Calculation, Allocation, Scope, Category, Source, Emission, Intensity, Baseline, Target, Reduction Initiative, Product/SKU, BOM, Material, Process, Route, Packaging, Functional Unit, PCF/LCA, Supplier, Questionnaire, Submission, Evidence, Scorecard, Action Plan, Framework, Disclosure, Data Point, Report, Assurance Request, Credit/Offset.

> These names are the **platform vocabulary** — API resources, DB tables, and UI labels must use exactly these terms.

---

## 7. Key Functional Requirements

**FR-7.1 Role-based access and tenant/entity segregation** — users see only permitted organizations, facilities, suppliers, products, calculations, evidence, and reports.

**FR-7.2 Audit-grade lineage** — every reported value traces to source activity, factor, method, unit conversion, allocation, assumptions, approvals, and timestamped changes.

**FR-7.3 Calculation governance** — controlled factor libraries, methodology/version locking, recalculation impact analysis, review/approval, restatement, and reproducibility.

**FR-7.4 Data-quality workflow** — completeness, validation, anomaly flags, estimation/gap filling, uncertainty, confidence scoring, remediation tasks, and evidence status.

**FR-7.5 Search and navigation** — across entities, sources, products, suppliers, factors, calculations, disclosures, evidence, and actions, with filters and saved views.

**FR-7.6 Notifications/workflows** — for missing data, supplier deadlines, validation failures, target deviations, factor updates, approvals, assurance requests, and regulations.

**FR-7.7 Bulk operations and exports** — activity/factor imports, supplier campaigns, calculation batches, evidence packs, PCF exchange, disclosure tables, and scheduled reports.

**FR-7.8 Scenario isolation** — forecasts and what-if models **never alter approved actuals**; comparisons show assumptions, versions, uncertainty, and selected reduction levers.

---

## Explicitly out of scope (stated by the source)

- Timelines / delivery schedule
- Security standards

*(The document does not specify them — that is not the same as the platform omitting authentication or access control; FR-7.1 still mandates role-based access and tenant segregation.)*
