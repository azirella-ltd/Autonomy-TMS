"""
TMS Hive Signal Types — Stigmergic Coordination for Transportation TRMs

Extends the base HiveSignalType enum with transportation-specific signals.
These enable the 11 TMS TRM agents to communicate asynchronously:
  - Capacity signals: capacity constraints, tender outcomes
  - Shipment signals: tracking events, ETA changes, exceptions
  - Network signals: lane congestion, carrier availability
  - Dock signals: appointment conflicts, dwell time alerts

Signal flow example (freight procurement cycle):
1. DemandSensingTRM emits VOLUME_SURGE on lane →
2. CapacityBufferTRM reads, emits CAPACITY_GAP →
3. FreightProcurementTRM reads, emits TENDER_SENT →
4. ShipmentTrackingTRM reads, monitors execution →
5. ExceptionMgmtTRM reads exceptions, emits EXCEPTION_DETECTED →
6. EquipmentRepositionTRM reads network state, emits REPOSITION_NEEDED
"""

from enum import Enum


class TMSHiveSignalType(str, Enum):
    """Transportation-specific hive signals.

    Organized by agent function:
      Scout: demand sensing, volume forecasting
      Carrier: capacity, procurement, tender
      Tracker: shipment visibility, ETA, exceptions
      Dock: scheduling, dwell, appointment
      Network: lane, equipment, intermodal
    """

    # ── Scout signals (demand / volume sensing) ─────────────────────────
    VOLUME_SURGE = "volume_surge"              # Lane volume above forecast
    VOLUME_DROP = "volume_drop"                # Lane volume below forecast
    SEASONAL_SHIFT = "seasonal_shift"          # Seasonal pattern detected
    FORECAST_ADJUSTED = "tms_forecast_adjusted"  # Volume forecast revised

    # ── Carrier / Capacity signals ──────────────────────────────────────
    CAPACITY_GAP = "capacity_gap"              # Committed < required loads
    CAPACITY_SURPLUS = "capacity_surplus"       # Excess committed capacity
    TENDER_SENT = "tender_sent"                # Freight tender dispatched
    TENDER_ACCEPTED = "tender_accepted"        # Carrier accepted tender
    TENDER_REJECTED = "tender_rejected"        # Carrier declined tender
    TENDER_EXPIRED = "tender_expired"          # Tender timed out
    CARRIER_SUSPENDED = "carrier_suspended"    # Carrier deactivated
    RATE_SPIKE = "rate_spike"                  # Spot rate exceeds threshold
    CONTRACT_EXPIRING = "contract_expiring"    # Carrier contract near expiry

    # ── Shipment tracking signals ───────────────────────────────────────
    SHIPMENT_PICKED_UP = "shipment_picked_up"
    SHIPMENT_IN_TRANSIT = "shipment_in_transit"
    SHIPMENT_DELIVERED = "shipment_delivered"
    SHIPMENT_DELAYED = "shipment_delayed"      # ETA slipped
    ETA_UPDATED = "eta_updated"                # New ETA from conformal/p44
    TRACKING_LOST = "tracking_lost"            # No updates for N hours

    # ── Exception signals ───────────────────────────────────────────────
    EXCEPTION_DETECTED = "exception_detected"  # Any shipment exception
    EXCEPTION_ESCALATED = "exception_escalated"  # Severity upgraded
    EXCEPTION_RESOLVED = "exception_resolved"
    LATE_PICKUP = "late_pickup"
    LATE_DELIVERY = "late_delivery"
    TEMPERATURE_EXCURSION = "temperature_excursion"
    DAMAGE_REPORTED = "damage_reported"
    CUSTOMS_HOLD = "tms_customs_hold"

    # ── Dock / Appointment signals ──────────────────────────────────────
    DOCK_CONGESTION = "dock_congestion"        # Facility approaching capacity
    APPOINTMENT_CONFLICT = "appointment_conflict"
    DWELL_TIME_ALERT = "dwell_time_alert"      # Excessive wait at facility
    DETENTION_RISK = "detention_risk"           # Approaching detention threshold
    APPOINTMENT_NO_SHOW = "appointment_no_show"

    # ── Load building signals ───────────────────────────────────────────
    LOAD_CONSOLIDATED = "load_consolidated"    # Shipments merged into load
    LOAD_SPLIT = "load_split"                  # Load broken apart
    LOAD_OPTIMIZED = "load_optimized"          # Load plan improved
    UNDERUTILIZED_LOAD = "underutilized_load"  # Load below weight/volume threshold

    # ── Equipment / Reposition signals ──────────────────────────────────
    REPOSITION_NEEDED = "reposition_needed"    # Empty equipment at wrong location
    EQUIPMENT_SHORTAGE = "equipment_shortage"   # No available equipment at facility
    EQUIPMENT_AVAILABLE = "equipment_available" # Equipment freed up

    # ── Intermodal / Transfer signals ───────────────────────────────────
    MODE_SHIFT_OPPORTUNITY = "mode_shift_opportunity"  # Cheaper mode available
    TRANSLOAD_NEEDED = "transload_needed"      # Cross-dock or mode change needed
    PORT_CONGESTION = "tms_port_congestion"    # Port delays affecting ocean legs
    RAIL_DELAY = "rail_delay"                  # Rail segment delayed

    # ── Network-level (from tGNN) ───────────────────────────────────────
    NETWORK_CAPACITY_TIGHT = "network_capacity_tight"
    NETWORK_CAPACITY_LOOSE = "network_capacity_loose"
    LANE_DISRUPTION = "lane_disruption"        # Lane unavailable (weather, road closure)
    CARRIER_NETWORK_SHIFT = "carrier_network_shift"  # Carrier coverage changed


# ── Convenience sets for agent-based filtering ──────────────────────────

SCOUT_SIGNALS = frozenset({
    TMSHiveSignalType.VOLUME_SURGE,
    TMSHiveSignalType.VOLUME_DROP,
    TMSHiveSignalType.SEASONAL_SHIFT,
    TMSHiveSignalType.FORECAST_ADJUSTED,
})

CARRIER_SIGNALS = frozenset({
    TMSHiveSignalType.CAPACITY_GAP,
    TMSHiveSignalType.CAPACITY_SURPLUS,
    TMSHiveSignalType.TENDER_SENT,
    TMSHiveSignalType.TENDER_ACCEPTED,
    TMSHiveSignalType.TENDER_REJECTED,
    TMSHiveSignalType.TENDER_EXPIRED,
    TMSHiveSignalType.CARRIER_SUSPENDED,
    TMSHiveSignalType.RATE_SPIKE,
    TMSHiveSignalType.CONTRACT_EXPIRING,
})

TRACKING_SIGNALS = frozenset({
    TMSHiveSignalType.SHIPMENT_PICKED_UP,
    TMSHiveSignalType.SHIPMENT_IN_TRANSIT,
    TMSHiveSignalType.SHIPMENT_DELIVERED,
    TMSHiveSignalType.SHIPMENT_DELAYED,
    TMSHiveSignalType.ETA_UPDATED,
    TMSHiveSignalType.TRACKING_LOST,
})

EXCEPTION_SIGNALS = frozenset({
    TMSHiveSignalType.EXCEPTION_DETECTED,
    TMSHiveSignalType.EXCEPTION_ESCALATED,
    TMSHiveSignalType.EXCEPTION_RESOLVED,
    TMSHiveSignalType.LATE_PICKUP,
    TMSHiveSignalType.LATE_DELIVERY,
    TMSHiveSignalType.TEMPERATURE_EXCURSION,
    TMSHiveSignalType.DAMAGE_REPORTED,
    TMSHiveSignalType.CUSTOMS_HOLD,
})

DOCK_SIGNALS = frozenset({
    TMSHiveSignalType.DOCK_CONGESTION,
    TMSHiveSignalType.APPOINTMENT_CONFLICT,
    TMSHiveSignalType.DWELL_TIME_ALERT,
    TMSHiveSignalType.DETENTION_RISK,
    TMSHiveSignalType.APPOINTMENT_NO_SHOW,
})

LOAD_SIGNALS = frozenset({
    TMSHiveSignalType.LOAD_CONSOLIDATED,
    TMSHiveSignalType.LOAD_SPLIT,
    TMSHiveSignalType.LOAD_OPTIMIZED,
    TMSHiveSignalType.UNDERUTILIZED_LOAD,
})

EQUIPMENT_SIGNALS = frozenset({
    TMSHiveSignalType.REPOSITION_NEEDED,
    TMSHiveSignalType.EQUIPMENT_SHORTAGE,
    TMSHiveSignalType.EQUIPMENT_AVAILABLE,
})

INTERMODAL_SIGNALS = frozenset({
    TMSHiveSignalType.MODE_SHIFT_OPPORTUNITY,
    TMSHiveSignalType.TRANSLOAD_NEEDED,
    TMSHiveSignalType.PORT_CONGESTION,
    TMSHiveSignalType.RAIL_DELAY,
})

NETWORK_SIGNALS = frozenset({
    TMSHiveSignalType.NETWORK_CAPACITY_TIGHT,
    TMSHiveSignalType.NETWORK_CAPACITY_LOOSE,
    TMSHiveSignalType.LANE_DISRUPTION,
    TMSHiveSignalType.CARRIER_NETWORK_SHIFT,
})
