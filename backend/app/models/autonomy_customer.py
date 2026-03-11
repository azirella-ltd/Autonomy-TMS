"""
Autonomy Customer Registry

Tracks platform customers, their paired tenants (production + optional learning),
and the tenant admins. Only accessible by SYSTEM_ADMIN users.

This is a platform-level management table — NOT the AWS SC 'customer' concept
(which is a trading partner via TradingPartner with tpartner_type='customer').
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base


class AutonomyCustomer(Base):
    """
    Registry of Autonomy platform customers.

    Each customer gets a production tenant (required) and optionally a learning
    tenant (clone of Default TBG for training/simulation). The system admin
    (systemadmin@autonomy.com) uses this table to audit all customers and their
    tenant/admin pairings.
    """
    __tablename__ = "autonomy_customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    # Production tenant (required for every customer)
    production_tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="SET NULL"),
                                  nullable=True, index=True)
    production_admin_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                                 nullable=True)

    # Learning tenant (optional)
    learning_tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="SET NULL"),
                                nullable=True, index=True)
    learning_admin_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                               nullable=True)
    has_learning_tenant = Column(Boolean, default=False, nullable=False)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    production_tenant = relationship("Tenant", foreign_keys=[production_tenant_id])
    learning_tenant = relationship("Tenant", foreign_keys=[learning_tenant_id])
    production_admin = relationship("User", foreign_keys=[production_admin_id])
    learning_admin = relationship("User", foreign_keys=[learning_admin_id])

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "production_tenant_id": self.production_tenant_id,
            "production_admin_id": self.production_admin_id,
            "production_tenant_name": self.production_tenant.name if self.production_tenant else None,
            "production_admin_email": self.production_admin.email if self.production_admin else None,
            "learning_tenant_id": self.learning_tenant_id,
            "learning_admin_id": self.learning_admin_id,
            "learning_tenant_name": self.learning_tenant.name if self.learning_tenant else None,
            "learning_admin_email": self.learning_admin.email if self.learning_admin else None,
            "has_learning_tenant": self.has_learning_tenant,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
