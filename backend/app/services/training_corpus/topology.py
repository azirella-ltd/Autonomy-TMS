"""Topology-aware TRM capability resolution.

Maps a site's master_type (from the AWS SC data model) to the set of TRM
types that are valid for it. The corpus build skips out-of-topology TRMs
silently (Case A — not an error).

Source of truth: docs/internal/architecture — Manufacturer: 12 TRMs,
DC (inventory): 8, Retailer: 7.
"""

from typing import FrozenSet

# All 12 TRM types
ALL_TRMS: FrozenSet[str] = frozenset({
    "forecast_baseline",
    "forecast_adjustment",
    "atp_allocation",
    "po_creation",
    "mo_execution",
    "to_execution",
    "inventory_buffer",
    "rebalancing",
    "quality_disposition",
    "maintenance_scheduling",
    "subcontracting",
    "order_tracking",
})

# Manufacturer: all 12
_MANUFACTURER_TRMS: FrozenSet[str] = ALL_TRMS

# DC (inventory node): no production, no manufacturing-specific TRMs
_DC_TRMS: FrozenSet[str] = frozenset({
    "forecast_baseline",
    "forecast_adjustment",
    "atp_allocation",
    "po_creation",
    "to_execution",
    "inventory_buffer",
    "rebalancing",
    "order_tracking",
})

# Retailer: customer-facing, no inter-site rebalancing authority
_RETAILER_TRMS: FrozenSet[str] = frozenset({
    "forecast_baseline",
    "forecast_adjustment",
    "atp_allocation",
    "po_creation",
    "to_execution",
    "inventory_buffer",
    "order_tracking",
})

# Vendor / customer: external trading partners, no internal agents
_EXTERNAL_TRMS: FrozenSet[str] = frozenset()


def valid_trms_for_site_type(master_type: str) -> FrozenSet[str]:
    """Return the set of TRM types valid for a site of the given master_type.

    master_type values from AWS SC data model: manufacturer, inventory,
    retailer, vendor, customer.
    """
    mt = (master_type or "").lower()
    if mt == "manufacturer":
        return _MANUFACTURER_TRMS
    if mt == "inventory":
        return _DC_TRMS
    if mt == "retailer":
        return _RETAILER_TRMS
    if mt in ("vendor", "customer"):
        return _EXTERNAL_TRMS
    # Unknown master_type: conservative — return empty, caller will skip
    return _EXTERNAL_TRMS


def is_in_scope(trm_type: str, master_type: str) -> bool:
    """True if this TRM is in-scope for a site of this master_type."""
    return trm_type in valid_trms_for_site_type(master_type)
