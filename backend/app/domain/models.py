"""The 40 Core Data Objects of FR-6, plus the supporting tables the
key functional requirements (FR-7) demand.

Naming rule: table and class names use the platform vocabulary exactly as the
requirements document writes it. No synonyms.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ScenarioMixin:
    """FR-7.8 - scenario isolation.

    scenario_id IS NULL means *approved actual*. Anything non-null is a sandbox
    copy. The repository guard in app/core/scoping.py makes it structurally
    impossible for a scenario-context write to land on NULL.
    """
    scenario_id: Mapped[int | None] = mapped_column(
        ForeignKey("scenario.id", ondelete="CASCADE"), nullable=True, index=True
    )


# ---------------------------------------------------------------------------
# Access & identity (FR-2, FR-7.1)
# ---------------------------------------------------------------------------

class Role(Base, TimestampMixin):
    __tablename__ = "role"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    group: Mapped[str] = mapped_column(String(32))          # RoleGroup
    description: Mapped[str] = mapped_column(Text, default="")
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    landing_route: Mapped[str] = mapped_column(String(128), default="/")


class User(Base, TimestampMixin):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    full_name: Mapped[str] = mapped_column(String(160))
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"))
    language: Mapped[str] = mapped_column(String(8), default="en")
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("supplier.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[Role] = relationship(lazy="joined")


class UserScope(Base, TimestampMixin):
    """FR-7.1 - the permitted set. Absence of a row means no access."""
    __tablename__ = "user_scope"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    object_type: Mapped[str] = mapped_column(String(48))   # organization|entity|facility|supplier|product
    object_id: Mapped[int] = mapped_column(Integer)


# ---------------------------------------------------------------------------
# 1-6  Organization model (FR-3.A.5)
# ---------------------------------------------------------------------------

class Organization(Base, TimestampMixin):
    __tablename__ = "organization"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    tenant_key: Mapped[str] = mapped_column(String(64), unique=True)
    industry: Mapped[str] = mapped_column(String(96), default="")
    country: Mapped[str] = mapped_column(String(2), default="")
    reporting_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    fiscal_year_start_month: Mapped[int] = mapped_column(Integer, default=1)
    entities: Mapped[list["Entity"]] = relationship(back_populates="organization")


class Entity(Base, TimestampMixin):
    """Legal/reporting entity. Self-referencing for group structure."""
    __tablename__ = "entity"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("entity.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(48))
    country: Mapped[str] = mapped_column(String(2), default="")
    # FR-3.A.5 ownership controls
    ownership_pct: Mapped[float] = mapped_column(Float, default=100.0)
    consolidation_method: Mapped[str] = mapped_column(String(32), default="operational_control")
    is_consolidated: Mapped[bool] = mapped_column(Boolean, default=True)
    revenue: Mapped[float] = mapped_column(Float, default=0.0)
    employees: Mapped[int] = mapped_column(Integer, default=0)
    organization: Mapped[Organization] = relationship(back_populates="entities")
    facilities: Mapped[list["Facility"]] = relationship(back_populates="entity")


class Facility(Base, TimestampMixin):
    __tablename__ = "facility"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(48))
    facility_type: Mapped[str] = mapped_column(String(64), default="plant")
    country: Mapped[str] = mapped_column(String(2), default="")
    region: Mapped[str] = mapped_column(String(96), default="")
    grid_region: Mapped[str] = mapped_column(String(64), default="")
    latitude: Mapped[float] = mapped_column(Float, default=0.0)
    longitude: Mapped[float] = mapped_column(Float, default=0.0)
    floor_area_m2: Mapped[float] = mapped_column(Float, default=0.0)
    entity: Mapped[Entity] = relationship(back_populates="facilities")


class Department(Base, TimestampMixin):
    __tablename__ = "department"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("facility.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(48))
    headcount: Mapped[int] = mapped_column(Integer, default=0)


class CostCenter(Base, TimestampMixin):
    __tablename__ = "cost_center"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("department.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str] = mapped_column(String(48))
    budget: Mapped[float] = mapped_column(Float, default=0.0)


class ReportingBoundary(Base, TimestampMixin):
    """FR-3.A.5 - boundary + baseline year + consolidation rule."""
    __tablename__ = "reporting_boundary"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    consolidation_method: Mapped[str] = mapped_column(String(32), default="operational_control")
    baseline_year: Mapped[int] = mapped_column(Integer, default=2020)
    included_entity_ids: Mapped[list] = mapped_column(JSON, default=list)
    scopes_covered: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------------------------------------------------------------------
# 7-12  Activity, factors, calculation (FR-3.A.1 - .4)
# ---------------------------------------------------------------------------

class Source(Base, TimestampMixin):
    """An emission source: a boiler, a fleet, a purchased-goods category."""
    __tablename__ = "source"
    id: Mapped[int] = mapped_column(primary_key=True)
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("facility.id"), nullable=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    scope: Mapped[str] = mapped_column(String(16))
    source_type: Mapped[str] = mapped_column(String(64))   # Scope1Source or scope3 method
    category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id"), nullable=True)
    activity_key: Mapped[str] = mapped_column(String(96), default="")
    unit: Mapped[str] = mapped_column(String(24), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Category(Base, TimestampMixin):
    """GHG Protocol category. Scope 3 has all 15 (FR-3.A.3)."""
    __tablename__ = "category"
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(16))
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")


class FactorLibrary(Base, TimestampMixin):
    """FR-5.3 / FR-7.3 - controlled, versioned, lockable factor libraries."""
    __tablename__ = "factor_library"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(96))       # ecoinvent, GaBi, DEFRA, EPA, IEA
    version: Mapped[str] = mapped_column(String(48))
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (UniqueConstraint("provider", "version", name="uq_library_version"),)


class EmissionFactor(Base, TimestampMixin):
    """FR-3.A.4 - factor selection is by activity + region + period + version."""
    __tablename__ = "emission_factor"
    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("factor_library.id"), index=True)
    activity_key: Mapped[str] = mapped_column(String(96), index=True)
    name: Mapped[str] = mapped_column(String(200))
    scope: Mapped[str] = mapped_column(String(16))
    country: Mapped[str] = mapped_column(String(8), default="GLOBAL")   # FR-3.A.2: 150+ countries
    region: Mapped[str] = mapped_column(String(64), default="")
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    unit: Mapped[str] = mapped_column(String(24))            # denominator, e.g. kWh, litre, kg, EUR
    value_kgco2e: Mapped[float] = mapped_column(Float)       # pre-aggregated CO2e per unit
    gas_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)   # {"CO2":..,"CH4":..,"N2O":..}
    method: Mapped[str] = mapped_column(String(48), default="location_based")
    uncertainty_pct: Mapped[float] = mapped_column(Float, default=10.0)
    # FR-3.D.4 factor confidence / FR-7.4 pedigree
    pedigree: Mapped[dict] = mapped_column(JSON, default=dict)
    source_reference: Mapped[str] = mapped_column(String(255), default="")
    library: Mapped[FactorLibrary] = relationship()


class ActivityData(Base, TimestampMixin, ScenarioMixin):
    """The raw quantity that everything is computed from."""
    __tablename__ = "activity_data"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("facility.id"), nullable=True, index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("department.id"), nullable=True)
    cost_center_id: Mapped[int | None] = mapped_column(ForeignKey("cost_center.id"), nullable=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("source.id"), nullable=True, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("supplier.id"), nullable=True, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("product.id"), nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id"), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(16), index=True)
    activity_key: Mapped[str] = mapped_column(String(96), index=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(24))
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date)
    data_origin: Mapped[str] = mapped_column(String(32), default="estimated")
    scope3_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scope2_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # FR-7.4 data quality
    is_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    completeness_pct: Mapped[float] = mapped_column(Float, default=100.0)
    evidence_status: Mapped[str] = mapped_column(String(32), default="missing")
    notes: Mapped[str] = mapped_column(Text, default="")
    external_ref: Mapped[str] = mapped_column(String(128), default="")
    connector_id: Mapped[int | None] = mapped_column(ForeignKey("connector.id"), nullable=True)


class MeterReading(Base, TimestampMixin):
    """FR-3.A.1 / .2 - meter, sensor and telematics capture."""
    __tablename__ = "meter_reading"
    id: Mapped[int] = mapped_column(primary_key=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facility.id"), index=True)
    meter_code: Mapped[str] = mapped_column(String(64), index=True)
    meter_type: Mapped[str] = mapped_column(String(48))     # electricity|gas|water|steam|fuel
    capture_method: Mapped[str] = mapped_column(String(32), default="meter")  # meter|sensor|telematics
    reading_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(24))
    is_cumulative: Mapped[bool] = mapped_column(Boolean, default=False)
    quality_flag: Mapped[str] = mapped_column(String(32), default="ok")
    activity_data_id: Mapped[int | None] = mapped_column(ForeignKey("activity_data.id"), nullable=True)


class Transaction(Base, TimestampMixin):
    """Spend record - the entry point for spend-based Scope 3 (FR-3.A.3, FR-3.D.1)."""
    __tablename__ = "transaction"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    cost_center_id: Mapped[int | None] = mapped_column(ForeignKey("cost_center.id"), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("supplier.id"), nullable=True, index=True)
    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String(255))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    gl_account: Mapped[str] = mapped_column(String(48), default="")
    source_system: Mapped[str] = mapped_column(String(48), default="")
    # FR-3.D.1 automated spend categorization
    category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id"), nullable=True)
    categorization_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    categorized_by: Mapped[str] = mapped_column(String(24), default="unclassified")  # ai|rule|human
    activity_data_id: Mapped[int | None] = mapped_column(ForeignKey("activity_data.id"), nullable=True)


class Calculation(Base, TimestampMixin, ScenarioMixin):
    """FR-3.A.4 + FR-7.2. Immutable once approved; every field of the lineage
    chain is physically stored on the row, not reconstructed."""
    __tablename__ = "calculation"
    id: Mapped[int] = mapped_column(primary_key=True)
    activity_data_id: Mapped[int] = mapped_column(ForeignKey("activity_data.id"), index=True)
    emission_factor_id: Mapped[int] = mapped_column(ForeignKey("emission_factor.id"))
    factor_library_id: Mapped[int] = mapped_column(ForeignKey("factor_library.id"))
    factor_library_version: Mapped[str] = mapped_column(String(48))
    method: Mapped[str] = mapped_column(String(64))
    method_version: Mapped[str] = mapped_column(String(48))
    gwp_set: Mapped[str] = mapped_column(String(16))
    # inputs as used
    input_quantity: Mapped[float] = mapped_column(Float)
    input_unit: Mapped[str] = mapped_column(String(24))
    normalized_quantity: Mapped[float] = mapped_column(Float)
    normalized_unit: Mapped[str] = mapped_column(String(24))
    unit_conversion_chain: Mapped[list] = mapped_column(JSON, default=list)
    factor_value: Mapped[float] = mapped_column(Float)
    # outputs
    gas_results_kg: Mapped[dict] = mapped_column(JSON, default=dict)
    co2e_kg: Mapped[float] = mapped_column(Float, index=True)
    allocation_basis: Mapped[str | None] = mapped_column(String(32), nullable=True)
    allocation_share: Mapped[float] = mapped_column(Float, default=1.0)
    consolidation_method: Mapped[str] = mapped_column(String(32), default="operational_control")
    ownership_share: Mapped[float] = mapped_column(Float, default=1.0)
    consolidated_co2e_kg: Mapped[float] = mapped_column(Float, default=0.0)
    # quality
    uncertainty_pct: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    data_quality_rating: Mapped[str] = mapped_column(String(16), default="unrated")
    # governance
    status: Mapped[str] = mapped_column(String(24), default="calculated", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("calculation.id"), nullable=True)
    restatement_reason: Mapped[str] = mapped_column(Text, default="")
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # FR-7.2 the human-readable audit trail
    formula: Mapped[str] = mapped_column(Text, default="")
    assumptions: Mapped[list] = mapped_column(JSON, default=list)
    lineage: Mapped[dict] = mapped_column(JSON, default=dict)
    activity_data: Mapped[ActivityData] = relationship()
    emission_factor: Mapped[EmissionFactor] = relationship()


class Allocation(Base, TimestampMixin):
    """FR-3.A.4 - splitting a calculation across entities/products/cost centers."""
    __tablename__ = "allocation"
    id: Mapped[int] = mapped_column(primary_key=True)
    calculation_id: Mapped[int] = mapped_column(ForeignKey("calculation.id", ondelete="CASCADE"), index=True)
    target_type: Mapped[str] = mapped_column(String(32))    # entity|facility|cost_center|product|functional_unit
    target_id: Mapped[int] = mapped_column(Integer)
    basis: Mapped[str] = mapped_column(String(32))
    basis_value: Mapped[float] = mapped_column(Float, default=0.0)
    share: Mapped[float] = mapped_column(Float)
    allocated_co2e_kg: Mapped[float] = mapped_column(Float)


class Emission(Base, TimestampMixin, ScenarioMixin):
    """Reporting-shaped result. One row per calculation, denormalized for
    dashboards and drill-down (FR-3.E.2)."""
    __tablename__ = "emission"
    id: Mapped[int] = mapped_column(primary_key=True)
    calculation_id: Mapped[int] = mapped_column(ForeignKey("calculation.id", ondelete="CASCADE"), index=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("facility.id"), nullable=True, index=True)
    cost_center_id: Mapped[int | None] = mapped_column(ForeignKey("cost_center.id"), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("supplier.id"), nullable=True, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("product.id"), nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id"), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(16), index=True)
    scope2_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country: Mapped[str] = mapped_column(String(8), default="")
    period_start: Mapped[date] = mapped_column(Date, index=True)
    period_end: Mapped[date] = mapped_column(Date)
    year: Mapped[int] = mapped_column(Integer, index=True)
    co2e_kg: Mapped[float] = mapped_column(Float)
    data_quality_rating: Mapped[str] = mapped_column(String(16), default="unrated")
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(24), default="calculated", index=True)


# ---------------------------------------------------------------------------
# 13-20  Targets & performance (FR-3.E.1)
# ---------------------------------------------------------------------------

class Baseline(Base, TimestampMixin):
    __tablename__ = "baseline"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    scope: Mapped[str] = mapped_column(String(16))
    co2e_tonnes: Mapped[float] = mapped_column(Float)
    is_recalculated: Mapped[bool] = mapped_column(Boolean, default=False)
    recalculation_reason: Mapped[str] = mapped_column(Text, default="")
    locked: Mapped[bool] = mapped_column(Boolean, default=False)


class Target(Base, TimestampMixin):
    __tablename__ = "target"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    target_type: Mapped[str] = mapped_column(String(24))
    scopes_covered: Mapped[list] = mapped_column(JSON, default=list)
    base_year: Mapped[int] = mapped_column(Integer)
    base_value: Mapped[float] = mapped_column(Float)
    target_year: Mapped[int] = mapped_column(Integer)
    reduction_pct: Mapped[float] = mapped_column(Float)
    intensity_denominator: Mapped[str] = mapped_column(String(48), default="")
    sbti_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    sbti_ambition: Mapped[str] = mapped_column(String(24), default="1.5C")
    trajectory: Mapped[list] = mapped_column(JSON, default=list)   # [{year, allowed_tco2e}]


class Intensity(Base, TimestampMixin):
    __tablename__ = "intensity"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    metric: Mapped[str] = mapped_column(String(64))      # per_revenue|per_employee|per_unit|per_m2
    numerator_tco2e: Mapped[float] = mapped_column(Float)
    denominator_value: Mapped[float] = mapped_column(Float)
    denominator_unit: Mapped[str] = mapped_column(String(32))
    value: Mapped[float] = mapped_column(Float)


class ReductionInitiative(Base, TimestampMixin, ScenarioMixin):
    """FR-3.D.3 / FR-3.E.3 - levers with abatement, cost, ROI."""
    __tablename__ = "reduction_initiative"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("facility.id"), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("supplier.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    lever_category: Mapped[str] = mapped_column(String(64))
    scope: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="proposed")
    start_year: Mapped[int] = mapped_column(Integer, default=2025)
    end_year: Mapped[int] = mapped_column(Integer, default=2030)
    capex: Mapped[float] = mapped_column(Float, default=0.0)
    annual_opex_delta: Mapped[float] = mapped_column(Float, default=0.0)
    annual_abatement_tco2e: Mapped[float] = mapped_column(Float, default=0.0)
    lifetime_years: Mapped[int] = mapped_column(Integer, default=10)
    marginal_abatement_cost: Mapped[float] = mapped_column(Float, default=0.0)   # EUR/tCO2e
    roi_pct: Mapped[float] = mapped_column(Float, default=0.0)
    payback_years: Mapped[float] = mapped_column(Float, default=0.0)
    investment_priority: Mapped[int] = mapped_column(Integer, default=0)
    technology_readiness: Mapped[str] = mapped_column(String(32), default="mature")
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    realized_abatement_tco2e: Mapped[float] = mapped_column(Float, default=0.0)


# ---------------------------------------------------------------------------
# 21-28  Product LCA & PCF (FR-3.B)
# ---------------------------------------------------------------------------

class FunctionalUnit(Base, TimestampMixin):
    __tablename__ = "functional_unit"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    unit: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    description: Mapped[str] = mapped_column(Text, default="")


class Material(Base, TimestampMixin):
    __tablename__ = "material"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    material_class: Mapped[str] = mapped_column(String(96), default="")
    activity_key: Mapped[str] = mapped_column(String(96), default="")
    density_kg_m3: Mapped[float] = mapped_column(Float, default=0.0)
    recycled_content_pct: Mapped[float] = mapped_column(Float, default=0.0)
    recyclable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_alternative: Mapped[bool] = mapped_column(Boolean, default=False)
    hazardous: Mapped[bool] = mapped_column(Boolean, default=False)


class Product(Base, TimestampMixin):
    """Product/SKU (FR-3.B.5)."""
    __tablename__ = "product"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    sku: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(96), default="")
    functional_unit_id: Mapped[int | None] = mapped_column(ForeignKey("functional_unit.id"), nullable=True)
    mass_kg: Mapped[float] = mapped_column(Float, default=0.0)
    annual_volume: Mapped[float] = mapped_column(Float, default=0.0)
    lifetime_years: Mapped[float] = mapped_column(Float, default=5.0)
    plm_ref: Mapped[str] = mapped_column(String(96), default="")
    erp_ref: Mapped[str] = mapped_column(String(96), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class BOM(Base, TimestampMixin):
    """Bill of materials header - versioned per product."""
    __tablename__ = "bom"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), index=True)
    version: Mapped[str] = mapped_column(String(32), default="1.0")
    source_system: Mapped[str] = mapped_column(String(48), default="PLM")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    items: Mapped[list["BOMItem"]] = relationship(back_populates="bom", cascade="all, delete-orphan")


class BOMItem(Base, TimestampMixin):
    """FR-3.B.1 - multi-level BOM via parent_item_id; alternative materials via
    alternative_for_id."""
    __tablename__ = "bom_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    bom_id: Mapped[int] = mapped_column(ForeignKey("bom.id", ondelete="CASCADE"), index=True)
    parent_item_id: Mapped[int | None] = mapped_column(ForeignKey("bom_item.id"), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    component_name: Mapped[str] = mapped_column(String(200))
    material_id: Mapped[int | None] = mapped_column(ForeignKey("material.id"), nullable=True)
    component_supplier_id: Mapped[int | None] = mapped_column(ForeignKey("supplier.id"), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    unit: Mapped[str] = mapped_column(String(24), default="kg")
    mass_kg: Mapped[float] = mapped_column(Float, default=0.0)
    scrap_pct: Mapped[float] = mapped_column(Float, default=0.0)
    alternative_for_id: Mapped[int | None] = mapped_column(ForeignKey("bom_item.id"), nullable=True)
    is_alternative: Mapped[bool] = mapped_column(Boolean, default=False)
    bom: Mapped[BOM] = relationship(back_populates="items", foreign_keys=[bom_id])


class Process(Base, TimestampMixin):
    """FR-3.B.2 - manufacturing process step."""
    __tablename__ = "process"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), index=True)
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("facility.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    production_mode: Mapped[str] = mapped_column(String(24), default="batch")
    energy_kwh_per_unit: Mapped[float] = mapped_column(Float, default=0.0)
    thermal_mj_per_unit: Mapped[float] = mapped_column(Float, default=0.0)
    direct_emissions_kgco2e: Mapped[float] = mapped_column(Float, default=0.0)
    scrap_rate_pct: Mapped[float] = mapped_column(Float, default=0.0)
    defect_rate_pct: Mapped[float] = mapped_column(Float, default=0.0)
    yield_pct: Mapped[float] = mapped_column(Float, default=100.0)
    batch_size: Mapped[float] = mapped_column(Float, default=1.0)


class Route(Base, TimestampMixin):
    """FR-3.B.2 - a multimodal logistics leg."""
    __tablename__ = "route"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("product.id"), nullable=True, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("supplier.id"), nullable=True)
    leg_sequence: Mapped[int] = mapped_column(Integer, default=1)
    stage: Mapped[str] = mapped_column(String(32), default="inbound")  # inbound|internal|outbound
    mode: Mapped[str] = mapped_column(String(24), default="road")
    origin: Mapped[str] = mapped_column(String(128), default="")
    destination: Mapped[str] = mapped_column(String(128), default="")
    distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    payload_tonnes: Mapped[float] = mapped_column(Float, default=0.0)
    load_factor_pct: Mapped[float] = mapped_column(Float, default=80.0)
    warehouse_days: Mapped[float] = mapped_column(Float, default=0.0)


class Packaging(Base, TimestampMixin):
    __tablename__ = "packaging"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), index=True)
    level: Mapped[str] = mapped_column(String(24), default="primary")  # primary|secondary|tertiary
    material_id: Mapped[int | None] = mapped_column(ForeignKey("material.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(160))
    mass_kg: Mapped[float] = mapped_column(Float, default=0.0)
    recycled_content_pct: Mapped[float] = mapped_column(Float, default=0.0)
    recyclable: Mapped[bool] = mapped_column(Boolean, default=True)
    reuse_cycles: Mapped[int] = mapped_column(Integer, default=0)


class PCF(Base, TimestampMixin, ScenarioMixin):
    """Product Carbon Footprint / LCA result (FR-3.B.3 - .5)."""
    __tablename__ = "pcf"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id"), index=True)
    functional_unit_id: Mapped[int | None] = mapped_column(ForeignKey("functional_unit.id"), nullable=True)
    boundary: Mapped[str] = mapped_column(String(32), default="cradle_to_gate")
    allocation_basis: Mapped[str] = mapped_column(String(32), default="mass")
    reference_period: Mapped[int] = mapped_column(Integer, default=2025)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    total_kgco2e: Mapped[float] = mapped_column(Float, default=0.0)
    per_functional_unit_kgco2e: Mapped[float] = mapped_column(Float, default=0.0)
    stage_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    biogenic_kgco2e: Mapped[float] = mapped_column(Float, default=0.0)
    # FR-3.B.3 circularity
    recycled_content_pct: Mapped[float] = mapped_column(Float, default=0.0)
    recyclability_pct: Mapped[float] = mapped_column(Float, default=0.0)
    end_of_life_scenario: Mapped[str] = mapped_column(String(48), default="mixed")
    circularity_score: Mapped[float] = mapped_column(Float, default=0.0)
    # FR-3.B.4 reporting rigour
    assumptions: Mapped[list] = mapped_column(JSON, default=list)
    uncertainty_pct: Mapped[float] = mapped_column(Float, default=0.0)
    sensitivity: Mapped[list] = mapped_column(JSON, default=list)
    iso14067_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    peer_reviewer: Mapped[str] = mapped_column(String(160), default="")
    peer_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verifier: Mapped[str] = mapped_column(String(160), default="")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    certification_ref: Mapped[str] = mapped_column(String(128), default="")
    # FR-3.B.5 declarations
    label_claim: Mapped[str] = mapped_column(String(255), default="")
    qr_payload: Mapped[str] = mapped_column(Text, default="")
    lineage: Mapped[dict] = mapped_column(JSON, default=dict)
    product: Mapped[Product] = relationship()


# ---------------------------------------------------------------------------
# 29-34  Supplier engagement (FR-3.C)
# ---------------------------------------------------------------------------

class Supplier(Base, TimestampMixin):
    __tablename__ = "supplier"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    parent_supplier_id: Mapped[int | None] = mapped_column(ForeignKey("supplier.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(64))
    tier: Mapped[int] = mapped_column(Integer, default=1)     # FR-3.C.4 multi-tier
    category: Mapped[str] = mapped_column(String(96), default="")
    country: Mapped[str] = mapped_column(String(2), default="")
    latitude: Mapped[float] = mapped_column(Float, default=0.0)
    longitude: Mapped[float] = mapped_column(Float, default=0.0)
    annual_spend: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    language: Mapped[str] = mapped_column(String(8), default="en")
    contact_email: Mapped[str] = mapped_column(String(255), default="")
    contact_name: Mapped[str] = mapped_column(String(160), default="")
    onboarding_status: Mapped[str] = mapped_column(String(32), default="not_invited")
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    has_data_agreement: Mapped[bool] = mapped_column(Boolean, default=False)
    contract_clauses: Mapped[list] = mapped_column(JSON, default=list)
    risk_rating: Mapped[str] = mapped_column(String(24), default="medium")


class Questionnaire(Base, TimestampMixin):
    """FR-3.C.1 - materiality-based, multi-language."""
    __tablename__ = "questionnaire"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    framework: Mapped[str] = mapped_column(String(48), default="internal")
    materiality_level: Mapped[str] = mapped_column(String(24), default="standard")  # light|standard|deep
    target_categories: Mapped[list] = mapped_column(JSON, default=list)
    languages: Mapped[list] = mapped_column(JSON, default=list)
    questions: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[str] = mapped_column(String(24), default="1.0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Campaign(Base, TimestampMixin):
    """FR-3.C.1 / FR-7.7 - a bulk supplier engagement run."""
    __tablename__ = "campaign"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    questionnaire_id: Mapped[int] = mapped_column(ForeignKey("questionnaire.id"))
    name: Mapped[str] = mapped_column(String(200))
    reporting_year: Mapped[int] = mapped_column(Integer, default=2025)
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    reminder_cadence_days: Mapped[int] = mapped_column(Integer, default=7)
    invited_count: Mapped[int] = mapped_column(Integer, default=0)
    responded_count: Mapped[int] = mapped_column(Integer, default=0)


class SupplierInvitation(Base, TimestampMixin):
    __tablename__ = "supplier_invitation"
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaign.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier.id"), index=True)
    language: Mapped[str] = mapped_column(String(8), default="en")
    status: Mapped[str] = mapped_column(String(32), default="not_started")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reminders_sent: Mapped[int] = mapped_column(Integer, default=0)
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    access_token: Mapped[str] = mapped_column(String(64), default="")


class Submission(Base, TimestampMixin):
    """FR-3.C.2 - primary data from the supplier, with attestation."""
    __tablename__ = "submission"
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaign.id"), nullable=True, index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier.id"), index=True)
    questionnaire_id: Mapped[int] = mapped_column(ForeignKey("questionnaire.id"))
    reporting_year: Mapped[int] = mapped_column(Integer, default=2025)
    status: Mapped[str] = mapped_column(String(32), default="not_started")
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    capture_channel: Mapped[str] = mapped_column(String(24), default="form")  # form|ocr|api|mobile
    validation_errors: Mapped[list] = mapped_column(JSON, default=list)
    completeness_pct: Mapped[float] = mapped_column(Float, default=0.0)
    attested: Mapped[bool] = mapped_column(Boolean, default=False)
    attested_by: Mapped[str] = mapped_column(String(160), default="")
    attested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    review_notes: Mapped[str] = mapped_column(Text, default="")


class Evidence(Base, TimestampMixin):
    """FR-3.C.2 / FR-4.5 / FR-7.4 - the evidence library."""
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    object_type: Mapped[str] = mapped_column(String(48), index=True)
    object_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(200))
    evidence_type: Mapped[str] = mapped_column(String(48), default="document")
    filename: Mapped[str] = mapped_column(String(255), default="")
    mime_type: Mapped[str] = mapped_column(String(96), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="uploaded")
    ocr_text: Mapped[str] = mapped_column(Text, default="")
    extracted_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)


class Scorecard(Base, TimestampMixin):
    """FR-3.C.3"""
    __tablename__ = "scorecard"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier.id"), index=True)
    period_year: Mapped[int] = mapped_column(Integer, index=True)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    disclosure_score: Mapped[float] = mapped_column(Float, default=0.0)
    performance_score: Mapped[float] = mapped_column(Float, default=0.0)
    data_quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    target_score: Mapped[float] = mapped_column(Float, default=0.0)
    maturity_level: Mapped[str] = mapped_column(String(32), default="beginner")
    rank: Mapped[int] = mapped_column(Integer, default=0)
    category_rank: Mapped[int] = mapped_column(Integer, default=0)
    yoy_delta: Mapped[float] = mapped_column(Float, default=0.0)
    emissions_tco2e: Mapped[float] = mapped_column(Float, default=0.0)
    emission_intensity: Mapped[float] = mapped_column(Float, default=0.0)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class ActionPlan(Base, TimestampMixin):
    """FR-3.C.3 / FR-7.4 - improvement plans and remediation tasks."""
    __tablename__ = "action_plan"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("supplier.id"), nullable=True, index=True)
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("entity.id"), nullable=True)
    object_type: Mapped[str] = mapped_column(String(48), default="supplier")
    object_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plan_type: Mapped[str] = mapped_column(String(48), default="improvement")  # improvement|remediation|joint_project
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(160), default="")
    assistance_offered: Mapped[str] = mapped_column(String(200), default="")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open")
    priority: Mapped[str] = mapped_column(String(24), default="medium")
    expected_abatement_tco2e: Mapped[float] = mapped_column(Float, default=0.0)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)


# ---------------------------------------------------------------------------
# 35-40  Compliance & carbon finance (FR-4, FR-3.E.3)
# ---------------------------------------------------------------------------

class Framework(Base, TimestampMixin):
    __tablename__ = "framework"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    regulator: Mapped[str] = mapped_column(String(128), default="")
    jurisdiction: Mapped[str] = mapped_column(String(96), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Disclosure(Base, TimestampMixin):
    __tablename__ = "disclosure"
    id: Mapped[int] = mapped_column(primary_key=True)
    framework_id: Mapped[int] = mapped_column(ForeignKey("framework.id"), index=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    reporting_year: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(24), default="draft")
    completeness_pct: Mapped[float] = mapped_column(Float, default=0.0)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assurance_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    xbrl_document: Mapped[str] = mapped_column(Text, default="")
    narrative: Mapped[str] = mapped_column(Text, default="")


class DataPoint(Base, TimestampMixin):
    """FR-4.1 - the atomic disclosure element, verified and XBRL-tagged."""
    __tablename__ = "data_point"
    id: Mapped[int] = mapped_column(primary_key=True)
    disclosure_id: Mapped[int] = mapped_column(ForeignKey("disclosure.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(64), index=True)     # e.g. ESRS E1-6
    label: Mapped[str] = mapped_column(String(255))
    value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(String(32), default="")
    xbrl_tag: Mapped[str] = mapped_column(String(160), default="")
    source_calculation_ids: Mapped[list] = mapped_column(JSON, default=list)
    verification_status: Mapped[str] = mapped_column(String(32), default="unverified")
    verified_by: Mapped[str] = mapped_column(String(160), default="")
    is_material: Mapped[bool] = mapped_column(Boolean, default=True)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")


class Report(Base, TimestampMixin):
    """FR-7.7 - generated and scheduled outputs."""
    __tablename__ = "report"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    report_type: Mapped[str] = mapped_column(String(64))
    framework_id: Mapped[int | None] = mapped_column(ForeignKey("framework.id"), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("entity.id"), nullable=True)
    reporting_year: Mapped[int] = mapped_column(Integer, default=2025)
    format: Mapped[str] = mapped_column(String(16), default="json")
    status: Mapped[str] = mapped_column(String(24), default="draft")
    is_scheduled: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule_cron: Mapped[str] = mapped_column(String(64), default="")
    last_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    recipients: Mapped[list] = mapped_column(JSON, default=list)


class AssuranceRequest(Base, TimestampMixin):
    """FR-4.1 / FR-4.5 - external verification workflow."""
    __tablename__ = "assurance_request"
    id: Mapped[int] = mapped_column(primary_key=True)
    disclosure_id: Mapped[int | None] = mapped_column(ForeignKey("disclosure.id"), nullable=True, index=True)
    pcf_id: Mapped[int | None] = mapped_column(ForeignKey("pcf.id"), nullable=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    assurer: Mapped[str] = mapped_column(String(160))
    assurance_level: Mapped[str] = mapped_column(String(32), default="limited")  # limited|reasonable
    scope_description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="requested")
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    findings: Mapped[list] = mapped_column(JSON, default=list)
    evidence_pack_ref: Mapped[str] = mapped_column(String(200), default="")


class CreditOffset(Base, TimestampMixin):
    """FR-3.E.3 - credit/offset registry with retirement evidence."""
    __tablename__ = "credit_offset"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    project_name: Mapped[str] = mapped_column(String(200))
    registry: Mapped[str] = mapped_column(String(96))      # Verra, Gold Standard, ...
    serial_number: Mapped[str] = mapped_column(String(128), default="")
    project_type: Mapped[str] = mapped_column(String(96), default="")
    country: Mapped[str] = mapped_column(String(2), default="")
    vintage_year: Mapped[int] = mapped_column(Integer)
    quantity_tco2e: Mapped[float] = mapped_column(Float)
    price_per_tonne: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    status: Mapped[str] = mapped_column(String(24), default="held")
    retired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retirement_evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidence.id"), nullable=True)
    retirement_reason: Mapped[str] = mapped_column(String(200), default="")
    is_removal: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------------------------------------------------------------------
# Compliance specifics (FR-4.1 - .5)
# ---------------------------------------------------------------------------

class MaterialityAssessment(Base, TimestampMixin):
    """FR-4.1 - CSRD double materiality."""
    __tablename__ = "materiality_assessment"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    reporting_year: Mapped[int] = mapped_column(Integer)
    topic_code: Mapped[str] = mapped_column(String(48))
    topic: Mapped[str] = mapped_column(String(200))
    impact_score: Mapped[float] = mapped_column(Float, default=0.0)      # inside-out
    financial_score: Mapped[float] = mapped_column(Float, default=0.0)   # outside-in
    is_material: Mapped[bool] = mapped_column(Boolean, default=False)
    value_chain_stage: Mapped[str] = mapped_column(String(48), default="own_operations")
    rationale: Mapped[str] = mapped_column(Text, default="")
    stakeholders_consulted: Mapped[list] = mapped_column(JSON, default=list)


class TransitionPlan(Base, TimestampMixin):
    """FR-4.1 - CSRD transition plan."""
    __tablename__ = "transition_plan"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    target_year: Mapped[int] = mapped_column(Integer, default=2050)
    ambition: Mapped[str] = mapped_column(String(48), default="net_zero")
    capex_aligned_pct: Mapped[float] = mapped_column(Float, default=0.0)
    levers: Mapped[list] = mapped_column(JSON, default=list)
    milestones: Mapped[list] = mapped_column(JSON, default=list)
    narrative: Mapped[str] = mapped_column(Text, default="")


class CBAMDeclaration(Base, TimestampMixin):
    """FR-4.2 - imported goods, embedded emissions, certificates, payments."""
    __tablename__ = "cbam_declaration"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    reporting_year: Mapped[int] = mapped_column(Integer, index=True)
    quarter: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_embedded_tco2e: Mapped[float] = mapped_column(Float, default=0.0)
    certificates_required: Mapped[float] = mapped_column(Float, default=0.0)
    certificate_price: Mapped[float] = mapped_column(Float, default=0.0)
    payment_due: Mapped[float] = mapped_column(Float, default=0.0)
    payment_status: Mapped[str] = mapped_column(String(24), default="unpaid")
    adjustments: Mapped[list] = mapped_column(JSON, default=list)


class CBAMGood(Base, TimestampMixin):
    """FR-4.2 - imported-product mapping line."""
    __tablename__ = "cbam_good"
    id: Mapped[int] = mapped_column(primary_key=True)
    declaration_id: Mapped[int] = mapped_column(ForeignKey("cbam_declaration.id", ondelete="CASCADE"), index=True)
    cn_code: Mapped[str] = mapped_column(String(16))
    goods_category: Mapped[str] = mapped_column(String(96))
    description: Mapped[str] = mapped_column(String(200), default="")
    product_id: Mapped[int | None] = mapped_column(ForeignKey("product.id"), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("supplier.id"), nullable=True)
    origin_country: Mapped[str] = mapped_column(String(2), default="")
    quantity_tonnes: Mapped[float] = mapped_column(Float, default=0.0)
    direct_embedded_tco2e_per_t: Mapped[float] = mapped_column(Float, default=0.0)
    indirect_embedded_tco2e_per_t: Mapped[float] = mapped_column(Float, default=0.0)
    data_basis: Mapped[str] = mapped_column(String(16), default="default")   # default|actual
    supplier_request_status: Mapped[str] = mapped_column(String(32), default="not_requested")
    carbon_price_paid: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_id: Mapped[int | None] = mapped_column(ForeignKey("evidence.id"), nullable=True)


class ClimateRisk(Base, TimestampMixin):
    """FR-4.3 - TCFD risks/opportunities with financial impact."""
    __tablename__ = "climate_risk"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    risk_type: Mapped[str] = mapped_column(String(32))     # physical_acute|physical_chronic|transition_policy|...
    is_opportunity: Mapped[bool] = mapped_column(Boolean, default=False)
    horizon: Mapped[str] = mapped_column(String(24), default="medium")  # short|medium|long
    likelihood: Mapped[str] = mapped_column(String(24), default="possible")
    impact_rating: Mapped[str] = mapped_column(String(24), default="moderate")
    financial_impact_low: Mapped[float] = mapped_column(Float, default=0.0)
    financial_impact_high: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    scenario_ref: Mapped[str] = mapped_column(String(48), default="")
    mitigation: Mapped[str] = mapped_column(Text, default="")
    control: Mapped[str] = mapped_column(Text, default="")
    governance_owner: Mapped[str] = mapped_column(String(160), default="")


class ClimateScenario(Base, TimestampMixin):
    """FR-4.3 - TCFD scenario definitions (distinct from what-if Scenario)."""
    __tablename__ = "climate_scenario"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    pathway: Mapped[str] = mapped_column(String(48))       # 1.5C|2C|4C|NGFS-Orderly
    horizon_year: Mapped[int] = mapped_column(Integer, default=2050)
    carbon_price_assumption: Mapped[float] = mapped_column(Float, default=0.0)
    narrative: Mapped[str] = mapped_column(Text, default="")
    financial_impact: Mapped[dict] = mapped_column(JSON, default=dict)


class TaxonomyActivity(Base, TimestampMixin):
    """FR-4.4 - EU Taxonomy eligibility/alignment with DNSH and safeguards."""
    __tablename__ = "taxonomy_activity"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    reporting_year: Mapped[int] = mapped_column(Integer)
    activity_code: Mapped[str] = mapped_column(String(32))
    activity_name: Mapped[str] = mapped_column(String(200))
    objective: Mapped[str] = mapped_column(String(96), default="climate_mitigation")
    is_eligible: Mapped[bool] = mapped_column(Boolean, default=False)
    is_aligned: Mapped[bool] = mapped_column(Boolean, default=False)
    substantial_contribution_met: Mapped[bool] = mapped_column(Boolean, default=False)
    technical_criteria: Mapped[dict] = mapped_column(JSON, default=dict)
    dnsh_checks: Mapped[dict] = mapped_column(JSON, default=dict)
    minimum_safeguards_met: Mapped[bool] = mapped_column(Boolean, default=False)
    revenue_amount: Mapped[float] = mapped_column(Float, default=0.0)
    capex_amount: Mapped[float] = mapped_column(Float, default=0.0)
    opex_amount: Mapped[float] = mapped_column(Float, default=0.0)
    revenue_share_pct: Mapped[float] = mapped_column(Float, default=0.0)
    capex_share_pct: Mapped[float] = mapped_column(Float, default=0.0)
    opex_share_pct: Mapped[float] = mapped_column(Float, default=0.0)


class CDPResponse(Base, TimestampMixin):
    """FR-4.5 - CDP questionnaire response history and benchmarks."""
    __tablename__ = "cdp_response"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    reporting_year: Mapped[int] = mapped_column(Integer, index=True)
    question_code: Mapped[str] = mapped_column(String(48))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default="")
    module: Mapped[str] = mapped_column(String(96), default="")
    status: Mapped[str] = mapped_column(String(24), default="draft")
    score: Mapped[str] = mapped_column(String(8), default="")
    peer_benchmark_score: Mapped[str] = mapped_column(String(8), default="")
    reviewer: Mapped[str] = mapped_column(String(160), default="")
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)


class Benchmark(Base, TimestampMixin):
    """FR-3.E.1 / FR-4.5 - peer benchmarks."""
    __tablename__ = "benchmark"
    id: Mapped[int] = mapped_column(primary_key=True)
    industry: Mapped[str] = mapped_column(String(96))
    metric: Mapped[str] = mapped_column(String(96))
    year: Mapped[int] = mapped_column(Integer)
    peer_median: Mapped[float] = mapped_column(Float)
    peer_best: Mapped[float] = mapped_column(Float)
    peer_worst: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32), default="")
    source: Mapped[str] = mapped_column(String(128), default="")


# ---------------------------------------------------------------------------
# Carbon finance (FR-3.E.3)
# ---------------------------------------------------------------------------

class CarbonBudget(Base, TimestampMixin):
    __tablename__ = "carbon_budget"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    scope: Mapped[str] = mapped_column(String(16), default="all")
    budget_tco2e: Mapped[float] = mapped_column(Float)
    consumed_tco2e: Mapped[float] = mapped_column(Float, default=0.0)
    owner: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(24), default="on_track")


class InternalCarbonPrice(Base, TimestampMixin):
    __tablename__ = "internal_carbon_price"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    price_type: Mapped[str] = mapped_column(String(32), default="shadow")  # shadow|fee|implicit
    price_per_tonne: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    effective_from: Mapped[date] = mapped_column(Date)
    scopes_covered: Mapped[list] = mapped_column(JSON, default=list)
    applies_to: Mapped[str] = mapped_column(String(96), default="capex_decisions")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------------------
# Integrations (FR-5)
# ---------------------------------------------------------------------------

class Connector(Base, TimestampMixin):
    __tablename__ = "connector"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    system: Mapped[str] = mapped_column(String(96))       # SAP|Oracle|Dynamics|NetSuite|...
    category: Mapped[str] = mapped_column(String(24))     # ConnectorCategory
    protocol: Mapped[str] = mapped_column(String(32), default="rest")  # rest|graphql|webhook|batch|streaming|sftp
    data_format: Mapped[str] = mapped_column(String(16), default="json")  # json|xml|csv
    endpoint: Mapped[str] = mapped_column(String(255), default="")
    credential_ref: Mapped[str] = mapped_column(String(128), default="")
    credential_status: Mapped[str] = mapped_column(String(24), default="not_configured")
    schedule_cron: Mapped[str] = mapped_column(String(64), default="0 2 * * *")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(24), default="never_run")
    health_score: Mapped[float] = mapped_column(Float, default=100.0)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    records_synced: Mapped[int] = mapped_column(Integer, default=0)
    factor_library_id: Mapped[int | None] = mapped_column(ForeignKey("factor_library.id"), nullable=True)
    data_version: Mapped[str] = mapped_column(String(48), default="")


class FieldMapping(Base, TimestampMixin):
    """FR-5.4 - schema mapping."""
    __tablename__ = "field_mapping"
    id: Mapped[int] = mapped_column(primary_key=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connector.id", ondelete="CASCADE"), index=True)
    source_field: Mapped[str] = mapped_column(String(128))
    target_object: Mapped[str] = mapped_column(String(64))
    target_field: Mapped[str] = mapped_column(String(128))
    transform: Mapped[str] = mapped_column(String(128), default="")
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
    default_value: Mapped[str] = mapped_column(String(128), default="")


class SyncRun(Base, TimestampMixin):
    """FR-5.5 - sync status, retries, transaction logs."""
    __tablename__ = "sync_run"
    id: Mapped[int] = mapped_column(primary_key=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connector.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="running")
    records_read: Mapped[int] = mapped_column(Integer, default=0)
    records_written: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    reconciliation_delta: Mapped[float] = mapped_column(Float, default=0.0)
    log: Mapped[list] = mapped_column(JSON, default=list)


class ImportBatch(Base, TimestampMixin):
    """FR-5.4 / FR-7.7 - import validation and error queues."""
    __tablename__ = "import_batch"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    connector_id: Mapped[int | None] = mapped_column(ForeignKey("connector.id"), nullable=True)
    import_type: Mapped[str] = mapped_column(String(48))    # activity_data|emission_factor|supplier|transaction|bom
    filename: Mapped[str] = mapped_column(String(255), default="")
    format: Mapped[str] = mapped_column(String(16), default="csv")
    status: Mapped[str] = mapped_column(String(24), default="queued")
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_valid: Mapped[int] = mapped_column(Integer, default=0)
    rows_invalid: Mapped[int] = mapped_column(Integer, default=0)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)


class Webhook(Base, TimestampMixin):
    """FR-5.4"""
    __tablename__ = "webhook"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    target_url: Mapped[str] = mapped_column(String(255))
    event_types: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    secret_ref: Mapped[str] = mapped_column(String(96), default="")
    last_delivery_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------------------
# Platform services (FR-7)
# ---------------------------------------------------------------------------

class Scenario(Base, TimestampMixin):
    """FR-7.8 - the sandbox address space."""
    __tablename__ = "scenario"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    scenario_type: Mapped[str] = mapped_column(String(32), default="what_if")  # what_if|forecast|pathway
    base_year: Mapped[int] = mapped_column(Integer, default=2025)
    horizon_year: Mapped[int] = mapped_column(Integer, default=2030)
    description: Mapped[str] = mapped_column(Text, default="")
    assumptions: Mapped[dict] = mapped_column(JSON, default=dict)
    selected_lever_ids: Mapped[list] = mapped_column(JSON, default=list)
    internal_carbon_price: Mapped[float] = mapped_column(Float, default=0.0)
    method_version: Mapped[str] = mapped_column(String(48), default="")
    factor_library_version: Mapped[str] = mapped_column(String(48), default="")
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    uncertainty: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)


class DataQualityAssessment(Base, TimestampMixin):
    """FR-7.4 / FR-3.D.4"""
    __tablename__ = "data_quality_assessment"
    id: Mapped[int] = mapped_column(primary_key=True)
    object_type: Mapped[str] = mapped_column(String(48), index=True)
    object_id: Mapped[int] = mapped_column(Integer, index=True)
    entity_id: Mapped[int | None] = mapped_column(ForeignKey("entity.id"), nullable=True, index=True)
    scope: Mapped[str | None] = mapped_column(String(16), nullable=True)
    period_year: Mapped[int] = mapped_column(Integer, index=True)
    completeness_pct: Mapped[float] = mapped_column(Float, default=0.0)
    validation_passed: Mapped[bool] = mapped_column(Boolean, default=True)
    validation_messages: Mapped[list] = mapped_column(JSON, default=list)
    anomaly_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    anomaly_reason: Mapped[str] = mapped_column(String(255), default="")
    is_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    gap_filled: Mapped[bool] = mapped_column(Boolean, default=False)
    uncertainty_pct: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    factor_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    rating: Mapped[str] = mapped_column(String(16), default="unrated")
    evidence_status: Mapped[str] = mapped_column(String(32), default="missing")
    remediation_action_id: Mapped[int | None] = mapped_column(ForeignKey("action_plan.id"), nullable=True)


class Anomaly(Base, TimestampMixin):
    """FR-3.D.1"""
    __tablename__ = "anomaly"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    object_type: Mapped[str] = mapped_column(String(48))
    object_id: Mapped[int] = mapped_column(Integer)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    anomaly_type: Mapped[str] = mapped_column(String(48))   # spike|drop|outlier|duplicate|unit_mismatch
    severity: Mapped[str] = mapped_column(String(24), default="medium")
    observed_value: Mapped[float] = mapped_column(Float, default=0.0)
    expected_value: Mapped[float] = mapped_column(Float, default=0.0)
    deviation_pct: Mapped[float] = mapped_column(Float, default=0.0)
    z_score: Mapped[float] = mapped_column(Float, default=0.0)
    explanation: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="open")


class DataGap(Base, TimestampMixin):
    """FR-3.D.1 / FR-7.4 - gap identification and gap filling."""
    __tablename__ = "data_gap"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entity.id"), index=True)
    facility_id: Mapped[int | None] = mapped_column(ForeignKey("facility.id"), nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("supplier.id"), nullable=True)
    scope: Mapped[str] = mapped_column(String(16))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id"), nullable=True)
    period_year: Mapped[int] = mapped_column(Integer, index=True)
    period_label: Mapped[str] = mapped_column(String(32), default="")
    gap_type: Mapped[str] = mapped_column(String(48), default="missing_activity")
    description: Mapped[str] = mapped_column(String(255), default="")
    estimated_co2e_kg: Mapped[float] = mapped_column(Float, default=0.0)
    estimation_method: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(24), default="open")


class Approval(Base, TimestampMixin):
    """FR-7.3 / FR-7.6 - the approval workflow record."""
    __tablename__ = "approval"
    id: Mapped[int] = mapped_column(primary_key=True)
    object_type: Mapped[str] = mapped_column(String(48), index=True)
    object_id: Mapped[int] = mapped_column(Integer, index=True)
    step: Mapped[str] = mapped_column(String(48), default="review")
    status: Mapped[str] = mapped_column(String(24), default="pending")
    requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")


class Notification(Base, TimestampMixin):
    """FR-7.6 - all eight trigger types the document lists."""
    __tablename__ = "notification"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True, index=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    trigger: Mapped[str] = mapped_column(String(48), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info")
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    object_type: Mapped[str] = mapped_column(String(48), default="")
    object_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    link: Mapped[str] = mapped_column(String(255), default="")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SavedView(Base, TimestampMixin):
    """FR-7.5"""
    __tablename__ = "saved_view"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    object_type: Mapped[str] = mapped_column(String(48))
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    columns: Mapped[list] = mapped_column(JSON, default=list)
    sort: Mapped[str] = mapped_column(String(64), default="")
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)


class Job(Base, TimestampMixin):
    """FR-7.7 - bulk operations and exports run as tracked jobs."""
    __tablename__ = "job"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    job_type: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(24), default="queued")
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)


class AuditLog(Base, TimestampMixin):
    """FR-7.2 - timestamped changes on everything."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    user_email: Mapped[str] = mapped_column(String(255), default="")
    action: Mapped[str] = mapped_column(String(64), index=True)
    object_type: Mapped[str] = mapped_column(String(48), index=True)
    object_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text, default="")


class ProcurementDecision(Base, TimestampMixin):
    """FR-3.C.5 - carbon-weighted bids and carbon-inclusive TCO."""
    __tablename__ = "procurement_decision"
    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(96), default="")
    status: Mapped[str] = mapped_column(String(24), default="open")
    carbon_weight_pct: Mapped[float] = mapped_column(Float, default=20.0)
    internal_carbon_price: Mapped[float] = mapped_column(Float, default=0.0)
    decision_notes: Mapped[str] = mapped_column(Text, default="")
    awarded_bid_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Bid(Base, TimestampMixin):
    __tablename__ = "bid"
    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("procurement_decision.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier.id"), index=True)
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    embodied_kgco2e_per_unit: Mapped[float] = mapped_column(Float, default=0.0)
    logistics_kgco2e_per_unit: Mapped[float] = mapped_column(Float, default=0.0)
    lifetime_years: Mapped[float] = mapped_column(Float, default=5.0)
    annual_operating_cost: Mapped[float] = mapped_column(Float, default=0.0)
    annual_operating_kgco2e: Mapped[float] = mapped_column(Float, default=0.0)
    quality_score: Mapped[float] = mapped_column(Float, default=70.0)
    # computed
    carbon_cost: Mapped[float] = mapped_column(Float, default=0.0)
    carbon_inclusive_tco: Mapped[float] = mapped_column(Float, default=0.0)
    weighted_score: Mapped[float] = mapped_column(Float, default=0.0)
    rank: Mapped[int] = mapped_column(Integer, default=0)
