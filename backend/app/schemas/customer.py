from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
from enum import Enum

from .user import UserCreate, User


class CustomerModeEnum(str, Enum):
    """Customer operating mode."""
    LEARNING = "learning"      # User education mode
    PRODUCTION = "production"  # Real data, real planning


class ClockModeEnum(str, Enum):
    """Clock progression mode for learning customers."""
    TURN_BASED = "turn_based"
    TIMED = "timed"
    REALTIME = "realtime"


class CustomerBase(BaseModel):
    name: str
    description: Optional[str] = None
    logo: Optional[str] = None


class CustomerCreate(CustomerBase):
    admin: UserCreate
    mode: CustomerModeEnum = CustomerModeEnum.PRODUCTION
    clock_mode: Optional[ClockModeEnum] = None
    round_duration_seconds: Optional[int] = None


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    logo: Optional[str] = None
    mode: Optional[CustomerModeEnum] = None
    clock_mode: Optional[ClockModeEnum] = None
    round_duration_seconds: Optional[int] = None
    data_refresh_schedule: Optional[str] = None


class Customer(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    logo: Optional[str] = None
    admin: Optional[User] = None
    mode: CustomerModeEnum = CustomerModeEnum.PRODUCTION
    clock_mode: Optional[ClockModeEnum] = None
    round_duration_seconds: Optional[int] = None
    data_refresh_schedule: Optional[str] = None
    last_data_import: Optional[datetime] = None

    class Config:
        orm_mode = True


class CustomerSummary(BaseModel):
    """Lightweight customer info for navigation/context purposes."""
    id: int
    name: str
    mode: CustomerModeEnum = CustomerModeEnum.PRODUCTION
    clock_mode: Optional[ClockModeEnum] = None

    class Config:
        orm_mode = True


# Backward compatibility aliases
GroupModeEnum = CustomerModeEnum
GroupBase = CustomerBase
GroupCreate = CustomerCreate
GroupUpdate = CustomerUpdate
Group = Customer
GroupSummary = CustomerSummary
