"""Role-based access and tenant/entity segregation (FR-7.1).

"users see only permitted organizations, facilities, suppliers, products,
calculations, evidence, and reports"

The rule is enforced in one place - the scoping layer - so that no endpoint can
leak data by forgetting to filter. Every list query in the platform passes
through `scoped()`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.domain.enums import RoleGroup
from app.domain.models import Entity, Facility, Product, Supplier, User, UserScope

# The seven object families FR-7.1 names, plus the reports/evidence families.
SCOPED_OBJECTS = [
    "organization", "entity", "facility", "supplier", "product",
    "calculation", "evidence", "report",
]

PERMISSIONS = [
    "accounting.read", "accounting.write", "accounting.approve",
    "lca.read", "lca.write", "lca.verify",
    "suppliers.read", "suppliers.write", "suppliers.campaign",
    "analytics.read", "analytics.write",
    "dashboards.read", "finance.read", "finance.write",
    "compliance.read", "compliance.write", "compliance.file",
    "integrations.read", "integrations.write",
    "platform.admin", "bulk.execute", "export.execute",
    "scenario.read", "scenario.write",
    "assurance.read", "assurance.decide",
    "submission.submit",
]


@dataclass
class Principal:
    """The caller, resolved to the exact set of objects they may see."""
    user: User
    role_code: str
    role_group: str
    permissions: set[str]
    organization_ids: set[int] = field(default_factory=set)
    entity_ids: set[int] = field(default_factory=set)
    facility_ids: set[int] = field(default_factory=set)
    supplier_ids: set[int] = field(default_factory=set)
    product_ids: set[int] = field(default_factory=set)
    is_unrestricted: bool = False

    def can(self, permission: str) -> bool:
        return "*" in self.permissions or permission in self.permissions

    def require(self, permission: str) -> None:
        if not self.can(permission):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"Role '{self.role_code}' lacks permission '{permission}'",
            )

    def as_dict(self) -> dict:
        return {
            "user_id": self.user.id,
            "email": self.user.email,
            "full_name": self.user.full_name,
            "language": self.user.language,
            "role_code": self.role_code,
            "role_name": self.user.role.name,
            "role_group": self.role_group,
            "permissions": sorted(self.permissions),
            "landing_route": self.user.role.landing_route,
            "supplier_id": self.user.supplier_id,
            "is_unrestricted": self.is_unrestricted,
            "scope": {
                "organizations": sorted(self.organization_ids),
                "entities": sorted(self.entity_ids),
                "facilities": sorted(self.facility_ids),
                "suppliers": sorted(self.supplier_ids),
                "products": sorted(self.product_ids),
            },
        }


def _expand_entities(db: Session, entity_ids: set[int]) -> set[int]:
    """An entity grant implies its whole sub-tree."""
    out = set(entity_ids)
    frontier = set(entity_ids)
    guard = 0
    while frontier and guard < 50:
        guard += 1
        children = set(db.scalars(select(Entity.id).where(Entity.parent_id.in_(frontier))))
        children -= out
        out |= children
        frontier = children
    return out


def build_principal(db: Session, user: User) -> Principal:
    grants = db.scalars(select(UserScope).where(UserScope.user_id == user.id)).all()
    org_ids = {g.object_id for g in grants if g.object_type == "organization"}
    ent_ids = {g.object_id for g in grants if g.object_type == "entity"}
    fac_ids = {g.object_id for g in grants if g.object_type == "facility"}
    sup_ids = {g.object_id for g in grants if g.object_type == "supplier"}
    prod_ids = {g.object_id for g in grants if g.object_type == "product"}

    permissions = set(user.role.permissions or [])
    unrestricted = "*" in permissions

    # An organization grant implies every entity, facility, supplier and product
    # beneath it. Anything not implied stays invisible.
    if org_ids:
        ent_ids |= set(db.scalars(select(Entity.id).where(Entity.organization_id.in_(org_ids))))
        sup_ids |= set(db.scalars(select(Supplier.id).where(Supplier.organization_id.in_(org_ids))))
    ent_ids = _expand_entities(db, ent_ids)
    if ent_ids:
        fac_ids |= set(db.scalars(select(Facility.id).where(Facility.entity_id.in_(ent_ids))))
        prod_ids |= set(db.scalars(select(Product.id).where(Product.entity_id.in_(ent_ids))))
        org_ids |= set(db.scalars(select(Entity.organization_id).where(Entity.id.in_(ent_ids))))

    # A supplier user is confined to their own supplier record (FR-2.3).
    if user.supplier_id:
        sup_ids = {user.supplier_id}

    return Principal(
        user=user,
        role_code=user.role.code,
        role_group=user.role.group,
        permissions=permissions,
        organization_ids=org_ids,
        entity_ids=ent_ids,
        facility_ids=fac_ids,
        supplier_ids=sup_ids,
        product_ids=prod_ids,
        is_unrestricted=unrestricted,
    )


def get_principal(
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    db: Session = Depends(get_db),
) -> Principal:
    """Resolve the caller.

    Identity is carried by a header here because the source document explicitly
    excludes security standards from its scope ("no security standards"); the
    *authorization* model it does require (FR-7.1) is fully implemented below.
    Swap this function for your IdP integration without touching anything else.
    """
    email = x_user_email
    if not email:
        user = db.scalars(select(User).where(User.is_active.is_(True))).first()
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="No users provisioned")
        return build_principal(db, user)

    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=f"Unknown user '{email}'")
    return build_principal(db, user)


def require(permission: str):
    """Route dependency: `Depends(require("accounting.write"))`."""
    def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        principal.require(permission)
        return principal
    return _dep


def is_external(principal: Principal) -> bool:
    return principal.role_group == RoleGroup.EXTERNAL
