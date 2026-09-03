"""Nexgile-DecarbX Environmental Intelligence Platform - API entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.db import Base, SessionLocal, engine
from app.core.scoping import ScenarioIsolationError
from app.domain import models  # noqa: F401 - registers the mappers
from app.modules.accounting.router import router as accounting_router
from app.modules.analytics.router import router as analytics_router
from app.modules.compliance.router import router as compliance_router
from app.modules.dashboards.router import router as dashboards_router
from app.modules.integrations.router import router as integrations_router
from app.modules.lca.router import router as lca_router
from app.modules.platform.router import router as platform_router
from app.modules.suppliers.router import router as suppliers_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    from app.seed import seed_if_empty
    with SessionLocal() as db:
        seed_if_empty(db)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "One environmental intelligence platform for audit-grade carbon accounting, "
        "product footprinting, supply-chain decarbonization, reduction planning and "
        "regulatory reporting (FR-1.1).\n\n"
        "Identify yourself with the `X-User-Email` header to exercise role-based views "
        "(FR-2, FR-7.1). Add `?scenario_id=` to any endpoint to work inside a what-if "
        "sandbox (FR-7.8)."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ScenarioIsolationError)
async def scenario_isolation_handler(_request: Request, exc: ScenarioIsolationError):
    return JSONResponse(status_code=409, content={"detail": str(exc),
                                                  "requirement": "FR-7.8"})


for router in (accounting_router, lca_router, suppliers_router, analytics_router,
               dashboards_router, compliance_router, integrations_router,
               platform_router):
    app.include_router(router, prefix="/api")


@app.get("/api/health", tags=["Platform"])
def health():
    return {"status": "ok", "platform": settings.app_name, "version": settings.version}


@app.get("/api/requirements/coverage", tags=["Platform"])
def coverage():
    """Which module owns which requirement - the traceability map, live."""
    return {
        "FR-1.1": "Whole platform",
        "FR-2.1/2.2/2.3": "core/rbac.py + /api/platform/roles",
        "FR-3.A.1": "/api/accounting/scope1/summary",
        "FR-3.A.2": "/api/accounting/scope2/summary + /api/accounting/grid-factors/countries",
        "FR-3.A.3": "/api/accounting/scope3/summary",
        "FR-3.A.4": "engine/calculator.py + /api/accounting/calculations/run",
        "FR-3.A.5": "/api/accounting/entities/tree + /reporting-boundaries",
        "FR-3.B.1": "/api/lca/products/{id}/bom",
        "FR-3.B.2": "/api/lca/products/{id}/processes + /routes",
        "FR-3.B.3": "/api/lca/products/{id}/pcf/calculate",
        "FR-3.B.4": "/api/lca/pcf/{id}/iso14067-report + /certification-pack",
        "FR-3.B.5": "/api/lca/pcf/{id}/declaration + /exchange + /eco-design/compare",
        "FR-3.C.1": "/api/suppliers/campaigns",
        "FR-3.C.2": "/api/suppliers/submissions + /documents/extract",
        "FR-3.C.3": "/api/suppliers/scorecards",
        "FR-3.C.4": "/api/suppliers/network/map + /resilience-scenarios",
        "FR-3.C.5": "/api/suppliers/procurement/decisions + /category-strategy",
        "FR-3.D.1": "/api/analytics/spend/categorize, /anomalies, /gaps, /forecast",
        "FR-3.D.2": "/api/analytics/scenarios/{id}/run, /monte-carlo, /pathways/sbti",
        "FR-3.D.3": "/api/analytics/hotspots/pareto, /macc, /roadmap, /progress",
        "FR-3.D.4": "/api/analytics/data-quality/scores + /calculation-versions",
        "FR-3.E.1": "/api/dashboards/scorecard/executive",
        "FR-3.E.2": "/api/dashboards/drilldown",
        "FR-3.E.3": "/api/dashboards/carbon-budgets, /credits, /project-economics",
        "FR-4.1": "/api/compliance/csrd/*",
        "FR-4.2": "/api/compliance/cbam/*",
        "FR-4.3": "/api/compliance/tcfd/*",
        "FR-4.4": "/api/compliance/taxonomy/*",
        "FR-4.5": "/api/compliance/sec/* + /cdp/*",
        "FR-5.1/5.2/5.3": "/api/integrations/catalog + /connectors",
        "FR-5.4": "/api/integrations/imports + /webhooks + /api/lca/pcf/{id}/exchange",
        "FR-5.5": "/api/integrations/sync-status + /transaction-logs",
        "FR-6": "domain/models.py - the 40 core data objects",
        "FR-7.1": "core/rbac.py + core/scoping.py + /api/platform/access-check",
        "FR-7.2": "engine/lineage.py + /api/accounting/calculations/{id}/lineage",
        "FR-7.3": "engine/recalc.py + /api/accounting/recalculation/*",
        "FR-7.4": "/api/analytics/data-quality/*",
        "FR-7.5": "/api/platform/search + /saved-views",
        "FR-7.6": "/api/platform/notifications + /approvals",
        "FR-7.7": "/api/platform/bulk/jobs + /exports/{dataset}",
        "FR-7.8": "core/scoping.py ScenarioContext + /api/analytics/scenarios",
    }
