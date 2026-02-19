"""
Audit Log Models

Provides comprehensive audit trail for all system actions:
- User actions (login, logout, profile changes)
- Resource operations (create, read, update, delete)
- Permission changes (role assignments, permission grants)
- Configuration changes (settings, supply chain configs)
- Administrative actions (tenant management, user management)
"""

from typing import TYPE_CHECKING, Optional
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Index, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from .base import Base

# Import for type checking only to avoid circular imports
if TYPE_CHECKING:
    from .user import User
    from .tenant import Tenant


class AuditAction(str, enum.Enum):
    """Types of audit actions"""
    # Authentication
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PASSWORD_CHANGE = "password_change"
    PASSWORD_RESET = "password_reset"
    MFA_ENABLE = "mfa_enable"
    MFA_DISABLE = "mfa_disable"

    # CRUD Operations
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"

    # Permissions
    ROLE_ASSIGN = "role_assign"
    ROLE_REVOKE = "role_revoke"
    PERMISSION_GRANT = "permission_grant"
    PERMISSION_REVOKE = "permission_revoke"

    # Administrative
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"
    USER_ACTIVATE = "user_activate"
    USER_DEACTIVATE = "user_deactivate"

    # Tenant
    TENANT_CREATE = "tenant_create"
    TENANT_UPDATE = "tenant_update"
    TENANT_DELETE = "tenant_delete"

    # SSO
    SSO_LOGIN = "sso_login"
    SSO_PROVIDER_CREATE = "sso_provider_create"
    SSO_PROVIDER_UPDATE = "sso_provider_update"
    SSO_PROVIDER_DELETE = "sso_provider_delete"

    # Games
    GAME_CREATE = "game_create"
    GAME_START = "game_start"
    GAME_COMPLETE = "game_complete"
    GAME_DELETE = "game_delete"

    # Configuration
    CONFIG_CREATE = "config_create"
    CONFIG_UPDATE = "config_update"
    CONFIG_DELETE = "config_delete"

    # Export/Import
    DATA_EXPORT = "data_export"
    DATA_IMPORT = "data_import"


class AuditStatus(str, enum.Enum):
    """Status of audited action"""
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"  # Partially completed
    ERROR = "error"      # System error occurred


class AuditLog(Base):
    """
    Audit Log Model

    Records all significant actions in the system for security and compliance.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    # Who
    user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    username = Column(String(100), nullable=True)  # Denormalized for history
    user_email = Column(String(255), nullable=True)  # Denormalized for history

    # What
    action = Column(Enum(AuditAction, name="audit_action"), nullable=False, index=True)
    resource_type = Column(String(50), nullable=True, index=True)  # e.g., "game", "user", "role"
    resource_id = Column(Integer, nullable=True)
    resource_name = Column(String(255), nullable=True)  # Denormalized for readability

    # Details
    description = Column(Text, nullable=True)
    old_value = Column(JSON, nullable=True)  # Previous state (for updates/deletes)
    new_value = Column(JSON, nullable=True)  # New state (for creates/updates)
    changes = Column(JSON, nullable=True)    # Specific fields changed

    # Status
    status = Column(Enum(AuditStatus, name="audit_status"), nullable=False, default=AuditStatus.SUCCESS, index=True)
    error_message = Column(Text, nullable=True)

    # Context
    tenant_id = Column(Integer, ForeignKey('tenants.id', ondelete='CASCADE'), nullable=True, index=True)
    session_id = Column(String(255), nullable=True, index=True)
    correlation_id = Column(String(255), nullable=True, index=True)  # For request tracing

    # Network
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(Text, nullable=True)

    # Additional Data
    extra_data = Column(JSON, nullable=True)  # Additional context-specific data (renamed from metadata to avoid SQLAlchemy conflict)

    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    tenant = relationship("Tenant", back_populates="audit_logs")

    # Composite indexes for common queries
    __table_args__ = (
        Index('idx_audit_tenant_created', 'tenant_id', 'created_at'),
        Index('idx_audit_user_created', 'user_id', 'created_at'),
        Index('idx_audit_resource', 'resource_type', 'resource_id'),
        Index('idx_audit_action_created', 'action', 'created_at'),
        Index('idx_audit_status_created', 'status', 'created_at'),
    )

    def __repr__(self):
        return f"<AuditLog {self.action} by user_id={self.user_id} at {self.created_at}>"

    def to_dict(self):
        """Convert audit log to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "user_email": self.user_email,
            "action": self.action.value if self.action else None,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "resource_name": self.resource_name,
            "description": self.description,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "changes": self.changes,
            "status": self.status.value if self.status else None,
            "error_message": self.error_message,
            "tenant_id": self.tenant_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class AuditLogSummary(Base):
    """
    Audit Log Summary Model

    Aggregated statistics for audit logs (updated periodically).
    Useful for dashboards and reporting without querying full audit logs.
    """
    __tablename__ = "audit_log_summaries"

    id = Column(Integer, primary_key=True, index=True)

    # Scope
    tenant_id = Column(Integer, ForeignKey('tenants.id', ondelete='CASCADE'), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True)

    # Period
    period_start = Column(DateTime, nullable=False, index=True)
    period_end = Column(DateTime, nullable=False, index=True)

    # Statistics
    total_actions = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)

    # By Action Type (JSON for flexibility)
    action_counts = Column(JSON, nullable=True)  # {"login": 150, "create": 45, ...}
    resource_counts = Column(JSON, nullable=True)  # {"game": 30, "user": 10, ...}

    # Most Active
    most_active_users = Column(JSON, nullable=True)  # [{"user_id": 1, "count": 50}, ...]
    most_accessed_resources = Column(JSON, nullable=True)

    # Peak Activity
    peak_hour = Column(Integer, nullable=True)  # 0-23
    peak_day = Column(Integer, nullable=True)   # 0-6 (Monday=0)

    # Metadata
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant")
    user = relationship("User")

    def __repr__(self):
        return f"<AuditLogSummary tenant_id={self.tenant_id} {self.period_start} to {self.period_end}>"
