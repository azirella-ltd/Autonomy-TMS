#!/usr/bin/env python3
"""
Seed Food Dist Allocation & ATP Demo Data

Creates comprehensive allocation planning and ATP consumption/order promising
demo data for the Food Dist customer. Seeds:

1. Site hierarchy (Company → Region → Country → Site)
2. Product hierarchy (Category → Family → Group → Product)
3. Layer licenses (enterprise tier)
4. Planning cascade (PolicyEnvelope → SupBP → SC → SBP → AllocationCommits)
5. Inventory projections (700 rows - 25 products × 28 days)
6. ATP projections (~2100 rows - with customer-specific allocations)
7. Order promises (~80 orders across 10 customers)
8. Feedback signals and agent decision metrics
9. Two new demo users (Allocation Manager, Order Promising Manager)

Prerequisites:
    - seed_dot_foods_demo.py must have been run first
    - Food Dist SC config must exist (from FoodDistConfigGenerator)

Usage:
    docker compose exec backend python scripts/seed_dot_foods_allocation_demo.py
"""

import os
import sys
import random
import hashlib
import json
from pathlib import Path
from datetime import datetime, date, timedelta

# Ensure backend package is importable
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import select

from app.db.session import sync_engine
from app.models.user import User, UserTypeEnum, PowellRoleEnum
from app.models.tenant import Tenant
from app.models.supply_chain_config import SupplyChainConfig
from app.models.sc_entities import Product
from app.models.planning_hierarchy import (
    SiteHierarchyNode, ProductHierarchyNode,
    SiteHierarchyLevel, ProductHierarchyLevel,
)
from app.models.planning_cascade import (
    PolicyEnvelope, SupplyBaselinePack, SupplyCommit, SolverBaselinePack,
    AllocationCommit, FeedBackSignal, AgentDecisionMetrics, LayerLicense,
    PolicySource, CommitStatus, LayerName, LayerMode,
    CandidateMethod, AllocationMethod,
)
from app.models.inventory_projection import InvProjection, AtpProjection, OrderPromise
from app.models.decision_tracking import AgentDecision, DecisionType, DecisionStatus, DecisionUrgency
from app.core.security import get_password_hash
from app.core.capabilities import (
    SOP_DIRECTOR_CAPABILITIES, MPS_MANAGER_CAPABILITIES,
)
from app.services.rbac_service import RBACService, seed_default_permissions

# Seed for reproducibility
random.seed(42)

DEFAULT_PASSWORD = os.getenv("AUTONOMY_DEFAULT_PASSWORD", "Autonomy@2025")

# =============================================================================
# Customer → Priority Mapping
# =============================================================================

CUSTOMER_PRIORITIES = {
    "METROGRO":   {"segment": "key_account",  "priority": 1, "pct": 0.30, "demand_mult": 2.0},
    "QUICKSERV":  {"segment": "key_account",  "priority": 1, "pct": 0.30, "demand_mult": 1.8},
    "RESTSUPPLY": {"segment": "contract",     "priority": 2, "pct": 0.25, "demand_mult": 1.5},
    "COASTHLTH":  {"segment": "contract",     "priority": 2, "pct": 0.25, "demand_mult": 0.9},
    "SCHLDFOOD":  {"segment": "contract",     "priority": 2, "pct": 0.25, "demand_mult": 1.4},
    "CAMPUSDINE": {"segment": "retail",       "priority": 3, "pct": 0.20, "demand_mult": 1.2},
    "FAMREST":    {"segment": "retail",       "priority": 3, "pct": 0.20, "demand_mult": 1.0},
    "PREMCATER":  {"segment": "retail",       "priority": 3, "pct": 0.20, "demand_mult": 1.1},
    "DWNTWNDELI": {"segment": "wholesale",   "priority": 4, "pct": 0.15, "demand_mult": 0.6},
    "GREENVAL":   {"segment": "spot_market",  "priority": 5, "pct": 0.10, "demand_mult": 0.7},
}

# Product SKUs grouped by family
PRODUCT_FAMILIES = {
    "FROZEN_PROTEINS":    ["FP001", "FP002", "FP003", "FP004", "FP005"],
    "FROZEN_DESSERTS":    ["FD001", "FD002", "FD003", "FD004", "FD005"],
    "REFRIGERATED_DAIRY": ["RD001", "RD002", "RD003", "RD004", "RD005"],
    "DRY_PANTRY":         ["DP001", "DP002", "DP003", "DP004", "DP005"],
    "BEVERAGES":          ["BV001", "BV002", "BV003", "BV004", "BV005"],
}

FAMILY_TO_CATEGORY = {
    "FROZEN_PROTEINS": "FROZEN",
    "FROZEN_DESSERTS": "FROZEN",
    "REFRIGERATED_DAIRY": "REFRIGERATED",
    "DRY_PANTRY": "DRY",
    "BEVERAGES": "DRY",
}

ALL_SKUS = [sku for skus in PRODUCT_FAMILIES.values() for sku in skus]

# Supplier mapping (from FoodDistConfigGenerator)
SKU_SUPPLIER = {
    "FP001": "TYSON", "FP002": "TYSON", "FP003": "SYSCOMEAT", "FP004": "SYSCOMEAT", "FP005": "SYSCOMEAT",
    "RD001": "KRAFT", "RD002": "KRAFT", "RD003": "LANDOLAKES", "RD004": "LANDOLAKES", "RD005": "LANDOLAKES",
    "DP001": "GENMILLS", "DP002": "GENMILLS", "DP003": "CONAGRA", "DP004": "CONAGRA", "DP005": "CONAGRA",
    "FD001": "NESTLE", "FD002": "NESTLE", "FD003": "RICHPROD", "FD004": "RICHPROD", "FD005": "RICHPROD",
    "BV001": "TROP", "BV002": "TROP", "BV003": "COCACOLA", "BV004": "COCACOLA", "BV005": "COCACOLA",
}

# Base weekly demand per SKU (cases)
SKU_BASE_DEMAND = {
    "FP001": 150, "FP002": 120, "FP003": 80, "FP004": 60, "FP005": 40,
    "RD001": 200, "RD002": 250, "RD003": 180, "RD004": 300, "RD005": 100,
    "DP001": 200, "DP002": 180, "DP003": 150, "DP004": 160, "DP005": 120,
    "FD001": 80, "FD002": 40, "FD003": 50, "FD004": 60, "FD005": 35,
    "BV001": 220, "BV002": 150, "BV003": 180, "BV004": 200, "BV005": 140,
}


def _compute_hash(data: dict) -> str:
    """Compute SHA-256 hash for a data dict."""
    json_str = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(json_str.encode()).hexdigest()[:64]


# =============================================================================
# 1. Site Hierarchy
# =============================================================================

def seed_site_hierarchy(db: Session, customer_id: int) -> dict:
    """Seed site hierarchy nodes. Returns dict of code → SiteHierarchyNode."""
    print("\n  Seeding site hierarchy...")

    # Check if already seeded
    existing = db.query(SiteHierarchyNode).filter(
        SiteHierarchyNode.customer_id == customer_id,
        SiteHierarchyNode.code == "DF_COMPANY"
    ).first()
    if existing:
        print("    Site hierarchy already exists, loading...")
        nodes = db.query(SiteHierarchyNode).filter(
            SiteHierarchyNode.customer_id == customer_id
        ).all()
        return {n.code: n for n in nodes}

    nodes = {}

    # Use string values for hierarchy_level (PostgreSQL enum uses lowercase values)
    # Company level
    company = SiteHierarchyNode(
        code="DF_COMPANY", name="Food Dist Inc.",
        hierarchy_level=SiteHierarchyLevel.COMPANY,
        hierarchy_path="DF_COMPANY", depth=0,
        customer_id=customer_id, is_plannable=True,
    )
    db.add(company)
    db.flush()
    nodes["DF_COMPANY"] = company

    # Region level
    region = SiteHierarchyNode(
        code="DF_CENTRAL", name="Central US",
        parent_id=company.id,
        hierarchy_level=SiteHierarchyLevel.REGION,
        hierarchy_path="DF_COMPANY/DF_CENTRAL", depth=1,
        customer_id=customer_id, is_plannable=True,
    )
    db.add(region)
    db.flush()
    nodes["DF_CENTRAL"] = region

    # Country level
    country = SiteHierarchyNode(
        code="DF_US", name="United States",
        parent_id=region.id,
        hierarchy_level=SiteHierarchyLevel.COUNTRY,
        hierarchy_path="DF_COMPANY/DF_CENTRAL/DF_US", depth=2,
        customer_id=customer_id, is_plannable=True,
    )
    db.add(country)
    db.flush()
    nodes["DF_US"] = country

    # Site level - DC + all 10 customers
    site_defs = [
        ("FOODDIST_DC", "Food Dist Central DC"),
        ("RESTSUPPLY", "Restaurant Supply Co"),
        ("METROGRO", "Metro Grocery Chain"),
        ("CAMPUSDINE", "Campus Dining Services"),
        ("COASTHLTH", "Coastal Healthcare System"),
        ("DWNTWNDELI", "Downtown Deli Group"),
        ("FAMREST", "Family Restaurant Inc"),
        ("QUICKSERV", "Quick Serve Foods LLC"),
        ("GREENVAL", "Green Valley Markets"),
        ("PREMCATER", "Premier Catering Services"),
        ("SCHLDFOOD", "School District Foods"),
    ]

    for code, name in site_defs:
        node = SiteHierarchyNode(
            code=f"DF_SITE_{code}", name=name,
            parent_id=country.id,
            hierarchy_level=SiteHierarchyLevel.SITE,
            hierarchy_path=f"DF_COMPANY/DF_CENTRAL/DF_US/{code}",
            depth=3, customer_id=customer_id, is_plannable=True,
        )
        db.add(node)
        db.flush()
        nodes[f"DF_SITE_{code}"] = node

    db.flush()
    print(f"    Created {len(nodes)} site hierarchy nodes")
    return nodes


# =============================================================================
# 2. Product Hierarchy
# =============================================================================

def seed_product_hierarchy(db: Session, customer_id: int) -> dict:
    """Seed product hierarchy nodes. Returns dict of code → ProductHierarchyNode."""
    print("\n  Seeding product hierarchy...")

    existing = db.query(ProductHierarchyNode).filter(
        ProductHierarchyNode.customer_id == customer_id,
        ProductHierarchyNode.code == "DF_ALL_PRODUCTS"
    ).first()
    if existing:
        print("    Product hierarchy already exists, loading...")
        nodes = db.query(ProductHierarchyNode).filter(
            ProductHierarchyNode.customer_id == customer_id
        ).all()
        return {n.code: n for n in nodes}

    nodes = {}

    # Top level
    top = ProductHierarchyNode(
        code="DF_ALL_PRODUCTS", name="All Products",
        hierarchy_level=ProductHierarchyLevel.CATEGORY,
        hierarchy_path="DF_ALL_PRODUCTS", depth=0,
        customer_id=customer_id, is_plannable=True,
    )
    db.add(top)
    db.flush()
    nodes["DF_ALL_PRODUCTS"] = top

    # Temperature categories
    categories = {
        "FROZEN": "Frozen Products",
        "REFRIGERATED": "Refrigerated Products",
        "DRY": "Dry/Ambient Products",
    }

    cat_nodes = {}
    for cat_code, cat_name in categories.items():
        cat = ProductHierarchyNode(
            code=f"DF_CAT_{cat_code}", name=cat_name,
            parent_id=top.id,
            hierarchy_level=ProductHierarchyLevel.CATEGORY,
            hierarchy_path=f"DF_ALL_PRODUCTS/{cat_code}", depth=1,
            customer_id=customer_id, is_plannable=True,
        )
        db.add(cat)
        db.flush()
        nodes[f"DF_CAT_{cat_code}"] = cat
        cat_nodes[cat_code] = cat

    # Families
    family_nodes = {}
    for family_code, sku_list in PRODUCT_FAMILIES.items():
        cat_code = FAMILY_TO_CATEGORY[family_code]
        fam = ProductHierarchyNode(
            code=f"DF_FAM_{family_code}", name=family_code.replace("_", " ").title(),
            parent_id=cat_nodes[cat_code].id,
            hierarchy_level=ProductHierarchyLevel.FAMILY,
            hierarchy_path=f"DF_ALL_PRODUCTS/{cat_code}/{family_code}", depth=2,
            customer_id=customer_id, is_plannable=True,
        )
        db.add(fam)
        db.flush()
        nodes[f"DF_FAM_{family_code}"] = fam
        family_nodes[family_code] = fam

    # Products (SKU level)
    for family_code, sku_list in PRODUCT_FAMILIES.items():
        cat_code = FAMILY_TO_CATEGORY[family_code]
        for sku in sku_list:
            prod = ProductHierarchyNode(
                code=f"DF_SKU_{sku}", name=sku,
                parent_id=family_nodes[family_code].id,
                hierarchy_level=ProductHierarchyLevel.PRODUCT,
                hierarchy_path=f"DF_ALL_PRODUCTS/{cat_code}/{family_code}/{sku}",
                depth=3, customer_id=customer_id, is_plannable=True,
                product_id=sku,  # Link to existing Product
            )
            db.add(prod)
            db.flush()
            nodes[f"DF_SKU_{sku}"] = prod

    db.flush()
    print(f"    Created {len(nodes)} product hierarchy nodes")
    return nodes


# =============================================================================
# 3. Layer Licenses
# =============================================================================

def seed_layer_licenses(db: Session, customer_id: int):
    """Seed enterprise-tier layer licenses for Food Dist."""
    print("\n  Seeding layer licenses...")

    layers = [
        (LayerName.SOP, "enterprise"),
        (LayerName.MRS, "planning"),
        (LayerName.SUPPLY_AGENT, "ai_execution"),
        (LayerName.ALLOCATION_AGENT, "ai_execution"),
        (LayerName.EXECUTION, "foundation"),
    ]

    count = 0
    for layer, tier in layers:
        existing = db.query(LayerLicense).filter(
            LayerLicense.customer_id == customer_id,
            LayerLicense.layer == layer,
        ).first()
        if existing:
            continue

        ll = LayerLicense(
            customer_id=customer_id,
            layer=layer,
            mode=LayerMode.ACTIVE,
            activated_at=datetime.utcnow(),
            package_tier=tier,
        )
        db.add(ll)
        count += 1

    db.flush()
    print(f"    Created {count} layer licenses (skipped {len(layers) - count} existing)")


# =============================================================================
# 4. Planning Cascade
# =============================================================================

def seed_planning_cascade(db: Session, config_id: int, customer_id: int, sop_director_id: int, alloc_mgr_id: int):
    """Seed the full planning cascade: PolicyEnvelope → SupBP → SC → SBP → AllocationCommits."""
    print("\n  Seeding planning cascade...")

    # Check for existing cascade data
    existing_pe = db.query(PolicyEnvelope).filter(
        PolicyEnvelope.config_id == config_id,
        PolicyEnvelope.customer_id == customer_id,
    ).first()
    if existing_pe:
        print("    Planning cascade already seeded, skipping")
        return

    base_date = date(2026, 2, 3)  # Monday of current week

    # -- PolicyEnvelope --
    pe_data = {
        "config_id": config_id,
        "safety_stock_targets": {"frozen": 2.5, "refrigerated": 2.0, "dry": 3.0},
        "otif_floors": {"key_account": 0.99, "contract": 0.95, "retail": 0.92, "wholesale": 0.90, "spot_market": 0.85},
        "allocation_reserves": {"key_account": 0.30, "contract": 0.25, "retail": 0.20, "wholesale": 0.15, "spot_market": 0.10},
        "expedite_caps": {"frozen": 10000, "refrigerated": 8000, "dry": 5000},
        "effective_date": base_date.isoformat(),
    }
    pe = PolicyEnvelope(
        hash=_compute_hash(pe_data),
        config_id=config_id, customer_id=customer_id,
        generated_by=PolicySource.CUSTOMER_INPUT,
        safety_stock_targets=pe_data["safety_stock_targets"],
        otif_floors=pe_data["otif_floors"],
        allocation_reserves=pe_data["allocation_reserves"],
        expedite_caps=pe_data["expedite_caps"],
        dos_ceilings={"frozen": 14, "refrigerated": 10, "dry": 21},
        effective_date=base_date,
        created_by=sop_director_id,
        approved_at=datetime(2026, 2, 3, 9, 0, 0),
        approved_by=sop_director_id,
    )
    db.add(pe)
    db.flush()
    print(f"    PolicyEnvelope id={pe.id}")

    # -- SupplyBaselinePack (3 candidates) --
    supbp_candidates = []
    for method in ["REORDER_POINT_V1", "PARAMETRIC_CFA_V1", "SERVICE_MAXIMIZED_V1"]:
        orders = []
        for sku in ALL_SKUS:
            base_qty = SKU_BASE_DEMAND[sku] * 2  # ~2 weeks cover
            if method == "SERVICE_MAXIMIZED_V1":
                base_qty = int(base_qty * 1.3)
            elif method == "REORDER_POINT_V1":
                base_qty = int(base_qty * 0.85)
            orders.append({
                "sku": sku,
                "supplier": SKU_SUPPLIER[sku],
                "qty": base_qty,
                "date": (base_date + timedelta(days=2)).isoformat(),
            })
        cost_factor = {"REORDER_POINT_V1": 0.90, "PARAMETRIC_CFA_V1": 1.0, "SERVICE_MAXIMIZED_V1": 1.15}[method]
        otif_factor = {"REORDER_POINT_V1": 0.91, "PARAMETRIC_CFA_V1": 0.96, "SERVICE_MAXIMIZED_V1": 0.98}[method]
        supbp_candidates.append({
            "method": method,
            "orders": orders,
            "projected_cost": round(125000 * cost_factor, 2),
            "projected_otif": otif_factor,
            "projected_dos": round(12.5 * cost_factor, 1),
        })

    supbp_data = {"policy_envelope_hash": pe.hash, "candidates": supbp_candidates}
    supbp = SupplyBaselinePack(
        hash=_compute_hash(supbp_data),
        policy_envelope_id=pe.id, policy_envelope_hash=pe.hash,
        config_id=config_id, customer_id=customer_id,
        generated_by=PolicySource.AUTONOMY_SIM,
        candidates=supbp_candidates,
        tradeoff_frontier=[
            {"method": "REORDER_POINT_V1", "cost": 112500, "otif": 0.91},
            {"method": "PARAMETRIC_CFA_V1", "cost": 125000, "otif": 0.96},
            {"method": "SERVICE_MAXIMIZED_V1", "cost": 143750, "otif": 0.98},
        ],
        planning_horizon_days=28,
    )
    db.add(supbp)
    db.flush()
    print(f"    SupplyBaselinePack id={supbp.id}")

    # -- SupplyCommit (ACCEPTED, using PARAMETRIC_CFA) --
    sc_recs = supbp_candidates[1]["orders"]  # PARAMETRIC_CFA candidate
    sc_data = {"supbp_hash": supbp.hash, "recommendations": sc_recs}
    sc = SupplyCommit(
        hash=_compute_hash(sc_data),
        supply_baseline_pack_id=supbp.id, supply_baseline_pack_hash=supbp.hash,
        config_id=config_id, customer_id=customer_id,
        selected_method="PARAMETRIC_CFA_V1",
        recommendations=sc_recs,
        projected_otif=0.96, projected_inventory_cost=125000, projected_dos=12.5,
        status=CommitStatus.ACCEPTED,
        agent_confidence=0.92,
        agent_reasoning="Selected PARAMETRIC_CFA for optimal cost-service balance. OTIF 96% meets all segment floors.",
        reviewed_by=sop_director_id,
        reviewed_at=datetime(2026, 2, 4, 10, 30, 0),
        approved_by=sop_director_id,
        approved_at=datetime(2026, 2, 4, 10, 35, 0),
        created_at=datetime(2026, 2, 4, 8, 0, 0),
        submitted_at=datetime(2026, 2, 4, 10, 35, 0),
    )
    db.add(sc)
    db.flush()
    print(f"    SupplyCommit id={sc.id}")

    # -- SolverBaselinePack (3 allocation candidates) --
    sbp_candidates = []
    for method in ["FAIR_SHARE_V1", "PRIORITY_V1", "LP_OPTIMAL_V1"]:
        allocs = _generate_allocation_entries(base_date, method)
        sbp_candidates.append({
            "method": method,
            "allocations": allocs[:20],  # Store summary in JSON
            "total_allocated": sum(a["entitlement_qty"] for a in allocs),
            "service_floor_compliance": {"FAIR_SHARE_V1": 0.88, "PRIORITY_V1": 0.97, "LP_OPTIMAL_V1": 0.95}[method],
        })

    sbp_data = {"supply_commit_hash": sc.hash, "candidates": sbp_candidates}
    sbp = SolverBaselinePack(
        hash=_compute_hash(sbp_data),
        supply_commit_id=sc.id, supply_commit_hash=sc.hash,
        config_id=config_id, customer_id=customer_id,
        candidates=sbp_candidates,
    )
    db.add(sbp)
    db.flush()
    print(f"    SolverBaselinePack id={sbp.id}")

    # -- AllocationCommits (4 weeks) --
    week_configs = [
        (base_date, CommitStatus.ACCEPTED, "PRIORITY_V1", None, datetime(2026, 2, 4, 14, 0, 0)),
        (base_date + timedelta(days=7), CommitStatus.OVERRIDDEN, "PRIORITY_V1",
         {"changes": [
             {"sku": "RD001", "customer": "CAMPUSDINE", "original_qty": 25, "new_qty": 40, "reason": "Upcoming campus event"},
             {"sku": "FP001", "customer": "DWNTWNDELI", "original_qty": 8, "new_qty": 15, "reason": "New menu launch"},
         ]},
         datetime(2026, 2, 9, 9, 0, 0)),
        (base_date + timedelta(days=14), CommitStatus.PROPOSED, "PRIORITY_V1", None, None),
        (base_date + timedelta(days=21), CommitStatus.PROPOSED, "PRIORITY_V1", None, None),
    ]

    for i, (week_start, status, method, overrides, reviewed_at) in enumerate(week_configs):
        week_label = f"2026-W{week_start.isocalendar()[1]:02d}"
        allocs = _generate_allocation_entries(week_start, method)

        ac_data = {"supply_commit_hash": sc.hash, "sbp_hash": sbp.hash, "allocations": allocs}
        ac = AllocationCommit(
            hash=_compute_hash({**ac_data, "week": week_label}),
            supply_commit_id=sc.id, supply_commit_hash=sc.hash,
            solver_baseline_pack_id=sbp.id, solver_baseline_pack_hash=sbp.hash,
            config_id=config_id, customer_id=customer_id,
            selected_method=method,
            allocations=allocs,
            status=status,
            agent_confidence=round(0.88 + random.uniform(0, 0.10), 2),
            agent_reasoning=f"Priority-based allocation for {week_label}. P1/P2 customers receive priority fill.",
            override_details=overrides,
            reviewed_by=alloc_mgr_id if status != CommitStatus.PROPOSED else None,
            reviewed_at=reviewed_at,
            created_at=datetime(2026, 2, 3 + i * 7, 6, 0, 0),
        )
        db.add(ac)
        db.flush()
        print(f"    AllocationCommit week={week_label} status={status.value} id={ac.id}")

    db.flush()


def _generate_allocation_entries(week_start: date, method: str) -> list:
    """Generate allocation entries for all SKUs × customers for a given week."""
    entries = []
    week_label = f"2026-W{week_start.isocalendar()[1]:02d}"

    for sku in ALL_SKUS:
        total_supply = SKU_BASE_DEMAND[sku] * 2  # 2 weeks of supply available

        for cust_code, info in CUSTOMER_PRIORITIES.items():
            priority = info["priority"]
            pct = info["pct"]
            demand_mult = info["demand_mult"]

            # Base allocation: supply × priority percentage × customer demand weight
            cust_demand = SKU_BASE_DEMAND[sku] * demand_mult / 7  # daily demand
            weekly_demand = int(cust_demand * 7)

            if method == "FAIR_SHARE_V1":
                entitlement = int(total_supply * 0.10)  # Equal share
            elif method == "PRIORITY_V1":
                entitlement = int(total_supply * pct * demand_mult / 5)  # Priority-weighted
            else:  # LP_OPTIMAL
                entitlement = int(min(weekly_demand, total_supply * pct * demand_mult / 4))

            entitlement = max(1, entitlement)

            entries.append({
                "sku": sku,
                "segment": info["segment"],
                "customer_id": cust_code,
                "entitlement_qty": entitlement,
                "priority": priority,
                "time_bucket": week_label,
            })

    return entries


# =============================================================================
# 5. Inventory Projections
# =============================================================================

def seed_inv_projections(db: Session, config_id: int, customer_id: int, dc_site_id: int):
    """Seed 28-day inventory projections for all 25 products."""
    print("\n  Seeding inventory projections...")

    base_date = date(2026, 2, 3)

    existing = db.query(InvProjection).filter(
        InvProjection.company_id == customer_id,
        InvProjection.product_id == ALL_SKUS[0],
        InvProjection.projection_date == base_date,
    ).first()
    if existing:
        print("    InvProjections already exist, skipping")
        return

    count = 0
    for sku in ALL_SKUS:
        base_demand = SKU_BASE_DEMAND[sku]
        daily_demand = base_demand / 7
        initial_inv = base_demand * 3  # ~3 weeks stock

        inv = initial_inv
        for day_offset in range(28):
            proj_date = base_date + timedelta(days=day_offset)

            # Demand depletion with some noise
            demand = max(0, daily_demand * (1 + random.gauss(0, 0.15)))

            # Replenishment every ~10 days
            supply = 0
            if day_offset % 10 == 3:
                supply = base_demand * 2  # 2-week replenishment

            in_transit = supply * 0.5 if (day_offset % 10 == 1 or day_offset % 10 == 2) else 0

            inv = max(0, inv - demand + supply)
            allocated = min(inv * 0.6, demand * 2)
            available = max(0, inv - allocated)
            atp = max(0, available + in_transit)

            # Stochastic bands
            std_dev = daily_demand * 0.3
            p50 = inv
            p10 = max(0, inv - 1.28 * std_dev * (day_offset + 1) ** 0.5)
            p90 = inv + 1.28 * std_dev * (day_offset + 1) ** 0.5
            stockout_prob = max(0, min(1, 0.5 - inv / (daily_demand * 5 + 1))) if daily_demand > 0 else 0
            dos = inv / daily_demand if daily_demand > 0 else 99

            proj = InvProjection(
                company_id=customer_id,
                product_id=sku,
                site_id=dc_site_id,
                projection_date=proj_date,
                on_hand_qty=round(inv, 1),
                in_transit_qty=round(in_transit, 1),
                on_order_qty=round(supply * 0.3, 1),
                allocated_qty=round(allocated, 1),
                available_qty=round(available, 1),
                reserved_qty=0,
                supply_qty=round(supply, 1),
                demand_qty=round(demand, 1),
                opening_inventory=round(inv + demand - supply, 1),
                closing_inventory=round(inv, 1),
                atp_qty=round(atp, 1),
                ctp_qty=round(atp * 1.1, 1),
                closing_inventory_p10=round(p10, 1),
                closing_inventory_p50=round(p50, 1),
                closing_inventory_p90=round(p90, 1),
                closing_inventory_std_dev=round(std_dev * (day_offset + 1) ** 0.5, 1),
                stockout_probability=round(stockout_prob, 3),
                days_of_supply=round(dos, 1),
                config_id=config_id,
                source="seed_allocation_demo",
            )
            db.add(proj)
            count += 1

    db.flush()
    print(f"    Created {count} InvProjection rows")


# =============================================================================
# 6. ATP Projections
# =============================================================================

def seed_atp_projections(db: Session, config_id: int, customer_id: int, dc_site_id: int):
    """Seed ATP projections with customer-specific allocations."""
    print("\n  Seeding ATP projections...")

    base_date = date(2026, 2, 3)

    existing = db.query(AtpProjection).filter(
        AtpProjection.company_id == customer_id,
        AtpProjection.product_id == ALL_SKUS[0],
        AtpProjection.atp_date == base_date,
    ).first()
    if existing:
        print("    AtpProjections already exist, skipping")
        return

    count = 0
    for sku in ALL_SKUS:
        base_demand = SKU_BASE_DEMAND[sku]
        daily_supply = base_demand * 2 / 7  # avg daily supply
        initial_atp = base_demand * 1.5  # starting ATP

        cumulative_atp = 0
        atp = initial_atp

        for day_offset in range(28):
            atp_date = base_date + timedelta(days=day_offset)
            daily_demand = base_demand / 7

            # Overall supply/demand
            supply = daily_supply * (1 + random.gauss(0, 0.1))
            demand = daily_demand * (1 + random.gauss(0, 0.15))
            allocated = demand * 0.8

            atp = max(0, atp + supply - demand)
            cumulative_atp += atp

            # Aggregate ATP row (no customer)
            db.add(AtpProjection(
                company_id=customer_id,
                product_id=sku, site_id=dc_site_id,
                atp_date=atp_date,
                atp_qty=round(atp, 1),
                cumulative_atp_qty=round(cumulative_atp, 1),
                opening_balance=round(atp + demand - supply, 1),
                supply_qty=round(supply, 1),
                demand_qty=round(demand, 1),
                allocated_qty=round(allocated, 1),
                atp_rule="cumulative",
                source="seed_allocation_demo",
                config_id=config_id,
            ))
            count += 1

            # Customer-specific ATP for P1 and P2 customers
            for cust_code, info in CUSTOMER_PRIORITIES.items():
                if info["priority"] > 2:
                    continue  # Only P1/P2 get customer-specific ATP rows
                cust_pct = info["pct"]
                cust_atp = round(atp * cust_pct, 1)
                db.add(AtpProjection(
                    company_id=customer_id,
                    product_id=sku, site_id=dc_site_id,
                    atp_date=atp_date,
                    atp_qty=cust_atp,
                    cumulative_atp_qty=round(cumulative_atp * cust_pct, 1),
                    opening_balance=round((atp + demand - supply) * cust_pct, 1),
                    supply_qty=round(supply * cust_pct, 1),
                    demand_qty=round(demand * info["demand_mult"] / 10, 1),
                    allocated_qty=round(allocated * cust_pct, 1),
                    customer_id=cust_code,
                    allocation_priority=info["priority"],
                    allocation_percentage=cust_pct,
                    atp_rule="cumulative",
                    source="seed_allocation_demo",
                    config_id=config_id,
                ))
                count += 1

    db.flush()
    print(f"    Created {count} AtpProjection rows")


# =============================================================================
# 7. Order Promises
# =============================================================================

def seed_order_promises(db: Session, customer_id: int, dc_site_id: int):
    """Seed ~80 order promises across 10 customers."""
    print("\n  Seeding order promises...")

    base_date = date(2026, 2, 3)

    existing = db.query(OrderPromise).filter(
        OrderPromise.company_id == customer_id,
        OrderPromise.order_id.like("DF-ORD-%"),
    ).first()
    if existing:
        print("    OrderPromises already exist, skipping")
        return

    order_num = 1000
    count = 0

    for cust_code, info in CUSTOMER_PRIORITIES.items():
        # More orders for higher-priority customers
        num_orders = {1: 12, 2: 10, 3: 8, 4: 5, 5: 4}[info["priority"]]

        for _ in range(num_orders):
            sku = random.choice(ALL_SKUS)
            order_num += 1
            order_id = f"DF-ORD-{order_num}"
            req_date = base_date + timedelta(days=random.randint(0, 21))
            req_qty = int(SKU_BASE_DEMAND[sku] * info["demand_mult"] / 7 * random.uniform(0.5, 2.0))
            req_qty = max(5, req_qty)

            # Promise depends on priority
            if info["priority"] <= 2:
                # P1/P2: usually full fill, on time
                promised_qty = req_qty
                promised_date = req_date
                fulfillment = "single"
                partial = False
                backorder_qty = None
                status_roll = random.random()
                if status_roll < 0.15:
                    status = "FULFILLED"
                elif status_roll < 0.35:
                    status = "PROPOSED"
                else:
                    status = "CONFIRMED"
                confidence = round(random.uniform(0.92, 0.99), 2)
            elif info["priority"] == 3:
                # P3: mostly full, some partial
                if random.random() < 0.25:
                    promised_qty = int(req_qty * random.uniform(0.6, 0.9))
                    fulfillment = "partial"
                    partial = True
                    backorder_qty = req_qty - promised_qty
                else:
                    promised_qty = req_qty
                    fulfillment = "single"
                    partial = False
                    backorder_qty = None
                promised_date = req_date + timedelta(days=random.randint(0, 2))
                status_roll = random.random()
                if status_roll < 0.10:
                    status = "FULFILLED"
                elif status_roll < 0.35:
                    status = "PROPOSED"
                else:
                    status = "CONFIRMED"
                confidence = round(random.uniform(0.82, 0.94), 2)
            else:
                # P4/P5: partial fills common, delays
                if random.random() < 0.45:
                    promised_qty = int(req_qty * random.uniform(0.4, 0.8))
                    fulfillment = "partial"
                    partial = True
                    backorder_qty = req_qty - promised_qty
                elif random.random() < 0.15:
                    promised_qty = 0
                    fulfillment = "single"
                    partial = False
                    backorder_qty = req_qty
                    status = "CANCELLED"
                    confidence = 0.0
                else:
                    promised_qty = req_qty
                    fulfillment = "single"
                    partial = False
                    backorder_qty = None
                promised_date = req_date + timedelta(days=random.randint(1, 5))

                if promised_qty > 0:
                    status_roll = random.random()
                    if status_roll < 0.40:
                        status = "PROPOSED"
                    else:
                        status = "CONFIRMED"
                    confidence = round(random.uniform(0.65, 0.85), 2)

            promise_source = "ATP"
            if partial and backorder_qty:
                promise_source = "BACKORDER"

            op = OrderPromise(
                order_id=order_id,
                order_line_number=1,
                company_id=customer_id,
                product_id=sku,
                site_id=dc_site_id,
                customer_id=cust_code,
                requested_quantity=req_qty,
                requested_date=req_date,
                promised_quantity=promised_qty,
                promised_date=promised_date,
                promise_source=promise_source,
                fulfillment_type=fulfillment,
                partial_promise=partial,
                backorder_quantity=backorder_qty,
                backorder_date=promised_date + timedelta(days=7) if backorder_qty else None,
                promise_status=status,
                promise_confidence=confidence,
                source="seed_allocation_demo",
            )
            db.add(op)
            count += 1

    db.flush()
    print(f"    Created {count} OrderPromise rows")


# =============================================================================
# 8. Feedback Signals + Agent Decision Metrics
# =============================================================================

def seed_feedback_and_metrics(db: Session, config_id: int, customer_id: int, alloc_mgr_id: int):
    """Seed feedback signals and agent decision metrics."""
    print("\n  Seeding feedback signals and agent decision metrics...")

    existing = db.query(FeedBackSignal).filter(
        FeedBackSignal.config_id == config_id,
        FeedBackSignal.customer_id == customer_id,
    ).first()
    if existing:
        print("    Feedback/metrics already exist, skipping")
        return

    # Feedback signals
    signals = [
        # OTIF signals per segment
        ("actual_otif", "execution", "allocation_agent", "key_account_otif", 0.985, 0.99, -0.005,
         {"segment": "key_account", "actual": 0.985, "floor": 0.99}),
        ("actual_otif", "execution", "allocation_agent", "contract_otif", 0.96, 0.95, 0.01,
         {"segment": "contract", "actual": 0.96, "floor": 0.95}),
        ("actual_otif", "execution", "allocation_agent", "retail_otif", 0.93, 0.92, 0.01,
         {"segment": "retail", "actual": 0.93, "floor": 0.92}),
        ("actual_otif", "execution", "allocation_agent", "wholesale_otif", 0.85, 0.90, -0.05,
         {"segment": "wholesale", "actual": 0.85, "floor": 0.90}),
        ("actual_otif", "execution", "allocation_agent", "spot_market_otif", 0.72, 0.85, -0.13,
         {"segment": "spot_market", "actual": 0.72, "floor": 0.85}),
        # Shortfall signal
        ("allocation_shortfall", "allocation", "supply_agent", "p4_p5_shortfall", 0.18, 0.10, 0.08,
         {"segments": ["wholesale", "spot_market"], "shortfall_pct": 0.18, "threshold": 0.10}),
        # Override outcome
        ("override_outcome", "allocation", "allocation_agent", "week2_override_impact", 0.04, 0.0, 0.04,
         {"week": "2026-W07", "overrider": "allocation_manager", "impact": "+4% retail OTIF from P3 qty increase"}),
        # Expedite signal
        ("expedite_frequency", "execution", "sop", "frozen_expedites", 3, 2, 1,
         {"category": "frozen", "count": 3, "threshold": 2, "cost": 4500}),
    ]

    for sig_type, layer, fed_to, metric, value, thresh, dev, details in signals:
        fb = FeedBackSignal(
            config_id=config_id, customer_id=customer_id,
            signal_type=sig_type,
            measured_at_layer=layer,
            fed_back_to=fed_to,
            metric_name=metric,
            metric_value=value,
            threshold=thresh,
            deviation=dev,
            details=details,
            measured_at=datetime(2026, 2, 9, 8, 0, 0),
        )
        # Add suggested retune for underperforming segments
        if dev < 0 and sig_type == "actual_otif":
            segment = details["segment"]
            current_reserve = {"key_account": 0.30, "contract": 0.25, "retail": 0.20, "wholesale": 0.15, "spot_market": 0.10}[segment]
            fb.suggested_retune = {
                "parameter": f"allocation_reserves.{segment}",
                "current": current_reserve,
                "suggested": round(current_reserve + 0.05, 2),
            }
        db.add(fb)

    print(f"    Created {len(signals)} FeedBackSignal rows")

    # Agent decision metrics - 2 weeks × 2 agents
    metrics_data = [
        # Week 1 - supply agent
        ("supply_agent", date(2026, 2, 3), date(2026, 2, 9),
         0.75, 12.5, 8.2, 0.25, 0.12, 0.94, 25, 18, 5, 2, 0, 0, 1),
        # Week 1 - allocation agent
        ("allocation_agent", date(2026, 2, 3), date(2026, 2, 9),
         0.60, 8.8, 15.3, 0.40, 0.18, 0.88, 250, 150, 70, 28, 2, 1, 3),
        # Week 2 - supply agent (improving)
        ("supply_agent", date(2026, 2, 10), date(2026, 2, 16),
         0.82, 15.2, 5.1, 0.18, 0.08, 0.96, 25, 20, 4, 1, 0, 0, 0),
        # Week 2 - allocation agent (improving)
        ("allocation_agent", date(2026, 2, 10), date(2026, 2, 16),
         0.68, 11.5, 12.0, 0.32, 0.15, 0.91, 250, 170, 55, 22, 3, 0, 2),
    ]

    for (agent_type, start, end, touchless, a_score, u_score, override_rt, odr, dsc,
         total, auto, reviewed, overridden, rejected, integ, risk) in metrics_data:
        m = AgentDecisionMetrics(
            config_id=config_id, customer_id=customer_id,
            agent_type=agent_type,
            period_start=start, period_end=end,
            touchless_rate=touchless,
            agent_score=a_score, user_score=u_score,
            human_override_rate=override_rt,
            override_dependency_ratio=odr,
            downstream_coherence=dsc,
            total_decisions=total, auto_submitted=auto,
            reviewed=reviewed, overridden=overridden, rejected=rejected,
            integrity_violations_count=integ, risk_flags_count=risk,
        )
        db.add(m)

    print(f"    Created {len(metrics_data)} AgentDecisionMetrics rows")
    db.flush()


# =============================================================================
# 9. Demo Users
# =============================================================================

def seed_demo_users(db: Session, customer_id: int) -> dict:
    """Create allocation manager and order promising manager users."""
    print("\n  Seeding demo users...")

    users = {}

    # Allocation Manager
    alloc_user = _create_or_get_user(
        db, username="alloc_manager",
        email="allocmgr@distdemo.com",
        full_name="Rachel Martinez (Allocation Manager)",
        user_type=UserTypeEnum.USER,
        customer_id=customer_id,
        powell_role=PowellRoleEnum.ALLOCATION_MANAGER,  # Narrow scope: Allocation Worklist only
    )
    users["alloc_manager"] = alloc_user

    # Order Promising Manager
    order_user = _create_or_get_user(
        db, username="order_promise_mgr",
        email="orderpromise@distdemo.com",
        full_name="Carlos Rivera (Order Promising Manager)",
        user_type=UserTypeEnum.USER,
        customer_id=customer_id,
        powell_role=PowellRoleEnum.ORDER_PROMISE_MANAGER,  # Narrow scope: ATP Worklist only
    )
    users["order_promise_mgr"] = order_user

    # Assign RBAC roles
    rbac_service = RBACService(db)

    # Allocation Manager gets narrow ALLOCATION_MANAGER role (only Allocation Worklist)
    alloc_role = rbac_service.get_role_by_slug("allocation_manager", tenant_id=None)
    if not alloc_role:
        # Create if not yet seeded by seed_dot_foods_demo.py
        from scripts.seed_dot_foods_demo import create_powell_role
        alloc_role = create_powell_role(db, rbac_service, "ALLOCATION_MANAGER")
    # Remove any broader roles first
    alloc_user.roles = [r for r in alloc_user.roles if r.slug not in ("sop_director",)]
    if alloc_role not in alloc_user.roles:
        alloc_user.roles.append(alloc_role)
    print(f"    Assigned RBAC role 'ALLOCATION_MANAGER' to alloc_manager")

    # Order Promising Manager gets narrow ORDER_PROMISE_MANAGER role (ATP Worklist only)
    opm_role = rbac_service.get_role_by_slug("order_promise_manager", tenant_id=None)
    if not opm_role:
        from scripts.seed_dot_foods_demo import create_powell_role
        opm_role = create_powell_role(db, rbac_service, "ORDER_PROMISE_MANAGER")
    # Remove any broader roles first
    order_user.roles = [r for r in order_user.roles if r.slug not in ("mps_manager",)]
    if opm_role not in order_user.roles:
        order_user.roles.append(opm_role)
    print(f"    Assigned RBAC role 'ORDER_PROMISE_MANAGER' to order_promise_mgr")

    db.flush()
    return users


def _create_or_get_user(
    db: Session, username: str, email: str, full_name: str,
    user_type: UserTypeEnum, customer_id: int,
    powell_role: PowellRoleEnum = None,
) -> User:
    """Create a user or return existing."""
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        print(f"    User '{username}' already exists (id={existing.id})")
        existing.powell_role = powell_role
        existing.customer_id = customer_id
        db.flush()
        return existing

    user = User(
        username=username,
        email=email,
        full_name=full_name,
        hashed_password=get_password_hash(DEFAULT_PASSWORD),
        user_type=user_type,
        customer_id=customer_id,
        powell_role=powell_role,
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    db.flush()
    print(f"    Created user '{username}' (id={user.id}, powell_role={powell_role.value if powell_role else 'None'})")
    return user


# =============================================================================
# Main
# =============================================================================

def _fix_enum_casing(engine):
    """Add uppercase enum values for SQLAlchemy SAEnum compatibility.

    SQLAlchemy SAEnum uses Python enum member .name (UPPERCASE) for persistence.
    If PostgreSQL enums were created with lowercase values, add uppercase alternatives.
    """
    from sqlalchemy import text

    # Map: enum_type_name -> list of UPPERCASE values to add
    # SAEnum-named enums (from planning_hierarchy.py):
    enum_fixes = {
        "site_hierarchy_level_enum": ["COMPANY", "REGION", "COUNTRY", "STATE", "SITE"],
        "product_hierarchy_level_enum": ["CATEGORY", "FAMILY", "GROUP", "PRODUCT"],
        "time_bucket_type_enum": ["HOUR", "DAY", "WEEK", "MONTH", "QUARTER", "YEAR"],
        # Auto-named enums (from planning_cascade.py Column(Enum(...))):
        "layername": ["SOP", "MRS", "SUPPLY_AGENT", "ALLOCATION_AGENT", "EXECUTION"],
        "layermode": ["ACTIVE", "INPUT", "DISABLED"],
        "commitstatus": ["PROPOSED", "REVIEWED", "ACCEPTED", "OVERRIDDEN", "SUBMITTED", "AUTO_SUBMITTED", "REJECTED"],
        "policysource": ["AUTONOMY_SIM", "CUSTOMER_INPUT", "SYSTEM_DEFAULT"],
    }

    for enum_name, values in enum_fixes.items():
        for val in values:
            try:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{val}'"))
            except Exception:
                pass  # Already exists or enum doesn't exist yet


def ensure_tables_exist():
    """Ensure all required tables exist via SQLAlchemy create_all.

    Patches unnamed enums in unrelated models (achievements, leaderboards) that
    block create_all, then creates all missing tables via ORM metadata.
    """
    from sqlalchemy import inspect, text
    from sqlalchemy.types import Enum as SAEnumType
    from app.db.base import Base

    # Fix enum casing first (add UPPERCASE values for SAEnum compatibility)
    _fix_enum_casing(sync_engine)

    # Patch unnamed enums so create_all doesn't fail
    for table_name, table in Base.metadata.tables.items():
        for col in table.columns:
            t = col.type
            while hasattr(t, 'impl'):
                t = t.impl
            if isinstance(t, SAEnumType) and not getattr(t, 'name', None):
                # Generate a name from table + column
                t.name = f"{table_name}_{col.name}"

    inspector = inspect(sync_engine)
    existing = set(inspector.get_table_names())

    needed = {
        "site_hierarchy_node", "product_hierarchy_node", "planning_hierarchy_config",
        "time_bucket_config", "planning_horizon_template", "aggregated_plan",
        "planning_policy_envelope", "supply_baseline_pack", "supply_commit",
        "solver_baseline_pack", "allocation_commit", "planning_feedback_signal",
        "agent_decision_metrics", "layer_license",
        "inv_projection", "atp_projection", "order_promise", "ctp_projection",
    }
    missing = needed - existing

    if not missing:
        print("  All required tables already exist")
        return

    print(f"  Missing tables: {', '.join(sorted(missing))}")

    # Drop any tables created with wrong enum types from previous runs
    with sync_engine.begin() as conn:
        # Check and drop empty tables with wrong schema
        for tbl in list(existing):
            if tbl in missing:
                continue  # Not in DB
            # If a needed table exists but has wrong columns, we can't easily detect
            # Just ensure old-style enum names don't block
        for old_name in ["layer_name_enum", "layer_mode_enum", "commit_status_enum", "policy_source_enum"]:
            try:
                conn.execute(text(f"DROP TYPE IF EXISTS {old_name} CASCADE"))
            except Exception:
                conn.execute(text("ROLLBACK"))
                conn.execute(text("BEGIN"))

    # Use SQLAlchemy create_all with checkfirst for all tables
    Base.metadata.create_all(sync_engine, checkfirst=True)
    print("  Created missing tables via SQLAlchemy metadata")


def seed_daily_powell_allocations(db: Session, config_id: int, dc_site_id: int):
    """
    Seed daily powell_allocations rows for the allocation timeline view.

    Creates 25 products x 5 priorities x 15 days = 1,875 rows with
    daily-cadence allocations. Past days include consumed_qty to show
    realistic consumption patterns.
    """
    from app.models.powell_allocation import PowellAllocation

    # Clean existing daily allocations for this config
    deleted = db.query(PowellAllocation).filter(
        PowellAllocation.config_id == config_id,
        PowellAllocation.allocation_cadence == "daily",
    ).delete()
    if deleted:
        print(f"  Cleaned {deleted} existing daily allocations")

    today = date.today()
    days_past = 5
    days_future = 9
    location_id = str(dc_site_id)

    # Priority percentage of weekly demand allocated to each tier
    priority_pcts = {1: 0.30, 2: 0.25, 3: 0.20, 4: 0.15, 5: 0.10}

    count = 0
    for sku in ALL_SKUS:
        weekly_demand = SKU_BASE_DEMAND[sku]
        for priority, pct in priority_pcts.items():
            daily_alloc = round(weekly_demand * pct / 7, 1)
            # Add some variance across days (+/- 15%)
            for day_offset in range(-days_past, days_future + 1):
                bucket_date = today + timedelta(days=day_offset)
                variance = random.uniform(0.85, 1.15)
                qty = round(daily_alloc * variance, 1)

                # Past days: simulate partial consumption (30-80%)
                consumed = 0.0
                if day_offset < 0:
                    consumed = round(qty * random.uniform(0.30, 0.80), 1)
                elif day_offset == 0:
                    consumed = round(qty * random.uniform(0.10, 0.40), 1)

                alloc = PowellAllocation(
                    config_id=config_id,
                    product_id=sku,
                    location_id=location_id,
                    priority=priority,
                    allocated_qty=qty,
                    consumed_qty=consumed,
                    reserved_qty=0,
                    allocation_source="tgnn",
                    allocation_cadence="daily",
                    valid_from=datetime.combine(bucket_date, datetime.min.time()),
                    valid_to=datetime.combine(bucket_date, datetime.max.time()),
                    is_active=True,
                )
                db.add(alloc)
                count += 1

    db.flush()
    print(f"  Created {count} daily powell_allocations")


# =============================================================================
# 10. ATP Agent Decisions (for Order Promising Manager worklist)
# =============================================================================

# Customer full names for readable display
CUSTOMER_NAMES = {
    "METROGRO": "Metro Grocery Chain",
    "QUICKSERV": "Quick Serve Foods LLC",
    "RESTSUPPLY": "Restaurant Supply Co",
    "COASTHLTH": "Coastal Healthcare System",
    "SCHLDFOOD": "School District Foods",
    "CAMPUSDINE": "Campus Dining Services",
    "FAMREST": "Family Restaurant Inc",
    "PREMCATER": "Premier Catering Services",
    "DWNTWNDELI": "Downtown Deli Group",
    "GREENVAL": "Green Valley Markets",
}

# SKU display names
SKU_NAMES = {
    "FP001": "Premium Beef Patties", "FP002": "Chicken Breast Strips", "FP003": "Pork Sausage Links",
    "FP004": "Turkey Burgers", "FP005": "Lamb Kebab Mix",
    "FD001": "Vanilla Ice Cream 1gal", "FD002": "Chocolate Cake Slices", "FD003": "Frozen Fruit Bars",
    "FD004": "Cheesecake Sampler", "FD005": "Frozen Cookie Dough",
    "RD001": "Shredded Mozzarella 5lb", "RD002": "Butter Pats 1lb", "RD003": "Heavy Cream Qt",
    "RD004": "Greek Yogurt Case", "RD005": "Sour Cream Tub",
    "DP001": "All-Purpose Flour 25lb", "DP002": "Granulated Sugar 10lb", "DP003": "Marinara Sauce Gal",
    "DP004": "Olive Oil 1gal", "DP005": "Ranch Dressing Gal",
    "BV001": "Orange Juice 46oz", "BV002": "Apple Juice Box 40pk", "BV003": "Cola Syrup BIB",
    "BV004": "Lemonade Concentrate", "BV005": "Iced Tea Bags 100ct",
}


def seed_atp_decisions(db: Session, customer_id: int, order_promise_user_id: int):
    """Seed AgentDecision rows for the ATP Fulfillment worklist.

    Creates ~30 decisions across SKUs and customers with a mix of statuses
    (PENDING for worklist, ACCEPTED, REJECTED) and ATP-specific context_data.
    """
    print("\n  Seeding ATP agent decisions...")

    existing = db.query(AgentDecision).filter(
        AgentDecision.customer_id == customer_id,
        AgentDecision.decision_type == DecisionType.ATP_ALLOCATION,
    ).first()
    if existing:
        print("    ATP decisions already exist, skipping")
        return

    base_date = datetime(2026, 2, 7, 6, 0, 0)  # Friday morning
    count = 0

    # Decision templates: (customer, sku, action, status, confidence, urgency_enum)
    decisions = [
        # --- PENDING decisions (show in worklist) ---
        ("METROGRO", "RD001", "FULFILL", DecisionStatus.PENDING, 0.96, DecisionUrgency.URGENT),
        ("METROGRO", "FP001", "FULFILL", DecisionStatus.PENDING, 0.94, DecisionUrgency.URGENT),
        ("QUICKSERV", "BV003", "FULFILL", DecisionStatus.PENDING, 0.93, DecisionUrgency.URGENT),
        ("QUICKSERV", "DP003", "FULFILL", DecisionStatus.PENDING, 0.91, DecisionUrgency.STANDARD),
        ("RESTSUPPLY", "FP002", "PARTIAL", DecisionStatus.PENDING, 0.87, DecisionUrgency.STANDARD),
        ("RESTSUPPLY", "RD004", "FULFILL", DecisionStatus.PENDING, 0.90, DecisionUrgency.STANDARD),
        ("COASTHLTH", "RD003", "FULFILL", DecisionStatus.PENDING, 0.88, DecisionUrgency.STANDARD),
        ("SCHLDFOOD", "DP001", "PARTIAL", DecisionStatus.PENDING, 0.82, DecisionUrgency.STANDARD),
        ("CAMPUSDINE", "BV001", "DEFER", DecisionStatus.PENDING, 0.79, DecisionUrgency.LOW),
        ("FAMREST", "FD001", "PARTIAL", DecisionStatus.PENDING, 0.76, DecisionUrgency.LOW),
        ("DWNTWNDELI", "FP003", "DEFER", DecisionStatus.PENDING, 0.72, DecisionUrgency.LOW),
        ("GREENVAL", "DP005", "REJECT", DecisionStatus.PENDING, 0.68, DecisionUrgency.LOW),
        # --- ACCEPTED decisions (already actioned) ---
        ("METROGRO", "BV001", "FULFILL", DecisionStatus.ACCEPTED, 0.97, DecisionUrgency.URGENT),
        ("QUICKSERV", "FP001", "FULFILL", DecisionStatus.ACCEPTED, 0.95, DecisionUrgency.URGENT),
        ("RESTSUPPLY", "DP002", "FULFILL", DecisionStatus.ACCEPTED, 0.92, DecisionUrgency.STANDARD),
        ("COASTHLTH", "FD002", "FULFILL", DecisionStatus.ACCEPTED, 0.89, DecisionUrgency.STANDARD),
        ("SCHLDFOOD", "BV002", "PARTIAL", DecisionStatus.ACCEPTED, 0.84, DecisionUrgency.STANDARD),
        ("CAMPUSDINE", "RD002", "FULFILL", DecisionStatus.ACCEPTED, 0.88, DecisionUrgency.STANDARD),
        ("FAMREST", "DP004", "FULFILL", DecisionStatus.ACCEPTED, 0.85, DecisionUrgency.STANDARD),
        ("PREMCATER", "FP004", "PARTIAL", DecisionStatus.ACCEPTED, 0.80, DecisionUrgency.LOW),
        # --- REJECTED / overridden decisions ---
        ("DWNTWNDELI", "RD005", "REJECT", DecisionStatus.REJECTED, 0.71, DecisionUrgency.LOW),
        ("GREENVAL", "FD003", "REJECT", DecisionStatus.REJECTED, 0.65, DecisionUrgency.LOW),
        ("PREMCATER", "BV004", "DEFER", DecisionStatus.REJECTED, 0.74, DecisionUrgency.LOW),
        # --- Additional PENDING for volume ---
        ("METROGRO", "DP001", "FULFILL", DecisionStatus.PENDING, 0.95, DecisionUrgency.URGENT),
        ("QUICKSERV", "RD001", "FULFILL", DecisionStatus.PENDING, 0.92, DecisionUrgency.STANDARD),
        ("RESTSUPPLY", "BV005", "PARTIAL", DecisionStatus.PENDING, 0.83, DecisionUrgency.STANDARD),
        ("COASTHLTH", "FP005", "DEFER", DecisionStatus.PENDING, 0.77, DecisionUrgency.LOW),
        ("SCHLDFOOD", "FD004", "PARTIAL", DecisionStatus.PENDING, 0.80, DecisionUrgency.STANDARD),
    ]

    action_reasoning = {
        "FULFILL": "Sufficient ATP available. Customer priority tier {tier} ({segment}) within allocation entitlement. Recommend full fulfillment.",
        "PARTIAL": "Partial ATP available ({available} of {requested} cases). Recommend shipping available quantity to maintain service level for {segment} segment.",
        "DEFER": "ATP exhausted for current bucket. Next available supply in {lead_time} days. Recommend deferral to {defer_date} to preserve higher-priority allocations.",
        "REJECT": "No ATP available within acceptable lead time. Customer priority P{tier} ({segment}) below allocation threshold. Recommend rejection with backorder option.",
    }

    for i, (cust, sku, action, status, confidence, urgency) in enumerate(decisions):
        info = CUSTOMER_PRIORITIES[cust]
        tier = info["priority"]
        segment = info["segment"]
        base_demand = SKU_BASE_DEMAND[sku]
        demand_mult = info["demand_mult"]

        requested_qty = int(base_demand * demand_mult / 7 * random.uniform(0.5, 2.0))
        requested_qty = max(10, requested_qty)

        if action == "FULFILL":
            promised_qty = requested_qty
            available_atp = int(requested_qty * random.uniform(1.0, 1.5))
        elif action == "PARTIAL":
            fill_ratio = random.uniform(0.4, 0.8)
            promised_qty = int(requested_qty * fill_ratio)
            available_atp = promised_qty
        elif action == "DEFER":
            promised_qty = 0
            available_atp = 0
        else:  # REJECT
            promised_qty = 0
            available_atp = 0

        lead_time = random.randint(3, 10)
        defer_date = (base_date + timedelta(days=lead_time)).strftime("%b %d")

        reasoning = action_reasoning[action].format(
            tier=tier, segment=segment, available=available_atp,
            requested=requested_qty, lead_time=lead_time, defer_date=defer_date,
        )

        order_id = f"DF-ORD-{2000 + i}"
        created_at = base_date + timedelta(hours=random.uniform(0, 48))

        # Build rich context_data that column renderers extract
        context_data = {
            "sku": sku,
            "product_id": sku,
            "product_name": SKU_NAMES.get(sku, sku),
            "customer_id": cust,
            "customer_name": CUSTOMER_NAMES.get(cust, cust),
            "customer_priority": tier,
            "priority": tier,
            "segment": segment,
            "order_id": order_id,
            "requested_qty": requested_qty,
            "promised_qty": promised_qty,
            "available_atp": available_atp,
            "recommended_action": action,
            "allocation_entitlement": int(base_demand * info["pct"] * demand_mult / 5),
            "service_level_target": {1: 0.99, 2: 0.95, 3: 0.92, 4: 0.90, 5: 0.85}[tier],
        }

        recommendation_text = f"{action} order {order_id} for {CUSTOMER_NAMES.get(cust, cust)}: {requested_qty} cases of {SKU_NAMES.get(sku, sku)}"

        decision = AgentDecision(
            customer_id=customer_id,
            user_id=order_promise_user_id if status != DecisionStatus.PENDING else None,
            decision_type=DecisionType.ATP_ALLOCATION,
            item_code=sku,
            item_name=SKU_NAMES.get(sku, sku),
            category=segment,
            issue_summary=f"Order {order_id}: {cust} requests {requested_qty} cases of {sku}",
            impact_value=round(requested_qty * random.uniform(2.5, 8.0), 2),
            impact_description=f"Revenue impact: ${round(requested_qty * random.uniform(2.5, 8.0), 0):.0f}",
            agent_recommendation=recommendation_text,
            agent_reasoning=reasoning,
            agent_confidence=confidence,
            recommended_value=float(promised_qty),
            previous_value=float(requested_qty),
            status=status,
            urgency=urgency,
            due_date=created_at + timedelta(hours=24),
            user_action="override" if status == DecisionStatus.REJECTED else ("accept" if status == DecisionStatus.ACCEPTED else None),
            override_reason="Manual override: customer requested expedited fulfillment" if status == DecisionStatus.REJECTED else None,
            action_timestamp=created_at + timedelta(hours=random.uniform(1, 6)) if status != DecisionStatus.PENDING else None,
            agent_type="atp_executor",
            agent_version="1.0.0",
            planning_cycle="2026-W06",
            context_data=context_data,
            created_at=created_at,
        )
        db.add(decision)
        count += 1

    db.flush()
    print(f"    Created {count} ATP AgentDecision rows ({sum(1 for d in decisions if d[3] == DecisionStatus.PENDING)} pending)")


def main():
    print("=" * 70)
    print("Seeding Food Dist Allocation & ATP Demo Data")
    print("=" * 70)

    # Ensure all required tables exist
    print("\n0. Ensuring required tables exist...")
    ensure_tables_exist()

    SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
    db: Session = SyncSessionLocal()

    try:
        # Step 1: Validate prerequisites
        print("\n1. Validating prerequisites...")

        tenant = db.query(Tenant).filter(Tenant.name == "Food Dist").first()
        if not tenant:
            print("ERROR: 'Food Dist' tenant not found. Run seed_dot_foods_demo.py first.")
            sys.exit(1)
        print(f"   Tenant: {tenant.name} (id={tenant.id})")

        config = db.query(SupplyChainConfig).filter(
            SupplyChainConfig.tenant_id == tenant.id
        ).first()
        if not config:
            print("ERROR: No SC config found for Food Dist. Run FoodDistConfigGenerator first.")
            sys.exit(1)
        print(f"   SC Config: {config.name} (id={config.id})")

        # Verify products exist
        product_count = db.query(Product).filter(Product.id.in_(ALL_SKUS)).count()
        if product_count < 25:
            print(f"WARNING: Only {product_count}/25 products found. Some hierarchy links may fail.")
        print(f"   Products: {product_count}/25 found")

        # Get DC site ID (integer PK from site table)
        from app.models.supply_chain_config import Site
        dc_node = db.query(Site).filter(
            Site.config_id == config.id,
            Site.name == "FOODDIST_DC",
        ).first()
        if not dc_node:
            dc_node = db.query(Site).filter(
                Site.config_id == config.id,
                Site.name.like("%FOODDIST%"),
            ).first()
        if not dc_node:
            # Fallback: get first INVENTORY site
            dc_node = db.query(Site).filter(
                Site.config_id == config.id,
                Site.master_type == "INVENTORY",
            ).first()
        if not dc_node:
            print("ERROR: No DC site found in SC config.")
            sys.exit(1)
        print(f"   DC Site: {dc_node.name} (id={dc_node.id})")

        # Get sop_director user for reviewed_by fields
        sop_user = db.query(User).filter(User.email == "sopdir@distdemo.com").first()
        sop_user_id = sop_user.id if sop_user else None

        # Ensure permissions exist
        seed_default_permissions(db)
        db.commit()

        # Step 2: Create demo users first (needed for reviewed_by references)
        print("\n2. Creating demo users...")
        users = seed_demo_users(db, tenant.id)
        db.commit()

        alloc_mgr_id = users["alloc_manager"].id
        if not sop_user_id:
            sop_user_id = alloc_mgr_id

        # Step 3: Seed site hierarchy
        print("\n3. Seeding site hierarchy...")
        site_nodes = seed_site_hierarchy(db, tenant.id)
        db.commit()

        # Step 4: Seed product hierarchy
        print("\n4. Seeding product hierarchy...")
        product_nodes = seed_product_hierarchy(db, tenant.id)
        db.commit()

        # Step 5: Seed layer licenses
        print("\n5. Seeding layer licenses...")
        seed_layer_licenses(db, tenant.id)
        db.commit()

        # Step 6: Seed planning cascade
        print("\n6. Seeding planning cascade...")
        seed_planning_cascade(db, config.id, tenant.id, sop_user_id, alloc_mgr_id)
        db.commit()

        # Step 7: Seed inventory projections
        print("\n7. Seeding inventory projections...")
        seed_inv_projections(db, config.id, tenant.id, dc_node.id)
        db.commit()

        # Step 8: Seed ATP projections
        print("\n8. Seeding ATP projections...")
        seed_atp_projections(db, config.id, tenant.id, dc_node.id)
        db.commit()

        # Step 9: Seed order promises
        print("\n9. Seeding order promises...")
        seed_order_promises(db, tenant.id, dc_node.id)
        db.commit()

        # Step 10: Seed feedback signals and metrics
        print("\n10. Seeding feedback signals and metrics...")
        seed_feedback_and_metrics(db, config.id, tenant.id, alloc_mgr_id)
        db.commit()

        # Step 11: Seed daily powell_allocations for timeline view
        print("\n11. Seeding daily powell_allocations for timeline...")
        seed_daily_powell_allocations(db, config.id, dc_node.id)
        db.commit()

        # Step 12: Seed ATP agent decisions for Order Promising Manager worklist
        print("\n12. Seeding ATP agent decisions...")
        order_promise_user = users.get("order_promise_mgr")
        opm_id = order_promise_user.id if order_promise_user else alloc_mgr_id
        seed_atp_decisions(db, tenant.id, opm_id)
        db.commit()

        # Summary
        print("\n" + "=" * 70)
        print("Food Dist Allocation & ATP Demo Data Seeded Successfully!")
        print("=" * 70)
        print(f"\nGroup: {tenant.name} (id={tenant.id})")
        print(f"SC Config: {config.name} (id={config.id})")
        print(f"DC Site: {dc_node.name} (id={dc_node.id})")
        print(f"\nData created:")
        print(f"  Site hierarchy nodes:     {len(site_nodes)}")
        print(f"  Product hierarchy nodes:  {len(product_nodes)}")
        print(f"  Layer licenses:           5")
        print(f"  Planning cascade:         PE(1) + SupBP(1) + SC(1) + SBP(1) + AC(4)")
        print(f"  Inventory projections:    ~700 (25 SKUs x 28 days)")
        print(f"  ATP projections:          ~2100 (aggregate + P1/P2 customer-specific)")
        print(f"  Order promises:           ~80 orders across 10 customers")
        print(f"  Feedback signals:         8")
        print(f"  Agent metrics:            4 (2 weeks x 2 agents)")
        print(f"  Powell allocations:       1,875 (25 SKUs x 5 priorities x 15 days)")
        print(f"  ATP agent decisions:      28 (mix of PENDING/ACCEPTED/REJECTED)")

        print(f"\nNew demo users (password: {DEFAULT_PASSWORD}):")
        print(f"  {'allocmgr@distdemo.com':<30} Rachel Martinez (Allocation Manager)")
        print(f"  {'orderpromise@distdemo.com':<30} Carlos Rivera (Order Promising Manager)")

        print(f"\nCustomer Priority Tiers:")
        for cust, info in sorted(CUSTOMER_PRIORITIES.items(), key=lambda x: x[1]["priority"]):
            print(f"  P{info['priority']} ({info['segment']:<12}): {cust}")

        print(f"\nAllocation Commit Status (for worklist demo):")
        print(f"  Week 1 (Feb 3):  ACCEPTED  - agent decision accepted by Rachel")
        print(f"  Week 2 (Feb 10): OVERRIDDEN - Rachel increased P3/P4 allocations")
        print(f"  Week 3 (Feb 17): PROPOSED   - pending review (worklist item!)")
        print(f"  Week 4 (Feb 24): PROPOSED   - future week")

        print(f"\nDemo Flow:")
        print(f"  1. Login as allocmgr@distdemo.com")
        print(f"  2. Navigate to Allocation Worklist - see Week 3 pending")
        print(f"  3. Review allocation: P1/P2 get priority, P4/P5 show shortfall")
        print(f"  4. Override: increase P3 allocation for specific customer")
        print(f"  5. Login as orderpromise@distdemo.com")
        print(f"  6. View order promises - P1/P2 fully filled, P4/P5 partial")
        print(f"  7. Override: change promised date/qty for specific order")
        print()

    except Exception as e:
        print(f"\nERROR: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
