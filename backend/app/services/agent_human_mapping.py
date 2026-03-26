"""
Agent-Human Mapping Service — determines which TRM agents need human
counterparts at each site, based on DAG topology and site role.

The core insight: not every active TRM needs a dedicated human analyst.
A CDC (hub) needs PO and Forecast analysts but not ATP (no customer-facing).
An RDC (spoke) needs ATP but not PO (receives from CDC, not suppliers).

Three layers of logic:
  1. TRM_TO_DECISION_LEVEL — which DecisionLevelEnum is the counterpart
     for each TRM canonical name
  2. Site role detection — classify sites as hub/spoke/factory/standalone
     by analyzing the DAG topology (upstream/downstream relationships)
  3. HUMAN_COUNTERPART_MAP — (trm_type, site_role) -> needs_human

Usage:
    from app.services.agent_human_mapping import (
        recommend_users_for_config,
        classify_site_role,
        needs_human_for_trm,
    )

    # Get full user recommendation for a config
    recommendations = await recommend_users_for_config(db, config_id)
    # => [UserRecommendation(decision_level="ATP_ANALYST",
    #       site_scope=["SITE_RDC_NW", "SITE_RDC_SW"], ...)]

    # Check a single site
    role = classify_site_role(site, all_lanes)
    needs = needs_human_for_trm("atp_executor", role)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.powell.site_capabilities import get_active_trms


# ---------------------------------------------------------------------------
# TRM canonical name -> DecisionLevelEnum value
# ---------------------------------------------------------------------------
# Only 4 TRM types have dedicated analyst-level roles.
# The remaining 7 are managed by MPS_MANAGER (or higher).
# This mapping determines which decision_level to assign when seeding users.

TRM_TO_DECISION_LEVEL: Dict[str, str] = {
    # Analyst-level (dedicated specialist per TRM)
    "atp_executor": "ATP_ANALYST",
    "rebalancing": "REBALANCING_ANALYST",
    "po_creation": "PO_ANALYST",
    "order_tracking": "ORDER_TRACKING_ANALYST",
    # Manager-level (MPS Manager covers these — no individual analyst role)
    "mo_execution": "MPS_MANAGER",
    "to_execution": "MPS_MANAGER",
    "quality_disposition": "MPS_MANAGER",
    "maintenance_scheduling": "MPS_MANAGER",
    "subcontracting": "MPS_MANAGER",
    "forecast_adjustment": "MPS_MANAGER",
    "inventory_buffer": "MPS_MANAGER",
}

# Reverse: decision_level -> which TRMs it covers
DECISION_LEVEL_TRMS: Dict[str, List[str]] = {}
for _trm, _dl in TRM_TO_DECISION_LEVEL.items():
    DECISION_LEVEL_TRMS.setdefault(_dl, []).append(_trm)


# ---------------------------------------------------------------------------
# Site role classification
# ---------------------------------------------------------------------------

class SiteRole(str, Enum):
    """Topological role of a site within the supply chain DAG.

    Derived from the site's master_type and its position in the lane graph
    (upstream/downstream internal connections).
    """
    # Distribution hub: internal INVENTORY site with downstream internal sites
    # (e.g., CDC that ships to RDCs).  Handles procurement, forecasting, buffer.
    HUB = "hub"

    # Distribution spoke: internal INVENTORY site with NO downstream internal
    # sites — terminal customer-facing node (e.g., RDC, Retailer).
    # Handles ATP, order tracking.
    SPOKE = "spoke"

    # Manufacturing site: MANUFACTURER master_type.  Full TRM complement.
    FACTORY = "factory"

    # Only one internal INVENTORY site in the network — acts as both hub and
    # spoke (handles procurement, ATP, everything).
    STANDALONE = "standalone"

    # External trading partner — no TRM hive, no human needed.
    EXTERNAL = "external"


# ---------------------------------------------------------------------------
# Human counterpart mapping
# ---------------------------------------------------------------------------
# For each (trm_type, site_role) pair: does a human analyst need to be
# assigned at that site?
#
# True  = this site needs a human reviewing this TRM's decisions
# False = TRM runs autonomously at this site (or is managed by a higher-level
#         role covering all sites, like SOP_DIRECTOR)
#
# Design rationale (Food Dist example):
#   CDC (hub): PO yes (orders from suppliers), Rebalancing yes (manages
#     cross-DC transfers), Forecast yes, Buffer yes, Order Tracking yes,
#     ATP no (not customer-facing), TO no (automated outbound).
#   RDC (spoke): ATP yes (customer-facing promising), Order Tracking yes,
#     PO no (receives from CDC), Rebalancing no (CDC manages), Forecast no,
#     Buffer no, TO no (automated inbound).
#   Factory: all 11 TRMs need human review for production decisions.
#   Standalone DC: both hub and spoke duties — all applicable TRMs.

_HUMAN_COUNTERPART_MAP: Dict[Tuple[str, SiteRole], bool] = {
    # ---- HUB (CDC-like) ----
    ("atp_executor", SiteRole.HUB): False,        # not customer-facing
    ("order_tracking", SiteRole.HUB): True,        # monitors supplier orders
    ("po_creation", SiteRole.HUB): True,           # orders from suppliers
    ("rebalancing", SiteRole.HUB): True,           # manages cross-site transfers
    ("forecast_adjustment", SiteRole.HUB): True,   # demand planning
    ("inventory_buffer", SiteRole.HUB): True,      # buffer management
    ("to_execution", SiteRole.HUB): False,         # automated outbound transfers
    # MFG TRMs not applicable to hub (INVENTORY master_type)
    ("mo_execution", SiteRole.HUB): False,
    ("quality_disposition", SiteRole.HUB): False,
    ("maintenance_scheduling", SiteRole.HUB): False,
    ("subcontracting", SiteRole.HUB): False,

    # ---- SPOKE (RDC-like, customer-facing) ----
    ("atp_executor", SiteRole.SPOKE): True,        # customer-facing promising
    ("order_tracking", SiteRole.SPOKE): True,      # monitors customer orders
    ("po_creation", SiteRole.SPOKE): False,        # receives from hub, not suppliers
    ("rebalancing", SiteRole.SPOKE): False,        # hub manages transfers
    ("forecast_adjustment", SiteRole.SPOKE): False, # hub manages forecasting
    ("inventory_buffer", SiteRole.SPOKE): False,   # hub manages buffer params
    ("to_execution", SiteRole.SPOKE): False,       # automated inbound transfers
    # MFG TRMs not applicable to spoke (INVENTORY master_type)
    ("mo_execution", SiteRole.SPOKE): False,
    ("quality_disposition", SiteRole.SPOKE): False,
    ("maintenance_scheduling", SiteRole.SPOKE): False,
    ("subcontracting", SiteRole.SPOKE): False,

    # ---- FACTORY (manufacturer) ----
    ("atp_executor", SiteRole.FACTORY): True,
    ("order_tracking", SiteRole.FACTORY): True,
    ("po_creation", SiteRole.FACTORY): True,
    ("rebalancing", SiteRole.FACTORY): True,
    ("forecast_adjustment", SiteRole.FACTORY): True,
    ("inventory_buffer", SiteRole.FACTORY): True,
    ("to_execution", SiteRole.FACTORY): True,
    ("mo_execution", SiteRole.FACTORY): True,
    ("quality_disposition", SiteRole.FACTORY): True,
    ("maintenance_scheduling", SiteRole.FACTORY): True,
    ("subcontracting", SiteRole.FACTORY): True,

    # ---- STANDALONE (single DC — does everything) ----
    ("atp_executor", SiteRole.STANDALONE): True,
    ("order_tracking", SiteRole.STANDALONE): True,
    ("po_creation", SiteRole.STANDALONE): True,
    ("rebalancing", SiteRole.STANDALONE): False,   # no other sites to rebalance with
    ("forecast_adjustment", SiteRole.STANDALONE): True,
    ("inventory_buffer", SiteRole.STANDALONE): True,
    ("to_execution", SiteRole.STANDALONE): False,  # no transfer partners
    ("mo_execution", SiteRole.STANDALONE): False,
    ("quality_disposition", SiteRole.STANDALONE): False,
    ("maintenance_scheduling", SiteRole.STANDALONE): False,
    ("subcontracting", SiteRole.STANDALONE): False,

    # ---- EXTERNAL (vendor/customer) — no humans needed ----
    # External sites have no TRM hive and no decisions to review.
}


def needs_human_for_trm(trm_name: str, site_role: SiteRole) -> bool:
    """Check whether a TRM agent at a site with given role needs a human.

    Returns False for EXTERNAL sites (no TRM hive).
    Returns False for unknown (trm_name, site_role) pairs — safe default
    since unknown combos likely mean the TRM isn't active there.
    """
    if site_role == SiteRole.EXTERNAL:
        return False
    return _HUMAN_COUNTERPART_MAP.get((trm_name, site_role), False)


def get_human_trms_for_site(
    master_type: str,
    site_role: SiteRole,
    sc_site_type: Optional[str] = None,
) -> FrozenSet[str]:
    """Return TRMs that need a human at this site.

    Intersection of:
      1. TRMs active for this site type (from site_capabilities)
      2. TRMs that need a human for this site role (from mapping)
    """
    active = get_active_trms(master_type, sc_site_type)
    return frozenset(
        trm for trm in active
        if needs_human_for_trm(trm, site_role)
    )


# ---------------------------------------------------------------------------
# DAG topology analysis — classify each site's role
# ---------------------------------------------------------------------------

@dataclass
class SiteInfo:
    """Lightweight site descriptor for topology analysis."""
    id: int
    key: str                 # site code / key
    name: str
    master_type: str         # "manufacturer", "inventory", "vendor", "customer"
    sc_site_type: Optional[str] = None  # NodeType enum value
    dag_type: Optional[str] = None      # "CDC", "RDC", "market_supply", etc.
    is_external: bool = False
    role: SiteRole = SiteRole.EXTERNAL
    region: Optional[str] = None


@dataclass
class LaneInfo:
    """Lightweight lane descriptor."""
    source_site_id: int
    dest_site_id: int


@dataclass
class UserRecommendation:
    """Recommended user to seed for a config."""
    decision_level: str       # DecisionLevelEnum value
    site_scope: List[str]     # site keys this user should be scoped to
    product_scope: Optional[List[str]] = None
    trm_types_covered: List[str] = field(default_factory=list)
    site_names: List[str] = field(default_factory=list)  # human-readable
    rationale: str = ""


def classify_site_roles(
    sites: List[SiteInfo],
    lanes: List[LaneInfo],
) -> List[SiteInfo]:
    """Classify each site's topological role based on DAG structure.

    Mutates each SiteInfo.role in place and returns the list.

    Algorithm:
      1. External sites (vendor/customer/is_external) -> EXTERNAL
      2. Manufacturer master_type -> FACTORY
      3. For INVENTORY sites, analyze internal lane graph:
         - Build set of internal site IDs
         - For each internal INVENTORY site, check if it has downstream
           internal sites (via lanes where it is source)
         - Has downstream internal -> HUB
         - No downstream internal -> SPOKE
         - If only one internal INVENTORY site exists -> STANDALONE
    """
    internal_ids: Set[int] = set()
    inventory_ids: Set[int] = set()
    site_by_id: Dict[int, SiteInfo] = {}

    for site in sites:
        site_by_id[site.id] = site

        # Step 1: external
        mt = site.master_type.lower()
        if site.is_external or mt in ("vendor", "customer", "market_supply", "market_demand"):
            site.role = SiteRole.EXTERNAL
            continue

        internal_ids.add(site.id)

        # Step 2: manufacturer
        if mt == "manufacturer":
            site.role = SiteRole.FACTORY
            continue

        # Step 3: inventory — will be classified below
        inventory_ids.add(site.id)

    # If only one internal inventory site, it's standalone
    if len(inventory_ids) == 1:
        only_id = next(iter(inventory_ids))
        site_by_id[only_id].role = SiteRole.STANDALONE
        return sites

    # Build downstream-internal adjacency for inventory sites
    has_downstream_internal: Set[int] = set()
    for lane in lanes:
        if lane.source_site_id in inventory_ids and lane.dest_site_id in internal_ids:
            has_downstream_internal.add(lane.source_site_id)

    for sid in inventory_ids:
        if sid in has_downstream_internal:
            site_by_id[sid].role = SiteRole.HUB
        else:
            site_by_id[sid].role = SiteRole.SPOKE

    return sites


def recommend_users(
    sites: List[SiteInfo],
    lanes: List[LaneInfo],
) -> List[UserRecommendation]:
    """Generate user recommendations for a supply chain config.

    For each site, determines which TRMs need humans, then aggregates
    by decision_level to produce one UserRecommendation per analyst role
    with the correct site_scope.

    Also includes planning-level users (SC_VP, SOP_DIRECTOR, MPS_MANAGER)
    that span all internal sites.

    Returns a list of UserRecommendation objects ready for user seeding.
    """
    # Classify site roles
    classify_site_roles(sites, lanes)

    # Collect: decision_level -> set of (site_key, site_name, trm_type)
    level_sites: Dict[str, List[Tuple[str, str, str]]] = {}

    for site in sites:
        if site.role == SiteRole.EXTERNAL:
            continue

        human_trms = get_human_trms_for_site(
            master_type=site.master_type,
            site_role=site.role,
            sc_site_type=site.sc_site_type,
        )

        for trm in human_trms:
            dl = TRM_TO_DECISION_LEVEL.get(trm)
            if not dl:
                continue
            level_sites.setdefault(dl, []).append((site.key, site.name, trm))

    recommendations: List[UserRecommendation] = []

    # Planning-level users (full site scope)
    internal_site_keys = [s.key for s in sites if s.role != SiteRole.EXTERNAL]

    for planning_level in ["SC_VP", "SOP_DIRECTOR"]:
        recommendations.append(UserRecommendation(
            decision_level=planning_level,
            site_scope=[],  # empty = full access (strategic level)
            trm_types_covered=[],
            site_names=[],
            rationale=f"{planning_level} — strategic/tactical level, full site visibility",
        ))

    # MPS_MANAGER: needs site scope if there are MPS-managed TRMs at specific sites
    mps_entries = level_sites.pop("MPS_MANAGER", [])
    if mps_entries:
        mps_site_keys = sorted(set(sk for sk, _, _ in mps_entries))
        mps_site_names = sorted(set(sn for _, sn, _ in mps_entries))
        mps_trms = sorted(set(t for _, _, t in mps_entries))
        recommendations.append(UserRecommendation(
            decision_level="MPS_MANAGER",
            site_scope=mps_site_keys if len(mps_site_keys) < len(internal_site_keys) else [],
            trm_types_covered=mps_trms,
            site_names=mps_site_names,
            rationale=f"MPS Manager — covers {', '.join(mps_trms)} at {', '.join(mps_site_names)}",
        ))
    else:
        # Still seed an MPS manager with full scope
        recommendations.append(UserRecommendation(
            decision_level="MPS_MANAGER",
            site_scope=[],
            trm_types_covered=[],
            site_names=[],
            rationale="MPS Manager — operational level, full site visibility",
        ))

    # Analyst-level users: one per decision_level with scoped sites
    for dl, entries in sorted(level_sites.items()):
        site_keys = sorted(set(sk for sk, _, _ in entries))
        site_names = sorted(set(sn for _, sn, _ in entries))
        trm_types = sorted(set(t for _, _, t in entries))

        recommendations.append(UserRecommendation(
            decision_level=dl,
            site_scope=site_keys,
            trm_types_covered=trm_types,
            site_names=site_names,
            rationale=(
                f"{dl} — covers {', '.join(trm_types)} at "
                f"{', '.join(site_names)}"
            ),
        ))

    return recommendations


async def recommend_users_for_config(
    db: AsyncSession,
    config_id: int,
) -> List[UserRecommendation]:
    """Load sites and lanes from DB, then generate user recommendations.

    This is the main entry point for provisioning integration.
    """
    from app.models.supply_chain_config import (
        SupplyChainConfig,
        Site,
        TransportationLane,
    )

    # Load sites
    result = await db.execute(
        select(Site).where(Site.config_id == config_id)
    )
    db_sites = result.scalars().all()

    # Load lanes
    result = await db.execute(
        select(TransportationLane).where(
            TransportationLane.config_id == config_id
        )
    )
    db_lanes = result.scalars().all()

    # Convert to lightweight dataclasses
    sites = []
    for s in db_sites:
        mt = (s.master_type or "inventory").lower()
        is_ext = bool(getattr(s, "is_external", False))
        # Infer external from tpartner_type if master_type not set
        tpt = getattr(s, "tpartner_type", None)
        if tpt in ("vendor", "customer"):
            is_ext = True
            mt = tpt

        # Site key uses SITE_<name> convention for scope matching
        site_key = f"SITE_{s.name}" if s.name else str(s.id)

        sites.append(SiteInfo(
            id=s.id,
            key=site_key,
            name=s.name or str(s.id),
            master_type=mt,
            sc_site_type=getattr(s, "type", None),
            dag_type=getattr(s, "dag_type", None),
            is_external=is_ext,
        ))

    lanes = []
    for ln in db_lanes:
        # TransportationLane uses from_site_id / to_site_id for internal lanes
        src_id = ln.from_site_id
        dst_id = ln.to_site_id
        # Skip external-endpoint lanes (partner-only, no site FK)
        if src_id is None or dst_id is None:
            continue
        lanes.append(LaneInfo(source_site_id=src_id, dest_site_id=dst_id))

    return recommend_users(sites, lanes)


# ---------------------------------------------------------------------------
# Diagnostic / reporting helpers
# ---------------------------------------------------------------------------

def format_recommendations(recs: List[UserRecommendation]) -> str:
    """Format recommendations as a human-readable report."""
    lines = ["Agent-Human Mapping Recommendations", "=" * 45, ""]
    for r in recs:
        scope_str = ", ".join(r.site_scope) if r.site_scope else "(all sites)"
        lines.append(f"  {r.decision_level:<30} scope: {scope_str}")
        if r.trm_types_covered:
            lines.append(f"    TRMs: {', '.join(r.trm_types_covered)}")
        lines.append(f"    Rationale: {r.rationale}")
        lines.append("")
    return "\n".join(lines)


def format_site_analysis(sites: List[SiteInfo]) -> str:
    """Format site role classification as a human-readable report."""
    lines = ["Site Role Analysis", "=" * 45, ""]
    for s in sites:
        active_trms = get_active_trms(s.master_type, s.sc_site_type) if s.role != SiteRole.EXTERNAL else frozenset()
        human_trms = get_human_trms_for_site(s.master_type, s.role, s.sc_site_type) if s.role != SiteRole.EXTERNAL else frozenset()
        lines.append(f"  {s.name} ({s.key})")
        lines.append(f"    master_type: {s.master_type}, role: {s.role.value}")
        lines.append(f"    active TRMs: {len(active_trms)}, need human: {len(human_trms)}")
        if human_trms:
            lines.append(f"    human TRMs: {', '.join(sorted(human_trms))}")
        lines.append("")
    return "\n".join(lines)
