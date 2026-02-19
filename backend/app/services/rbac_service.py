"""
RBAC Service

Provides Role-Based Access Control functionality for managing users, roles, and permissions.
Integrates with the 59 granular capabilities defined in the frontend.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.user import User, UserTypeEnum
from app.models.rbac import Role, Permission, user_roles, role_permissions
from app.core.capabilities import Capability


class RBACService:
    """Service for managing roles, permissions, and user assignments."""

    def __init__(self, db: Session):
        self.db = db

    # ===== Permission Management =====

    def get_or_create_permission(
        self,
        name: str,
        resource: str,
        action: str,
        description: Optional[str] = None,
        category: Optional[str] = None,
        is_system: bool = True
    ) -> Permission:
        """
        Get existing permission or create if it doesn't exist.

        Args:
            name: Permission name (e.g., "view_mps")
            resource: Resource name (e.g., "mps")
            action: Action name (e.g., "view")
            description: Human-readable description
            category: Category for grouping (e.g., "Tactical Planning")
            is_system: Whether this is a system permission

        Returns:
            Permission object
        """
        # Check if permission exists
        permission = self.db.query(Permission).filter(Permission.name == name).first()

        if permission:
            return permission

        # Create new permission
        permission = Permission(
            name=name,
            resource=resource,
            action=action,
            description=description,
            category=category,
            is_system=is_system
        )

        self.db.add(permission)

        try:
            self.db.commit()
            self.db.refresh(permission)
        except IntegrityError:
            self.db.rollback()
            # Race condition - another process created it
            permission = self.db.query(Permission).filter(Permission.name == name).first()

        return permission

    def get_permission_by_name(self, name: str) -> Optional[Permission]:
        """Get permission by name."""
        return self.db.query(Permission).filter(Permission.name == name).first()

    def list_permissions(
        self,
        category: Optional[str] = None,
        resource: Optional[str] = None
    ) -> List[Permission]:
        """
        List permissions with optional filtering.

        Args:
            category: Filter by category
            resource: Filter by resource

        Returns:
            List of Permission objects
        """
        query = self.db.query(Permission)

        if category:
            query = query.filter(Permission.category == category)

        if resource:
            query = query.filter(Permission.resource == resource)

        return query.order_by(Permission.category, Permission.name).all()

    # ===== Role Management =====

    def create_role(
        self,
        name: str,
        slug: str,
        description: Optional[str] = None,
        tenant_id: Optional[int] = None,
        permission_names: Optional[List[str]] = None,
        is_system: bool = False
    ) -> Role:
        """
        Create a new role.

        Args:
            name: Role name (e.g., "Demand Planner")
            slug: URL-safe slug (e.g., "demand-planner")
            description: Human-readable description
            tenant_id: Tenant/group ID (None for global roles)
            permission_names: List of permission names to assign
            is_system: Whether this is a system role

        Returns:
            Created Role object
        """
        role = Role(
            name=name,
            slug=slug,
            description=description,
            tenant_id=tenant_id,
            is_system=is_system
        )

        # Assign permissions if provided
        if permission_names:
            for perm_name in permission_names:
                permission = self.get_permission_by_name(perm_name)
                if permission:
                    role.permissions.append(permission)

        self.db.add(role)
        self.db.commit()
        self.db.refresh(role)

        return role

    def get_role_by_id(self, role_id: int) -> Optional[Role]:
        """Get role by ID."""
        return self.db.query(Role).filter(Role.id == role_id).first()

    def get_role_by_slug(self, slug: str, tenant_id: Optional[int] = None) -> Optional[Role]:
        """Get role by slug and tenant."""
        query = self.db.query(Role).filter(Role.slug == slug)

        if tenant_id is not None:
            query = query.filter(Role.tenant_id == tenant_id)
        else:
            query = query.filter(Role.tenant_id.is_(None))

        return query.first()

    def list_roles(self, tenant_id: Optional[int] = None) -> List[Role]:
        """
        List roles, optionally filtered by tenant.

        Args:
            tenant_id: Filter by tenant (None = global roles only, -1 = all roles)

        Returns:
            List of Role objects
        """
        query = self.db.query(Role)

        if tenant_id is None:
            # Global roles only
            query = query.filter(Role.tenant_id.is_(None))
        elif tenant_id >= 0:
            # Specific tenant or global
            query = query.filter(
                (Role.tenant_id == tenant_id) | (Role.tenant_id.is_(None))
            )
        # If tenant_id == -1, return all roles (no filter)

        return query.order_by(Role.name).all()

    def add_permission_to_role(self, role_id: int, permission_name: str) -> bool:
        """
        Add a permission to a role.

        Returns:
            True if successful, False if permission or role not found
        """
        role = self.get_role_by_id(role_id)
        permission = self.get_permission_by_name(permission_name)

        if not role or not permission:
            return False

        if permission not in role.permissions:
            role.permissions.append(permission)
            self.db.commit()

        return True

    def remove_permission_from_role(self, role_id: int, permission_name: str) -> bool:
        """
        Remove a permission from a role.

        Returns:
            True if successful, False if permission or role not found
        """
        role = self.get_role_by_id(role_id)
        permission = self.get_permission_by_name(permission_name)

        if not role or not permission:
            return False

        if permission in role.permissions:
            role.permissions.remove(permission)
            self.db.commit()

        return True

    # ===== User-Role Assignment =====

    def assign_role_to_user(self, user_id: int, role_id: int) -> bool:
        """
        Assign a role to a user.

        Returns:
            True if successful, False if user or role not found
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        role = self.get_role_by_id(role_id)

        if not user or not role:
            return False

        if role not in user.roles:
            user.roles.append(role)
            self.db.commit()

        return True

    def remove_role_from_user(self, user_id: int, role_id: int) -> bool:
        """
        Remove a role from a user.

        Returns:
            True if successful, False if user or role not found
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        role = self.get_role_by_id(role_id)

        if not user or not role:
            return False

        if role in user.roles:
            user.roles.remove(role)
            self.db.commit()

        return True

    def sync_user_capabilities(
        self,
        user_id: int,
        capability_names: List[str],
        tenant_id: Optional[int] = None
    ) -> bool:
        """
        Sync user's capabilities by creating/updating a custom role.

        This creates a user-specific role (if it doesn't exist) and assigns
        the specified capabilities to it.

        Args:
            user_id: User ID
            capability_names: List of capability names (e.g., ["view_mps", "manage_mps"])
            tenant_id: Tenant/group ID

        Returns:
            True if successful, False otherwise
        """
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return False

        # Create user-specific role slug
        role_slug = f"user_{user_id}_custom"

        # Check if user already has a custom role
        custom_role = self.get_role_by_slug(role_slug, tenant_id)

        if not custom_role:
            # Create new custom role
            custom_role = self.create_role(
                name=f"Custom Role for {user.email}",
                slug=role_slug,
                description=f"Custom capability set for user {user.email}",
                tenant_id=tenant_id,
                permission_names=capability_names,
                is_system=False
            )

            # Assign role to user
            if custom_role not in user.roles:
                user.roles.append(custom_role)
        else:
            # Update existing custom role permissions
            # Remove all existing permissions
            custom_role.permissions.clear()

            # Add new permissions
            for cap_name in capability_names:
                permission = self.get_permission_by_name(cap_name)
                if permission:
                    custom_role.permissions.append(permission)

        self.db.commit()
        return True

    def get_user_capabilities(self, user: User) -> List[str]:
        """
        Get all capability names for a user from their assigned roles.

        Args:
            user: User object (with roles eagerly loaded)

        Returns:
            List of capability names (e.g., ["view_mps", "manage_mps"])
        """
        if not user or not user.is_active:
            return []

        # System admins get all capabilities
        if user.is_superuser or user.user_type == UserTypeEnum.SYSTEM_ADMIN:
            return [cap.value for cap in Capability]

        # Collect unique capabilities from all roles
        capabilities = set()

        for role in user.roles:
            for permission in role.permissions:
                capabilities.add(permission.name)

        return list(capabilities)

    def user_has_capability(self, user: User, capability_name: str) -> bool:
        """
        Check if user has a specific capability.

        Args:
            user: User object
            capability_name: Capability name to check

        Returns:
            True if user has the capability
        """
        if not user or not user.is_active:
            return False

        # System admins have all capabilities
        if user.is_superuser or user.user_type == UserTypeEnum.SYSTEM_ADMIN:
            return True

        # Check user's roles
        for role in user.roles:
            if role.has_permission(capability_name):
                return True

        return False


def seed_default_permissions(db: Session) -> None:
    """
    Seed the database with all capability permissions.

    This creates a Permission record for every Capability enum value,
    ensuring RBAC roles can be assigned any capability.

    This should be called during database initialization.
    """
    count = seed_capability_permissions(db)
    print(f"seed_default_permissions: {count} capabilities seeded")


def seed_capability_permissions(db: Session) -> int:
    """
    Seed ALL Capability enum values as permissions.

    This ensures that any capability used in the system has a corresponding
    Permission record, enabling RBAC role assignment to work correctly.

    Returns:
        Number of permissions created or updated
    """
    rbac_service = RBACService(db)
    count = 0

    # Category mappings based on capability naming patterns
    category_map = {
        "dashboard": "Overview",
        "analytics": "Analytics",
        "sc_analytics": "Analytics",
        "uncertainty": "Analytics",
        "insights": "Insights",
        "risk": "Risk Analysis",
        "watchlist": "Risk Analysis",
        "prediction": "Risk Analysis",
        "shipment": "Execution",
        "inventory": "Execution",
        "recommendation": "Recommendations",
        "game": "Simulation",
        "sc_config": "Supply Chain Design",
        "inventory_model": "Supply Chain Design",
        "group_config": "Supply Chain Design",
        "ntier": "Supply Chain Design",
        "order_planning": "Operational Planning",
        "demand_planning": "Demand Planning",
        "forecast": "Demand Planning",
        "supply_planning": "Supply Planning",
        "mps": "Tactical Planning",
        "production_order": "Execution",
        "capacity_planning": "Tactical Planning",
        "supplier": "Execution",
        "inventory_projection": "Operational Planning",
        "sales_forecast": "Demand Planning",
        "consensus_demand": "Demand Planning",
        "scenario": "Planning",
        "monte_carlo": "Planning",
        "fulfillment": "Execution",
        "backorder": "Execution",
        "optimization": "Planning",
        "project_order": "Execution",
        "maintenance_order": "Execution",
        "turnaround_order": "Execution",
        "ai_assistant": "AI & Agents",
        "trm": "AI & Agents",
        "gnn": "AI & Agents",
        "rl": "AI & Agents",
        "model_setup": "AI & Agents",
        "powell": "Powell Framework",
        "atp_ctp": "Powell Framework",
        "executive_dashboard": "Powell Framework",
        "sop_worklist": "Powell Framework",
        "agent_decisions": "Powell Framework",
        "collaboration": "Collaboration",
        "agent_explanation": "AI & Agents",
        "agent_suggestion": "AI & Agents",
        "admin": "Administration",
        "system": "Administration",
        "governance": "Administration",
        "permission": "Administration",
        "approval": "Administration",
        "user": "Administration",
        "user": "Administration",
        "group": "Administration",
    }

    for cap in Capability:
        cap_name = cap.value  # e.g., "view_executive_dashboard"

        # Parse capability name to determine resource and action
        parts = cap_name.split("_", 1)
        if len(parts) == 2:
            action, resource = parts[0], parts[1]
        else:
            action, resource = "access", cap_name

        # Determine category from resource
        category = "Other"
        for key, cat in category_map.items():
            if key in resource.lower():
                category = cat
                break

        # Create description from capability name
        description = cap_name.replace("_", " ").title()

        # Create or get permission
        rbac_service.get_or_create_permission(
            name=cap_name,
            resource=resource,
            action=action,
            description=description,
            category=category,
            is_system=True
        )
        count += 1

    db.commit()
    return count
