from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING, Any, Dict, List
from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Table, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Enum as SAEnum
from pydantic import BaseModel, Field
from .explainability import ExplainabilityLevel

try:  # pragma: no cover - optional dependency shim for email validation
    from email_validator import validate_email  # type: ignore
except ImportError:  # pragma: no cover
    validate_email = None  # type: ignore

if validate_email is not None:
    from pydantic import EmailStr  # type: ignore
else:
    class EmailStr(str):  # type: ignore
        """Fallback string-only email type when ``email-validator`` is unavailable."""

        @classmethod
        def __get_validators__(cls):
            yield cls.validate

        @classmethod
        def validate(cls, value):
            if not isinstance(value, str):
                raise TypeError("string required")
            return value

from .base import Base

# Import for type checking only to avoid circular imports
if TYPE_CHECKING:
    from .scenario import Scenario
    from .participant import Participant
    from .session import UserSession
    from .auth_models import PasswordHistory, PasswordResetToken
    from .user import RefreshToken
    from .sso_provider import UserSSOMapping
    from .tenant import Tenant
    from .rbac import Role
    from .notification import PushToken, NotificationPreference
    from .supply_plan import SupplyPlanRequest, SupplyPlanComparison, SupplyPlanExport

# Association table for many-to-many relationship between users and scenarios
user_scenarios = Table(
    'user_scenarios',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('scenario_id', Integer, ForeignKey('scenarios.id'), primary_key=True)
)

class UserTypeEnum(str, Enum):
    """Application-level user type classification."""
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    TENANT_ADMIN = "TENANT_ADMIN"
    USER = "USER"


class PowellRoleEnum(str, Enum):
    """
    Powell Framework role classification for Production tenant users.

    Determines landing page routing (fixed) while capabilities can be customized.

    Planning hierarchy:
    - SC_VP: Strategic/CFA level → /executive-dashboard
    - SOP_DIRECTOR: Tactical/S&OP level → /sop-worklist
    - MPS_MANAGER: Operational/TRM level → /insights/actions

    Execution specialists (subordinate to MPS_MANAGER):
    - ATP_ANALYST: ATP fulfillment decisions → /planning/execution/atp-worklist
    - REBALANCING_ANALYST: Inventory transfers → /planning/execution/rebalancing-worklist
    - PO_ANALYST: Purchase order creation → /planning/execution/po-worklist
    - ORDER_TRACKING_ANALYST: Exception handling → /planning/execution/order-tracking-worklist

    Note: DEMO_ALL is a special role for demo users with all capabilities.
    """
    SC_VP = "SC_VP"
    SOP_DIRECTOR = "SOP_DIRECTOR"
    MPS_MANAGER = "MPS_MANAGER"
    ALLOCATION_MANAGER = "ALLOCATION_MANAGER"
    ORDER_PROMISE_MANAGER = "ORDER_PROMISE_MANAGER"
    # TRM Specialist roles (subordinate to MPS_MANAGER)
    ATP_ANALYST = "ATP_ANALYST"
    REBALANCING_ANALYST = "REBALANCING_ANALYST"
    PO_ANALYST = "PO_ANALYST"
    ORDER_TRACKING_ANALYST = "ORDER_TRACKING_ANALYST"
    DEMO_ALL = "DEMO_ALL"  # Special: has all Powell capabilities


class UserBase(BaseModel):
    """Base Pydantic model for User data validation."""
    email: EmailStr
    username: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool = True
    is_superuser: bool = False
    tenant_id: Optional[int] = None
    user_type: UserTypeEnum = Field(default=UserTypeEnum.USER)
    powell_role: Optional[PowellRoleEnum] = Field(
        default=None,
        description="Powell role determines landing page; capabilities can be customized separately"
    )

    class Config:
        from_attributes = True  # Updated from orm_mode in Pydantic v2
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }

class UserCreate(UserBase):
    """Model for creating a new user."""
    password: str = Field(..., min_length=8)

class UserUpdate(UserBase):
    """Model for updating an existing user."""
    email: Optional[EmailStr] = None
    password: Optional[str] = None

class UserPasswordChange(BaseModel):
    """Model for changing a user's password."""
    current_password: str
    new_password: str = Field(..., min_length=8)

class UserInDB(UserBase):
    """Model for user data in the database."""
    id: int
    hashed_password: str
    created_at: datetime
    updated_at: datetime

class UserPublic(UserBase):
    """Public user model (excludes sensitive data)."""
    id: int
    created_at: datetime
    updated_at: datetime
    is_superuser: bool = False
    last_login: Optional[datetime] = None
    
    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }

class User(Base):
    """User model for authentication and authorization."""
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    user_type: Mapped[UserTypeEnum] = mapped_column(
        SAEnum(UserTypeEnum, name="user_type_enum"),
        nullable=False,
        server_default=UserTypeEnum.USER.value,
        default=UserTypeEnum.USER,
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_password_change: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    mfa_secret: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)

    # Powell Framework Role - determines landing page for Production tenant users
    # NULL means use user_type for routing (e.g., TENANT_ADMIN → /admin/production)
    # This is separate from capabilities which can be customized by tenant admin
    powell_role: Mapped[Optional[PowellRoleEnum]] = mapped_column(
        SAEnum(PowellRoleEnum, name="powell_role_enum"),
        nullable=True,
        index=True,
        comment="Powell role determines landing page; capabilities can be customized"
    )

    # Agent Explainability Override (user-level override of tenant default)
    explainability_level_override: Mapped[Optional[ExplainabilityLevel]] = mapped_column(
        SAEnum(ExplainabilityLevel, name="explainability_level_enum"),
        nullable=True,  # NULL means use tenant default
    )

    # Span of Control - Geographic and Product Scope (AIIO Framework)
    # NULL or empty means full access (TENANT_ADMIN always has full access)
    # These reference AWS SC hierarchy tables: site_hierarchy_node, product_hierarchy_node
    site_scope: Mapped[Optional[List]] = mapped_column(
        JSON,
        nullable=True,
        comment="Site hierarchy keys user can access: ['REGION_Americas', 'SITE_DC-West']. NULL = full access."
    )
    product_scope: Mapped[Optional[List]] = mapped_column(
        JSON,
        nullable=True,
        comment="Product hierarchy keys user can access: ['CATEGORY_Electronics', 'FAMILY_Phones']. NULL = full access."
    )
    # Functional scope (optional - for future use)
    functional_scope: Mapped[Optional[List]] = mapped_column(
        JSON,
        nullable=True,
        comment="Functional areas user can access: ['inventory', 'procurement', 'demand']. NULL = full access."
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Helper methods
    @property
    def is_authenticated(self) -> bool:
        """Check if the user is authenticated."""
        return self.is_active

    @property
    def is_tenant_admin(self) -> bool:
        """Check if the user is classified as a tenant administrator."""
        return self.user_type == UserTypeEnum.TENANT_ADMIN

    def has_role(self, role: str) -> bool:
        """Legacy role helper for compatibility with older checks."""
        normalized = (role or "").strip().lower()
        if normalized in {"systemadmin", "system_admin", "superadmin"}:
            return self.user_type == UserTypeEnum.SYSTEM_ADMIN
        if normalized in {"tenantadmin", "tenant_admin", "admin"}:
            return self.user_type == UserTypeEnum.TENANT_ADMIN
        if normalized in {"player", "user"}:
            return self.user_type == UserTypeEnum.USER
        return False

    @property
    def has_full_site_scope(self) -> bool:
        """Check if user has full site access (TENANT_ADMIN or no restrictions)."""
        if self.user_type == UserTypeEnum.TENANT_ADMIN:
            return True
        return not self.site_scope or len(self.site_scope) == 0

    @property
    def has_full_product_scope(self) -> bool:
        """Check if user has full product access (TENANT_ADMIN or no restrictions)."""
        if self.user_type == UserTypeEnum.TENANT_ADMIN:
            return True
        return not self.product_scope or len(self.product_scope) == 0

    @property
    def has_full_scope(self) -> bool:
        """Check if user has full access to all dimensions."""
        return self.has_full_site_scope and self.has_full_product_scope

    def can_access_site(self, site_key: str) -> bool:
        """
        Check if user can access a specific site.

        Args:
            site_key: Site hierarchy key (e.g., 'SITE_DC-West', 'REGION_Americas')

        Returns:
            True if user has access, False otherwise
        """
        if self.has_full_site_scope:
            return True
        if not self.site_scope:
            return True
        # Check if site_key or any of its ancestors are in scope
        # For now, exact match - later can add hierarchy traversal
        return site_key in self.site_scope

    def can_access_product(self, product_key: str) -> bool:
        """
        Check if user can access a specific product.

        Args:
            product_key: Product hierarchy key (e.g., 'PRODUCT_Product-6pk', 'FAMILY_Beverage')

        Returns:
            True if user has access, False otherwise
        """
        if self.has_full_product_scope:
            return True
        if not self.product_scope:
            return True
        # Check if product_key or any of its ancestors are in scope
        # For now, exact match - later can add hierarchy traversal
        return product_key in self.product_scope

    def can_access_functional_area(self, area: str) -> bool:
        """
        Check if user can access a specific functional area.

        Args:
            area: Functional area (e.g., 'inventory', 'procurement', 'demand')

        Returns:
            True if user has access, False otherwise
        """
        if self.user_type == UserTypeEnum.TENANT_ADMIN:
            return True
        if not self.functional_scope or len(self.functional_scope) == 0:
            return True
        return area in self.functional_scope

    def to_dict(self) -> Dict[str, Any]:
        """Convert user object to dictionary."""
        return {
            "id": self.id,
            "email": self.email,
            "username": self.username,
            "full_name": self.full_name,
            "is_active": self.is_active,
            "is_superuser": self.is_superuser,
            "tenant_id": self.tenant_id,
            "user_type": self.user_type.value,
            "site_scope": self.site_scope,
            "product_scope": self.product_scope,
            "functional_scope": self.functional_scope,
            "has_full_scope": self.has_full_scope,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    # Relationships
    scenarios: Mapped[List["Scenario"]] = relationship(
        "Scenario",
        secondary=user_scenarios,
        back_populates="users",
        lazy='selectin'
    )

    scenario_users: Mapped[List["ScenarioUser"]] = relationship("ScenarioUser", back_populates="user", lazy="selectin")
    sessions: Mapped[List["UserSession"]] = relationship(
        "UserSession", 
        back_populates="user", 
        cascade="all, delete-orphan"
    )
    password_history: Mapped[List["PasswordHistory"]] = relationship(
        "PasswordHistory", 
        back_populates="user", 
        cascade="all, delete-orphan"
    )
    password_reset_tokens: Mapped[List["PasswordResetToken"]] = relationship(
        "PasswordResetToken", 
        back_populates="user", 
        cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken", 
        back_populates="user", 
        cascade="all, delete-orphan"
    )
    
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant", back_populates="users", foreign_keys=[tenant_id])
    admin_of_tenant: Mapped[Optional["Tenant"]] = relationship(
        "Tenant", back_populates="admin", uselist=False, foreign_keys="Tenant.admin_id"
    )

    # SSO mappings
    sso_mappings: Mapped[List["UserSSOMapping"]] = relationship(
        "UserSSOMapping",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # Supply plan requests, comparisons, and exports
    supply_plan_requests: Mapped[List["SupplyPlanRequest"]] = relationship(
        "SupplyPlanRequest",
        back_populates="user"
    )
    supply_plan_comparisons: Mapped[List["SupplyPlanComparison"]] = relationship(
        "SupplyPlanComparison",
        back_populates="user"
    )
    supply_plan_exports: Mapped[List["SupplyPlanExport"]] = relationship(
        "SupplyPlanExport",
        back_populates="user"
    )

    # RBAC roles
    roles: Mapped[List["Role"]] = relationship(
        "Role",
        secondary="user_roles",
        primaryjoin="User.id==user_roles.c.user_id",
        secondaryjoin="Role.id==user_roles.c.role_id",
        back_populates="users"
    )

    # Push notification relationships
    push_tokens: Mapped[List["PushToken"]] = relationship(
        "PushToken",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    notification_preferences: Mapped[Optional["NotificationPreference"]] = relationship(
        "NotificationPreference",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )

    # Watchlists relationship
    watchlists: Mapped[List["Watchlist"]] = relationship(
        "Watchlist",
        back_populates="creator",
        foreign_keys="Watchlist.created_by",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.username}>"

class RefreshToken(Base):
    """Refresh token model for JWT token refresh functionality."""
    __tablename__ = "refresh_tokens"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")
