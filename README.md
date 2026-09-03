# Nexgile · DecarbX

An environmental intelligence platform for audit-grade carbon accounting, product carbon footprints, supplier engagement, reduction planning, and regulatory reporting.

Nexgile brings the environmental data lifecycle into one workspace: collect activity data, apply governed emission factors, calculate emissions with full lineage, assess quality, approve results, model scenarios, and prepare disclosures.

## Highlights

- **Carbon accounting** — Scope 1, Scope 2 (location- and market-based), and all 15 Scope 3 categories.
- **Calculation governance** — deterministic unit conversion, factor selection, GWP conversion, allocation, consolidation, uncertainty, versioning, and restatement analysis.
- **Product LCA and PCF** — multi-level BOMs, process and logistics modelling, ISO 14067-ready PCFs, eco-design comparisons, declarations, and PACT/TfS exchange payloads.
- **Supplier decarbonization** — supplier onboarding, questionnaires, submissions, evidence, scorecards, network analysis, and carbon-aware procurement decisions.
- **Analytics and planning** — data-quality scoring, validations, anomalies, gap analysis, scenarios, Monte Carlo analysis, pathways, MACC, and reduction roadmaps.
- **Reporting and finance** — executive scorecards, operational drill-down, carbon budgets, internal carbon pricing, credits, and project economics.
- **Compliance** — workflows for CSRD/ESRS, CBAM, TCFD, EU Taxonomy, SEC climate disclosures, and CDP.
- **Auditability by design** — tenant-aware access control, immutable calculation lineage, governed factor libraries, and isolated scenario sandboxes.

## Architecture

```text
frontend/                 React + TypeScript + Vite application
  src/
    components/           Shared layout, tables, charts, lineage UI
    pages/                Accounting, LCA, suppliers, analytics, compliance
    lib/                  API client and session/scenario state

backend/                  FastAPI + SQLAlchemy service
  app/
    core/                 Configuration, database, RBAC, scoping, serialization
    domain/               Core data models and enums
    engine/               Calculation, factors, GWP, allocation, lineage, uncertainty
    modules/              API modules by business domain
    seed.py               Demonstration dataset

docs/                     Requirements traceability and functional architecture
```

### Calculation pipeline

```text
Activity data
  → normalize units
  → resolve versioned emission factor
  → apply factor and GWP set
  → allocate and consolidate
  → assess uncertainty and confidence
  → persist a versioned result with complete lineage
```

Every calculation preserves the inputs, factor and library version, methodology, conversion chain, allocation basis, assumptions, ownership treatment, and timestamp required to reproduce it.

## Technology

| Layer | Technology |
| --- | --- |
| Web application | React 18, TypeScript, Vite, React Router |
| API | FastAPI, Pydantic |
| Data layer | SQLAlchemy 2 |
| Default storage | SQLite (zero-configuration local setup) |
| Production database | PostgreSQL via `DECARBX_DATABASE_URL` |
| API documentation | OpenAPI/Swagger provided by FastAPI |

## Quick start

### Prerequisites

- Python 3.11+
- Node.js 20+ and npm

### 1. Start the API

From the repository root:

```bash
cd backend
python -m venv .venv
```

Activate the environment:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate
```

Install dependencies and run the API:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8077
```

On first start, the API creates the local SQLite database and loads a demonstration dataset automatically.

### 2. Start the web application

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open [http://127.0.0.1:5180](http://127.0.0.1:5180). The Vite development server proxies `/api` requests to the API at port `8077`.

### 3. Explore the API

- Health check: [http://127.0.0.1:8077/api/health](http://127.0.0.1:8077/api/health)
- Interactive API documentation: [http://127.0.0.1:8077/docs](http://127.0.0.1:8077/docs)
- Requirement coverage map: [http://127.0.0.1:8077/api/requirements/coverage](http://127.0.0.1:8077/api/requirements/coverage)

Requests can identify the acting demo user with the `X-User-Email` header. The browser application uses `ana.k@meridian.example` by default and allows the acting user to be changed from the top bar.

## Configuration

The application runs locally without environment variables. To use PostgreSQL, set `DECARBX_DATABASE_URL` before starting the API:

```bash
# Windows PowerShell
$env:DECARBX_DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/decarbx"

# macOS/Linux
export DECARBX_DATABASE_URL="postgresql+psycopg://user:password@localhost:5432/decarbx"
```

The default database is `backend/data/decarbx.db`. It is intentionally excluded from version control because it is local runtime data.

## Verification

Run these checks before submitting changes:

```bash
# Backend syntax check
cd backend
python -m compileall -q app

# Frontend type-check and production build
cd ../frontend
npm run build
```

## Documentation

- [Functional requirements](docs/REQUIREMENTS.md)
- [Functional architecture](docs/ARCHITECTURE.md)

## Status

This repository contains a working, seeded platform prototype designed around the supplied functional requirements. It is intended for local demonstration and product development; production deployment should add environment-specific security, observability, migrations, and operational controls.

