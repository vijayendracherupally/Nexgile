"""Demo dataset so every screen and every requirement is exercisable on first run."""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.enums import (
    SCOPE3_CATEGORIES, CalculationStatus, ConsolidationMethod, CreditStatus, DataOrigin,
    EvidenceStatus, FrameworkCode, LCABoundary, PCFStatus, ProductionMode, RoleGroup,
    Scope, Scope1Source, Scope2Method, SubmissionStatus, TransportMode,
)
from app.domain.models import (
    BOM, PCF, ActionPlan, ActivityData, Baseline, Benchmark, Bid, CBAMDeclaration,
    CBAMGood, CDPResponse, Campaign, CarbonBudget, Category, ClimateRisk,
    ClimateScenario, Connector, CostCenter, CreditOffset, Department, Disclosure,
    Emission, EmissionFactor, Entity, Evidence, Facility, FactorLibrary, FieldMapping,
    Framework, FunctionalUnit, InternalCarbonPrice, MaterialityAssessment, Material,
    MeterReading, Organization, Packaging, ProcurementDecision, Process, Product,
    Questionnaire, ReductionInitiative, ReportingBoundary, Role, Route, Scenario,
    Source, Submission, Supplier, SupplierInvitation, Target, TaxonomyActivity,
    TransitionPlan, Transaction, User, UserScope, BOMItem,
)
from app.engine.calculator import CalculationOptions, approve as approve_calc, calculate

RNG = random.Random(20260903)
YEARS = [2022, 2023, 2024, 2025]
CURRENT_YEAR = 2025

# FR-3.A.2 - grid factors for 150+ countries (kgCO2e/kWh, indicative 2024 values).
GRID_FACTORS = {
    "AE": 0.417, "AF": 0.121, "AL": 0.024, "AM": 0.212, "AO": 0.180, "AR": 0.353,
    "AT": 0.111, "AU": 0.634, "AZ": 0.534, "BA": 0.721, "BD": 0.532, "BE": 0.138,
    "BF": 0.520, "BG": 0.372, "BH": 0.489, "BI": 0.283, "BJ": 0.640, "BN": 0.541,
    "BO": 0.407, "BR": 0.098, "BW": 0.900, "BY": 0.400, "BZ": 0.320, "CA": 0.130,
    "CD": 0.025, "CF": 0.183, "CG": 0.410, "CH": 0.029, "CI": 0.412, "CL": 0.331,
    "CM": 0.278, "CN": 0.555, "CO": 0.164, "CR": 0.033, "CU": 0.669, "CY": 0.585,
    "CZ": 0.417, "DE": 0.363, "DJ": 0.640, "DK": 0.116, "DO": 0.560, "DZ": 0.488,
    "EC": 0.171, "EE": 0.652, "EG": 0.451, "ER": 0.640, "ES": 0.151, "ET": 0.024,
    "FI": 0.068, "FR": 0.056, "GA": 0.397, "GB": 0.207, "GE": 0.146, "GH": 0.379,
    "GM": 0.640, "GN": 0.286, "GQ": 0.492, "GR": 0.334, "GT": 0.323, "GW": 0.640,
    "HK": 0.710, "HN": 0.389, "HR": 0.196, "HT": 0.628, "HU": 0.223, "ID": 0.716,
    "IE": 0.290, "IL": 0.523, "IN": 0.713, "IQ": 0.638, "IR": 0.638, "IS": 0.010,
    "IT": 0.257, "JM": 0.598, "JO": 0.436, "JP": 0.464, "KE": 0.076, "KG": 0.087,
    "KH": 0.463, "KP": 0.372, "KR": 0.436, "KW": 0.591, "KZ": 0.759, "LA": 0.271,
    "LB": 0.629, "LK": 0.514, "LR": 0.640, "LS": 0.020, "LT": 0.181, "LU": 0.130,
    "LV": 0.109, "LY": 0.884, "MA": 0.685, "MD": 0.437, "ME": 0.481, "MG": 0.457,
    "MK": 0.586, "ML": 0.451, "MM": 0.470, "MN": 0.816, "MR": 0.560, "MT": 0.394,
    "MU": 0.694, "MW": 0.161, "MX": 0.423, "MY": 0.585, "MZ": 0.117, "NA": 0.090,
    "NE": 0.640, "NG": 0.422, "NI": 0.378, "NL": 0.328, "NO": 0.019, "NP": 0.024,
    "NZ": 0.116, "OM": 0.480, "PA": 0.174, "PE": 0.239, "PH": 0.634, "PK": 0.437,
    "PL": 0.662, "PS": 0.523, "PT": 0.170, "PY": 0.015, "QA": 0.487, "RO": 0.264,
    "RS": 0.720, "RU": 0.361, "RW": 0.278, "SA": 0.588, "SD": 0.400, "SE": 0.023,
    "SG": 0.408, "SI": 0.211, "SK": 0.136, "SN": 0.520, "SO": 0.640, "SS": 0.400,
    "SV": 0.214, "SY": 0.638, "SZ": 0.020, "TD": 0.640, "TG": 0.520, "TH": 0.507,
    "TJ": 0.087, "TM": 0.879, "TN": 0.468, "TR": 0.442, "TT": 0.535, "TW": 0.509,
    "TZ": 0.335, "UA": 0.283, "UG": 0.027, "US": 0.369, "UY": 0.060, "UZ": 0.575,
    "VE": 0.229, "VN": 0.475, "YE": 0.638, "ZA": 0.912, "ZM": 0.030, "ZW": 0.480,
}

ROLES = [
    # FR-2.1 Sustainability
    ("cso", "Chief Sustainability Officer", RoleGroup.SUSTAINABILITY, ["*"], "/"),
    ("esg_manager", "ESG Manager", RoleGroup.SUSTAINABILITY,
     ["accounting.read", "accounting.write", "lca.read", "suppliers.read",
      "suppliers.write", "analytics.read", "analytics.write", "dashboards.read",
      "compliance.read", "compliance.write", "scenario.read", "scenario.write",
      "export.execute", "bulk.execute", "integrations.read"], "/"),
    ("carbon_accountant", "Carbon Accountant", RoleGroup.SUSTAINABILITY,
     ["accounting.read", "accounting.write", "accounting.approve", "analytics.read",
      "dashboards.read", "compliance.read", "export.execute", "bulk.execute",
      "scenario.read", "integrations.read"], "/accounting/scope/scope_1"),
    ("environmental_manager", "Environmental Manager", RoleGroup.SUSTAINABILITY,
     ["accounting.read", "accounting.write", "analytics.read", "dashboards.read",
      "lca.read", "scenario.read"], "/accounting/scope/scope_1"),
    ("assurance_team", "Assurance Team", RoleGroup.SUSTAINABILITY,
     ["accounting.read", "compliance.read", "assurance.read", "assurance.decide",
      "dashboards.read", "analytics.read", "lca.read"], "/compliance"),
    # FR-2.2 Business
    ("procurement", "Supply Chain / Procurement", RoleGroup.BUSINESS,
     ["suppliers.read", "suppliers.write", "suppliers.campaign", "dashboards.read",
      "analytics.read", "accounting.read", "scenario.read"], "/suppliers"),
    ("product_rnd", "Product / R&D", RoleGroup.BUSINESS,
     ["lca.read", "lca.write", "dashboards.read", "analytics.read",
      "accounting.read", "scenario.read", "scenario.write"], "/lca/products"),
    ("operations", "Manufacturing / Operations", RoleGroup.BUSINESS,
     ["accounting.read", "accounting.write", "dashboards.read", "analytics.read",
      "lca.read"], "/dashboards/drilldown"),
    ("finance", "Finance", RoleGroup.BUSINESS,
     ["dashboards.read", "finance.read", "finance.write", "accounting.read",
      "analytics.read", "compliance.read", "export.execute"], "/finance"),
    ("compliance_officer", "Compliance", RoleGroup.BUSINESS,
     ["compliance.read", "compliance.write", "compliance.file", "accounting.read",
      "dashboards.read", "analytics.read", "export.execute"], "/compliance"),
    ("risk", "Risk", RoleGroup.BUSINESS,
     ["dashboards.read", "compliance.read", "analytics.read", "accounting.read",
      "scenario.read"], "/finance"),
    ("c_suite", "C-suite Leadership", RoleGroup.BUSINESS,
     ["dashboards.read", "accounting.read", "analytics.read", "compliance.read",
      "suppliers.read", "lca.read", "finance.read"], "/"),
    # FR-2.3 External
    ("supplier_user", "Supplier", RoleGroup.EXTERNAL,
     ["suppliers.read", "submission.submit"], "/portal/supplier"),
    ("data_provider", "Data Provider", RoleGroup.EXTERNAL,
     ["integrations.read", "integrations.write"], "/integrations"),
    ("auditor", "Auditor / Verifier", RoleGroup.EXTERNAL,
     ["accounting.read", "compliance.read", "assurance.read", "assurance.decide",
      "lca.read", "lca.verify", "analytics.read"], "/compliance/assurance"),
    ("consultant", "Consultant", RoleGroup.EXTERNAL,
     ["accounting.read", "analytics.read", "dashboards.read", "lca.read",
      "suppliers.read", "scenario.read", "scenario.write"], "/"),
    ("customer", "Customer", RoleGroup.EXTERNAL,
     ["lca.read"], "/lca/products"),
    ("regulator", "Regulatory Reporting Stakeholder", RoleGroup.EXTERNAL,
     ["compliance.read", "accounting.read"], "/compliance"),
]


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(func.count()).select_from(Organization)):
        return
    seed(db)


def seed(db: Session) -> None:  # noqa: C901 - a demo dataset is inherently long
    # ---------------- roles & organization -------------------------------
    roles = {}
    for code, name, group, perms, landing in ROLES:
        r = Role(code=code, name=name, group=group, permissions=perms,
                 landing_route=landing,
                 description=f"{group.replace('_', ' ').title()} role: {name}")
        db.add(r)
        roles[code] = r
    db.flush()

    org = Organization(name="Meridian Industrial Group", tenant_key="meridian",
                       industry="Industrial Manufacturing", country="DE",
                       reporting_currency="EUR")
    db.add(org)
    db.flush()

    group_entity = Entity(organization_id=org.id, name="Meridian Industrial Group",
                          code="MIG", country="DE", ownership_pct=100.0,
                          consolidation_method=ConsolidationMethod.OPERATIONAL_CONTROL,
                          revenue=1_850_000_000, employees=7400)
    db.add(group_entity)
    db.flush()

    entity_specs = [
        ("Meridian Manufacturing GmbH", "MIG-DE", "DE", 100.0, 620_000_000, 2600, True),
        ("Meridian Components SAS", "MIG-FR", "FR", 100.0, 310_000_000, 1350, True),
        ("Meridian Polska Sp. z o.o.", "MIG-PL", "PL", 85.0, 245_000_000, 1500, True),
        ("Meridian Americas Inc.", "MIG-US", "US", 100.0, 430_000_000, 1400, True),
        ("Meridian Asia Pte Ltd", "MIG-SG", "SG", 60.0, 180_000_000, 480, True),
        ("Nordwind Ventures AB", "MIG-SE", "SE", 35.0, 65_000_000, 70, False),
    ]
    entities = []
    for name, code, country, pct, revenue, employees, consolidated in entity_specs:
        e = Entity(organization_id=org.id, parent_id=group_entity.id, name=name,
                   code=code, country=country, ownership_pct=pct,
                   consolidation_method=ConsolidationMethod.OPERATIONAL_CONTROL,
                   is_consolidated=consolidated, revenue=revenue, employees=employees)
        db.add(e)
        entities.append(e)
    db.flush()

    facility_specs = [
        (0, "Stuttgart Plant", "DE-STU", "plant", "DE", 48.7758, 9.1829, 42000),
        (0, "Hamburg Distribution Centre", "DE-HAM", "warehouse", "DE", 53.5511, 9.9937, 26000),
        (1, "Lyon Assembly", "FR-LYO", "plant", "FR", 45.7640, 4.8357, 31000),
        (2, "Wroclaw Foundry", "PL-WRO", "plant", "PL", 51.1079, 17.0385, 38000),
        (3, "Cleveland Works", "US-CLE", "plant", "US", 41.4993, -81.6944, 45000),
        (3, "Austin R&D Campus", "US-AUS", "office", "US", 30.2672, -97.7431, 12000),
        (4, "Singapore Hub", "SG-SIN", "warehouse", "SG", 1.3521, 103.8198, 18000),
    ]
    facilities = []
    for idx, name, code, ftype, country, lat, lon, area in facility_specs:
        f = Facility(entity_id=entities[idx].id, name=name, code=code,
                     facility_type=ftype, country=country, region=country,
                     grid_region=country, latitude=lat, longitude=lon,
                     floor_area_m2=area)
        db.add(f)
        facilities.append(f)
    db.flush()

    departments, cost_centers = [], []
    for e in entities:
        for dname in ("Operations", "Logistics", "Procurement", "R&D"):
            d = Department(entity_id=e.id, name=dname,
                           code=f"{e.code}-{dname[:3].upper()}",
                           headcount=RNG.randint(20, 400))
            db.add(d)
            departments.append(d)
    db.flush()
    for d in departments:
        cc = CostCenter(entity_id=d.entity_id, department_id=d.id,
                        name=f"{d.name} cost centre", code=f"CC-{d.code}",
                        budget=RNG.randint(500_000, 9_000_000))
        db.add(cc)
        cost_centers.append(cc)
    db.flush()

    db.add(ReportingBoundary(
        organization_id=org.id, name="Group reporting boundary 2025",
        consolidation_method=ConsolidationMethod.OPERATIONAL_CONTROL,
        baseline_year=2022,
        included_entity_ids=[group_entity.id] + [e.id for e in entities if e.is_consolidated],
        scopes_covered=[s.value for s in Scope],
        description="Operational control boundary. Nordwind Ventures AB (35% equity, "
                    "no operational control) is excluded from consolidated actuals."))

    # ---------------- users ----------------------------------------------
    user_specs = [
        ("ana.k@meridian.example", "Ana Kowalski", "cso", None),
        ("marcus.r@meridian.example", "Marcus Reiner", "esg_manager", None),
        ("priya.s@meridian.example", "Priya Sharma", "carbon_accountant", None),
        ("tom.b@meridian.example", "Tom Berger", "environmental_manager", None),
        ("lena.v@meridian.example", "Lena Vogel", "assurance_team", None),
        ("carlos.m@meridian.example", "Carlos Mendes", "procurement", None),
        ("yuki.t@meridian.example", "Yuki Tanaka", "product_rnd", None),
        ("sam.o@meridian.example", "Sam Okafor", "operations", None),
        ("iris.d@meridian.example", "Iris Delacroix", "finance", None),
        ("rafael.g@meridian.example", "Rafael Gomez", "compliance_officer", None),
        ("nina.h@meridian.example", "Nina Haas", "risk", None),
        ("erik.l@meridian.example", "Erik Lindqvist", "c_suite", None),
        ("audit@northstar-assurance.example", "Northstar Assurance", "auditor", None),
        ("data@gridwatch.example", "GridWatch Data Services", "data_provider", None),
        ("advisor@verdant.example", "Verdant Advisory", "consultant", None),
        ("buyer@atlascorp.example", "Atlas Corp Procurement", "customer", None),
        ("filings@eu-regulator.example", "EU Reporting Desk", "regulator", None),
    ]
    users = {}
    for email, full_name, role_code, supplier_id in user_specs:
        u = User(email=email, full_name=full_name, role_id=roles[role_code].id,
                 supplier_id=supplier_id)
        db.add(u)
        users[role_code] = u
    db.flush()
    for u in users.values():
        db.add(UserScope(user_id=u.id, object_type="organization", object_id=org.id))
    # A deliberately narrowed principal proves FR-7.1 is real.
    db.add(UserScope(user_id=users["operations"].id, object_type="entity",
                     object_id=entities[0].id))
    db.flush()

    # ---------------- categories ------------------------------------------
    categories = {}
    for scope, label in ((Scope.SCOPE_1, "Direct emissions"),
                         (Scope.SCOPE_2, "Purchased energy")):
        c = Category(scope=scope, number=None, name=label,
                     description=f"{scope} aggregate category")
        db.add(c)
        categories[scope] = c
    scope3_categories = {}
    for number, name in SCOPE3_CATEGORIES.items():
        c = Category(scope=Scope.SCOPE_3, number=number, name=name,
                     description=f"GHG Protocol Scope 3 category {number}")
        db.add(c)
        scope3_categories[number] = c
    db.flush()

    # ---------------- factor libraries & factors --------------------------
    libraries = {}
    lib_specs = [
        ("ecoinvent", "ecoinvent", "3.10", date(2023, 11, 1), True, False),
        ("GaBi / Sphera", "GaBi", "2024.1", date(2024, 3, 15), False, False),
        ("DEFRA GHG Conversion Factors", "DEFRA", "2024", date(2024, 6, 1), False, False),
        ("US EPA eGRID + Emission Factors Hub", "EPA", "2024", date(2024, 4, 10), False, False),
        ("IEA Emission Factors", "IEA", "2024", date(2024, 9, 1), False, False),
    ]
    for name, provider, version, released, is_default, locked in lib_specs:
        lib = FactorLibrary(name=name, provider=provider, version=version,
                            release_date=released, is_default=is_default,
                            is_locked=locked,
                            notes="Controlled library under FR-7.3 version locking.")
        db.add(lib)
        libraries[provider] = lib
    db.flush()
    default_lib = libraries["ecoinvent"]

    def add_factor(activity_key, name, scope, unit, value, country="GLOBAL",
                   gases=None, method="location_based", uncertainty=12.0,
                   library=None, valid_from=date(2022, 1, 1), reference=""):
        db.add(EmissionFactor(
            library_id=(library or default_lib).id, activity_key=activity_key,
            name=name, scope=scope, country=country, region=country,
            valid_from=valid_from, unit=unit, value_kgco2e=value,
            gas_breakdown=gases or {}, method=method, uncertainty_pct=uncertainty,
            source_reference=reference or f"{(library or default_lib).provider} "
                                          f"{(library or default_lib).version}",
            pedigree={"reliability": 2, "completeness": 2, "temporal": 1,
                      "geographical": 1 if country != "GLOBAL" else 4,
                      "technological": 2}))

    # Scope 1 - stationary, mobile, fleet, process, fugitive (per-gas where real)
    add_factor("natural_gas.stationary", "Natural gas combustion (stationary)",
               Scope.SCOPE_1, "kWh", 0.20297,
               gases={"CO2": 0.20242, "CH4": 0.0000037, "N2O": 0.0000011},
               uncertainty=6.0, reference="DEFRA 2024 - gaseous fuels")
    add_factor("diesel.mobile", "Diesel combustion (mobile)", Scope.SCOPE_1, "L", 2.66155,
               gases={"CO2": 2.62694, "CH4": 0.00012, "N2O": 0.00011},
               uncertainty=7.0)
    add_factor("petrol.mobile", "Petrol combustion (mobile)", Scope.SCOPE_1, "L", 2.30
               , gases={"CO2": 2.28, "CH4": 0.00025, "N2O": 0.00013}, uncertainty=7.0)
    add_factor("fleet.diesel", "Fleet diesel (telematics distance)", Scope.SCOPE_1,
               "km", 0.17, gases={"CO2": 0.168, "CH4": 0.00002, "N2O": 0.00002},
               uncertainty=14.0)
    add_factor("process.clinker", "Process emissions - calcination", Scope.SCOPE_1,
               "t", 525.0, gases={"CO2": 525.0}, uncertainty=9.0)
    add_factor("process.steel_reduction", "Process emissions - direct reduction",
               Scope.SCOPE_1, "t", 1420.0, gases={"CO2": 1420.0}, uncertainty=11.0)
    add_factor("fugitive.r410a", "Fugitive refrigerant R-410A", Scope.SCOPE_1, "kg",
               2256.0, gases={"R-410A": 1.0}, uncertainty=25.0)
    add_factor("fugitive.hfc134a", "Fugitive refrigerant HFC-134a", Scope.SCOPE_1, "kg",
               1530.0, gases={"HFC-134a": 1.0}, uncertainty=25.0)
    add_factor("fugitive.sf6", "Fugitive SF6 from switchgear", Scope.SCOPE_1, "kg",
               25200.0, gases={"SF6": 1.0}, uncertainty=30.0)

    # Scope 2 - grid factors for 150+ countries, plus market-based instruments
    for country, value in GRID_FACTORS.items():
        add_factor("electricity.grid", f"Grid electricity - {country}", Scope.SCOPE_2,
                   "kWh", value, country=country, method=Scope2Method.LOCATION_BASED,
                   uncertainty=8.0, library=libraries["IEA"],
                   reference="IEA Emission Factors 2024")
    add_factor("electricity.grid", "Grid electricity - global average", Scope.SCOPE_2,
               "kWh", 0.475, method=Scope2Method.LOCATION_BASED, uncertainty=20.0,
               library=libraries["IEA"])
    for country, residual in (("DE", 0.412), ("FR", 0.072), ("PL", 0.731),
                              ("US", 0.412), ("SG", 0.421)):
        add_factor("electricity.market", f"Residual mix - {country}", Scope.SCOPE_2,
                   "kWh", residual, country=country,
                   method=Scope2Method.MARKET_BASED, uncertainty=10.0,
                   library=libraries["IEA"])
    add_factor("electricity.renewable_ppa", "Renewable PPA / guarantee of origin",
               Scope.SCOPE_2, "kWh", 0.0, method=Scope2Method.MARKET_BASED,
               uncertainty=2.0, library=libraries["IEA"])
    add_factor("district_heat.purchased", "Purchased district heat", Scope.SCOPE_2,
               "kWh", 0.171, uncertainty=12.0)
    add_factor("steam.purchased", "Purchased steam", Scope.SCOPE_2, "kWh", 0.190,
               uncertainty=12.0)

    # Scope 3 - one or more factors per category so all 15 can report
    scope3_factors = [
        ("purchased_goods.spend", "Purchased goods & services (spend-based)", "EUR", 0.31, 30.0),
        ("purchased_goods.steel", "Steel, primary route", "kg", 2.29, 15.0),
        ("purchased_goods.aluminium", "Aluminium, primary", "kg", 8.24, 16.0),
        ("purchased_goods.polymer", "Polypropylene granulate", "kg", 1.95, 14.0),
        ("purchased_goods.copper", "Copper cathode", "kg", 3.83, 18.0),
        ("purchased_goods.electronics", "Electronic components", "kg", 12.6, 28.0),
        ("capital_goods.spend", "Capital goods (spend-based)", "EUR", 0.42, 32.0),
        ("fuel_energy.wtt", "Well-to-tank and T&D losses", "kWh", 0.052, 18.0),
        ("transport.road", "Road freight (HGV, average load)", "tkm", 0.11, 20.0),
        ("transport.rail", "Rail freight", "tkm", 0.028, 18.0),
        ("transport.sea", "Sea freight (container)", "tkm", 0.011, 22.0),
        ("transport.air", "Air freight", "tkm", 0.60, 25.0),
        ("transport.inland_waterway", "Inland waterway freight", "tkm", 0.031, 22.0),
        ("waste.landfill", "Waste to landfill", "t", 458.0, 30.0),
        ("waste.recycling", "Waste to recycling", "t", 21.3, 28.0),
        ("waste.incineration", "Waste to incineration", "t", 883.0, 26.0),
        ("business_travel.air_short", "Air travel - short haul", "pkm", 0.158, 18.0),
        ("business_travel.air_long", "Air travel - long haul", "pkm", 0.195, 18.0),
        ("business_travel.rail", "Rail travel", "pkm", 0.035, 15.0),
        ("business_travel.hotel", "Hotel night", "unit", 12.2, 35.0),
        ("commuting.average", "Employee commuting (average mix)", "pkm", 0.142, 30.0),
        ("upstream_leased.floor_area", "Upstream leased assets", "m2", 38.0, 30.0),
        ("downstream_transport.road", "Downstream distribution", "tkm", 0.12, 22.0),
        ("processing_sold.energy", "Processing of sold products", "kWh", 0.42, 30.0),
        ("use_phase.electricity", "Use of sold products", "kWh", 0.41, 25.0),
        ("eol.mixed", "End-of-life treatment (mixed)", "kg", 0.31, 32.0),
        ("downstream_leased.floor_area", "Downstream leased assets", "m2", 34.0, 30.0),
        ("franchise.revenue", "Franchises (revenue-based)", "EUR", 0.18, 38.0),
        ("investments.equity", "Investments (equity share)", "EUR", 0.22, 40.0),
        ("material.generic", "Generic material (screening)", "kg", 2.1, 45.0),
    ]
    for key, name, unit, value, unc in scope3_factors:
        add_factor(key, name, Scope.SCOPE_3, unit, value, uncertainty=unc)
    db.flush()

    # ---------------- sources ---------------------------------------------
    source_specs = [
        (Scope.SCOPE_1, Scope1Source.STATIONARY_COMBUSTION, "natural_gas.stationary",
         "Process boilers", "kWh"),
        (Scope.SCOPE_1, Scope1Source.MOBILE_COMBUSTION, "diesel.mobile",
         "Forklifts and yard vehicles", "L"),
        (Scope.SCOPE_1, Scope1Source.FLEET, "fleet.diesel", "Company fleet (telematics)", "km"),
        (Scope.SCOPE_1, Scope1Source.PROCESS, "process.steel_reduction",
         "Direct reduction furnace", "t"),
        (Scope.SCOPE_1, Scope1Source.FUGITIVE, "fugitive.r410a", "Chiller refrigerant losses", "kg"),
        (Scope.SCOPE_2, "purchased_electricity", "electricity.grid",
         "Site electricity supply", "kWh"),
        (Scope.SCOPE_2, "district_heat", "district_heat.purchased", "District heat", "kWh"),
    ]
    sources = []
    for f in facilities:
        for scope, stype, key, name, unit in source_specs:
            s = Source(facility_id=f.id, entity_id=f.entity_id, name=f"{f.code} {name}",
                       scope=scope, source_type=stype, activity_key=key, unit=unit,
                       category_id=categories[scope].id if scope in categories else None)
            db.add(s)
            sources.append(s)
    db.flush()

    # ---------------- suppliers -------------------------------------------
    supplier_specs = [
        ("Nordstahl AG", "SUP-001", 1, "Metals", "DE", 51.23, 6.78, 48_000_000, "de", True),
        ("Alumétal SA", "SUP-002", 1, "Metals", "FR", 45.19, 5.72, 31_000_000, "fr", True),
        ("PolyForm Kunststoffe", "SUP-003", 1, "Polymers", "DE", 50.11, 8.68, 22_500_000, "de", False),
        ("Shenzhen Precision Electronics", "SUP-004", 1, "Electronics", "CN", 22.54, 114.06, 39_000_000, "zh-CN", True),
        ("Vidyut Components Pvt Ltd", "SUP-005", 1, "Electronics", "IN", 12.97, 77.59, 18_200_000, "hi", False),
        ("TransEuropa Logistics", "SUP-006", 1, "Logistics", "PL", 52.23, 21.01, 14_800_000, "pl", False),
        ("Pacific Freight Lines", "SUP-007", 1, "Logistics", "SG", 1.29, 103.85, 12_400_000, "en", False),
        ("Cascade Packaging Co", "SUP-008", 1, "Packaging", "US", 45.52, -122.68, 9_600_000, "en", False),
        ("Iberia Chemicals SL", "SUP-009", 1, "Chemicals", "ES", 41.39, 2.17, 16_300_000, "es", False),
        ("Baltic Foundry OU", "SUP-010", 1, "Metals", "EE", 59.44, 24.75, 7_900_000, "en", False),
        ("Tokai Specialty Alloys", "SUP-011", 1, "Metals", "JP", 35.18, 136.91, 11_200_000, "ja", False),
        ("Cerrado Mineração", "SUP-012", 2, "Raw materials", "BR", -19.92, -43.94, 6_100_000, "pt", False),
        ("Guinée Bauxite SARL", "SUP-013", 2, "Raw materials", "GN", 9.64, -13.58, 4_300_000, "fr", False),
        ("Anhui Resin Works", "SUP-014", 2, "Chemicals", "CN", 31.86, 117.28, 5_400_000, "zh-CN", False),
        ("Kerala Rare Earths", "SUP-015", 3, "Raw materials", "IN", 8.52, 76.94, 2_100_000, "ta", False),
        ("Ankara Metal Isleme", "SUP-016", 2, "Metals", "TR", 39.93, 32.86, 3_800_000, "tr", False),
        ("Nova Scotia Timber", "SUP-017", 2, "Packaging", "CA", 44.65, -63.58, 2_700_000, "en", False),
        ("Bangkok Circuit Assembly", "SUP-018", 2, "Electronics", "TH", 13.76, 100.50, 4_900_000, "th", False),
    ]
    suppliers = []
    for name, code, tier, cat, country, lat, lon, spend, lang, critical in supplier_specs:
        s = Supplier(organization_id=org.id, name=name, code=code, tier=tier,
                     category=cat, country=country, latitude=lat, longitude=lon,
                     annual_spend=spend, language=lang, is_critical=critical,
                     contact_email=f"esg@{code.lower()}.example",
                     contact_name="ESG Contact",
                     risk_rating="high" if tier >= 2 and critical is False and
                     country in ("GN", "IN", "CN") else "medium",
                     has_data_agreement=tier == 1 and critical)
        db.add(s)
        suppliers.append(s)
    db.flush()
    # multi-tier links (FR-3.C.4)
    for child_idx, parent_idx in ((11, 0), (12, 1), (13, 2), (14, 3), (15, 9),
                                  (16, 7), (17, 3)):
        suppliers[child_idx].parent_supplier_id = suppliers[parent_idx].id
    db.flush()

    supplier_user = User(email="esg@sup-001.example", full_name="Nordstahl ESG Team",
                         role_id=roles["supplier_user"].id, language="de",
                         supplier_id=suppliers[0].id)
    db.add(supplier_user)
    db.flush()
    db.add(UserScope(user_id=supplier_user.id, object_type="supplier",
                     object_id=suppliers[0].id))

    # ---------------- materials, products, BOM, processes -----------------
    material_specs = [
        ("Structural steel S355", "Metal", "purchased_goods.steel", 12.0, True, False),
        ("Recycled steel scrap", "Metal", "purchased_goods.steel", 92.0, True, True),
        ("Aluminium 6061", "Metal", "purchased_goods.aluminium", 18.0, True, False),
        ("Recycled aluminium", "Metal", "purchased_goods.aluminium", 85.0, True, True),
        ("Polypropylene", "Polymer", "purchased_goods.polymer", 5.0, True, False),
        ("Bio-based polymer", "Polymer", "purchased_goods.polymer", 0.0, True, True),
        ("Copper wiring", "Metal", "purchased_goods.copper", 35.0, True, False),
        ("Electronic control unit", "Electronics", "purchased_goods.electronics", 8.0, False, False),
        ("Corrugated board", "Fibre", "material.generic", 78.0, True, False),
        ("EPS foam insert", "Polymer", "purchased_goods.polymer", 0.0, False, False),
        ("Moulded pulp insert", "Fibre", "material.generic", 95.0, True, True),
    ]
    materials = []
    for name, cls, key, recycled, recyclable, is_alt in material_specs:
        m = Material(name=name, material_class=cls, activity_key=key,
                     recycled_content_pct=recycled, recyclable=recyclable,
                     is_alternative=is_alt)
        db.add(m)
        materials.append(m)
    db.flush()

    fu_specs = [("One pump unit over 10 years", "unit", 1.0),
                ("One control module", "unit", 1.0),
                ("One tonne of finished assembly", "t", 1.0)]
    functional_units = []
    for name, unit, qty in fu_specs:
        fu = FunctionalUnit(name=name, unit=unit, quantity=qty,
                            description="Declared unit for the PCF study.")
        db.add(fu)
        functional_units.append(fu)
    db.flush()

    product_specs = [
        (0, "MP-4200", "Meridian Pump MP-4200", "Pumps", 0, 86.0, 24000, 10),
        (0, "MP-2100", "Meridian Pump MP-2100", "Pumps", 0, 41.0, 38000, 10),
        (1, "CM-880", "Control Module CM-880", "Electronics", 1, 3.4, 120000, 8),
        (2, "VH-500", "Valve Housing VH-500", "Castings", 2, 22.5, 65000, 15),
        (3, "MP-4200X", "Meridian Pump MP-4200X (US)", "Pumps", 0, 88.0, 19000, 10),
    ]
    products = []
    for eidx, sku, name, cat, fu_idx, mass, volume, life in product_specs:
        p = Product(entity_id=entities[eidx].id, sku=sku, name=name, category=cat,
                    functional_unit_id=functional_units[fu_idx].id, mass_kg=mass,
                    annual_volume=volume, lifetime_years=life,
                    plm_ref=f"PLM-{sku}", erp_ref=f"ERP-{sku}")
        db.add(p)
        products.append(p)
    db.flush()

    for p in products:
        bom = BOM(product_id=p.id, version="2.1", source_system="PLM")
        db.add(bom)
        db.flush()
        scale = p.mass_kg / 86.0
        level1 = [
            ("Pump casing", materials[0], suppliers[0], 38.0 * scale, 3.0),
            ("Impeller assembly", materials[2], suppliers[1], 12.0 * scale, 4.5),
            ("Drive housing", materials[0], suppliers[0], 18.0 * scale, 2.5),
            ("Control electronics", materials[7], suppliers[3], 3.2 * scale, 1.0),
            ("Wiring harness", materials[6], suppliers[4], 2.4 * scale, 2.0),
            ("Seals and gaskets", materials[4], suppliers[2], 1.6 * scale, 6.0),
        ]
        parents = []
        for cname, material, supplier, mass, scrap in level1:
            item = BOMItem(bom_id=bom.id, level=1, component_name=cname,
                           material_id=material.id, component_supplier_id=supplier.id,
                           quantity=1.0, unit="kg", mass_kg=round(mass, 3),
                           scrap_pct=scrap)
            db.add(item)
            parents.append((item, material))
        db.flush()
        # level 2 sub-components (FR-3.B.1 multi-level)
        for item, material in parents[:3]:
            sub = BOMItem(bom_id=bom.id, parent_item_id=item.id, level=2,
                          component_name=f"{item.component_name} - raw billet",
                          material_id=material.id,
                          component_supplier_id=suppliers[11].id,
                          quantity=1.0, unit="kg",
                          mass_kg=round(item.mass_kg * 0.55, 3), scrap_pct=1.5)
            db.add(sub)
        # alternative materials (FR-3.B.1)
        db.flush()
        for item, material in parents[:2]:
            alt_material = materials[1] if material is materials[0] else materials[3]
            db.add(BOMItem(bom_id=bom.id, level=item.level,
                           component_name=f"{item.component_name} (recycled route)",
                           material_id=alt_material.id,
                           component_supplier_id=item.component_supplier_id,
                           quantity=item.quantity, unit=item.unit,
                           mass_kg=item.mass_kg, scrap_pct=item.scrap_pct,
                           alternative_for_id=item.id, is_alternative=True))

        facility = facilities[0] if p.entity_id == entities[0].id else \
            next((f for f in facilities if f.entity_id == p.entity_id), facilities[0])
        proc_specs = [
            ("Casting", 1, ProductionMode.BATCH, 42.0 * scale, 180.0 * scale, 4.2 * scale, 6.0, 2.0, 94.0),
            ("Machining", 2, ProductionMode.BATCH, 28.0 * scale, 0.0, 0.0, 8.0, 1.5, 96.0),
            ("Surface treatment", 3, ProductionMode.CONTINUOUS, 11.0 * scale, 40.0 * scale, 0.8 * scale, 2.0, 1.0, 98.0),
            ("Assembly & test", 4, ProductionMode.BATCH, 6.5 * scale, 0.0, 0.0, 0.5, 3.0, 97.0),
        ]
        for pname, seq, mode, kwh, mj, direct, scrap, defect, yield_pct in proc_specs:
            db.add(Process(product_id=p.id, facility_id=facility.id, name=pname,
                           sequence=seq, production_mode=mode,
                           energy_kwh_per_unit=round(kwh, 3),
                           thermal_mj_per_unit=round(mj, 3),
                           direct_emissions_kgco2e=round(direct, 4),
                           scrap_rate_pct=scrap, defect_rate_pct=defect,
                           yield_pct=yield_pct, batch_size=50))

        route_specs = [
            ("inbound", TransportMode.SEA, "Shanghai", "Hamburg", 19500, 0.0, 4),
            ("inbound", TransportMode.ROAD, "Hamburg", "Stuttgart", 660, 0.0, 1),
            ("internal", TransportMode.ROAD, "Stuttgart", "Hamburg DC", 660, 0.0, 6),
            ("outbound", TransportMode.ROAD, "Hamburg DC", "EU customers", 780, 0.0, 0),
            ("outbound", TransportMode.AIR, "Hamburg", "Overseas expedite", 6200, 0.0, 0),
        ]
        for seq, (stage, mode, origin, dest, distance, payload, wh_days) in enumerate(route_specs, 1):
            db.add(Route(product_id=p.id, leg_sequence=seq, stage=stage, mode=mode,
                         origin=origin, destination=dest, distance_km=distance,
                         payload_tonnes=round(p.mass_kg / 1000, 5),
                         load_factor_pct=RNG.choice([70.0, 80.0, 85.0]),
                         warehouse_days=wh_days))

        pack_specs = [("primary", materials[8], "Corrugated carton", 1.8, 78.0, True, 0),
                      ("secondary", materials[9], "EPS protective insert", 0.35, 0.0, False, 0),
                      ("tertiary", materials[8], "Pallet and wrap", 2.2, 60.0, True, 8)]
        for level, material, pname, mass, recycled, recyclable, cycles in pack_specs:
            db.add(Packaging(product_id=p.id, level=level, material_id=material.id,
                             name=pname, mass_kg=round(mass * scale, 3),
                             recycled_content_pct=recycled, recyclable=recyclable,
                             reuse_cycles=cycles))
    db.flush()

    # ---------------- activity data across four years ---------------------
    activity_rows: list[ActivityData] = []

    def add_activity(**kwargs) -> ActivityData:
        a = ActivityData(**kwargs)
        db.add(a)
        activity_rows.append(a)
        return a

    for year in YEARS:
        decline = 1.0 - 0.045 * (year - YEARS[0])
        for facility in facilities:
            entity_id = facility.entity_id
            dept = next((d for d in departments if d.entity_id == entity_id), None)
            cc = next((c for c in cost_centers if c.entity_id == entity_id), None)
            scale = 1.0 if facility.facility_type == "plant" else 0.35
            for month in range(1, 13):
                start = date(year, month, 1)
                end = date(year, month, 28)
                seasonal = 1.0 + 0.18 * (1 if month in (1, 2, 11, 12) else -0.5 if month in (7, 8) else 0)

                add_activity(entity_id=entity_id, facility_id=facility.id,
                             department_id=dept.id if dept else None,
                             cost_center_id=cc.id if cc else None,
                             scope=Scope.SCOPE_1, activity_key="natural_gas.stationary",
                             description=f"{facility.name} boiler gas",
                             quantity=round(RNG.uniform(160000, 320000) * scale * decline * seasonal, 1),
                             unit="kWh", period_start=start, period_end=end,
                             data_origin=DataOrigin.METER,
                             category_id=categories[Scope.SCOPE_1].id,
                             evidence_status=EvidenceStatus.VALIDATED,
                             completeness_pct=100.0)
                add_activity(entity_id=entity_id, facility_id=facility.id,
                             scope=Scope.SCOPE_1, activity_key="diesel.mobile",
                             description=f"{facility.name} forklift diesel",
                             quantity=round(RNG.uniform(1800, 5200) * scale * decline, 1),
                             unit="L", period_start=start, period_end=end,
                             data_origin=DataOrigin.INVOICE,
                             category_id=categories[Scope.SCOPE_1].id,
                             evidence_status=EvidenceStatus.ACCEPTED)
                add_activity(entity_id=entity_id, facility_id=facility.id,
                             scope=Scope.SCOPE_1, activity_key="fleet.diesel",
                             description=f"{facility.name} fleet distance (telematics)",
                             quantity=round(RNG.uniform(22000, 68000) * scale * decline, 0),
                             unit="km", period_start=start, period_end=end,
                             data_origin=DataOrigin.TELEMATICS,
                             category_id=categories[Scope.SCOPE_1].id,
                             evidence_status=EvidenceStatus.VALIDATED)
                if facility.facility_type == "plant":
                    add_activity(entity_id=entity_id, facility_id=facility.id,
                                 scope=Scope.SCOPE_1, activity_key="process.steel_reduction",
                                 description=f"{facility.name} direct reduction process",
                                 quantity=round(RNG.uniform(18, 46) * decline, 2),
                                 unit="t", period_start=start, period_end=end,
                                 data_origin=DataOrigin.SENSOR,
                                 category_id=categories[Scope.SCOPE_1].id,
                                 evidence_status=EvidenceStatus.VALIDATED)
                if month in (3, 9):
                    add_activity(entity_id=entity_id, facility_id=facility.id,
                                 scope=Scope.SCOPE_1, activity_key="fugitive.r410a",
                                 description=f"{facility.name} refrigerant top-up",
                                 quantity=round(RNG.uniform(4, 22), 2), unit="kg",
                                 period_start=start, period_end=end,
                                 data_origin=DataOrigin.INVOICE,
                                 category_id=categories[Scope.SCOPE_1].id,
                                 evidence_status=EvidenceStatus.UPLOADED)

                grid_kwh = round(RNG.uniform(420000, 1_150_000) * scale * decline * seasonal, 1)
                add_activity(entity_id=entity_id, facility_id=facility.id,
                             department_id=dept.id if dept else None,
                             cost_center_id=cc.id if cc else None,
                             scope=Scope.SCOPE_2, activity_key="electricity.grid",
                             description=f"{facility.name} grid electricity",
                             quantity=grid_kwh, unit="kWh",
                             period_start=start, period_end=end,
                             data_origin=DataOrigin.METER,
                             scope2_method=Scope2Method.LOCATION_BASED,
                             category_id=categories[Scope.SCOPE_2].id,
                             evidence_status=EvidenceStatus.VALIDATED)
                renewable_share = min(0.75, 0.15 + 0.12 * (year - YEARS[0]))
                add_activity(entity_id=entity_id, facility_id=facility.id,
                             scope=Scope.SCOPE_2, activity_key="electricity.renewable_ppa",
                             description=f"{facility.name} renewable PPA coverage",
                             quantity=round(grid_kwh * renewable_share, 1), unit="kWh",
                             period_start=start, period_end=end,
                             data_origin=DataOrigin.SUPPLIER_PRIMARY,
                             scope2_method=Scope2Method.MARKET_BASED,
                             category_id=categories[Scope.SCOPE_2].id,
                             evidence_status=EvidenceStatus.ACCEPTED)
                add_activity(entity_id=entity_id, facility_id=facility.id,
                             scope=Scope.SCOPE_2, activity_key="electricity.market",
                             description=f"{facility.name} residual mix supply",
                             quantity=round(grid_kwh * (1 - renewable_share), 1), unit="kWh",
                             period_start=start, period_end=end,
                             data_origin=DataOrigin.SUPPLIER_PRIMARY,
                             scope2_method=Scope2Method.MARKET_BASED,
                             category_id=categories[Scope.SCOPE_2].id,
                             evidence_status=EvidenceStatus.ACCEPTED)

        # Scope 3 - every one of the 15 categories, using the named data methods
        scope3_plan = [
            (1, "purchased_goods.steel", "kg", (2_400_000, 4_800_000), "supplier_specific", DataOrigin.SUPPLIER_PRIMARY, 0),
            (1, "purchased_goods.spend", "EUR", (18_000_000, 32_000_000), "spend_based", DataOrigin.SPEND, None),
            (2, "capital_goods.spend", "EUR", (4_000_000, 11_000_000), "spend_based", DataOrigin.SPEND, None),
            (3, "fuel_energy.wtt", "kWh", (9_000_000, 16_000_000), "activity_based", DataOrigin.METER, None),
            (4, "transport.sea", "tkm", (18_000_000, 34_000_000), "logistics_based", DataOrigin.ERP, 6),
            (4, "transport.road", "tkm", (5_000_000, 9_000_000), "logistics_based", DataOrigin.ERP, 5),
            (5, "waste.landfill", "t", (600, 1900), "activity_based", DataOrigin.INVOICE, None),
            (5, "waste.recycling", "t", (1800, 4200), "activity_based", DataOrigin.INVOICE, None),
            (6, "business_travel.air_long", "pkm", (2_800_000, 6_400_000), "travel_based", DataOrigin.ERP, None),
            (6, "business_travel.hotel", "unit", (4000, 11000), "travel_based", DataOrigin.RECEIPT, None),
            (7, "commuting.average", "pkm", (12_000_000, 24_000_000), "activity_based", DataOrigin.SURVEY, None),
            (8, "upstream_leased.floor_area", "m2", (18000, 42000), "asset_based", DataOrigin.ERP, None),
            (9, "downstream_transport.road", "tkm", (6_000_000, 12_000_000), "logistics_based", DataOrigin.ERP, 5),
            (10, "processing_sold.energy", "kWh", (7_000_000, 14_000_000), "activity_based", DataOrigin.ESTIMATED, None),
            (11, "use_phase.electricity", "kWh", (120_000_000, 210_000_000), "use_phase", DataOrigin.ESTIMATED, None),
            (12, "eol.mixed", "kg", (2_000_000, 4_400_000), "end_of_life", DataOrigin.ESTIMATED, None),
            (13, "downstream_leased.floor_area", "m2", (9000, 21000), "asset_based", DataOrigin.ERP, None),
            (14, "franchise.revenue", "EUR", (2_000_000, 6_000_000), "spend_based", DataOrigin.ERP, None),
            (15, "investments.equity", "EUR", (14_000_000, 38_000_000), "spend_based", DataOrigin.ESTIMATED, None),
        ]
        for entity in entities:
            for number, key, unit, (lo, hi), method, origin, supplier_idx in scope3_plan:
                quantity = round(RNG.uniform(lo, hi) * decline * (0.4 if entity.revenue < 250_000_000 else 1.0), 2)
                estimated = origin in (DataOrigin.ESTIMATED, DataOrigin.SPEND)
                add_activity(entity_id=entity.id, scope=Scope.SCOPE_3,
                             activity_key=key,
                             description=f"Category {number}: {SCOPE3_CATEGORIES[number]}",
                             quantity=quantity, unit=unit,
                             period_start=date(year, 1, 1), period_end=date(year, 12, 31),
                             data_origin=origin, scope3_method=method,
                             category_id=scope3_categories[number].id,
                             supplier_id=suppliers[supplier_idx].id if supplier_idx is not None else None,
                             product_id=products[0].id if number in (10, 11, 12) else None,
                             is_estimated=estimated,
                             completeness_pct=RNG.choice([100.0, 100.0, 95.0, 88.0, 72.0]),
                             evidence_status=EvidenceStatus.VALIDATED if not estimated
                             else EvidenceStatus.MISSING)
    db.flush()

    # ---------------- run the engine over everything ----------------------
    options = CalculationOptions()
    calculated = 0
    for a in activity_rows:
        try:
            result = calculate(db, a, options)
            calculated += 1
            # Close out prior years: approve and lock (FR-7.3).
            if a.period_start.year < CURRENT_YEAR:
                approve_calc(db, result.calculation, user_id=users["carbon_accountant"].id,
                             user_email=users["carbon_accountant"].email,
                             comment="Prior-year close")
        except Exception:
            continue
    db.flush()

    # ---------------- meter readings --------------------------------------
    for facility in facilities:
        for week in range(52):
            db.add(MeterReading(
                facility_id=facility.id, meter_code=f"{facility.code}-ELEC-01",
                meter_type="electricity", capture_method="meter",
                reading_at=datetime(CURRENT_YEAR, 1, 1, tzinfo=timezone.utc) + timedelta(weeks=week),
                value=round(RNG.uniform(90000, 260000), 1), unit="kWh"))
        for week in range(0, 52, 4):
            db.add(MeterReading(
                facility_id=facility.id, meter_code=f"{facility.code}-GAS-01",
                meter_type="gas", capture_method="sensor",
                reading_at=datetime(CURRENT_YEAR, 1, 1, tzinfo=timezone.utc) + timedelta(weeks=week),
                value=round(RNG.uniform(40000, 120000), 1), unit="kWh"))

    # ---------------- transactions (spend for FR-3.D.1) -------------------
    descriptions = [
        "Steel coil purchase", "Aluminium billet supply", "Air travel booking Frankfurt-Chicago",
        "Hotel accommodation Munich", "Freight forwarding sea Shanghai-Hamburg",
        "Waste collection service", "Machine tool capital purchase",
        "Polymer resin delivery", "Employee commuting allowance",
        "Contract manufacturing service", "Electricity network transmission charge",
        "Warehouse rental", "Consulting services", "Office cleaning services",
        "Courier shipment", "Franchise royalty", "Equity fund investment",
        "Electronic component supply", "Rail ticket booking", "Landfill disposal fee",
    ]
    for entity in entities:
        for _ in range(90):
            supplier = RNG.choice(suppliers)
            db.add(Transaction(
                entity_id=entity.id,
                cost_center_id=RNG.choice([c.id for c in cost_centers
                                           if c.entity_id == entity.id] or [None]),
                supplier_id=supplier.id,
                transaction_date=date(CURRENT_YEAR, RNG.randint(1, 12), RNG.randint(1, 28)),
                description=RNG.choice(descriptions),
                amount=round(RNG.uniform(2500, 180000), 2), currency="EUR",
                gl_account=f"6{RNG.randint(100, 999)}", source_system="SAP S/4HANA"))
    db.flush()

    # ---------------- PCFs -------------------------------------------------
    from app.modules.lca import service as lca_service
    for idx, product in enumerate(products):
        boundary = LCABoundary.CRADLE_TO_GRAVE if idx == 0 else LCABoundary.CRADLE_TO_GATE
        computed = lca_service.compute_pcf(
            db, product, boundary=boundary, reference_period=CURRENT_YEAR,
            end_of_life_scenario="recycling" if idx == 0 else "mixed",
            include_use_phase_kwh_per_year=1400.0 if idx == 0 else None)
        pcf = lca_service.persist_pcf(db, product, computed)
        if idx == 0:
            pcf.status = PCFStatus.CERTIFIED
            pcf.peer_reviewer = "Dr. Helena Brandt"
            pcf.peer_reviewed_at = datetime(CURRENT_YEAR, 4, 12, tzinfo=timezone.utc)
            pcf.verifier = "Northstar Assurance"
            pcf.verified_at = datetime(CURRENT_YEAR, 5, 20, tzinfo=timezone.utc)
            pcf.certification_ref = f"ISO14067-{CURRENT_YEAR}-MP4200"
        elif idx == 1:
            pcf.status = PCFStatus.VERIFIED
            pcf.peer_reviewer = "Dr. Helena Brandt"
            pcf.peer_reviewed_at = datetime(CURRENT_YEAR, 4, 14, tzinfo=timezone.utc)
            pcf.verifier = "Northstar Assurance"
            pcf.verified_at = datetime(CURRENT_YEAR, 6, 2, tzinfo=timezone.utc)
        elif idx == 2:
            pcf.status = PCFStatus.PEER_REVIEWED
            pcf.peer_reviewer = "Yuki Tanaka"
            pcf.peer_reviewed_at = datetime(CURRENT_YEAR, 5, 3, tzinfo=timezone.utc)
        db.add(Evidence(organization_id=org.id, object_type="pcf", object_id=pcf.id,
                        title=f"Primary data pack - {product.sku}",
                        evidence_type="data_pack", status=EvidenceStatus.ACCEPTED,
                        uploaded_by_id=users["product_rnd"].id))
    db.flush()

    # ---------------- supplier engagement ---------------------------------
    questions = [
        {"code": "q1", "type": "choice", "required": True,
         "options": ["yes", "no", "partially"],
         "text": {"en": "Do you measure Scope 1 and 2 emissions?",
                  "de": "Erfassen Sie Scope-1- und Scope-2-Emissionen?",
                  "fr": "Mesurez-vous les emissions de scope 1 et 2 ?",
                  "zh-CN": "贵司是否核算范围一和范围二排放?"}},
        {"code": "scope1_tco2e", "type": "number", "required": True, "min": 0,
         "evidence_required": True,
         "text": {"en": "Reported Scope 1 emissions (tCO2e)",
                  "de": "Gemeldete Scope-1-Emissionen (tCO2e)"}},
        {"code": "scope2_tco2e", "type": "number", "required": True, "min": 0,
         "text": {"en": "Reported Scope 2 emissions, market-based (tCO2e)"}},
        {"code": "scope3_measured", "type": "choice", "required": False,
         "options": ["yes", "no"],
         "text": {"en": "Do you measure Scope 3 emissions?"}},
        {"code": "has_reduction_target", "type": "choice", "required": True,
         "options": ["yes", "no"], "text": {"en": "Do you have a reduction target?"}},
        {"code": "sbti_committed", "type": "choice", "required": False,
         "options": ["yes", "no"], "text": {"en": "Are your targets SBTi validated?"}},
        {"code": "renewable_share_pct", "type": "number", "required": False,
         "min": 0, "max": 100, "text": {"en": "Share of renewable electricity (%)"}},
        {"code": "reduction_achieved_pct", "type": "number", "required": False,
         "min": -100, "max": 100,
         "text": {"en": "Reduction achieved versus prior year (%)"}},
        {"code": "product_pcf_available", "type": "choice", "required": False,
         "options": ["yes", "no"],
         "text": {"en": "Can you provide product carbon footprints on request?"}},
        {"code": "primary_data_share_pct", "type": "number", "required": False,
         "min": 0, "max": 100, "text": {"en": "Share of primary data in your inventory (%)"}},
    ]
    questionnaire = Questionnaire(
        name="Supplier Climate Disclosure 2025", framework="GHG Protocol / CDP aligned",
        materiality_level="standard",
        target_categories=["Metals", "Electronics", "Logistics", "Polymers",
                           "Chemicals", "Packaging", "Raw materials"],
        languages=settings.supported_languages, questions=questions, version="2.0")
    db.add(questionnaire)
    light = Questionnaire(
        name="Supplier Screening (light)", framework="internal",
        materiality_level="light", languages=settings.supported_languages,
        questions=questions[:4], version="1.0")
    db.add(light)
    db.flush()

    campaign = Campaign(organization_id=org.id, questionnaire_id=questionnaire.id,
                        name="Scope 3 primary data campaign 2025",
                        reporting_year=CURRENT_YEAR,
                        due_date=date(CURRENT_YEAR, 11, 30), status="active",
                        invited_count=len(suppliers))
    db.add(campaign)
    db.flush()

    now = datetime.now(timezone.utc)
    for supplier in suppliers:
        invitation = SupplierInvitation(
            campaign_id=campaign.id, supplier_id=supplier.id,
            language=supplier.language, sent_at=now - timedelta(days=40),
            access_token=f"tok-{supplier.code.lower()}",
            reminders_sent=RNG.randint(0, 3))
        db.add(invitation)
        roll = RNG.random()
        if roll < 0.45:
            status = SubmissionStatus.ATTESTED
        elif roll < 0.62:
            status = SubmissionStatus.SUBMITTED
        elif roll < 0.78:
            status = SubmissionStatus.IN_PROGRESS
        else:
            status = SubmissionStatus.NOT_STARTED
        answered = status in (SubmissionStatus.ATTESTED, SubmissionStatus.SUBMITTED,
                              SubmissionStatus.IN_PROGRESS)
        answers = {}
        if answered:
            answers = {
                "q1": RNG.choice(["yes", "yes", "partially"]),
                "scope1_tco2e": round(RNG.uniform(900, 42000), 1),
                "scope2_tco2e": round(RNG.uniform(400, 26000), 1),
                "scope3_measured": RNG.choice(["yes", "no"]),
                "has_reduction_target": RNG.choice(["yes", "yes", "no"]),
                "sbti_committed": RNG.choice(["yes", "no", "no"]),
                "renewable_share_pct": round(RNG.uniform(5, 90), 1),
                "reduction_achieved_pct": round(RNG.uniform(-4, 14), 1),
                "product_pcf_available": RNG.choice(["yes", "no"]),
                "primary_data_share_pct": round(RNG.uniform(20, 95), 1),
            }
            if status == SubmissionStatus.IN_PROGRESS:
                for key in ("sbti_committed", "renewable_share_pct",
                            "primary_data_share_pct", "product_pcf_available"):
                    answers.pop(key, None)
        completeness = round(len(answers) / len(questions) * 100, 1) if answers else 0.0
        submission = Submission(
            campaign_id=campaign.id, supplier_id=supplier.id,
            questionnaire_id=questionnaire.id, reporting_year=CURRENT_YEAR,
            status=status, answers=answers,
            capture_channel=RNG.choice(["form", "form", "api", "ocr", "mobile"]),
            completeness_pct=completeness,
            attested=status == SubmissionStatus.ATTESTED,
            attested_by=supplier.contact_name if status == SubmissionStatus.ATTESTED else "",
            attested_at=now - timedelta(days=RNG.randint(2, 25))
            if status == SubmissionStatus.ATTESTED else None,
            submitted_at=now - timedelta(days=RNG.randint(2, 30)) if answered else None)
        db.add(submission)
        invitation.progress_pct = completeness
        invitation.status = status
        supplier.onboarding_status = "responded" if answered else "invited"
        if answered:
            db.add(Evidence(organization_id=org.id, object_type="submission",
                            object_id=supplier.id,
                            title=f"{supplier.name} - energy invoice bundle",
                            evidence_type="invoice",
                            status=EvidenceStatus.OCR_EXTRACTED,
                            ocr_text=f"Invoice {supplier.code}-2025-04  Total 48,220 kWh  "
                                     f"Period 2025-01-01 to 2025-03-31  Amount 12,480.55 EUR",
                            extracted_fields={"total_kwh": 48220.0,
                                              "total_amount": 12480.55,
                                              "currency": "EUR"}))
    campaign.responded_count = db.scalar(
        select(func.count()).select_from(Submission).where(
            Submission.campaign_id == campaign.id,
            Submission.status.in_([SubmissionStatus.SUBMITTED,
                                   SubmissionStatus.ATTESTED]))) or 0
    db.flush()

    from app.modules.suppliers import service as supplier_service
    for year in (CURRENT_YEAR - 1, CURRENT_YEAR):
        for supplier in suppliers:
            supplier_service.compute_scorecard(db, supplier, year)
        supplier_service.rank_scorecards(db, year, org.id)
    db.flush()

    for supplier in suppliers[:8]:
        db.add(ActionPlan(
            organization_id=org.id, supplier_id=supplier.id, object_type="supplier",
            object_id=supplier.id,
            plan_type=RNG.choice(["improvement", "joint_project", "remediation"]),
            title=f"Decarbonization plan - {supplier.name}",
            description="Agreed actions: renewable electricity contract, primary-data "
                        "reporting, and a validated reduction target.",
            owner="Carlos Mendes",
            assistance_offered="Joint funding for energy audit; PCF training",
            due_date=date(CURRENT_YEAR + 1, 6, 30),
            priority="high" if supplier.is_critical else "medium",
            expected_abatement_tco2e=round(RNG.uniform(400, 5200), 1),
            progress_pct=round(RNG.uniform(0, 70), 1)))

    decision = ProcurementDecision(
        organization_id=org.id, title="Casting supply tender 2026", category="Metals",
        carbon_weight_pct=25.0, internal_carbon_price=90.0)
    db.add(decision)
    db.flush()
    bid_specs = [(0, 1_180_000, 2.29, 0.14, 42000, 1200), (1, 1_240_000, 1.86, 0.31, 39000, 1100),
                 (9, 1_090_000, 2.61, 0.09, 46000, 1400), (10, 1_390_000, 1.42, 0.55, 35000, 900)]
    for sidx, price, embodied, logistics, op_cost, op_kg in bid_specs:
        db.add(Bid(decision_id=decision.id, supplier_id=suppliers[sidx].id,
                   price=price / 1000, quantity=1000, embodied_kgco2e_per_unit=embodied,
                   logistics_kgco2e_per_unit=logistics, lifetime_years=5,
                   annual_operating_cost=op_cost, annual_operating_kgco2e=op_kg,
                   quality_score=RNG.uniform(62, 92)))
    db.flush()
    supplier_service.score_bids(db, decision)

    # ---------------- targets, baselines, intensity, levers ---------------
    for entity in [group_entity] + entities:
        for scope in Scope:
            kg = db.scalar(select(func.coalesce(func.sum(Emission.co2e_kg), 0.0)).where(
                Emission.entity_id == entity.id, Emission.year == 2022,
                Emission.scope == scope, Emission.scenario_id.is_(None))) or 0.0
            if kg:
                db.add(Baseline(entity_id=entity.id, year=2022, scope=scope,
                                co2e_tonnes=round(float(kg) / 1000, 3), locked=True))
    db.flush()

    base_kg = db.scalar(select(func.coalesce(func.sum(Emission.co2e_kg), 0.0)).where(
        Emission.year == 2022, Emission.scenario_id.is_(None))) or 0.0
    base_t = float(base_kg) / 1000
    for entity, share in ((group_entity, 1.0), (entities[0], 0.34), (entities[3], 0.23)):
        db.add(Target(
            entity_id=entity.id,
            name=f"{entity.name} - 42% absolute reduction by 2030",
            target_type="absolute", scopes_covered=[Scope.SCOPE_1, Scope.SCOPE_2],
            base_year=2022, base_value=round(base_t * share, 3), target_year=2030,
            reduction_pct=42.0, sbti_validated=True, sbti_ambition="1.5C",
            trajectory=[{"year": y,
                         "allowed_tco2e": round(base_t * share * (1 - 0.42 * (y - 2022) / 8), 3)}
                        for y in range(2022, 2031)]))
    db.add(Target(entity_id=group_entity.id, name="Net zero across all scopes by 2050",
                  target_type="net_zero", scopes_covered=[s.value for s in Scope],
                  base_year=2022, base_value=round(base_t, 3), target_year=2050,
                  reduction_pct=90.0, sbti_validated=True, sbti_ambition="1.5C"))
    db.add(Target(entity_id=group_entity.id,
                  name="Intensity: 50% reduction per EUR million revenue by 2030",
                  target_type="intensity", scopes_covered=[s.value for s in Scope],
                  base_year=2022, base_value=round(base_t / 1850, 4), target_year=2030,
                  reduction_pct=50.0, intensity_denominator="EUR million revenue"))

    lever_specs = [
        ("On-site solar PV - Stuttgart", "renewable_energy", Scope.SCOPE_2, 4_200_000, -320_000, 5800, 2026, 2028, "mature"),
        ("Corporate renewable PPA (EU portfolio)", "renewable_energy", Scope.SCOPE_2, 800_000, -140_000, 21500, 2026, 2027, "mature"),
        ("Electrify process heat - Wroclaw", "electrification", Scope.SCOPE_1, 9_600_000, 180_000, 7400, 2027, 2031, "emerging"),
        ("Heat recovery on furnaces", "energy_efficiency", Scope.SCOPE_1, 2_100_000, -410_000, 3100, 2026, 2028, "mature"),
        ("Fleet electrification (light vehicles)", "electrification", Scope.SCOPE_1, 3_400_000, -260_000, 1450, 2026, 2030, "mature"),
        ("Green steel procurement (30% volume)", "supply_chain", Scope.SCOPE_3, 0, 5_800_000, 46000, 2027, 2032, "emerging"),
        ("Supplier engagement programme (top 50)", "supply_chain", Scope.SCOPE_3, 900_000, 220_000, 32000, 2026, 2030, "mature"),
        ("Modal shift sea to rail", "logistics", Scope.SCOPE_3, 150_000, -85_000, 4800, 2026, 2028, "mature"),
        ("Recycled aluminium substitution", "materials", Scope.SCOPE_3, 600_000, 340_000, 12800, 2027, 2030, "mature"),
        ("Product efficiency redesign (use phase)", "product_design", Scope.SCOPE_3, 5_200_000, -900_000, 58000, 2027, 2033, "emerging"),
        ("Refrigerant replacement programme", "process", Scope.SCOPE_1, 700_000, 40_000, 620, 2026, 2028, "mature"),
        ("Carbon capture pilot - Cleveland", "process", Scope.SCOPE_1, 18_000_000, 2_400_000, 9200, 2031, 2038, "early"),
    ]
    initiatives = []
    for name, cat, scope, capex, opex, abatement, start, end, readiness in lever_specs:
        init = ReductionInitiative(
            entity_id=group_entity.id, name=name, lever_category=cat, scope=scope,
            description=f"{name} - modelled lever with abatement and cost profile.",
            status=RNG.choice(["proposed", "approved", "in_delivery"]),
            start_year=start, end_year=end, capex=capex, annual_opex_delta=opex,
            annual_abatement_tco2e=abatement, lifetime_years=max(5, end - start + 5),
            technology_readiness=readiness,
            progress_pct=round(RNG.uniform(0, 55), 1),
            realized_abatement_tco2e=round(abatement * RNG.uniform(0, 0.4), 1))
        db.add(init)
        initiatives.append(init)
    db.flush()

    # ---------------- carbon finance ---------------------------------------
    db.add(InternalCarbonPrice(
        organization_id=org.id, name="Group shadow price 2026", price_type="shadow",
        price_per_tonne=90.0, currency="EUR", effective_from=date(2026, 1, 1),
        scopes_covered=[s.value for s in Scope], applies_to="capex_decisions",
        is_active=True))
    db.add(InternalCarbonPrice(
        organization_id=org.id, name="Internal fee (pilot)", price_type="fee",
        price_per_tonne=45.0, currency="EUR", effective_from=date(2025, 1, 1),
        scopes_covered=[Scope.SCOPE_1, Scope.SCOPE_2],
        applies_to="business_unit_charge", is_active=False))

    for entity in [group_entity] + entities[:4]:
        kg = db.scalar(select(func.coalesce(func.sum(Emission.co2e_kg), 0.0)).where(
            Emission.entity_id == entity.id, Emission.year == CURRENT_YEAR,
            Emission.scenario_id.is_(None))) or 0.0
        db.add(CarbonBudget(entity_id=entity.id, year=CURRENT_YEAR, scope="all",
                            budget_tco2e=round(float(kg) / 1000 * 1.05, 3),
                            owner="Iris Delacroix"))

    credit_specs = [
        ("Kariba REDD+ Forest Protection", "Verra", "ARR", "ZW", 2022, 18000, 9.5, CreditStatus.RETIRED, False),
        ("Enhanced Rock Weathering - Oman", "Puro.earth", "Removal", "OM", 2024, 4200, 128.0, CreditStatus.RETIRED, True),
        ("Biochar Carbon Removal - Finland", "Puro.earth", "Removal", "FI", 2024, 6800, 142.0, CreditStatus.HELD, True),
        ("Improved Cookstoves - Kenya", "Gold Standard", "Efficiency", "KE", 2023, 12500, 11.2, CreditStatus.HELD, False),
        ("Direct Air Capture - Iceland", "Puro.earth", "Removal", "IS", 2025, 900, 480.0, CreditStatus.HELD, True),
    ]
    for name, registry, ptype, country, vintage, qty, price, status, removal in credit_specs:
        credit = CreditOffset(
            organization_id=org.id, project_name=name, registry=registry,
            serial_number=f"{registry[:3].upper()}-{vintage}-{RNG.randint(100000, 999999)}",
            project_type=ptype, country=country, vintage_year=vintage,
            quantity_tco2e=qty, price_per_tonne=price, currency="EUR",
            status=status, is_removal=removal)
        db.add(credit)
        db.flush()
        if status == CreditStatus.RETIRED:
            ev = Evidence(organization_id=org.id, object_type="credit_offset",
                          object_id=credit.id,
                          title=f"Retirement certificate - {name}",
                          evidence_type="retirement_certificate",
                          status=EvidenceStatus.ACCEPTED,
                          extracted_fields={"registry": registry,
                                            "serial_number": credit.serial_number,
                                            "quantity_tco2e": qty})
            db.add(ev)
            db.flush()
            credit.retired_at = datetime(CURRENT_YEAR, 3, 15, tzinfo=timezone.utc)
            credit.retirement_evidence_id = ev.id
            credit.retirement_reason = "Voluntary retirement against residual emissions"

    for metric, median, best, worst, unit in (
        ("tCO2e per EUR million revenue", 62.0, 21.0, 148.0, "tCO2e/EURm"),
        ("Scope 3 share of total", 78.0, 61.0, 92.0, "%"),
        ("Renewable electricity share", 44.0, 96.0, 8.0, "%"),
    ):
        for year in (CURRENT_YEAR - 1, CURRENT_YEAR):
            db.add(Benchmark(industry="Industrial Manufacturing", metric=metric,
                             year=year, peer_median=median, peer_best=best,
                             peer_worst=worst, unit=unit,
                             source="Sector peer panel (n=42)"))

    # ---------------- compliance ------------------------------------------
    framework_specs = [
        (FrameworkCode.CSRD_ESRS, "Corporate Sustainability Reporting Directive / ESRS",
         "European Commission / EFRAG", "European Union"),
        (FrameworkCode.CBAM, "Carbon Border Adjustment Mechanism",
         "European Commission", "European Union"),
        (FrameworkCode.TCFD, "Task Force on Climate-related Financial Disclosures",
         "FSB / ISSB", "Global"),
        (FrameworkCode.EU_TAXONOMY, "EU Taxonomy Regulation",
         "European Commission", "European Union"),
        (FrameworkCode.SEC_CLIMATE, "SEC Climate-Related Disclosures",
         "U.S. Securities and Exchange Commission", "United States"),
        (FrameworkCode.CDP, "CDP Climate Change Questionnaire", "CDP", "Global"),
    ]
    frameworks = {}
    for code, name, regulator, jurisdiction in framework_specs:
        fw = Framework(code=code, name=name, regulator=regulator,
                       jurisdiction=jurisdiction,
                       description=f"{name} - reporting workspace.")
        db.add(fw)
        frameworks[code] = fw
    db.flush()

    topics = [
        ("E1", "Climate change", 4.8, 4.6, "own_operations"),
        ("E2", "Pollution", 3.2, 2.4, "own_operations"),
        ("E3", "Water and marine resources", 2.8, 2.1, "upstream"),
        ("E4", "Biodiversity and ecosystems", 2.4, 1.8, "upstream"),
        ("E5", "Resource use and circular economy", 4.1, 3.6, "downstream"),
        ("S1", "Own workforce", 3.9, 3.1, "own_operations"),
        ("S2", "Workers in the value chain", 4.2, 2.9, "upstream"),
        ("G1", "Business conduct", 3.4, 3.8, "own_operations"),
    ]
    for code, topic, impact, financial, stage in topics:
        db.add(MaterialityAssessment(
            entity_id=group_entity.id, reporting_year=CURRENT_YEAR, topic_code=code,
            topic=topic, impact_score=impact, financial_score=financial,
            is_material=impact >= 3 or financial >= 3, value_chain_stage=stage,
            rationale=f"Assessed through stakeholder consultation and financial screening.",
            stakeholders_consulted=["Investors", "Customers", "Employees", "Suppliers",
                                    "Regulators", "Local communities"]))

    db.add(TransitionPlan(
        entity_id=group_entity.id, name="Meridian Climate Transition Plan 2026-2050",
        target_year=2050, ambition="net_zero", capex_aligned_pct=38.5,
        levers=[i.name for i in initiatives[:8]],
        milestones=[{"year": 2030, "milestone": "42% absolute reduction in Scope 1+2"},
                    {"year": 2035, "milestone": "100% renewable electricity"},
                    {"year": 2040, "milestone": "50% Scope 3 reduction"},
                    {"year": 2050, "milestone": "Net zero across all scopes"}],
        narrative="Aligned to a 1.5C pathway and validated by SBTi. Capital allocation "
                  "is screened against a EUR 90/tCO2e internal shadow price."))
    db.flush()

    cbam_goods = [
        ("7208 51", "Iron and steel", "Hot-rolled steel plate", 0, "DE", 3200, 1.82, 0.34, "actual", 22.5),
        ("7601 10", "Aluminium", "Unwrought aluminium", 1, "FR", 980, 6.71, 1.92, "actual", 18.0),
        ("7208 39", "Iron and steel", "Cold-rolled coil", 9, "EE", 1450, 2.04, 0.41, "default", 0.0),
        ("2523 29", "Cement", "Portland cement", 8, "ES", 640, 0.78, 0.09, "default", 0.0),
        ("3102 10", "Fertilisers", "Urea", 13, "CN", 220, 1.61, 0.22, "default", 0.0),
    ]
    for quarter in (1, 2, 3, 4):
        declaration = CBAMDeclaration(
            entity_id=entities[0].id, reporting_year=CURRENT_YEAR, quarter=quarter,
            status="submitted" if quarter <= 3 else "draft",
            certificate_price=80.0,
            submitted_at=datetime(CURRENT_YEAR, quarter * 3, 28, tzinfo=timezone.utc)
            if quarter <= 3 else None)
        db.add(declaration)
        db.flush()
        total = 0.0
        for cn, cat, desc, sidx, origin, qty, direct, indirect, basis, paid in cbam_goods:
            quantity = round(qty * RNG.uniform(0.8, 1.2), 2)
            good = CBAMGood(
                declaration_id=declaration.id, cn_code=cn, goods_category=cat,
                description=desc, supplier_id=suppliers[sidx].id,
                origin_country=origin, quantity_tonnes=quantity,
                direct_embedded_tco2e_per_t=direct,
                indirect_embedded_tco2e_per_t=indirect, data_basis=basis,
                supplier_request_status="received" if basis == "actual" else "requested",
                carbon_price_paid=paid * quantity / 1000)
            db.add(good)
            db.flush()
            if basis == "actual":
                ev = Evidence(organization_id=org.id, object_type="cbam_good",
                              object_id=good.id,
                              title=f"Installation emissions report - {desc}",
                              evidence_type="supplier_report",
                              status=EvidenceStatus.ACCEPTED)
                db.add(ev)
                db.flush()
                good.evidence_id = ev.id
            total += (direct + indirect) * quantity
        declaration.total_embedded_tco2e = round(total, 3)
        declaration.certificates_required = round(total, 3)
        declaration.payment_due = round(total * 80.0, 2)
        declaration.payment_status = "paid" if quarter <= 2 else "unpaid"

    risk_specs = [
        ("Carbon price escalation in EU ETS and CBAM", "transition_policy", False,
         "medium", "likely", "high", 8_400_000, 22_600_000, "1.5C orderly"),
        ("Customer decarbonization requirements in tenders", "transition_market", False,
         "short", "almost_certain", "high", 12_000_000, 34_000_000, "1.5C orderly"),
        ("Flood exposure at Wroclaw foundry", "physical_acute", False,
         "medium", "possible", "severe", 4_200_000, 18_500_000, "4C hot house"),
        ("Heat stress reducing productivity in Asia hub", "physical_chronic", False,
         "long", "likely", "moderate", 900_000, 3_800_000, "4C hot house"),
        ("Supply disruption from bauxite region instability", "physical_chronic", False,
         "medium", "possible", "high", 3_100_000, 11_400_000, "2C disorderly"),
        ("Low-carbon product premium", "transition_market", True,
         "short", "likely", "high", 6_500_000, 24_000_000, "1.5C orderly"),
        ("Energy efficiency operating cost savings", "transition_technology", True,
         "medium", "almost_certain", "moderate", 2_800_000, 7_100_000, "1.5C orderly"),
        ("Reputational impact of missed SBTi targets", "transition_reputation", False,
         "short", "possible", "moderate", 1_200_000, 5_600_000, "2C disorderly"),
    ]
    for title, rtype, is_opp, horizon, likelihood, impact, low, high, scenario_ref in risk_specs:
        db.add(ClimateRisk(
            entity_id=group_entity.id, title=title, risk_type=rtype,
            is_opportunity=is_opp, horizon=horizon, likelihood=likelihood,
            impact_rating=impact, financial_impact_low=low, financial_impact_high=high,
            currency="EUR", scenario_ref=scenario_ref,
            mitigation="Hedging, capital plan alignment and supplier diversification.",
            control="Quarterly review by the Board Sustainability Committee.",
            governance_owner="Chief Sustainability Officer"))

    for name, pathway, horizon, price, narrative in (
        ("Orderly 1.5C", "1.5C", 2050, 250.0,
         "Immediate, predictable policy tightening; high transition cost, low physical risk."),
        ("Disorderly 2C", "2C", 2050, 160.0,
         "Delayed action to 2030 then abrupt tightening; elevated transition shock."),
        ("Hot house 4C", "4C", 2050, 25.0,
         "Limited policy response; severe chronic and acute physical risk."),
    ):
        db.add(ClimateScenario(entity_id=group_entity.id, name=name, pathway=pathway,
                               horizon_year=horizon, carbon_price_assumption=price,
                               narrative=narrative,
                               financial_impact={"revenue_at_risk_pct": RNG.uniform(2, 14),
                                                 "capex_required": RNG.uniform(20e6, 180e6)}))

    taxonomy_specs = [
        ("3.1", "Manufacture of renewable energy technologies", True, True, 148_000_000, 42_000_000, 9_800_000),
        ("3.6", "Manufacture of other low carbon technologies", True, True, 96_000_000, 28_000_000, 6_200_000),
        ("3.9", "Manufacture of iron and steel", True, False, 240_000_000, 51_000_000, 12_400_000),
        ("6.5", "Transport by motorbikes, passenger cars and light commercial vehicles", True, False, 18_000_000, 9_000_000, 2_100_000),
        ("7.7", "Acquisition and ownership of buildings", True, True, 0, 34_000_000, 4_600_000),
    ]
    for code, name, eligible, aligned, revenue, capex, opex in taxonomy_specs:
        db.add(TaxonomyActivity(
            entity_id=group_entity.id, reporting_year=CURRENT_YEAR,
            activity_code=code, activity_name=name, objective="climate_mitigation",
            is_eligible=eligible, is_aligned=aligned,
            substantial_contribution_met=aligned,
            technical_criteria={"threshold_met": aligned,
                                "criterion": "Annex I technical screening criteria"},
            dnsh_checks={"climate_adaptation": aligned, "water_and_marine": aligned,
                         "circular_economy": aligned, "pollution_prevention": aligned,
                         "biodiversity": aligned},
            minimum_safeguards_met=True, revenue_amount=revenue,
            capex_amount=capex, opex_amount=opex))

    cdp_specs = [
        ("C1.1", "Governance", "Is there board-level oversight of climate-related issues?",
         "Yes - the Board Sustainability Committee has explicit oversight and meets quarterly.", "A"),
        ("C2.3", "Risks and opportunities", "Have you identified inherent climate-related risks?",
         "Yes - eight risks and opportunities are registered with quantified financial impact.", "A-"),
        ("C4.1", "Targets", "Did you have an emissions target active in the reporting year?",
         "Yes - a 42% absolute reduction target for Scope 1+2 by 2030, SBTi validated.", "A"),
        ("C6.1", "Emissions data", "What were your gross Scope 1 emissions?",
         "Reported from the platform ledger with full calculation lineage.", "A"),
        ("C6.3", "Emissions data", "What were your gross Scope 2 emissions?",
         "Reported location-based and market-based.", "A"),
        ("C6.5", "Emissions data", "Account for your Scope 3 emissions.",
         "All 15 categories screened; 15 reported.", "B"),
        ("C7.9", "Emissions breakdown", "How do your gross emissions compare to the previous year?",
         "Decreased due to renewable procurement and efficiency levers.", "A-"),
        ("C12.1", "Engagement", "Do you engage with your value chain on climate?",
         "Yes - an annual primary-data campaign covering all strategic suppliers.", "B"),
    ]
    for year in (CURRENT_YEAR - 1, CURRENT_YEAR):
        for code, module, question, answer, score in cdp_specs:
            db.add(CDPResponse(
                entity_id=group_entity.id, reporting_year=year, question_code=code,
                question=question, answer=answer if year < CURRENT_YEAR or RNG.random() > 0.25 else "",
                module=module, status=RNG.choice(["draft", "in_review", "approved"]),
                score=score, peer_benchmark_score=RNG.choice(["B", "B-", "C", "A-"]),
                reviewer="Rafael Gomez"))

    disclosure = Disclosure(
        framework_id=frameworks[FrameworkCode.CSRD_ESRS].id,
        entity_id=group_entity.id, reporting_year=CURRENT_YEAR,
        title=f"CSRD/ESRS {CURRENT_YEAR} - Meridian Industrial Group",
        status="draft",
        narrative="Consolidated sustainability statement prepared under ESRS.")
    db.add(disclosure)
    db.flush()

    # ---------------- integrations ----------------------------------------
    connector_specs = [
        ("SAP S/4HANA - Finance & Procurement", "SAP", "enterprise", "rest", "json", None),
        ("Oracle PLM", "Oracle", "enterprise", "graphql", "json", None),
        ("Microsoft Dynamics 365", "Microsoft Dynamics", "enterprise", "rest", "json", None),
        ("NetSuite (Americas)", "NetSuite", "enterprise", "rest", "json", None),
        ("Siemens MES", "MES", "enterprise", "streaming", "json", None),
        ("Blue Yonder WMS", "WMS", "enterprise", "batch", "csv", None),
        ("Transporeon TMS", "TMS", "enterprise", "rest", "xml", None),
        ("Concur Travel & Expense", "Travel", "enterprise", "rest", "json", None),
        ("Utility invoice portal", "Utilities", "operational", "sftp", "csv", None),
        ("Facility IoT sensors", "IoT/Sensors", "operational", "streaming", "json", None),
        ("Fleet telematics (Webfleet)", "Fleet telematics", "operational", "rest", "json", None),
        ("Waste contractor portal", "Waste", "operational", "batch", "csv", None),
        ("HR system (commuting survey)", "HR", "operational", "rest", "json", None),
        ("ecoinvent factor service", "ecoinvent", "external", "rest", "json", "ecoinvent"),
        ("GaBi factor service", "GaBi", "external", "rest", "json", "GaBi"),
        ("IEA grid data feed", "Grid data", "external", "rest", "json", "IEA"),
        ("Weather & climate service", "Weather/climate services", "external", "rest", "json", None),
        ("Commodity index feed", "Commodity indices", "external", "rest", "json", None),
        ("Regulatory update service", "Regulatory updates", "external", "webhook", "json", None),
    ]
    for name, system, category, protocol, fmt, lib_key in connector_specs:
        c = Connector(organization_id=org.id, name=name, system=system,
                      category=category, protocol=protocol, data_format=fmt,
                      endpoint=f"https://api.{system.lower().replace(' ', '').replace('/', '')}.example/v1",
                      credential_ref=f"vault://meridian/{system.lower().replace(' ', '-')}",
                      credential_status="configured",
                      factor_library_id=libraries[lib_key].id if lib_key else None,
                      data_version=libraries[lib_key].version if lib_key else "",
                      status="healthy", health_score=round(RNG.uniform(88, 100), 1),
                      last_sync_at=now - timedelta(hours=RNG.randint(1, 40)),
                      next_sync_at=now + timedelta(hours=RNG.randint(2, 24)),
                      records_synced=RNG.randint(400, 96000))
        db.add(c)
        db.flush()
        for src, tgt_obj, tgt_field in (("PLANT_ID", "activity_data", "facility_id"),
                                        ("MATNR", "activity_data", "activity_key"),
                                        ("MENGE", "activity_data", "quantity"),
                                        ("MEINS", "activity_data", "unit"),
                                        ("BUDAT", "activity_data", "period_start")):
            db.add(FieldMapping(connector_id=c.id, source_field=src,
                                target_object=tgt_obj, target_field=tgt_field,
                                is_required=tgt_field in ("quantity", "unit")))

    # ---------------- scenarios (FR-7.8) ----------------------------------
    from app.modules.analytics import service as analytics_service
    scenario_specs = [
        ("Baseline trajectory (no new action)", "forecast",
         {"entity_id": group_entity.id, "annual_growth_pct": 2.0,
          "annual_grid_decarbonization_pct": 1.5, "supplier_engagement_reduction_pct": 0.0,
          "uncertainty_pct": 16.0}, [], 0.0),
        ("SBTi 1.5C aligned plan", "pathway",
         {"entity_id": group_entity.id, "annual_growth_pct": 1.5,
          "annual_grid_decarbonization_pct": 4.0, "supplier_engagement_reduction_pct": 12.0,
          "uncertainty_pct": 18.0},
         [i.id for i in initiatives[:8]], 90.0),
        ("Aggressive electrification + green steel", "what_if",
         {"entity_id": group_entity.id, "annual_growth_pct": 2.5,
          "annual_grid_decarbonization_pct": 5.0, "supplier_engagement_reduction_pct": 18.0,
          "uncertainty_pct": 22.0},
         [i.id for i in initiatives], 150.0),
    ]
    for name, stype, assumptions, lever_ids, price in scenario_specs:
        s = Scenario(organization_id=org.id, name=name, scenario_type=stype,
                     base_year=CURRENT_YEAR, horizon_year=2035,
                     description=f"{name} - isolated sandbox; never alters actuals.",
                     assumptions=assumptions, selected_lever_ids=lever_ids,
                     internal_carbon_price=price,
                     method_version=settings.default_method_version,
                     factor_library_version=default_lib.version,
                     created_by_id=users["esg_manager"].id)
        db.add(s)
        db.flush()
        analytics_service.run_scenario(db, s)

    # ---------------- analytics passes ------------------------------------
    analytics_service.run_spend_categorization(db)
    analytics_service.detect_anomalies(db)
    for entity in entities[:3]:
        analytics_service.identify_gaps(db, entity_id=entity.id, year=CURRENT_YEAR)
    analytics_service.build_macc(db, entity_id=group_entity.id)

    db.commit()


if __name__ == "__main__":  # pragma: no cover
    from app.core.db import Base, SessionLocal, engine
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_if_empty(session)
    print("Seed complete.")
