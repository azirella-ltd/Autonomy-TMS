"""
Tenant Operating Schedule — Business Hours for Human Oversight.

Defines when human reviewers are available to inspect and override
agent decisions before ERP write-back. The MCP write-back delay
countdown only ticks during these hours.

Timezone resolution chain: Schedule.timezone → Company.time_zone → 'UTC'

Schedule types:
  - STANDARD: Regular weekly business hours (Mon-Fri 8-17, etc.)
  - EXTENDED: Include evenings/weekends for 24/7 operations
  - CUSTOM: Per-day overrides

Holiday calendar: JSON array of ISO date strings when no oversight
is available, regardless of day-of-week schedule.

Extension: Platform-specific model for human oversight scheduling.
Not part of the AWS SC data model.
"""

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Time, Text, JSON,
    ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.sql import func

from app.models.base import Base


class TenantOperatingSchedule(Base):
    """Weekly operating schedule for human oversight availability.

    One row per tenant per day-of-week. If no rows exist for a tenant,
    the system assumes 24/7 availability (no delay pausing).
    """

    __tablename__ = "tenant_operating_schedule"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Day of week: 0=Monday, 1=Tuesday, ..., 6=Sunday (ISO 8601)
    day_of_week = Column(Integer, nullable=False,
                         comment="0=Monday ... 6=Sunday (ISO 8601)")

    # Operating window (local time in tenant's timezone)
    start_time = Column(String(5), nullable=False, default="08:00",
                        comment="HH:MM local time when oversight begins")
    end_time = Column(String(5), nullable=False, default="17:00",
                      comment="HH:MM local time when oversight ends")

    # Whether this day is a working day at all
    is_operating = Column(Boolean, nullable=False, default=True,
                          comment="False = no oversight this day (like weekends)")

    # Metadata
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "day_of_week", name="uq_schedule_tenant_day"),
        Index("idx_schedule_tenant", "tenant_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "day_of_week": self.day_of_week,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "is_operating": self.is_operating,
        }


class TenantHolidayCalendar(Base):
    """Holiday dates when no human oversight is available.

    Overrides the weekly schedule — even if a holiday falls on a
    normally operating day, the delay countdown pauses.
    """

    __tablename__ = "tenant_holiday_calendar"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Holiday date (no time — entire day)
    holiday_date = Column(DateTime, nullable=False,
                          comment="Date of the holiday (date only, no time)")
    name = Column(String(200), nullable=True,
                  comment="Holiday name (e.g., 'New Year', 'Thanksgiving')")
    recurring = Column(Boolean, nullable=False, default=False,
                       comment="If true, repeats annually (month+day)")

    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "holiday_date", name="uq_holiday_tenant_date"),
        Index("idx_holiday_tenant", "tenant_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "holiday_date": self.holiday_date.strftime("%Y-%m-%d") if self.holiday_date else None,
            "name": self.name,
            "recurring": self.recurring,
        }


class TenantOversightConfig(Base):
    """Per-tenant oversight configuration.

    Controls how write-back delays interact with business hours.
    Surfaced in Governance admin alongside the operating schedule.
    """

    __tablename__ = "tenant_oversight_config"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )

    # Timezone for the tenant (IANA format: "America/Chicago", "Europe/Berlin")
    # Falls back to Company.time_zone if not set
    timezone = Column(String(50), nullable=True, default="UTC",
                      comment="IANA timezone for schedule interpretation")

    # Whether write-back delays respect business hours
    respect_business_hours = Column(Boolean, nullable=False, default=True,
                                    comment="Pause delay countdown outside operating hours")

    # Urgent bypass: truly urgent decisions can ignore hours
    urgent_bypass_enabled = Column(Boolean, nullable=False, default=True,
                                   comment="Allow urgent decisions to bypass business hours")
    urgent_bypass_threshold = Column(Float, nullable=False, default=0.85,
                                     comment="Urgency >= this bypasses business hours (0-1)")

    # Weekend/holiday handling
    extend_delay_over_weekends = Column(Boolean, nullable=False, default=True,
                                        comment="Pause countdown on non-operating days")
    max_calendar_delay_hours = Column(Integer, nullable=False, default=72,
                                      comment="Max total calendar time even with pausing (3 days)")

    # On-call: if enabled, one designated user gets notified outside hours
    oncall_enabled = Column(Boolean, nullable=False, default=False,
                            comment="Notify on-call user for decisions outside hours")
    oncall_user_id = Column(Integer, ForeignKey("users.id"), nullable=True,
                            comment="Designated on-call user for after-hours decisions")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "timezone": self.timezone,
            "respect_business_hours": self.respect_business_hours,
            "urgent_bypass_enabled": self.urgent_bypass_enabled,
            "urgent_bypass_threshold": self.urgent_bypass_threshold,
            "extend_delay_over_weekends": self.extend_delay_over_weekends,
            "max_calendar_delay_hours": self.max_calendar_delay_hours,
            "oncall_enabled": self.oncall_enabled,
            "oncall_user_id": self.oncall_user_id,
        }
