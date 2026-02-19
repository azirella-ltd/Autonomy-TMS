from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel
from enum import Enum

from .user import UserCreate, User


class GroupModeEnum(str, Enum):
    """Group operating mode."""
    LEARNING = "learning"      # User education mode
    PRODUCTION = "production"  # Real data, real planning


class ClockModeEnum(str, Enum):
    """Clock progression mode for learning groups."""
    TURN_BASED = "turn_based"
    TIMED = "timed"
    REALTIME = "realtime"


class GroupBase(BaseModel):
    name: str
    description: Optional[str] = None
    logo: Optional[str] = None


class GroupCreate(GroupBase):
    admin: UserCreate
    mode: GroupModeEnum = GroupModeEnum.PRODUCTION
    clock_mode: Optional[ClockModeEnum] = None
    round_duration_seconds: Optional[int] = None


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    logo: Optional[str] = None
    mode: Optional[GroupModeEnum] = None
    clock_mode: Optional[ClockModeEnum] = None
    round_duration_seconds: Optional[int] = None
    data_refresh_schedule: Optional[str] = None


class Group(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    logo: Optional[str] = None
    admin: Optional[User] = None
    mode: GroupModeEnum = GroupModeEnum.PRODUCTION
    clock_mode: Optional[ClockModeEnum] = None
    round_duration_seconds: Optional[int] = None
    data_refresh_schedule: Optional[str] = None
    last_data_import: Optional[datetime] = None

    class Config:
        orm_mode = True


class GroupSummary(BaseModel):
    """Lightweight group info for navigation/context purposes."""
    id: int
    name: str
    mode: GroupModeEnum = GroupModeEnum.PRODUCTION
    clock_mode: Optional[ClockModeEnum] = None

    class Config:
        orm_mode = True
