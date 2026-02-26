"""
SAP User Import Models

Tracks provenance of users imported from SAP S/4HANA and configurable
role mapping rules. Only SC-planning-relevant users are imported.

Extension: Platform-specific tables not part of AWS SC core model.
"""

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, JSON, Text,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.sql import func
from .base import Base


class SAPUserImportLog(Base):
    """
    Audit log for each SAP user import run.

    One row per import execution (preview or commit).
    """
    __tablename__ = "sap_user_import_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
                    nullable=False, index=True)
    connection_id = Column(Integer, nullable=True)

    filter_config = Column(JSON, nullable=False)
    role_mapping_config = Column(JSON, nullable=False)

    is_preview = Column(Boolean, default=True, nullable=False)

    users_discovered = Column(Integer, default=0)
    users_sc_eligible = Column(Integer, default=0)
    users_created = Column(Integer, default=0)
    users_updated = Column(Integer, default=0)
    users_skipped = Column(Integer, default=0)
    users_failed = Column(Integer, default=0)

    errors = Column(JSON, nullable=True)
    warnings = Column(JSON, nullable=True)

    initiated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    started_at = Column(DateTime, server_default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "connection_id": self.connection_id,
            "filter_config": self.filter_config,
            "role_mapping_config": self.role_mapping_config,
            "is_preview": self.is_preview,
            "users_discovered": self.users_discovered,
            "users_sc_eligible": self.users_sc_eligible,
            "users_created": self.users_created,
            "users_updated": self.users_updated,
            "users_skipped": self.users_skipped,
            "users_failed": self.users_failed,
            "errors": self.errors,
            "warnings": self.warnings,
            "initiated_by": self.initiated_by,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
        }


class SAPRoleMapping(Base):
    """
    Configurable mapping from SAP AGR_NAME pattern to Autonomy powell_role.

    Stored per group so each customer can define their own mappings.
    Patterns are evaluated in priority order; first match wins.
    """
    __tablename__ = "sap_role_mappings"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
                    nullable=False, index=True)

    agr_name_pattern = Column(String(100), nullable=False)
    pattern_type = Column(String(10), default="glob", nullable=False)

    powell_role = Column(String(50), nullable=False)
    user_type = Column(String(20), default="USER", nullable=False)

    derive_site_scope_from_werks = Column(Boolean, default=True)
    derive_product_scope_from_matkl = Column(Boolean, default=False)

    priority = Column(Integer, default=100)
    is_active = Column(Boolean, default=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "agr_name_pattern",
                         name="uq_sap_role_mapping_tenant_pattern"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "agr_name_pattern": self.agr_name_pattern,
            "pattern_type": self.pattern_type,
            "powell_role": self.powell_role,
            "user_type": self.user_type,
            "derive_site_scope_from_werks": self.derive_site_scope_from_werks,
            "derive_product_scope_from_matkl": self.derive_product_scope_from_matkl,
            "priority": self.priority,
            "is_active": self.is_active,
            "description": self.description,
        }
