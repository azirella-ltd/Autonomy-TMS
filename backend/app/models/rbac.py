"""
Role-Based Access Control (RBAC) Models

Provides fine-grained permission system:
- Permissions: Granular access rights (e.g., "games.create", "users.delete")
- Roles: Collections of permissions (e.g., "Game Manager", "Analytics Viewer")
- User-Role assignments: Users can have multiple roles
- Tenant-scoped roles: Roles can be tenant-specific or global
"""

from typing import TYPE_CHECKING, List
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Table, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime

from .base import Base

# Import for type checking only to avoid circular imports
if TYPE_CHECKING:
    from .user import User
    from .tenant import Tenant


# Association table for many-to-many relationship between roles and permissions
role_permissions = Table(
    'role_permissions',
    Base.metadata,
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    Column('permission_id', Integer, ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True),
    Column('granted', Boolean, default=True, nullable=False),  # Allow deny rules
    Column('created_at', DateTime, default=datetime.utcnow, nullable=False)
)


# Association table for many-to-many relationship between users and roles
user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    Column('assigned_at', DateTime, default=datetime.utcnow, nullable=False),
    Column('assigned_by', Integer, ForeignKey('users.id'), nullable=True),
    Column('expires_at', DateTime, nullable=True)  # Optional expiration
)


class Permission(Base):
    """
    Permission Model

    Represents a granular access right in the system.
    Permissions follow the pattern: resource.action (e.g., "games.create", "users.delete")
    """
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True)

    # Permission Identification
    name = Column(String(100), unique=True, nullable=False, index=True)  # e.g., "games.create"
    resource = Column(String(50), nullable=False, index=True)  # e.g., "games"
    action = Column(String(50), nullable=False, index=True)  # e.g., "create", "read", "update", "delete"

    # Description
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)  # e.g., "Game Management", "User Management"

    # Metadata
    is_system = Column(Boolean, default=False, nullable=False)  # System permissions cannot be deleted
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    roles = relationship("Role", secondary=role_permissions, back_populates="permissions")

    # Unique constraint to prevent duplicate resource.action combinations
    __table_args__ = (
        UniqueConstraint('resource', 'action', name='uq_resource_action'),
    )

    def __repr__(self):
        return f"<Permission {self.name}>"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "resource": self.resource,
            "action": self.action,
            "description": self.description,
            "category": self.category,
            "is_system": self.is_system
        }


class Role(Base):
    """
    Role Model

    Represents a collection of permissions that can be assigned to users.
    Roles can be global (system-wide) or tenant-specific.
    """
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)

    # Role Identification
    name = Column(String(100), nullable=False, index=True)  # e.g., "Game Manager"
    slug = Column(String(100), nullable=False, index=True)  # e.g., "game-manager"
    description = Column(Text, nullable=True)

    # Scope
    is_system = Column(Boolean, default=False, nullable=False)  # System roles cannot be deleted
    tenant_id = Column(Integer, ForeignKey('tenants.id', ondelete='CASCADE'), nullable=True, index=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=True)

    # Relationships
    permissions = relationship("Permission", secondary=role_permissions, back_populates="roles")
    users = relationship(
        "User",
        secondary=user_roles,
        primaryjoin="Role.id==user_roles.c.role_id",
        secondaryjoin="User.id==user_roles.c.user_id",
        back_populates="roles"
    )
    # tenant = relationship("Tenant", back_populates="roles")  # TODO: Add back_populates to Tenant model

    # Unique constraint: role name must be unique per tenant (global roles have tenant_id=NULL)
    __table_args__ = (
        UniqueConstraint('slug', 'tenant_id', name='uq_role_slug_tenant'),
    )

    def __repr__(self):
        scope = f"tenant_{self.tenant_id}" if self.tenant_id else "global"
        return f"<Role {self.name} ({scope})>"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "is_system": self.is_system,
            "tenant_id": self.tenant_id,
            "permission_count": len(self.permissions) if self.permissions else 0,
            "user_count": len(self.users) if self.users else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    def has_permission(self, permission_name: str) -> bool:
        """Check if this role has a specific permission"""
        return any(p.name == permission_name for p in self.permissions)

    def has_resource_action(self, resource: str, action: str) -> bool:
        """Check if this role has permission for a resource.action"""
        return any(
            p.resource == resource and p.action == action
            for p in self.permissions
        )


class RolePermissionGrant(Base):
    """
    Role-Permission Grant Model

    Tracks when permissions were granted/denied to roles.
    This is separate from the association table to maintain audit history.
    """
    __tablename__ = "role_permission_grants"

    id = Column(Integer, primary_key=True, index=True)

    # Grant Details
    role_id = Column(Integer, ForeignKey('roles.id', ondelete='CASCADE'), nullable=False, index=True)
    permission_id = Column(Integer, ForeignKey('permissions.id', ondelete='CASCADE'), nullable=False, index=True)
    granted = Column(Boolean, default=True, nullable=False)  # True = grant, False = deny

    # Audit
    granted_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    granted_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    revoked_by = Column(Integer, ForeignKey('users.id'), nullable=True)

    # Relationships
    role = relationship("Role", foreign_keys=[role_id])
    permission = relationship("Permission", foreign_keys=[permission_id])
    granter = relationship("User", foreign_keys=[granted_by])
    revoker = relationship("User", foreign_keys=[revoked_by])

    def __repr__(self):
        action = "granted" if self.granted else "denied"
        return f"<RolePermissionGrant {action} permission_id={self.permission_id} to role_id={self.role_id}>"


class UserRoleAssignment(Base):
    """
    User-Role Assignment Model

    Tracks when roles were assigned to users with full audit trail.
    This is separate from the association table to maintain detailed history.
    """
    __tablename__ = "user_role_assignments"

    id = Column(Integer, primary_key=True, index=True)

    # Assignment Details
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey('roles.id', ondelete='CASCADE'), nullable=False, index=True)

    # Temporal
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    assigned_by = Column(Integer, ForeignKey('users.id'), nullable=True)
    expires_at = Column(DateTime, nullable=True, index=True)  # Optional expiration
    revoked_at = Column(DateTime, nullable=True)
    revoked_by = Column(Integer, ForeignKey('users.id'), nullable=True)

    # Scope (for temporary role assignments in specific contexts)
    scope = Column(String(100), nullable=True)  # e.g., "game_123", "project_456"

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    role = relationship("Role", foreign_keys=[role_id])
    assigner = relationship("User", foreign_keys=[assigned_by])
    revoker = relationship("User", foreign_keys=[revoked_by])

    def __repr__(self):
        return f"<UserRoleAssignment user_id={self.user_id} role_id={self.role_id}>"

    def is_active(self) -> bool:
        """Check if this role assignment is currently active"""
        now = datetime.utcnow()

        # Check if revoked
        if self.revoked_at:
            return False

        # Check if expired
        if self.expires_at and now > self.expires_at:
            return False

        return True
