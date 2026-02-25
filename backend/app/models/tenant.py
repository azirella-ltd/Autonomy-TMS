"""
Tenant Models for Multi-Tenancy

Provides full organizational isolation with:
- Subdomain routing (company1.autonomy.ai)
- Resource quotas and limits
- Custom branding per tenant
- Billing integration
- Complete data isolation
"""

from typing import TYPE_CHECKING
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Text, Enum, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

# IMPORTANT: Must use app.models.base.Base, not app.db.base_class.Base
# to ensure the tenant model is registered in the same SQLAlchemy metadata
try:
    from app.models.base import Base
except ImportError:
    # Fallback for circular import - this is only used during model definition
    from app.db.base_class import Base

# Import for type checking only to avoid circular imports
if TYPE_CHECKING:
    from .user import User
    from .sso_provider import SSOProvider
    from .game import Game
    from .supply_chain_config import SupplyChainConfig
    from .customer import Customer
    from .audit_log import AuditLog


class TenantStatus(str, enum.Enum):
    """Tenant account status"""
    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class BillingPlan(str, enum.Enum):
    """Billing plan types"""
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"


class Tenant(Base):
    """
    Tenant (Organization) Model

    Represents a multi-tenant organization with complete data isolation.
    Extends the Group concept to full organizational management.
    """
    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)

    # Basic Information
    name = Column(String(200), nullable=False, index=True)
    display_name = Column(String(200), nullable=True)  # Marketing/public name
    slug = Column(String(100), unique=True, nullable=False, index=True)  # URL-safe identifier

    # Subdomain Configuration
    subdomain = Column(String(50), unique=True, nullable=False, index=True)
    custom_domain = Column(String(200), nullable=True, unique=True)  # e.g., autonomy.company.com

    # Branding
    logo_url = Column(String(500), nullable=True)
    primary_color = Column(String(7), nullable=True)  # Hex color code
    secondary_color = Column(String(7), nullable=True)
    favicon_url = Column(String(500), nullable=True)

    # Contact Information
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    billing_email = Column(String(255), nullable=True)

    # Address
    address_line1 = Column(String(255), nullable=True)
    address_line2 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    postal_code = Column(String(20), nullable=True)
    country = Column(String(100), nullable=True)

    # Account Status
    status = Column(Enum(TenantStatus, name="tenant_status"), default=TenantStatus.TRIAL, nullable=False, index=True)

    # Billing
    billing_plan = Column(Enum(BillingPlan, name="billing_plan"), default=BillingPlan.FREE, nullable=False)
    stripe_customer_id = Column(String(255), nullable=True, unique=True, index=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    trial_ends_at = Column(DateTime, nullable=True)
    subscription_ends_at = Column(DateTime, nullable=True)

    # Resource Limits
    max_users = Column(Integer, default=50, nullable=False)
    max_games = Column(Integer, default=100, nullable=False)
    max_supply_chain_configs = Column(Integer, default=10, nullable=False)
    max_storage_mb = Column(Integer, default=1000, nullable=False)  # Storage quota in MB

    # Current Usage (tracked for quota enforcement)
    current_user_count = Column(Integer, default=0, nullable=False)
    current_game_count = Column(Integer, default=0, nullable=False)
    current_config_count = Column(Integer, default=0, nullable=False)
    current_storage_mb = Column(Integer, default=0, nullable=False)

    # Features
    features = Column(JSON, default=dict)  # Feature flags: {"ai_agents": true, "analytics": true, ...}

    # Settings
    settings = Column(JSON, default=dict)  # Custom settings

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)  # Soft delete

    # Owner
    # use_alter=True resolves circular FK dependency with users.tenant_id
    owner_id = Column(Integer, ForeignKey('users.id', use_alter=True, name='fk_tenant_owner'), nullable=True)  # Primary account owner

    # Legacy Group Mapping (for backward compatibility)
    customer_id = Column(Integer, ForeignKey('customers.id'), nullable=True, unique=True)

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id], back_populates="owned_tenants")
    users = relationship("User", back_populates="tenant", foreign_keys="User.tenant_id")
    # games = relationship("Game", back_populates="tenant")  # TODO: Add back_populates to Game model
    # supply_chain_configs = relationship("SupplyChainConfig", back_populates="tenant")  # TODO: Add back_populates to SupplyChainConfig model
    sso_providers = relationship("SSOProvider", back_populates="tenant")
    audit_logs = relationship("AuditLog", back_populates="tenant")
    # customer = relationship("Customer", foreign_keys=[customer_id], uselist=False)  # TODO: Add back_populates to Customer model

    def __repr__(self):
        return f"<Tenant {self.name} ({self.subdomain})>"

    def to_dict(self):
        """Convert tenant to dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "slug": self.slug,
            "subdomain": self.subdomain,
            "custom_domain": self.custom_domain,
            "logo_url": self.logo_url,
            "status": self.status.value,
            "billing_plan": self.billing_plan.value,
            "max_users": self.max_users,
            "max_games": self.max_games,
            "current_user_count": self.current_user_count,
            "current_game_count": self.current_game_count,
            "features": self.features,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def is_active(self) -> bool:
        """Check if tenant is active"""
        return self.status == TenantStatus.ACTIVE

    def is_trial(self) -> bool:
        """Check if tenant is on trial"""
        return self.status == TenantStatus.TRIAL

    def is_suspended(self) -> bool:
        """Check if tenant is suspended"""
        return self.status == TenantStatus.SUSPENDED

    def has_quota_remaining(self, resource: str) -> bool:
        """Check if tenant has quota remaining for a resource"""
        quota_map = {
            "users": (self.current_user_count, self.max_users),
            "games": (self.current_game_count, self.max_games),
            "configs": (self.current_config_count, self.max_supply_chain_configs),
            "storage": (self.current_storage_mb, self.max_storage_mb),
        }

        if resource not in quota_map:
            return True

        current, maximum = quota_map[resource]
        return current < maximum

    def has_feature(self, feature_name: str) -> bool:
        """Check if tenant has a specific feature enabled"""
        if not self.features:
            return False
        return self.features.get(feature_name, False)


class TenantInvitation(Base):
    """
    Tenant Invitation Model

    Allows tenant admins to invite new users to their organization
    """
    __tablename__ = "tenant_invitations"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)

    # Invitation Details
    email = Column(String(255), nullable=False, index=True)
    role = Column(String(50), default="USER", nullable=False)  # Role to assign when accepted
    token = Column(String(255), unique=True, nullable=False, index=True)  # Invitation token

    # Status
    status = Column(
        Enum('pending', 'accepted', 'expired', 'revoked', name='invitation_status'),
        default='pending',
        nullable=False,
        index=True
    )

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    accepted_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    # Tracking
    invited_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    accepted_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    # Relationships
    tenant = relationship("Tenant")
    invited_by = relationship("User", foreign_keys=[invited_by_id])
    accepted_by = relationship("User", foreign_keys=[accepted_by_id])

    def __repr__(self):
        return f"<TenantInvitation {self.email} to tenant {self.tenant_id}>"

    def is_valid(self) -> bool:
        """Check if invitation is still valid"""
        if self.status != 'pending':
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True


class TenantUsageLog(Base):
    """
    Tenant Usage Log

    Tracks tenant resource usage over time for billing and analytics
    """
    __tablename__ = "tenant_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)

    # Usage Metrics
    user_count = Column(Integer, default=0)
    game_count = Column(Integer, default=0)
    config_count = Column(Integer, default=0)
    storage_mb = Column(Integer, default=0)

    # API Usage
    api_requests_count = Column(Integer, default=0)

    # Timestamp
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    tenant = relationship("Tenant")

    def __repr__(self):
        return f"<TenantUsageLog tenant_id={self.tenant_id} at {self.recorded_at}>"
