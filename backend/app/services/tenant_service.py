import logging
import re

from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from ..models import (
    Tenant,
    User,
    SupplyChainConfig,
    Scenario as Game,
    ScenarioStatus as GameStatus,
    ScenarioUser as ScenarioUser,
    ScenarioUserRole as ScenarioUserRole,
    ScenarioUserType as ScenarioUserType,
    ScenarioUserStrategy as ScenarioUserStrategy,
)
from ..models.user import UserTypeEnum
from ..models.supply_chain_config import (
    Node,
    TransportationLane,
    Market,
    MarketDemand,
    NodeType,
)
from ..models.sc_entities import Product, ProductBom
from ..schemas.tenant import TenantCreate, TenantUpdate
from ..core.security import get_password_hash
from app.core.time_buckets import TimeBucket
from .supply_chain_config_service import SupplyChainConfigService
from .bootstrap import DEFAULT_ADMIN_PASSWORD
# Product imported from sc_entities (line 26)

logger = logging.getLogger(__name__)

DEFAULT_SITE_TYPE_DEFINITIONS = [
    {
        "type": "factory",
        "label": "Factory",
        "order": 4,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "distributor",
        "label": "Distributor",
        "order": 3,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "wholesaler",
        "label": "Wholesaler",
        "order": 2,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "retailer",
        "label": "Retailer",
        "order": 1,
        "is_required": False,
        "master_type": "inventory",
    },
    {
        "type": "market_supply",
        "label": "Market Supply",
        "order": 5,
        "is_required": True,
        "master_type": "market_supply",
    },
    {
        "type": "market_demand",
        "label": "Market Demand",
        "order": 0,
        "is_required": True,
        "master_type": "market_demand",
    },
]


class TenantService:
    """Service for managing Autonomy tenants (organization isolation boundary)."""

    def __init__(self, db: Session):
        self.db = db

    def get_tenants(self):
        """Return all tenants."""
        return self.db.query(Tenant).all()

    def get_tenant(self, tenant_id: int) -> Tenant:
        """Return a single tenant by ID, or raise 404."""
        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found",
            )
        return tenant

    def create_tenant(self, tenant_in: TenantCreate) -> Tenant:
        """Create a new tenant with admin user, default SC config, and default scenario."""
        admin_data = tenant_in.admin
        hashed_password = get_password_hash(admin_data.password)
        try:
            admin_user = User(
                username=admin_data.username,
                email=admin_data.email,
                full_name=admin_data.full_name,
                hashed_password=hashed_password,
                user_type=UserTypeEnum.TENANT_ADMIN,
                is_active=True,
                is_superuser=False,
            )
            self.db.add(admin_user)
            self.db.flush()

            # Generate URL-safe slug from tenant name
            slug = re.sub(r'[^a-z0-9]+', '-', tenant_in.name.lower()).strip('-')
            # Ensure uniqueness by appending suffix if needed
            base_slug = slug
            counter = 1
            while self.db.query(Tenant).filter(Tenant.slug == slug).first():
                slug = f"{base_slug}-{counter}"
                counter += 1

            tenant = Tenant(
                name=tenant_in.name,
                slug=slug,
                subdomain=slug[:50],
                description=tenant_in.description,
                logo=tenant_in.logo,
                admin_id=admin_user.id,
            )
            self.db.add(tenant)
            self.db.flush()

            admin_user.tenant_id = tenant.id
            self.db.add(admin_user)

            sc_config = SupplyChainConfig(
                name="Default Supply Chain",
                description="Default supply chain configuration",
                created_by=admin_user.id,
                tenant_id=tenant.id,
                is_active=True,
                time_bucket=TimeBucket.WEEK,
                site_type_definitions=DEFAULT_SITE_TYPE_DEFINITIONS,
            )
            self.db.add(sc_config)
            self.db.flush()

            self.db.commit()
            self.db.refresh(tenant)
            return tenant
        except Exception:
            self.db.rollback()
            logger.exception("Failed to create tenant %s", tenant_in.name)
            raise HTTPException(status_code=500, detail="Error creating tenant")

    def update_tenant(self, tenant_id: int, tenant_update: TenantUpdate) -> Tenant:
        """Update an existing tenant."""
        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        for field, value in tenant_update.dict(exclude_unset=True).items():
            setattr(tenant, field, value)
        self.db.commit()
        self.db.refresh(tenant)
        return tenant

    def delete_tenant(self, tenant_id: int):
        """Delete a tenant by ID."""
        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        self.db.delete(tenant)
        self.db.commit()
        return {"message": "Tenant deleted"}


# Backward compatibility aliases
CustomerService = TenantService
