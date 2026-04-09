"""
TMS Agent Capabilities — 11 TRM Declarations for Transportation

Maps the 11 SC TRM slots to transportation equivalents:

| # | SC TRM               | TMS TRM               | Phase    | Level     |
|---|----------------------|------------------------|----------|-----------|
| 1 | ATPExecutor          | CapacityPromise        | SENSE    | execution |
| 2 | InventoryBuffer      | CapacityBuffer         | ASSESS   | tactical  |
| 3 | POCreation           | FreightProcurement     | ACQUIRE  | execution |
| 4 | OrderTracking        | ShipmentTracking       | SENSE    | execution |
| 5 | MOExecution          | LoadBuild              | BUILD    | execution |
| 6 | TOExecution          | IntermodalTransfer     | BUILD    | execution |
| 7 | QualityDisposition   | ExceptionManagement    | ASSESS   | execution |
| 8 | MaintenanceScheduling| DockScheduling         | PROTECT  | execution |
| 9 | Subcontracting       | BrokerRouting          | ACQUIRE  | execution |
|10 | ForecastAdjustment   | DemandSensing          | SENSE    | tactical  |
|11 | Rebalancing          | EquipmentReposition    | REFLECT  | tactical  |

Each declaration specifies:
- Signal reads/emits (TMS hive signals)
- Decision table (for AIIO tracking)
- Site applicability (shipper, carrier, terminal, consignee)
- Skill escalation capability

Decision cycle phases (same 6 as SC):
  SENSE → ASSESS → ACQUIRE → PROTECT → BUILD → REFLECT
"""

from typing import Dict
from .agent_contract import AgentCapabilities
from .tms_hive_signals import TMSHiveSignalType as S


# ============================================================================
# TMS-Specific Agent Capabilities
# ============================================================================

TMS_TRM_CAPABILITIES: Dict[str, AgentCapabilities] = {

    # ── SENSE Phase ─────────────────────────────────────────────────────

    "capacity_promise": AgentCapabilities(
        trm_type="capacity_promise",
        display_name="Capacity Promise Agent",
        decision_phase="SENSE",
        decision_level="execution",
        reads_signals=frozenset({
            S.VOLUME_SURGE,
            S.CAPACITY_GAP,
            S.TENDER_REJECTED,
            S.RATE_SPIKE,
        }),
        emits_signals=frozenset({
            S.CAPACITY_GAP,
            S.CAPACITY_SURPLUS,
        }),
        decision_table="powell_capacity_promise_decisions",
        site_types=frozenset({"shipper", "terminal", "cross_dock"}),
        has_skill_escalation=True,
        skill_name="capacity_promise",
    ),

    "shipment_tracking": AgentCapabilities(
        trm_type="shipment_tracking",
        display_name="Shipment Tracking Agent",
        decision_phase="SENSE",
        decision_level="execution",
        reads_signals=frozenset({
            S.SHIPMENT_DELAYED,
            S.TRACKING_LOST,
            S.ETA_UPDATED,
            S.PORT_CONGESTION,
            S.RAIL_DELAY,
        }),
        emits_signals=frozenset({
            S.SHIPMENT_PICKED_UP,
            S.SHIPMENT_IN_TRANSIT,
            S.SHIPMENT_DELIVERED,
            S.SHIPMENT_DELAYED,
            S.ETA_UPDATED,
            S.TRACKING_LOST,
            S.EXCEPTION_DETECTED,
        }),
        decision_table="powell_shipment_tracking_decisions",
        site_types=frozenset({"shipper", "terminal", "consignee", "cross_dock"}),
        has_skill_escalation=True,
        skill_name="shipment_tracking",
    ),

    "demand_sensing": AgentCapabilities(
        trm_type="demand_sensing",
        display_name="Demand Sensing Agent",
        decision_phase="SENSE",
        decision_level="tactical",
        reads_signals=frozenset({
            S.VOLUME_SURGE,
            S.VOLUME_DROP,
            S.SEASONAL_SHIFT,
            S.EXCEPTION_DETECTED,
        }),
        emits_signals=frozenset({
            S.VOLUME_SURGE,
            S.VOLUME_DROP,
            S.SEASONAL_SHIFT,
            S.FORECAST_ADJUSTED,
        }),
        decision_table="powell_demand_sensing_decisions",
        site_types=frozenset({"shipper", "terminal", "consignee"}),
        has_skill_escalation=False,
    ),

    # ── ASSESS Phase ────────────────────────────────────────────────────

    "capacity_buffer": AgentCapabilities(
        trm_type="capacity_buffer",
        display_name="Capacity Buffer Agent",
        decision_phase="ASSESS",
        decision_level="tactical",
        reads_signals=frozenset({
            S.VOLUME_SURGE,
            S.VOLUME_DROP,
            S.FORECAST_ADJUSTED,
            S.CAPACITY_GAP,
            S.TENDER_REJECTED,
            S.CARRIER_SUSPENDED,
        }),
        emits_signals=frozenset({
            S.CAPACITY_GAP,
            S.CAPACITY_SURPLUS,
        }),
        decision_table="powell_capacity_buffer_decisions",
        site_types=frozenset({"shipper", "terminal"}),
        has_skill_escalation=True,
        skill_name="capacity_buffer",
    ),

    "exception_management": AgentCapabilities(
        trm_type="exception_management",
        display_name="Exception Management Agent",
        decision_phase="ASSESS",
        decision_level="execution",
        reads_signals=frozenset({
            S.EXCEPTION_DETECTED,
            S.SHIPMENT_DELAYED,
            S.LATE_PICKUP,
            S.LATE_DELIVERY,
            S.TEMPERATURE_EXCURSION,
            S.DAMAGE_REPORTED,
            S.CUSTOMS_HOLD,
        }),
        emits_signals=frozenset({
            S.EXCEPTION_ESCALATED,
            S.EXCEPTION_RESOLVED,
            S.TENDER_SENT,  # Re-tender on carrier failure
        }),
        decision_table="powell_exception_decisions",
        site_types=frozenset({"shipper", "terminal", "consignee", "cross_dock"}),
        has_skill_escalation=True,
        skill_name="exception_management",
    ),

    # ── ACQUIRE Phase ───────────────────────────────────────────────────

    "freight_procurement": AgentCapabilities(
        trm_type="freight_procurement",
        display_name="Freight Procurement Agent",
        decision_phase="ACQUIRE",
        decision_level="execution",
        reads_signals=frozenset({
            S.CAPACITY_GAP,
            S.TENDER_REJECTED,
            S.TENDER_EXPIRED,
            S.RATE_SPIKE,
            S.CONTRACT_EXPIRING,
            S.FORECAST_ADJUSTED,
        }),
        emits_signals=frozenset({
            S.TENDER_SENT,
            S.TENDER_ACCEPTED,
            S.TENDER_REJECTED,
            S.RATE_SPIKE,
        }),
        decision_table="powell_freight_procurement_decisions",
        site_types=frozenset({"shipper", "terminal"}),
        has_skill_escalation=True,
        skill_name="freight_procurement",
    ),

    "broker_routing": AgentCapabilities(
        trm_type="broker_routing",
        display_name="Broker Routing Agent",
        decision_phase="ACQUIRE",
        decision_level="execution",
        reads_signals=frozenset({
            S.TENDER_REJECTED,
            S.TENDER_EXPIRED,
            S.CAPACITY_GAP,
            S.RATE_SPIKE,
            S.CARRIER_SUSPENDED,
        }),
        emits_signals=frozenset({
            S.TENDER_SENT,
            S.TENDER_ACCEPTED,
        }),
        decision_table="powell_broker_routing_decisions",
        site_types=frozenset({"shipper"}),
        has_skill_escalation=True,
        skill_name="broker_routing",
    ),

    # ── PROTECT Phase ───────────────────────────────────────────────────

    "dock_scheduling": AgentCapabilities(
        trm_type="dock_scheduling",
        display_name="Dock Scheduling Agent",
        decision_phase="PROTECT",
        decision_level="execution",
        reads_signals=frozenset({
            S.DOCK_CONGESTION,
            S.APPOINTMENT_CONFLICT,
            S.DWELL_TIME_ALERT,
            S.DETENTION_RISK,
            S.SHIPMENT_DELAYED,
            S.ETA_UPDATED,
            S.APPOINTMENT_NO_SHOW,
        }),
        emits_signals=frozenset({
            S.DOCK_CONGESTION,
            S.APPOINTMENT_CONFLICT,
            S.DETENTION_RISK,
        }),
        decision_table="powell_dock_scheduling_decisions",
        site_types=frozenset({"shipper", "terminal", "consignee", "cross_dock"}),
        has_skill_escalation=True,
        skill_name="dock_scheduling",
    ),

    # ── BUILD Phase ─────────────────────────────────────────────────────

    "load_build": AgentCapabilities(
        trm_type="load_build",
        display_name="Load Build Agent",
        decision_phase="BUILD",
        decision_level="execution",
        reads_signals=frozenset({
            S.TENDER_ACCEPTED,
            S.CAPACITY_GAP,
            S.DOCK_CONGESTION,
            S.UNDERUTILIZED_LOAD,
            S.FORECAST_ADJUSTED,
        }),
        emits_signals=frozenset({
            S.LOAD_CONSOLIDATED,
            S.LOAD_SPLIT,
            S.LOAD_OPTIMIZED,
            S.UNDERUTILIZED_LOAD,
        }),
        decision_table="powell_load_build_decisions",
        site_types=frozenset({"shipper", "terminal", "cross_dock"}),
        has_skill_escalation=True,
        skill_name="load_build",
    ),

    "intermodal_transfer": AgentCapabilities(
        trm_type="intermodal_transfer",
        display_name="Intermodal Transfer Agent",
        decision_phase="BUILD",
        decision_level="execution",
        reads_signals=frozenset({
            S.MODE_SHIFT_OPPORTUNITY,
            S.TRANSLOAD_NEEDED,
            S.PORT_CONGESTION,
            S.RAIL_DELAY,
            S.RATE_SPIKE,
            S.LANE_DISRUPTION,
        }),
        emits_signals=frozenset({
            S.MODE_SHIFT_OPPORTUNITY,
            S.TRANSLOAD_NEEDED,
        }),
        decision_table="powell_intermodal_transfer_decisions",
        site_types=frozenset({"terminal", "cross_dock"}),
        has_skill_escalation=True,
        skill_name="intermodal_transfer",
    ),

    # ── REFLECT Phase ───────────────────────────────────────────────────

    "equipment_reposition": AgentCapabilities(
        trm_type="equipment_reposition",
        display_name="Equipment Reposition Agent",
        decision_phase="REFLECT",
        decision_level="tactical",
        reads_signals=frozenset({
            S.EQUIPMENT_SHORTAGE,
            S.EQUIPMENT_AVAILABLE,
            S.REPOSITION_NEEDED,
            S.CAPACITY_GAP,
            S.NETWORK_CAPACITY_TIGHT,
            S.LANE_DISRUPTION,
        }),
        emits_signals=frozenset({
            S.REPOSITION_NEEDED,
            S.EQUIPMENT_AVAILABLE,
            S.EQUIPMENT_SHORTAGE,
        }),
        decision_table="powell_equipment_reposition_decisions",
        site_types=frozenset({"shipper", "terminal", "cross_dock"}),
        has_skill_escalation=True,
        skill_name="equipment_reposition",
    ),
}


# ── TMS TRM Names ──────────────────────────────────────────────────────

ALL_TMS_TRM_NAMES = frozenset(TMS_TRM_CAPABILITIES.keys())

# Phase → TRM ordering (decision cycle execution order)
TMS_TRM_PHASE_MAP = {
    "SENSE": ["capacity_promise", "shipment_tracking", "demand_sensing"],
    "ASSESS": ["capacity_buffer", "exception_management"],
    "ACQUIRE": ["freight_procurement", "broker_routing"],
    "PROTECT": ["dock_scheduling"],
    "BUILD": ["load_build", "intermodal_transfer"],
    "REFLECT": ["equipment_reposition"],
}
