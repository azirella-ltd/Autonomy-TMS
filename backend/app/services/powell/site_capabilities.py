"""
Site Capability Mapping — TRM hive composition based on site type.

Maps master_type (and optionally sc_site_type) to the set of TRM agents
that are meaningful for that site.  A distribution center has no production
line, so mo_execution, quality_disposition, and maintenance_scheduling are
excluded.  A market-demand sink (customer) has no inventory to manage, so
only order_tracking and atp_executor apply.

The mapping is extracted from the DAG topology: master_type determines the
*physical capabilities* of a site (can it manufacture? store? source?).
The sc_site_type (RETAILER, WHOLESALER, DC, etc.) provides finer-grained
overrides where needed.

Usage:
    from app.services.powell.site_capabilities import get_active_trms

    active = get_active_trms(master_type="manufacturer")
    # => frozenset of all 11 TRM canonical names

    active = get_active_trms(master_type="inventory", sc_site_type="RETAILER")
    # => frozenset with atp, order_tracking, rebalancing, inventory_buffer,
    #    forecast_adjustment, to_execution

ALL_TRM_NAMES is the canonical set of 11 TRM names used throughout the
decision cycle (matches _CANONICAL_PHASE_MAP keys in decision_cycle.py).
"""

from __future__ import annotations

from typing import FrozenSet, Optional, Dict

# ---------------------------------------------------------------------------
# Canonical TRM names (must match decision_cycle._CANONICAL_PHASE_MAP)
# ---------------------------------------------------------------------------

ALL_TRM_NAMES: FrozenSet[str] = frozenset([
    "forecast_baseline",
    "atp_executor",
    "order_tracking",
    "inventory_buffer",
    "forecast_adjustment",
    "quality_disposition",
    "po_creation",
    "subcontracting",
    "maintenance_scheduling",
    "mo_execution",
    "to_execution",
    "rebalancing",
])

# ---------------------------------------------------------------------------
# Master-type capability mapping
# ---------------------------------------------------------------------------
#
# MANUFACTURER — full production site, all 11 TRMs active.
# INVENTORY    — storage/fulfillment (DC, Wholesaler, Distributor, Retailer).
#                No production capabilities, so no MO, Quality, Maintenance,
#                Subcontracting.  PO may or may not apply (see sc_site_type
#                overrides below).
# VENDOR — infinite supplier source.  Only PO creation (inbound) and
#                 order tracking are meaningful.
# CUSTOMER — terminal demand sink.  Only order tracking (outbound
#                 visibility) applies; the site itself makes no decisions.
#
# Rationale for each TRM inclusion/exclusion:
#   atp_executor      — any site that promises delivery to downstream
#   order_tracking     — any site that ships or receives orders
#   inventory_buffer   — any site holding physical inventory
#   forecast_adjustment— sites with demand signals to interpret
#   quality_disposition— only where production or inbound QC occurs
#   po_creation        — sites that purchase from external suppliers
#   subcontracting     — sites that can outsource production
#   maintenance_scheduling — sites with production equipment
#   mo_execution       — sites with manufacturing capability
#   to_execution       — sites that ship transfer orders
#   rebalancing        — sites in a network that can redistribute stock

_MASTER_TYPE_TRMS: Dict[str, FrozenSet[str]] = {
    "manufacturer": ALL_TRM_NAMES,

    "inventory": frozenset([
        "forecast_baseline",
        "atp_executor",
        "order_tracking",
        "inventory_buffer",
        "forecast_adjustment",
        "to_execution",
        "rebalancing",
        # PO creation included: DCs/Wholesalers may place POs to suppliers
        "po_creation",
    ]),

    # External parties (TradingPartner): no TRM hive — outside company authority.
    # is_external=True sites with tpartner_type='vendor' or 'customer' map here.
    "vendor": frozenset(),
    "customer": frozenset(),
}

# ---------------------------------------------------------------------------
# SC site type overrides — finer-grained adjustments within a master_type
# ---------------------------------------------------------------------------
#
# These override the master_type defaults when a more specific sc_site_type
# is known.  Values are stored uppercase in Site.type (NodeType enum).

_SC_SITE_TYPE_OVERRIDES: Dict[str, FrozenSet[str]] = {
    # Retailer: customer-facing, no PO (supplied via transfers from upstream DC)
    "RETAILER": frozenset([
        "atp_executor",
        "order_tracking",
        "inventory_buffer",
        "forecast_adjustment",
        "to_execution",
        "rebalancing",
    ]),

    # Supplier (component/raw material): only tracks outbound orders
    "SUPPLIER": frozenset([
        "order_tracking",
        "po_creation",
    ]),
}


def get_active_trms(
    master_type: str,
    sc_site_type: Optional[str] = None,
) -> FrozenSet[str]:
    """Return the set of TRM canonical names active for a given site type.

    Args:
        master_type: One of "manufacturer", "inventory" for internal sites, or
            "vendor"/"customer" for external TradingPartner-backed sites
            (lowercase, as stored in Site.master_type or Site.tpartner_type).
            The legacy values "vendor" and "customer" are mapped to
            "vendor" and "customer" respectively for backward compatibility.
        sc_site_type: Optional NodeType value (uppercase, e.g. "RETAILER",
            "DISTRIBUTOR").  If provided AND an override exists, it takes
            precedence over the master_type default.

    Returns:
        Frozen set of canonical TRM names that should be instantiated for
        this site.  Always a subset of ALL_TRM_NAMES.

    Raises:
        ValueError: If master_type is not recognized.
    """
    mt = master_type.lower()

    # Backward-compatibility: map legacy VENDOR/CUSTOMER to new names
    _LEGACY_MAP = {"vendor": "vendor", "customer": "customer"}
    mt = _LEGACY_MAP.get(mt, mt)

    # Check sc_site_type override first
    if sc_site_type:
        override = _SC_SITE_TYPE_OVERRIDES.get(sc_site_type.upper())
        if override is not None:
            return override

    trms = _MASTER_TYPE_TRMS.get(mt)
    if trms is None:
        raise ValueError(
            f"Unknown master_type: {master_type!r}. "
            f"Valid: {sorted(_MASTER_TYPE_TRMS)}"
        )
    return trms


def is_trm_active(
    trm_name: str,
    master_type: str,
    sc_site_type: Optional[str] = None,
) -> bool:
    """Check whether a specific TRM is active for a given site type."""
    return trm_name in get_active_trms(master_type, sc_site_type)


def get_active_trm_indices(
    master_type: str,
    sc_site_type: Optional[str] = None,
) -> list[int]:
    """Return sorted list of TRM slot indices that are active.

    Uses the canonical ordering from UrgencyVector.TRM_INDICES (0-10).
    Useful for Site tGNN node masking.
    """
    from .hive_signal import UrgencyVector

    active = get_active_trms(master_type, sc_site_type)
    indices = []
    for name in active:
        idx = UrgencyVector.TRM_INDICES.get(name)
        if idx is not None:
            indices.append(idx)
    return sorted(set(indices))
