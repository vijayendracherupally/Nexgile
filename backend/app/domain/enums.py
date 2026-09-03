"""Controlled vocabulary. These strings are the platform's language (FR-6)."""
from __future__ import annotations

from enum import StrEnum


class Scope(StrEnum):
    """FR-3.A.1 / .2 / .3"""
    SCOPE_1 = "scope_1"
    SCOPE_2 = "scope_2"
    SCOPE_3 = "scope_3"


class Scope1Source(StrEnum):
    """FR-3.A.1 - the five Scope 1 source types named in the source document."""
    STATIONARY_COMBUSTION = "stationary_combustion"
    MOBILE_COMBUSTION = "mobile_combustion"
    FLEET = "fleet"
    PROCESS = "process"
    FUGITIVE = "fugitive"


class Scope2Method(StrEnum):
    """FR-3.A.2 - both methods are mandatory, not alternatives."""
    LOCATION_BASED = "location_based"
    MARKET_BASED = "market_based"


# FR-3.A.3 - all 15 GHG Protocol Scope 3 categories. None may be omitted.
SCOPE3_CATEGORIES: dict[int, str] = {
    1: "Purchased goods and services",
    2: "Capital goods",
    3: "Fuel- and energy-related activities",
    4: "Upstream transportation and distribution",
    5: "Waste generated in operations",
    6: "Business travel",
    7: "Employee commuting",
    8: "Upstream leased assets",
    9: "Downstream transportation and distribution",
    10: "Processing of sold products",
    11: "Use of sold products",
    12: "End-of-life treatment of sold products",
    13: "Downstream leased assets",
    14: "Franchises",
    15: "Investments",
}

# FR-3.A.3 - the eight data methods the document names for Scope 3.
SCOPE3_DATA_METHODS = [
    "spend_based", "activity_based", "supplier_specific", "asset_based",
    "travel_based", "logistics_based", "use_phase", "end_of_life",
]


class DataOrigin(StrEnum):
    """Where a value physically came from - drives data quality (FR-7.4)."""
    METER = "meter"
    SENSOR = "sensor"
    TELEMATICS = "telematics"
    INVOICE = "invoice"
    RECEIPT = "receipt"
    SPEND = "spend"
    SUPPLIER_PRIMARY = "supplier_primary"
    SURVEY = "survey"
    ERP = "erp"
    ESTIMATED = "estimated"
    GAP_FILLED = "gap_filled"


MEASURED_ORIGINS = {
    DataOrigin.METER, DataOrigin.SENSOR, DataOrigin.TELEMATICS,
    DataOrigin.INVOICE, DataOrigin.SUPPLIER_PRIMARY,
}


class CalculationStatus(StrEnum):
    """FR-7.3 - approval freezes a value; locked values are immutable."""
    DRAFT = "draft"
    CALCULATED = "calculated"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    LOCKED = "locked"
    RESTATED = "restated"
    SUPERSEDED = "superseded"


class ConsolidationMethod(StrEnum):
    """FR-3.A.5 - ownership controls."""
    EQUITY_SHARE = "equity_share"
    FINANCIAL_CONTROL = "financial_control"
    OPERATIONAL_CONTROL = "operational_control"


class AllocationBasis(StrEnum):
    """FR-3.A.4 / FR-3.B.3"""
    MASS = "mass"
    ECONOMIC = "economic"
    PHYSICAL = "physical"
    ENERGY = "energy"
    VOLUME = "volume"
    HEADCOUNT = "headcount"
    FLOOR_AREA = "floor_area"


class LCABoundary(StrEnum):
    """FR-3.B.3"""
    CRADLE_TO_GATE = "cradle_to_gate"
    GATE_TO_GATE = "gate_to_gate"
    CRADLE_TO_GRAVE = "cradle_to_grave"


class PCFStatus(StrEnum):
    """FR-3.B.4 - the review chain the document requires."""
    DRAFT = "draft"
    CALCULATED = "calculated"
    PEER_REVIEWED = "peer_reviewed"
    VERIFIED = "verified"
    CERTIFIED = "certified"


class TransportMode(StrEnum):
    """FR-3.B.2 - multimodal logistics."""
    ROAD = "road"
    RAIL = "rail"
    SEA = "sea"
    AIR = "air"
    INLAND_WATERWAY = "inland_waterway"


class ProductionMode(StrEnum):
    """FR-3.B.2"""
    BATCH = "batch"
    CONTINUOUS = "continuous"


class SubmissionStatus(StrEnum):
    """FR-3.C.2"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    VALIDATED = "validated"
    ATTESTED = "attested"
    REJECTED = "rejected"


class EvidenceStatus(StrEnum):
    """FR-7.4 - evidence status is part of data quality."""
    MISSING = "missing"
    UPLOADED = "uploaded"
    OCR_EXTRACTED = "ocr_extracted"
    VALIDATED = "validated"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class FrameworkCode(StrEnum):
    """FR-4.1 - .5 - exactly the frameworks the document names."""
    CSRD_ESRS = "CSRD_ESRS"
    CBAM = "CBAM"
    TCFD = "TCFD"
    EU_TAXONOMY = "EU_TAXONOMY"
    SEC_CLIMATE = "SEC_CLIMATE"
    CDP = "CDP"


class DisclosureStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    FILED = "filed"
    ASSURED = "assured"


class ConnectorCategory(StrEnum):
    """FR-5.1 / .2 / .3"""
    ENTERPRISE = "enterprise"
    OPERATIONAL = "operational"
    EXTERNAL = "external"


class SyncStatus(StrEnum):
    """FR-5.5"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    NEVER_RUN = "never_run"
    RUNNING = "running"


class TargetType(StrEnum):
    """FR-3.E.1"""
    ABSOLUTE = "absolute"
    INTENSITY = "intensity"
    NET_ZERO = "net_zero"


class CreditStatus(StrEnum):
    """FR-3.E.3"""
    HELD = "held"
    RETIRED = "retired"
    CANCELLED = "cancelled"


class JobStatus(StrEnum):
    """FR-7.7"""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RoleGroup(StrEnum):
    """FR-2.1 / .2 / .3"""
    SUSTAINABILITY = "sustainability"
    BUSINESS = "business"
    EXTERNAL = "external"
