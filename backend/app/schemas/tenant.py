from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
from enum import Enum

from .user import UserCreate, User


class TenantModeEnum(str, Enum):
    """Tenant operating mode."""
    LEARNING = "learning"      # User education mode
    PRODUCTION = "production"  # Real data, real planning


class ClockModeEnum(str, Enum):
    """Clock progression mode for learning tenants."""
    TURN_BASED = "turn_based"
    TIMED = "timed"
    REALTIME = "realtime"


class TenantBase(BaseModel):
    name: str
    description: Optional[str] = None
    logo: Optional[str] = None


class TenantCreate(TenantBase):
    admin: UserCreate
    mode: TenantModeEnum = TenantModeEnum.PRODUCTION
    clock_mode: Optional[ClockModeEnum] = None
    round_duration_seconds: Optional[int] = None


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    logo: Optional[str] = None
    mode: Optional[TenantModeEnum] = None
    clock_mode: Optional[ClockModeEnum] = None
    round_duration_seconds: Optional[int] = None
    data_refresh_schedule: Optional[str] = None


class TenantResponse(BaseModel):
    """Tenant response model (full detail)."""
    id: int
    name: str
    description: Optional[str] = None
    logo: Optional[str] = None
    admin: Optional[User] = None
    mode: TenantModeEnum = TenantModeEnum.PRODUCTION
    clock_mode: Optional[ClockModeEnum] = None
    round_duration_seconds: Optional[int] = None
    data_refresh_schedule: Optional[str] = None
    last_data_import: Optional[datetime] = None

    class Config:
        orm_mode = True


class TenantSummary(BaseModel):
    """Lightweight tenant info for navigation/context purposes."""
    id: int
    name: str
    mode: TenantModeEnum = TenantModeEnum.PRODUCTION
    clock_mode: Optional[ClockModeEnum] = None

    class Config:
        orm_mode = True
