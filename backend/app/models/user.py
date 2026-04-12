"""User model — re-exports from canonical azirella-data-model + TMS Pydantic schemas.

The SQLAlchemy User and RefreshToken classes are now defined in
azirella-data-model and re-exported here. The Pydantic schemas
(UserBase, UserCreate, UserUpdate, etc.) stay local because they're
not in the canonical package.

DecisionLevelEnum has moved to app.models.tms.user_extensions
(TMS-specific). Re-exported here for backward compatibility.

Stage 3 Phase 3a — TMS adopts azirella-data-model tenant subpackage.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

try:
    from email_validator import validate_email  # type: ignore  # noqa: F401
except ImportError:
    validate_email = None  # type: ignore

if validate_email is not None:
    from pydantic import EmailStr
else:
    class EmailStr(str):  # type: ignore
        """Fallback when email-validator is unavailable."""
        @classmethod
        def __get_validators__(cls):
            yield cls.validate

        @classmethod
        def validate(cls, value):
            if not isinstance(value, str):
                raise TypeError("string required")
            return value


# ── Canonical re-exports ─────────────────────────────────────────────────────
from azirella_data_model.tenant import User, UserTypeEnum, RefreshToken  # noqa: F401

# ── TMS-specific re-export (backward compat for existing import paths) ───────
from app.models.tms.user_extensions import DecisionLevelEnum  # noqa: F401


# ── Pydantic schemas (TMS-local, not in canonical) ──────────────────────────

class UserBase(BaseModel):
    """Base Pydantic model for User data validation."""
    email: EmailStr
    username: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool = True
    is_superuser: bool = False
    tenant_id: Optional[int] = None
    user_type: UserTypeEnum = Field(default=UserTypeEnum.USER)
    decision_level: Optional[DecisionLevelEnum] = Field(
        default=None,
        description="Decision level determines landing page; capabilities can be customized separately"
    )

    class Config:
        from_attributes = True
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
    tenant_logo: Optional[str] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }


# ── Association table (TMS-local: user ↔ scenario many-to-many) ─────────────
# This table is TMS/SCP-specific (scenarios are app-level, not canonical).
# It must register against the canonical Base metadata so relationships resolve.
from sqlalchemy import Column, Integer, ForeignKey, Table
from azirella_data_model.base import Base

user_scenarios = Table(
    'user_scenarios',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('scenario_id', Integer, ForeignKey('scenarios.id'), primary_key=True)
)
