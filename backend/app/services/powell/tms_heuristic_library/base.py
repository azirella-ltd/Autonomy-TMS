"""
TMS Heuristic Library — State Dataclasses and Decision Output

Defines the input state for each of the 11 TMS TRM agents and the
common output format. These mirror the SC heuristic_library/base.py
pattern but with transportation-specific fields.

Each state dataclass serves as:
1. Input to the heuristic function (deterministic fallback)
2. Input to the TRM neural network (when model is available)
3. Feature vector definition for training data generation
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, date


# ============================================================================
# Common Decision Output
# ============================================================================

@dataclass(frozen=True)
class TMSHeuristicDecision:
    """Output of any TMS heuristic computation.

    Mirrors HeuristicDecision from SC library but with TMS context.
    """
    trm_type: str                          # Which TRM produced this
    action: int                            # Discrete action index
    quantity: float = 0.0                  # Continuous parameter (loads, hours, etc.)
    reasoning: str = ""                    # Human-readable explanation
    confidence: float = 1.0               # Always 1.0 for heuristics
    urgency: float = 0.5                  # 0-1 urgency signal
    params_used: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# 1. Capacity Promise State (replaces ATPState)
# ============================================================================

@dataclass
class CapacityPromiseState:
    """Input state for CapacityPromiseTRM.

    Evaluates whether a shipment request can be fulfilled given
    available carrier capacity on the requested lane/date.
    """
    # Request
    shipment_id: int = 0
    lane_id: int = 0
    requested_date: Optional[datetime] = None
    requested_loads: int = 1
    mode: str = "FTL"
    priority: int = 3                      # 1=critical, 5=low

    # Available capacity (from capacity buffer / committed)
    committed_capacity: int = 0            # Loads already committed on this lane/date
    total_capacity: int = 0                # Total carrier capacity (contracts + spot)
    buffer_capacity: int = 0               # Buffer above forecast

    # Demand context
    forecast_loads: int = 0                # Forecasted loads for this lane/date
    booked_loads: int = 0                  # Already booked

    # Carrier context
    primary_carrier_available: bool = True
    backup_carriers_count: int = 0
    spot_rate_premium_pct: float = 0.0     # How much spot exceeds contract

    def available_capacity(self) -> int:
        return max(0, self.total_capacity - self.booked_loads)

    def utilization_pct(self) -> float:
        if self.total_capacity == 0:
            return 1.0
        return self.booked_loads / self.total_capacity


# ============================================================================
# 2. Shipment Tracking State (replaces OrderTrackingState)
# ============================================================================

@dataclass
class ShipmentTrackingState:
    """Input state for ShipmentTrackingTRM.

    Evaluates shipment progress and detects exceptions based on
    tracking events from p44, carrier EDI, or manual updates.
    """
    shipment_id: int = 0
    shipment_status: str = "IN_TRANSIT"

    # Timing
    planned_pickup: Optional[datetime] = None
    actual_pickup: Optional[datetime] = None
    planned_delivery: Optional[datetime] = None
    current_eta: Optional[datetime] = None
    eta_p10: Optional[datetime] = None     # Conformal early bound
    eta_p90: Optional[datetime] = None     # Conformal late bound

    # Position
    current_lat: float = 0.0
    current_lon: float = 0.0
    last_update_hours_ago: float = 0.0     # Hours since last tracking event

    # Route context
    total_miles: float = 0.0
    miles_remaining: float = 0.0
    pct_complete: float = 0.0

    # Carrier performance
    carrier_otp_pct: float = 0.95          # Carrier's on-time performance
    carrier_reliability_score: float = 0.8

    # Exception context
    active_exceptions_count: int = 0
    is_temperature_sensitive: bool = False
    current_temp: Optional[float] = None
    temp_min: Optional[float] = None
    temp_max: Optional[float] = None

    def hours_to_delivery(self) -> Optional[float]:
        if self.current_eta:
            delta = self.current_eta - datetime.utcnow()
            return delta.total_seconds() / 3600
        return None

    def is_late(self) -> bool:
        if self.planned_delivery and self.current_eta:
            return self.current_eta > self.planned_delivery
        return False


# ============================================================================
# 3. Demand Sensing State (replaces ForecastAdjustmentState)
# ============================================================================

@dataclass
class DemandSensingState:
    """Input state for DemandSensingTRM.

    Evaluates whether shipping volume forecasts need adjustment
    based on signals, patterns, and external data.
    """
    lane_id: int = 0
    period_start: Optional[date] = None
    period_days: int = 7                   # Weekly by default

    # Current forecast
    forecast_loads: float = 0.0
    forecast_method: str = "CONFORMAL"
    forecast_mape: float = 0.0             # Mean absolute percentage error

    # Actuals / trend
    actual_loads_current: float = 0.0
    actual_loads_prior: float = 0.0
    week_over_week_change_pct: float = 0.0
    rolling_4wk_avg: float = 0.0

    # Signals
    signal_type: str = ""                  # VOLUME_SURGE, SEASONAL_SHIFT, etc.
    signal_magnitude: float = 0.0
    signal_confidence: float = 0.0

    # Context
    seasonal_index: float = 1.0
    is_peak_season: bool = False
    day_of_week_pattern: List[float] = field(default_factory=list)

    def forecast_bias(self) -> float:
        """Positive = over-forecasting, negative = under."""
        if self.forecast_loads == 0:
            return 0.0
        return (self.forecast_loads - self.actual_loads_current) / self.forecast_loads


# ============================================================================
# 4. Capacity Buffer State (replaces InventoryBufferState)
# ============================================================================

@dataclass
class CapacityBufferState:
    """Input state for CapacityBufferTRM.

    Evaluates whether to increase or decrease the capacity buffer
    (extra committed loads above forecast) on a lane.
    """
    lane_id: int = 0
    mode: str = "FTL"

    # Current buffer
    baseline_buffer_loads: int = 0         # Current buffer level
    buffer_policy: str = "PCT_FORECAST"    # FIXED, PCT_FORECAST, CONFORMAL

    # Forecast
    forecast_loads: int = 0
    forecast_p10: int = 0
    forecast_p90: int = 0

    # Capacity
    committed_loads: int = 0
    contract_capacity: int = 0
    spot_availability: int = 0

    # Performance
    recent_tender_reject_rate: float = 0.0
    recent_capacity_miss_count: int = 0
    avg_spot_premium_pct: float = 0.0

    # Demand context
    demand_cv: float = 0.0                 # Coefficient of variation
    demand_trend: float = 0.0              # +1 growing, -1 declining
    is_peak_season: bool = False

    def gap_loads(self) -> int:
        return max(0, self.forecast_loads - self.committed_loads)

    def buffer_ratio(self) -> float:
        if self.forecast_loads == 0:
            return 0.0
        return self.baseline_buffer_loads / self.forecast_loads


# ============================================================================
# 5. Exception Management State (replaces QualityState)
# ============================================================================

@dataclass
class ExceptionManagementState:
    """Input state for ExceptionManagementTRM.

    Evaluates the appropriate response to a shipment exception:
    re-tender, reroute, escalate, or accept delay.
    """
    exception_id: int = 0
    shipment_id: int = 0
    exception_type: str = ""               # ExceptionType enum value
    severity: str = "MEDIUM"               # LOW, MEDIUM, HIGH, CRITICAL
    hours_since_detected: float = 0.0

    # Impact
    estimated_delay_hrs: float = 0.0
    estimated_cost_impact: float = 0.0
    revenue_at_risk: float = 0.0

    # Shipment context
    shipment_priority: int = 3
    is_temperature_sensitive: bool = False
    is_hazmat: bool = False
    delivery_window_remaining_hrs: float = 0.0

    # Carrier context
    carrier_id: int = 0
    carrier_reliability_score: float = 0.8
    carrier_response_time_hrs: float = 2.0

    # Resolution options
    can_retender: bool = True
    alternate_carriers_available: int = 0
    can_reroute: bool = False
    can_partial_deliver: bool = False

    def is_critical_path(self) -> bool:
        return self.shipment_priority <= 2 or self.severity == "CRITICAL"


# ============================================================================
# 6. Freight Procurement State (replaces ReplenishmentState)
# ============================================================================

@dataclass
class FreightProcurementState:
    """Input state for FreightProcurementTRM.

    Evaluates carrier selection and tender timing for a load.
    Implements carrier waterfall logic.
    """
    load_id: int = 0
    lane_id: int = 0
    mode: str = "FTL"
    required_equipment: str = "DRY_VAN"

    # Load details
    weight: float = 0.0
    pallet_count: int = 0
    is_hazmat: bool = False
    is_temperature_sensitive: bool = False

    # Timing
    pickup_date: Optional[datetime] = None
    delivery_date: Optional[datetime] = None
    lead_time_hours: float = 48.0          # Hours until pickup

    # Carrier waterfall
    primary_carrier_id: Optional[int] = None
    primary_carrier_rate: float = 0.0
    primary_carrier_acceptance_pct: float = 0.85
    backup_carriers: List[Dict[str, Any]] = field(default_factory=list)
    # Each: {"id": int, "rate": float, "acceptance_pct": float, "priority": int}

    # Market context
    spot_rate: float = 0.0
    contract_rate: float = 0.0
    market_tightness: float = 0.5          # 0=loose, 1=very tight
    dat_benchmark_rate: float = 0.0

    # Tender context
    tender_attempt: int = 1                # Which attempt (waterfall position)
    max_tender_attempts: int = 3
    hours_to_tender_deadline: float = 24.0

    def rate_vs_benchmark(self) -> float:
        if self.dat_benchmark_rate == 0:
            return 0.0
        return (self.primary_carrier_rate - self.dat_benchmark_rate) / self.dat_benchmark_rate


# ============================================================================
# 7. Broker Routing State (replaces SubcontractingState)
# ============================================================================

@dataclass
class BrokerRoutingState:
    """Input state for BrokerRoutingTRM.

    Evaluates when to escalate to a broker after carrier waterfall
    exhaustion, and which broker to select.
    """
    load_id: int = 0
    lane_id: int = 0
    mode: str = "FTL"

    # Waterfall context
    tender_attempts_exhausted: int = 0
    all_contract_carriers_declined: bool = False
    hours_to_pickup: float = 24.0

    # Broker options
    available_brokers: List[Dict[str, Any]] = field(default_factory=list)
    # Each: {"id": int, "name": str, "rate": float, "reliability": float, "coverage_score": float}

    # Cost context
    contract_rate: float = 0.0
    spot_rate: float = 0.0
    broker_rate_premium_pct: float = 0.15  # Typical broker markup
    budget_remaining: float = 0.0

    # Urgency
    shipment_priority: int = 3
    is_customer_committed: bool = False    # Customer expecting specific delivery

    def should_broker(self) -> bool:
        """Simple rule: broker if all carriers declined and time is short."""
        return self.all_contract_carriers_declined and self.hours_to_pickup < 48


# ============================================================================
# 8. Dock Scheduling State (replaces MaintenanceState)
# ============================================================================

@dataclass
class DockSchedulingState:
    """Input state for DockSchedulingTRM.

    Evaluates dock door assignment, appointment timing, and
    identifies congestion / detention risks.
    """
    facility_id: int = 0
    appointment_id: int = 0
    appointment_type: str = "DELIVERY"     # PICKUP, DELIVERY, CROSS_DOCK, etc.

    # Facility capacity
    total_dock_doors: int = 10
    available_dock_doors: int = 5
    yard_spots_total: int = 50
    yard_spots_available: int = 20

    # Time slots
    requested_time: Optional[datetime] = None
    earliest_available_slot: Optional[datetime] = None
    latest_acceptable_slot: Optional[datetime] = None

    # Current load
    appointments_in_window: int = 0        # Other appointments in same 2hr window
    avg_dwell_time_minutes: float = 45.0
    current_queue_depth: int = 0           # Trucks waiting

    # Shipment context
    shipment_priority: int = 3
    is_live_load: bool = True              # vs drop-trailer
    estimated_load_time_minutes: float = 60.0

    # Detention risk
    free_time_minutes: float = 120.0       # Before detention charges start
    detention_rate_per_hour: float = 75.0
    carrier_avg_dwell_minutes: float = 90.0

    def utilization_pct(self) -> float:
        if self.total_dock_doors == 0:
            return 1.0
        return 1.0 - (self.available_dock_doors / self.total_dock_doors)

    def detention_risk_score(self) -> float:
        """0-1 score of detention likelihood."""
        if self.carrier_avg_dwell_minutes <= self.free_time_minutes:
            return 0.0
        overage = self.carrier_avg_dwell_minutes - self.free_time_minutes
        return min(1.0, overage / 120.0)


# ============================================================================
# 9. Load Build State (replaces MOExecutionState)
# ============================================================================

@dataclass
class LoadBuildState:
    """Input state for LoadBuildTRM.

    Evaluates shipment consolidation into loads for optimal
    equipment utilization and cost efficiency.
    """
    # Candidate shipments
    shipment_ids: List[int] = field(default_factory=list)
    lane_id: int = 0
    mode: str = "FTL"
    equipment_type: str = "DRY_VAN"

    # Capacity limits
    max_weight: float = 44000.0            # lbs (FTL standard)
    max_volume: float = 2700.0             # cuft (53ft trailer)
    max_pallets: int = 26

    # Current utilization
    total_weight: float = 0.0
    total_volume: float = 0.0
    total_pallets: int = 0
    shipment_count: int = 0

    # Compatibility
    has_hazmat_conflict: bool = False
    has_temp_conflict: bool = False
    has_destination_conflict: bool = False
    max_stops: int = 3                     # Multi-stop tolerance

    # Timing
    earliest_pickup: Optional[datetime] = None
    latest_pickup: Optional[datetime] = None
    consolidation_window_hours: float = 24.0

    # Cost
    ftl_rate: float = 0.0
    ltl_rate_sum: float = 0.0             # Sum of individual LTL rates
    consolidation_savings: float = 0.0

    def weight_utilization(self) -> float:
        if self.max_weight == 0:
            return 0.0
        return self.total_weight / self.max_weight

    def volume_utilization(self) -> float:
        if self.max_volume == 0:
            return 0.0
        return self.total_volume / self.max_volume

    def should_consolidate(self) -> bool:
        """Simple rule: consolidate if saves money and fits."""
        return (
            self.consolidation_savings > 0
            and self.weight_utilization() < 0.95
            and self.volume_utilization() < 0.95
            and not self.has_hazmat_conflict
            and not self.has_temp_conflict
        )


# ============================================================================
# 10. Intermodal Transfer State (replaces TOExecutionState)
# ============================================================================

@dataclass
class IntermodalTransferState:
    """Input state for IntermodalTransferTRM.

    Evaluates mode shift opportunities: truck↔rail, truck↔ocean,
    and manages transload operations at terminals.
    """
    shipment_id: int = 0
    current_mode: str = "FTL"
    candidate_mode: str = "RAIL_INTERMODAL"

    # Route
    origin_to_ramp_miles: float = 0.0      # Drayage to rail ramp
    ramp_to_ramp_miles: float = 0.0        # Rail linehaul
    ramp_to_dest_miles: float = 0.0        # Drayage from rail ramp
    total_truck_miles: float = 0.0         # All-truck alternative

    # Cost comparison
    truck_rate: float = 0.0
    intermodal_rate: float = 0.0           # Rail + drayage both ends
    drayage_rate_origin: float = 0.0
    drayage_rate_dest: float = 0.0

    # Transit time
    truck_transit_days: float = 0.0
    intermodal_transit_days: float = 0.0
    delivery_window_days: float = 0.0      # How much slack exists

    # Capacity
    rail_capacity_available: bool = True
    ramp_congestion_level: float = 0.0     # 0=clear, 1=congested

    # Risk
    intermodal_reliability_pct: float = 0.85
    weather_risk_score: float = 0.0

    def cost_savings_pct(self) -> float:
        if self.truck_rate == 0:
            return 0.0
        return (self.truck_rate - self.intermodal_rate) / self.truck_rate

    def transit_time_penalty_days(self) -> float:
        return max(0, self.intermodal_transit_days - self.truck_transit_days)

    def has_time_for_intermodal(self) -> bool:
        return self.transit_time_penalty_days() <= self.delivery_window_days


# ============================================================================
# 11. Equipment Reposition State (replaces RebalancingState)
# ============================================================================

@dataclass
class EquipmentRepositionState:
    """Input state for EquipmentRepositionTRM.

    Evaluates empty equipment repositioning to balance fleet
    across the network. Minimizes deadhead miles while ensuring
    equipment availability at high-demand locations.
    """
    equipment_type: str = "DRY_VAN"

    # Source (where equipment is)
    source_facility_id: int = 0
    source_equipment_count: int = 0
    source_demand_next_7d: int = 0         # Expected loads needing this equipment

    # Target (where equipment is needed)
    target_facility_id: int = 0
    target_equipment_count: int = 0
    target_demand_next_7d: int = 0

    # Reposition details
    reposition_miles: float = 0.0
    reposition_cost: float = 0.0
    reposition_transit_hours: float = 0.0

    # Network context
    network_surplus_locations: int = 0
    network_deficit_locations: int = 0
    total_fleet_size: int = 0
    fleet_utilization_pct: float = 0.0

    # Economics
    cost_of_not_repositioning: float = 0.0  # Spot rate premium if no equipment
    breakeven_loads: int = 1                 # Loads needed to justify reposition

    def source_surplus(self) -> int:
        return max(0, self.source_equipment_count - self.source_demand_next_7d)

    def target_deficit(self) -> int:
        return max(0, self.target_demand_next_7d - self.target_equipment_count)

    def reposition_roi(self) -> float:
        """ROI of repositioning: avoided spot premium / reposition cost."""
        if self.reposition_cost == 0:
            return float('inf') if self.cost_of_not_repositioning > 0 else 0.0
        return self.cost_of_not_repositioning / self.reposition_cost
