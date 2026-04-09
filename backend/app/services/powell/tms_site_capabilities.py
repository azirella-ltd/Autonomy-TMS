"""
TMS Site Capabilities — Which TRMs Are Active at Each Facility Type

In TMS context, facilities (Sites) have different physical capabilities:
- Shipper/Origin: loads freight, needs capacity, tenders loads
- Terminal/Cross-Dock: transfers, consolidates, stages
- Consignee/Destination: receives freight, appointment scheduling
- Carrier Yard: equipment staging, repositioning

Each facility type activates a subset of the 11 TMS TRMs based on
what decisions are physically meaningful at that location.
"""

from typing import FrozenSet, Optional

from .tms_agent_capabilities import ALL_TMS_TRM_NAMES


# ── Facility Type → Active TRMs ────────────────────────────────────────

_FACILITY_TRM_MAP = {
    # Shipper/Origin: all outbound decisions
    "shipper": frozenset({
        "capacity_promise",     # Promise capacity to orders
        "shipment_tracking",    # Track outbound shipments
        "demand_sensing",       # Forecast outbound volume
        "capacity_buffer",      # Buffer capacity above forecast
        "exception_management", # Handle outbound exceptions
        "freight_procurement",  # Tender loads to carriers
        "broker_routing",       # Fallback to brokers
        "dock_scheduling",      # Manage loading dock
        "load_build",           # Consolidate shipments into loads
        "equipment_reposition", # Manage trailer pool
    }),  # 10 of 11 (no intermodal_transfer — that's terminal)

    # Terminal / Cross-Dock: intermediate handling
    "terminal": frozenset({
        "capacity_promise",     # Capacity through terminal
        "shipment_tracking",    # Track in-terminal shipments
        "demand_sensing",       # Forecast terminal throughput
        "capacity_buffer",      # Terminal capacity buffers
        "exception_management", # Handle transload exceptions
        "freight_procurement",  # Outbound leg procurement
        "dock_scheduling",      # Dock door scheduling
        "load_build",           # Consolidation / deconsolidation
        "intermodal_transfer",  # Mode changes (truck→rail, etc.)
        "equipment_reposition", # Equipment management
    }),  # 10 of 11 (no broker_routing — shipper decides)

    # Cross-Dock: similar to terminal
    "cross_dock": frozenset({
        "capacity_promise",
        "shipment_tracking",
        "exception_management",
        "dock_scheduling",
        "load_build",
        "intermodal_transfer",
        "equipment_reposition",
    }),  # 7 — lean cross-dock operations

    # Consignee / Destination: inbound receiving
    "consignee": frozenset({
        "shipment_tracking",    # Track inbound shipments
        "demand_sensing",       # Forecast inbound volume
        "exception_management", # Handle delivery exceptions
        "dock_scheduling",      # Manage receiving dock
    }),  # 4 — receiving operations only

    # Carrier Yard: equipment management
    "carrier_yard": frozenset({
        "equipment_reposition", # Main function: manage fleet
        "shipment_tracking",    # Track assets in yard
    }),  # 2 — equipment-focused

    # Port / Rail Terminal: intermodal handling
    "port": frozenset({
        "shipment_tracking",
        "exception_management",
        "intermodal_transfer",
        "dock_scheduling",
        "equipment_reposition",
    }),  # 5 — intermodal focus
}


def get_active_tms_trms(
    facility_type: str,
    override_trms: Optional[FrozenSet[str]] = None,
) -> FrozenSet[str]:
    """
    Return the set of active TRM names for a given facility type.

    Args:
        facility_type: One of shipper, terminal, cross_dock, consignee,
                       carrier_yard, port
        override_trms: If provided, intersect with facility capabilities
                       (for per-site governance restrictions)

    Returns:
        Frozen set of TRM names that should be active
    """
    base = _FACILITY_TRM_MAP.get(facility_type.lower(), frozenset())

    if not base:
        # Unknown facility type: return all TRMs (backward compat)
        base = ALL_TMS_TRM_NAMES

    if override_trms is not None:
        return base & override_trms & ALL_TMS_TRM_NAMES

    return base


def get_all_facility_types() -> list:
    """Return all known facility types."""
    return list(_FACILITY_TRM_MAP.keys())


def get_trm_facility_coverage(trm_name: str) -> FrozenSet[str]:
    """Return which facility types a given TRM is active at."""
    return frozenset(
        ftype for ftype, trms in _FACILITY_TRM_MAP.items()
        if trm_name in trms
    )
