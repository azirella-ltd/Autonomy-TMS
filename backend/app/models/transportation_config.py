"""
Transportation Network Configuration

Extends the shared Site and TransportationLane models with TMS-specific
configuration: facility capabilities, lane service profiles, carrier
contracts, and operating schedules.

Shared entities (from supply_chain_config.py):
- SupplyChainConfig: Top-level config container (reused as-is)
- Site: Facility/location nodes (reused — TMS adds FacilityConfig overlay)
- TransportationLane: Origin-destination pairs (reused — TMS adds LaneProfile overlay)

TMS-specific entities (this file):
- FacilityConfig: Dock, yard, operating hours per Site
- LaneProfile: Mode, service level, transit stats per TransportationLane
- CarrierContract: Master agreement between tenant and carrier
- OperatingSchedule: Facility hours by day of week
- YardLocation: Yard spots for trailer/container staging
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Double,
    ForeignKey,
    DateTime,
    Date,
    Boolean,
    JSON,
    Text,
    UniqueConstraint,
    Index,
    Enum as SAEnum,
)
from sqlalchemy.orm import relationship
from datetime import datetime, date, time
from enum import Enum as PyEnum
from .base import Base


# ============================================================================
# Enums
# ============================================================================

class FacilityType(str, PyEnum):
    """TMS facility classification (overlays Site.type)"""
    SHIPPER = "SHIPPER"                 # Origin / loading point
    CONSIGNEE = "CONSIGNEE"             # Destination / delivery point
    TERMINAL = "TERMINAL"               # Carrier terminal (LTL break-bulk)
    CROSS_DOCK = "CROSS_DOCK"           # Cross-dock / transload
    YARD = "YARD"                       # Trailer/container yard
    PORT = "PORT"                       # Ocean port
    RAIL_TERMINAL = "RAIL_TERMINAL"     # Intermodal ramp
    AIRPORT = "AIRPORT"                 # Air cargo terminal
    DEPOT = "DEPOT"                     # Carrier depot / domicile
    BORDER_CROSSING = "BORDER_CROSSING" # Customs / border


class ContractStatus(str, PyEnum):
    """Carrier contract lifecycle"""
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    TERMINATED = "TERMINATED"
    RENEWED = "RENEWED"


class LaneDirection(str, PyEnum):
    """Lane directionality"""
    OUTBOUND = "OUTBOUND"       # From shipper toward consignee
    INBOUND = "INBOUND"         # From supplier toward shipper
    INTER_FACILITY = "INTER_FACILITY"  # Between own facilities
    RETURN = "RETURN"           # Reverse logistics


# ============================================================================
# Facility Configuration
# ============================================================================

class FacilityConfig(Base):
    """
    TMS-specific configuration overlay for a Site
    TMS Entity: facility_config

    Adds dock, yard, and scheduling attributes to the shared Site entity.
    One FacilityConfig per Site per config_id.
    """
    __tablename__ = "facility_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    site_id = Column(Integer, ForeignKey("site.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)

    facility_type = Column(SAEnum(FacilityType, name="facility_type_enum"), nullable=False)

    # Dock configuration
    total_dock_doors = Column(Integer, default=0)
    inbound_dock_doors = Column(Integer, default=0)
    outbound_dock_doors = Column(Integer, default=0)
    avg_load_time_minutes = Column(Integer, default=60, comment="Average loading time per trailer")
    avg_unload_time_minutes = Column(Integer, default=60, comment="Average unloading time per trailer")

    # Yard configuration
    total_yard_spots = Column(Integer, default=0, comment="Total trailer/container staging spots")
    reefer_yard_spots = Column(Integer, default=0, comment="Spots with reefer plug-ins")
    hazmat_capable = Column(Boolean, default=False)

    # Throughput
    max_daily_inbound_loads = Column(Integer, comment="Max loads that can be received per day")
    max_daily_outbound_loads = Column(Integer, comment="Max loads that can be shipped per day")
    avg_daily_volume = Column(Double, comment="Average daily volume (weight or units)")

    # Operating hours (JSON for flexibility, or use OperatingSchedule for detail)
    operating_hours = Column(JSON, comment='{"mon": {"open": "06:00", "close": "22:00"}, ...}')
    timezone = Column(String(50), default="America/Chicago")

    # Appointment requirements
    requires_appointment = Column(Boolean, default=True)
    appointment_lead_time_hrs = Column(Integer, default=24, comment="Min hours before appointment")
    default_appointment_duration_min = Column(Integer, default=60)

    # Capabilities
    capabilities = Column(JSON, comment='["LIVE_LOAD", "DROP_TRAILER", "CROSS_DOCK", "REEFER", "HAZMAT"]')
    equipment_compatible = Column(JSON, comment='["DRY_VAN", "REEFER", "FLATBED", "CONTAINER_40"]')

    # Contact
    shipping_contact_name = Column(String(200))
    shipping_contact_email = Column(String(200))
    shipping_contact_phone = Column(String(50))
    receiving_contact_name = Column(String(200))
    receiving_contact_email = Column(String(200))
    receiving_contact_phone = Column(String(50))

    # Geofence for arrival detection
    geofence_radius_miles = Column(Double, default=0.5)

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    site = relationship("Site")
    config = relationship("SupplyChainConfig")
    yard_locations = relationship("YardLocation", back_populates="facility", cascade="all, delete-orphan")
    operating_schedules = relationship("OperatingSchedule", back_populates="facility", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('site_id', 'config_id', name='uq_facility_config_site_config'),
        Index('idx_facility_config_tenant', 'tenant_id', 'facility_type'),
    )


class OperatingSchedule(Base):
    """
    Facility operating hours by day of week
    TMS Entity: operating_schedule

    Allows detailed per-day scheduling including split shifts and holiday overrides.
    """
    __tablename__ = "operating_schedule"

    id = Column(Integer, primary_key=True, autoincrement=True)
    facility_config_id = Column(Integer, ForeignKey("facility_config.id", ondelete="CASCADE"), nullable=False)

    day_of_week = Column(Integer, nullable=False, comment="0=Monday, 6=Sunday")
    is_open = Column(Boolean, default=True)
    open_time = Column(String(5), comment="HH:MM format, e.g. 06:00")
    close_time = Column(String(5), comment="HH:MM format, e.g. 22:00")

    # Split shift (optional second window)
    open_time_2 = Column(String(5))
    close_time_2 = Column(String(5))

    # Override for specific dates (holidays, closures)
    override_date = Column(Date, comment="If set, this record overrides the day_of_week for this specific date")
    override_reason = Column(String(200))

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    facility = relationship("FacilityConfig", back_populates="operating_schedules")

    __table_args__ = (
        Index('idx_op_schedule_facility', 'facility_config_id', 'day_of_week'),
    )


class YardLocation(Base):
    """
    Yard staging spot for trailers/containers
    TMS Entity: yard_location

    Used by EquipmentRepositionTRM for yard management decisions.
    """
    __tablename__ = "yard_location"

    id = Column(Integer, primary_key=True, autoincrement=True)
    facility_config_id = Column(Integer, ForeignKey("facility_config.id", ondelete="CASCADE"), nullable=False)

    spot_number = Column(String(20), nullable=False)
    zone = Column(String(50), comment="INBOUND, OUTBOUND, STAGING, REEFER, HAZMAT, OVERFLOW")
    has_reefer_plug = Column(Boolean, default=False)
    is_hazmat_approved = Column(Boolean, default=False)
    max_equipment_length_ft = Column(Double, default=53)

    # Current occupancy
    status = Column(String(20), default="EMPTY", comment="EMPTY, OCCUPIED, RESERVED, MAINTENANCE")
    current_equipment_id = Column(Integer, ForeignKey("equipment.id"))
    occupied_since = Column(DateTime)
    expected_departure = Column(DateTime)

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    facility = relationship("FacilityConfig", back_populates="yard_locations")
    current_equipment = relationship("Equipment", foreign_keys=[current_equipment_id])

    __table_args__ = (
        UniqueConstraint('facility_config_id', 'spot_number', name='uq_yard_spot_facility'),
        Index('idx_yard_status', 'facility_config_id', 'status'),
    )


# ============================================================================
# Lane Profile
# ============================================================================

class LaneProfile(Base):
    """
    TMS-specific attributes for a TransportationLane
    TMS Entity: lane_profile

    Adds mode, service level, distance, and performance stats to the
    shared TransportationLane entity.
    """
    __tablename__ = "lane_profile"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lane_id = Column(Integer, ForeignKey("transportation_lane.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)

    # Mode and service
    primary_mode = Column(String(20), nullable=False, comment="FTL, LTL, INTERMODAL, OCEAN, AIR, RAIL")
    alternate_modes = Column(JSON, comment='["LTL", "INTERMODAL"] — fallback modes')
    direction = Column(SAEnum(LaneDirection, name="lane_direction_enum"))

    # Distance and geography
    distance_miles = Column(Double)
    drive_time_hours = Column(Double)
    origin_region = Column(String(100), comment="Geographic region code for origin")
    destination_region = Column(String(100), comment="Geographic region code for destination")
    crosses_border = Column(Boolean, default=False)
    border_crossing_point = Column(String(200))

    # Transit performance (rolling averages, updated by agents)
    avg_transit_days = Column(Double)
    p10_transit_days = Column(Double, comment="10th percentile — best case")
    p50_transit_days = Column(Double, comment="Median transit time")
    p90_transit_days = Column(Double, comment="90th percentile — worst case")
    transit_time_dist = Column(JSON, comment='Stochastic: {"type": "lognormal", "mean": 3.2, "stddev": 0.5}')

    # Volume and utilization
    avg_weekly_volume = Column(Integer, comment="Average loads per week")
    peak_weekly_volume = Column(Integer)
    seasonality_pattern = Column(JSON, comment='Monthly indices: [1.0, 0.9, 1.1, ...] for 12 months')

    # Cost benchmarks
    avg_cost_per_mile = Column(Double)
    benchmark_rate = Column(Double, comment="Market benchmark rate for this lane")
    benchmark_source = Column(String(50), comment="DAT, SONAR, GREENSCREENS")
    benchmark_date = Column(Date)

    # Risk
    disruption_frequency = Column(Double, comment="Disruptions per 100 shipments")
    weather_risk_score = Column(Double, comment="0-1 weather disruption risk")
    congestion_risk_score = Column(Double, comment="0-1 congestion/delay risk")

    is_active = Column(Boolean, default=True)

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    lane = relationship("TransportationLane")
    config = relationship("SupplyChainConfig")

    __table_args__ = (
        UniqueConstraint('lane_id', 'config_id', name='uq_lane_profile_lane_config'),
        Index('idx_lane_profile_mode', 'tenant_id', 'primary_mode'),
        Index('idx_lane_profile_volume', 'tenant_id', 'avg_weekly_volume'),
    )


# ============================================================================
# Carrier Contract
# ============================================================================

class CarrierContract(Base):
    """
    Master agreement between tenant and carrier
    TMS Entity: carrier_contract

    Umbrella contract that governs freight rates, volume commitments,
    service levels, and terms. Individual FreightRate records reference
    the contract they fall under.
    """
    __tablename__ = "carrier_contract"

    id = Column(Integer, primary_key=True, autoincrement=True)
    carrier_id = Column(Integer, ForeignKey("carrier.id", ondelete="CASCADE"), nullable=False)
    contract_number = Column(String(100), nullable=False)
    description = Column(String(500))

    status = Column(SAEnum(ContractStatus, name="contract_status_enum"), nullable=False, default=ContractStatus.DRAFT)

    # Dates
    effective_date = Column(Date, nullable=False)
    expiration_date = Column(Date, nullable=False)
    signed_date = Column(Date)
    notice_period_days = Column(Integer, default=30, comment="Days notice required for termination")
    auto_renew = Column(Boolean, default=False)

    # Volume commitments
    min_annual_volume = Column(Integer, comment="Minimum loads per year")
    max_annual_volume = Column(Integer)
    volume_ytd = Column(Integer, default=0, comment="Year-to-date loads, updated periodically")

    # Financial terms
    payment_terms_days = Column(Integer, default=30, comment="Net 30, Net 45, etc.")
    currency = Column(String(3), default="USD")
    fuel_surcharge_method = Column(String(50), comment="DOE_INDEX, EIA_TABLE, FLAT_PCT, INCLUDED")
    fuel_base_price = Column(Double, comment="Base fuel price for surcharge calculation")

    # Service level agreement
    sla_on_time_pickup_pct = Column(Double, comment="Committed on-time pickup %")
    sla_on_time_delivery_pct = Column(Double, comment="Committed on-time delivery %")
    sla_damage_rate_pct = Column(Double, comment="Max acceptable damage rate %")
    sla_tracking_compliance_pct = Column(Double, comment="Required tracking update %")
    penalty_clauses = Column(JSON, comment='[{"metric": "otd", "threshold": 95, "penalty_per_pct": 500}]')

    # Lanes covered
    lane_scope = Column(String(20), default="SPECIFIED", comment="SPECIFIED, ALL_LANES, REGION")
    covered_regions = Column(JSON, comment='["US_SOUTHEAST", "US_MIDWEST"]')
    covered_modes = Column(JSON, comment='["FTL", "LTL"]')

    # Documents
    contract_document_url = Column(String(500))
    notes = Column(Text)

    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    carrier = relationship("Carrier")

    __table_args__ = (
        UniqueConstraint('tenant_id', 'contract_number', name='uq_contract_tenant_number'),
        Index('idx_contract_carrier', 'carrier_id', 'status'),
        Index('idx_contract_dates', 'effective_date', 'expiration_date'),
    )
