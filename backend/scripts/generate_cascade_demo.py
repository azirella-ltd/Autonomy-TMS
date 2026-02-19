#!/usr/bin/env python3
"""
Generate Cascade → TRM Execution Demo Data

Runs the full planning cascade for Food Dist and then feeds the output
through all four TRM execution services, persisting every decision to the
corresponding powell_* table.

Pipeline:
  1. Run Planning Cascade (S&OP → MRS → SupplyAgent → AllocationAgent)
  2. Materialize AllocationCommit → PowellAllocations
  3. ATP Execution (ATPExecutorTRM with priority consumption)
  4. Inventory Rebalancing (InventoryRebalancingTRM)
  5. PO Creation (POCreationTRM)
  6. Order Tracking (OrderTrackingTRM)
  7. Summary

Prerequisites:
    - seed_dot_foods_demo.py must have been run first
    - seed_dot_foods_allocation_demo.py recommended (creates hierarchies)

Usage:
    docker compose exec backend python scripts/generate_cascade_demo.py
"""

import sys
import random
from pathlib import Path
from datetime import datetime, date, timedelta

# Ensure backend package is importable
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import func

from app.db.session import sync_engine
from app.models.group import Group
from app.models.supply_chain_config import SupplyChainConfig, Site
from app.models.planning_cascade import AllocationCommit, CommitStatus
from app.models.powell_allocation import PowellAllocation
from app.models.powell_decisions import (
    PowellATPDecision, PowellRebalanceDecision,
    PowellPODecision, PowellOrderException,
)
from app.models.user import User

# Seed for reproducibility
random.seed(42)

# ---------------------------------------------------------------------------
# Constants imported from seed_dot_foods_allocation_demo
# ---------------------------------------------------------------------------

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

PRODUCT_FAMILIES = {
    "FROZEN_PROTEINS":    ["FP001", "FP002", "FP003", "FP004", "FP005"],
    "FROZEN_DESSERTS":    ["FD001", "FD002", "FD003", "FD004", "FD005"],
    "REFRIGERATED_DAIRY": ["RD001", "RD002", "RD003", "RD004", "RD005"],
    "DRY_PANTRY":         ["DP001", "DP002", "DP003", "DP004", "DP005"],
    "BEVERAGES":          ["BV001", "BV002", "BV003", "BV004", "BV005"],
}

ALL_SKUS = [sku for skus in PRODUCT_FAMILIES.values() for sku in skus]

SKU_SUPPLIER = {
    "FP001": "TYSON", "FP002": "TYSON", "FP003": "SYSCOMEAT", "FP004": "SYSCOMEAT", "FP005": "SYSCOMEAT",
    "RD001": "KRAFT", "RD002": "KRAFT", "RD003": "LANDOLAKES", "RD004": "LANDOLAKES", "RD005": "LANDOLAKES",
    "DP001": "GENMILLS", "DP002": "GENMILLS", "DP003": "CONAGRA", "DP004": "CONAGRA", "DP005": "CONAGRA",
    "FD001": "NESTLE", "FD002": "NESTLE", "FD003": "RICHPROD", "FD004": "RICHPROD", "FD005": "RICHPROD",
    "BV001": "TROP", "BV002": "TROP", "BV003": "COCACOLA", "BV004": "COCACOLA", "BV005": "COCACOLA",
}

SKU_BASE_DEMAND = {
    "FP001": 150, "FP002": 120, "FP003": 80, "FP004": 60, "FP005": 40,
    "RD001": 200, "RD002": 250, "RD003": 180, "RD004": 300, "RD005": 100,
    "DP001": 200, "DP002": 180, "DP003": 150, "DP004": 160, "DP005": 120,
    "FD001": 80, "FD002": 40, "FD003": 50, "FD004": 60, "FD005": 35,
    "BV001": 220, "BV002": 150, "BV003": 180, "BV004": 200, "BV005": 140,
}

# Supplier lead times (days)
SUPPLIER_LEAD_TIMES = {
    "TYSON": 5, "SYSCOMEAT": 4, "KRAFT": 3, "LANDOLAKES": 4,
    "GENMILLS": 3, "CONAGRA": 3, "NESTLE": 5, "RICHPROD": 4,
    "TROP": 3, "COCACOLA": 2,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_dc_site_id(db: Session, config_id: int) -> str:
    """Get the DC site's string identifier for allocation location."""
    dc_node = db.query(Site).filter(
        Site.config_id == config_id,
        Site.name == "FOODDIST_DC",
    ).first()
    if not dc_node:
        dc_node = db.query(Site).filter(
            Site.config_id == config_id,
            Site.name.like("%FOODDIST%"),
        ).first()
    if not dc_node:
        dc_node = db.query(Site).filter(
            Site.config_id == config_id,
            Site.master_type == "INVENTORY",
        ).first()
    if not dc_node:
        raise RuntimeError("No DC site found for Food Dist config")
    return str(dc_node.id)


# ===================================================================
# Step 1: Run Planning Cascade
# ===================================================================

def step1_run_cascade(db: Session, config_id: int, group_id: int, user_id: int):
    """Run the full planning cascade for Food Dist."""
    print("\n  Running Planning Cascade (S&OP → MRS → SupplyAgent → AllocationAgent)...")
    from app.services.planning_cascade.cascade_orchestrator import (
        CascadeOrchestrator, CascadeMode,
    )
    from app.models.planning_cascade import (
        PolicyEnvelope, SupplyBaselinePack, SupplyCommit as SCModel,
        SolverBaselinePack,
    )

    # Clean up prior cascade artifacts from previous runs to avoid hash collisions
    print("    Cleaning prior cascade artifacts...")
    for ac in db.query(AllocationCommit).filter(AllocationCommit.config_id == config_id).all():
        db.delete(ac)
    for sbp in db.query(SolverBaselinePack).filter(SolverBaselinePack.config_id == config_id).all():
        db.delete(sbp)
    for sc in db.query(SCModel).filter(SCModel.config_id == config_id).all():
        db.delete(sc)
    for supbp in db.query(SupplyBaselinePack).filter(SupplyBaselinePack.config_id == config_id).all():
        db.delete(supbp)
    for pe in db.query(PolicyEnvelope).filter(PolicyEnvelope.config_id == config_id).all():
        db.delete(pe)
    db.flush()

    # Also clean prior powell decision records
    print("    Cleaning prior powell decision records...")
    db.query(PowellATPDecision).filter(PowellATPDecision.config_id == config_id).delete()
    db.query(PowellRebalanceDecision).filter(PowellRebalanceDecision.config_id == config_id).delete()
    db.query(PowellPODecision).filter(PowellPODecision.config_id == config_id).delete()
    db.query(PowellOrderException).filter(PowellOrderException.config_id == config_id).delete()
    db.query(PowellAllocation).filter(
        PowellAllocation.config_id == config_id,
    ).delete()
    db.flush()

    orchestrator = CascadeOrchestrator(db, mode=CascadeMode.FULL, agent_mode="copilot")
    result = orchestrator.run_cascade_for_food_dist(config_id, group_id, user_id)

    print(f"    Policy Envelope: {result.policy_envelope.get('hash', 'N/A')[:12]}...")
    print(f"    Supply Commit:   {result.supply_commit.get('hash', 'N/A')[:12]}... ({result.total_orders} orders)")
    print(f"    Alloc Commit:    {result.allocation_commit.get('hash', 'N/A')[:12]}... ({result.total_allocations} allocations)")
    if result.integrity_violations:
        print(f"    Integrity violations: {result.integrity_violations}")
    if result.risk_flags:
        print(f"    Risk flags: {result.risk_flags}")

    db.commit()
    print("    Cascade committed to DB.")
    return result


# ===================================================================
# Step 2: Materialize Allocations
# ===================================================================

def step2_materialize_allocations(db: Session, cascade_result, config_id: int, dc_location_id: str):
    """Convert AllocationCommit → PowellAllocation rows + in-memory PriorityAllocations."""
    print("\n  Materializing AllocationCommit → PowellAllocations...")
    from app.services.powell.allocation_service import materialize_allocation_commit

    ac_id = cascade_result.allocation_commit.get("id")
    if not ac_id:
        print("    WARNING: No allocation commit ID in cascade result, skipping materialization.")
        return [], []

    ac = db.query(AllocationCommit).get(ac_id)
    if not ac:
        print(f"    WARNING: AllocationCommit id={ac_id} not found in DB.")
        return [], []

    # Force status to ACCEPTED for demo purposes
    if ac.status not in (CommitStatus.ACCEPTED, CommitStatus.SUBMITTED, CommitStatus.AUTO_SUBMITTED):
        print(f"    Setting AllocationCommit status from {ac.status.value} to ACCEPTED for demo.")
        ac.status = CommitStatus.ACCEPTED
        db.flush()

    powell_rows, priority_allocs = materialize_allocation_commit(
        db, ac, config_id, dc_location_id
    )

    db.commit()
    print(f"    Created {len(powell_rows)} PowellAllocation rows.")
    print(f"    Created {len(priority_allocs)} in-memory PriorityAllocation objects.")
    return powell_rows, priority_allocs


# ===================================================================
# Step 3: ATP Execution
# ===================================================================

def step3_atp_execution(db: Session, priority_allocs, config_id: int, dc_location_id: str):
    """Run ATP checks and commits for simulated customer orders."""
    print("\n  Running ATP Execution...")
    from app.services.powell.allocation_service import AllocationService, AllocationConfig
    from app.services.powell.atp_executor import ATPExecutorTRM, ATPRequest

    # Set up allocation service with materialized allocations
    alloc_service = AllocationService(AllocationConfig())
    alloc_service.set_allocations(priority_allocs)

    # Create executor with DB persistence
    executor = ATPExecutorTRM(alloc_service, db=db, config_id=config_id)

    # Generate simulated orders
    order_num = 0
    fulfilled = 0
    partial = 0
    rejected = 0

    # Sample 5 SKUs per customer for ~50 orders
    sample_skus = random.sample(ALL_SKUS, min(5, len(ALL_SKUS)))

    for customer_id, cust_info in CUSTOMER_PRIORITIES.items():
        for sku in sample_skus:
            order_num += 1
            base_demand = SKU_BASE_DEMAND.get(sku, 100)
            daily_demand = (base_demand / 7) * cust_info["demand_mult"]
            requested_qty = max(1, round(daily_demand * random.uniform(0.5, 2.0)))

            request = ATPRequest(
                order_id=f"ORD-{order_num:04d}",
                product_id=sku,
                location_id=dc_location_id,
                requested_qty=requested_qty,
                priority=cust_info["priority"],
                customer_id=customer_id,
                demand_source=cust_info["segment"],
            )

            response = executor.check_atp(request)

            if response.can_fulfill and response.promised_qty >= requested_qty:
                executor.commit_atp(request, response)
                fulfilled += 1
            elif response.can_fulfill and response.promised_qty > 0:
                executor.commit_atp(request, response)
                partial += 1
            else:
                rejected += 1

    db.commit()
    metrics = executor.get_metrics()
    total = order_num
    print(f"    {total} orders processed: {fulfilled} fulfilled, {partial} partial, {rejected} rejected")
    print(f"    Fulfillment rate: {metrics['fulfillment_rate']:.1%}")


# ===================================================================
# Step 4: Inventory Rebalancing
# ===================================================================

def step4_inventory_rebalancing(db: Session, config_id: int, dc_location_id: str):
    """Run inventory rebalancing for a set of SKUs."""
    print("\n  Running Inventory Rebalancing...")
    from app.services.powell.inventory_rebalancing_trm import (
        InventoryRebalancingTRM, RebalancingState, SiteInventoryState, TransferLane,
    )

    trm = InventoryRebalancingTRM(db=db, config_id=config_id)

    # Simulate DC (excess) and 3 satellite sites (varying deficit)
    satellite_sites = ["FOODDIST_RDC_EAST", "FOODDIST_RDC_WEST", "FOODDIST_RDC_CENTRAL"]
    total_recs = 0

    for sku in random.sample(ALL_SKUS, min(10, len(ALL_SKUS))):
        base_demand = SKU_BASE_DEMAND.get(sku, 100)
        daily_demand = base_demand / 7

        # DC has excess
        dc_state = SiteInventoryState(
            site_id=dc_location_id,
            product_id=sku,
            on_hand=daily_demand * 30,  # 30 days supply
            in_transit=daily_demand * 5,
            committed=daily_demand * 3,
            backlog=0,
            demand_forecast=daily_demand * 30,
            demand_uncertainty=daily_demand * 5,
            safety_stock=daily_demand * 7,
            target_dos=14,
        )

        site_states = {dc_location_id: dc_state}
        transfer_lanes = []

        for sat_id in satellite_sites:
            deficit_factor = random.uniform(0.2, 0.8)
            sat_state = SiteInventoryState(
                site_id=sat_id,
                product_id=sku,
                on_hand=daily_demand * 14 * deficit_factor,
                in_transit=0,
                committed=daily_demand * 2,
                backlog=daily_demand * random.uniform(0, 2),
                demand_forecast=daily_demand * 20,
                demand_uncertainty=daily_demand * 4,
                safety_stock=daily_demand * 5,
                target_dos=10,
            )
            site_states[sat_id] = sat_state
            transfer_lanes.append(TransferLane(
                from_site=dc_location_id,
                to_site=sat_id,
                transfer_time=random.uniform(1, 3),
                cost_per_unit=random.uniform(0.5, 2.0),
            ))

        state = RebalancingState(
            product_id=sku,
            site_states=site_states,
            transfer_lanes=transfer_lanes,
            network_imbalance_score=random.uniform(0.2, 0.8),
            total_network_inventory=sum(s.on_hand for s in site_states.values()),
            total_network_demand=sum(s.demand_forecast for s in site_states.values()),
        )

        recs = trm.evaluate_rebalancing(state)
        total_recs += len(recs)

    db.commit()
    print(f"    {total_recs} rebalancing recommendations generated for 10 SKUs.")


# ===================================================================
# Step 5: PO Creation
# ===================================================================

def step5_po_creation(db: Session, config_id: int, dc_location_id: str):
    """Run PO creation evaluation for all SKUs."""
    print("\n  Running PO Creation evaluation...")
    from app.services.powell.po_creation_trm import (
        POCreationTRM, POCreationState, InventoryPosition, SupplierInfo,
    )

    trm = POCreationTRM(db=db, config_id=config_id)
    total_recs = 0

    for sku in ALL_SKUS:
        base_demand = SKU_BASE_DEMAND.get(sku, 100)
        daily_demand = base_demand / 7
        supplier_id = SKU_SUPPLIER.get(sku, "UNKNOWN")
        lead_time = SUPPLIER_LEAD_TIMES.get(supplier_id, 4)

        # Randomize inventory state - some below reorder point
        inv_factor = random.uniform(0.3, 1.5)
        on_hand = daily_demand * 10 * inv_factor
        safety_stock = daily_demand * 5
        reorder_point = safety_stock + daily_demand * lead_time

        inv_pos = InventoryPosition(
            product_id=sku,
            location_id=dc_location_id,
            on_hand=on_hand,
            in_transit=daily_demand * random.uniform(0, 5),
            on_order=daily_demand * random.uniform(0, 3),
            committed=daily_demand * random.uniform(1, 4),
            backlog=daily_demand * random.uniform(0, 1),
            safety_stock=safety_stock,
            reorder_point=reorder_point,
            target_inventory=daily_demand * 21,
            average_daily_demand=daily_demand,
            demand_variability=daily_demand * 0.3,
        )

        supplier = SupplierInfo(
            supplier_id=supplier_id,
            product_id=sku,
            lead_time_days=lead_time,
            lead_time_variability=lead_time * 0.2,
            unit_cost=random.uniform(2, 25),
            order_cost=random.uniform(50, 200),
            min_order_qty=max(10, base_demand // 4),
            on_time_rate=random.uniform(0.85, 0.99),
        )

        state = POCreationState(
            product_id=sku,
            location_id=dc_location_id,
            inventory_position=inv_pos,
            suppliers=[supplier],
            forecast_next_30_days=daily_demand * 30,
            forecast_uncertainty=daily_demand * 5,
            supply_risk_score=random.uniform(0, 0.4),
            demand_volatility_score=random.uniform(0.1, 0.5),
        )

        recs = trm.evaluate_po_need(state)
        total_recs += len(recs)

    db.commit()
    print(f"    {total_recs} PO recommendations for {len(ALL_SKUS)} SKUs.")


# ===================================================================
# Step 6: Order Tracking
# ===================================================================

def step6_order_tracking(db: Session, config_id: int, dc_location_id: str):
    """Run order tracking exception detection for simulated open POs."""
    print("\n  Running Order Tracking exception detection...")
    from app.services.powell.order_tracking_trm import (
        OrderTrackingTRM, OrderState, OrderType, OrderStatus,
    )

    trm = OrderTrackingTRM(db=db, config_id=config_id)

    # Generate 25 simulated open POs with varied timing
    orders = []
    today = date.today()

    for i, sku in enumerate(ALL_SKUS):
        supplier_id = SKU_SUPPLIER.get(sku, "UNKNOWN")
        lead_time = SUPPLIER_LEAD_TIMES.get(supplier_id, 4)

        # Varied days_until_expected: -5 to +7 (negative = late)
        days_offset = random.randint(-5, 7)
        expected_date = today + timedelta(days=days_offset)
        created_date = expected_date - timedelta(days=lead_time + random.randint(0, 3))

        # Determine status based on timing
        if days_offset < -2:
            status = OrderStatus.IN_TRANSIT  # Late
        elif days_offset < 0:
            status = random.choice([OrderStatus.IN_TRANSIT, OrderStatus.PARTIALLY_RECEIVED])
        elif days_offset == 0:
            status = OrderStatus.IN_TRANSIT
        else:
            status = random.choice([OrderStatus.CONFIRMED, OrderStatus.IN_TRANSIT])

        ordered_qty = SKU_BASE_DEMAND.get(sku, 100)
        received_qty = 0
        if status == OrderStatus.PARTIALLY_RECEIVED:
            received_qty = ordered_qty * random.uniform(0.4, 0.8)

        order = OrderState(
            order_id=f"PO-{i+1:04d}",
            order_type=OrderType.PURCHASE_ORDER,
            status=status,
            created_date=created_date.strftime("%Y-%m-%d"),
            expected_date=expected_date.strftime("%Y-%m-%d"),
            ordered_qty=ordered_qty,
            received_qty=received_qty,
            remaining_qty=ordered_qty - received_qty,
            expected_unit_price=random.uniform(2, 25),
            actual_unit_price=random.uniform(2, 25),
            product_id=sku,
            from_location=supplier_id,
            to_location=dc_location_id,
            partner_id=supplier_id,
            partner_name=supplier_id,
            partner_on_time_rate=random.uniform(0.85, 0.99),
            partner_fill_rate=random.uniform(0.90, 0.99),
            typical_transit_days=lead_time,
        )
        orders.append(order)

    results = trm.evaluate_orders_batch(orders)

    exceptions = [r for r in results if r.exception_type.value != "no_exception"]
    critical = sum(1 for r in results if r.severity.value == "critical")
    high = sum(1 for r in results if r.severity.value == "high")
    warning = sum(1 for r in results if r.severity.value == "warning")

    db.commit()
    print(f"    {len(orders)} orders evaluated, {len(exceptions)} exceptions detected.")
    print(f"    Severity: {critical} critical, {high} high, {warning} warning")


# ===================================================================
# Step 7: Summary
# ===================================================================

def step7_summary(db: Session, config_id: int):
    """Print summary counts from powell_* tables."""
    print("\n" + "=" * 60)
    print("SUMMARY — Powell Execution Decision Records")
    print("=" * 60)

    alloc_count = db.query(func.count(PowellAllocation.id)).filter(
        PowellAllocation.config_id == config_id,
        PowellAllocation.allocation_source == "cascade",
    ).scalar() or 0

    atp_count = db.query(func.count(PowellATPDecision.id)).filter(
        PowellATPDecision.config_id == config_id,
    ).scalar() or 0

    rebalance_count = db.query(func.count(PowellRebalanceDecision.id)).filter(
        PowellRebalanceDecision.config_id == config_id,
    ).scalar() or 0

    po_count = db.query(func.count(PowellPODecision.id)).filter(
        PowellPODecision.config_id == config_id,
    ).scalar() or 0

    exception_count = db.query(func.count(PowellOrderException.id)).filter(
        PowellOrderException.config_id == config_id,
    ).scalar() or 0

    print(f"  powell_allocations (cascade):  {alloc_count:>6}")
    print(f"  powell_atp_decisions:          {atp_count:>6}")
    print(f"  powell_rebalance_decisions:    {rebalance_count:>6}")
    print(f"  powell_po_decisions:           {po_count:>6}")
    print(f"  powell_order_exceptions:       {exception_count:>6}")
    print(f"  {'─' * 40}")
    total = alloc_count + atp_count + rebalance_count + po_count + exception_count
    print(f"  TOTAL:                         {total:>6}")
    print()


# ===================================================================
# Main
# ===================================================================

def main():
    print("=" * 70)
    print("Generate Cascade → TRM Execution Demo Data")
    print("=" * 70)

    SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
    db: Session = SyncSessionLocal()

    try:
        # ------------- Prerequisites -------------
        print("\n0. Validating prerequisites...")

        group = db.query(Group).filter(Group.name == "Food Dist").first()
        if not group:
            print("ERROR: 'Food Dist' group not found. Run seed_dot_foods_demo.py first.")
            sys.exit(1)
        print(f"   Group: {group.name} (id={group.id})")

        config = db.query(SupplyChainConfig).filter(
            SupplyChainConfig.group_id == group.id
        ).first()
        if not config:
            print("ERROR: No SC config for Food Dist. Run seed_dot_foods_demo.py first.")
            sys.exit(1)
        print(f"   SC Config: {config.name} (id={config.id})")

        dc_location_id = get_dc_site_id(db, config.id)
        print(f"   DC Location ID: {dc_location_id}")

        # Get a user for cascade authoring
        sop_user = db.query(User).filter(User.email == "sopdir@distdemo.com").first()
        user_id = sop_user.id if sop_user else None

        # ------------- Step 1: Planning Cascade -------------
        print("\n" + "-" * 60)
        print("Step 1: Planning Cascade")
        print("-" * 60)
        cascade_result = step1_run_cascade(db, config.id, group.id, user_id)

        # ------------- Step 2: Materialize Allocations -------------
        print("\n" + "-" * 60)
        print("Step 2: Materialize Allocations")
        print("-" * 60)
        powell_rows, priority_allocs = step2_materialize_allocations(
            db, cascade_result, config.id, dc_location_id
        )

        if not priority_allocs:
            print("  WARNING: No allocations materialized. ATP step will have no supply to consume.")

        # ------------- Step 3: ATP Execution -------------
        print("\n" + "-" * 60)
        print("Step 3: ATP Execution")
        print("-" * 60)
        step3_atp_execution(db, priority_allocs, config.id, dc_location_id)

        # ------------- Step 4: Inventory Rebalancing -------------
        print("\n" + "-" * 60)
        print("Step 4: Inventory Rebalancing")
        print("-" * 60)
        step4_inventory_rebalancing(db, config.id, dc_location_id)

        # ------------- Step 5: PO Creation -------------
        print("\n" + "-" * 60)
        print("Step 5: PO Creation")
        print("-" * 60)
        step5_po_creation(db, config.id, dc_location_id)

        # ------------- Step 6: Order Tracking -------------
        print("\n" + "-" * 60)
        print("Step 6: Order Tracking")
        print("-" * 60)
        step6_order_tracking(db, config.id, dc_location_id)

        # ------------- Step 7: Summary -------------
        step7_summary(db, config.id)

        print("Done. All cascade → execution demo data generated successfully.")

    except Exception as e:
        db.rollback()
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
