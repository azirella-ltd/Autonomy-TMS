#!/usr/bin/env python3
"""
Test SiteAgent with Food Dist Configuration

Tests the SiteAgent deterministic engines and optionally TRM
against the Food Dist supply chain configuration.

Usage:
    python scripts/test_site_agent_food_dist.py [--with-trm] [--generate-data]

Examples:
    # Test deterministic engines only
    python scripts/test_site_agent_food_dist.py

    # Test with TRM (requires trained model)
    python scripts/test_site_agent_food_dist.py --with-trm

    # Generate Food Dist config if not exists, then test
    python scripts/test_site_agent_food_dist.py --generate-data
"""

import sys
import os
import asyncio
import argparse
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.supply_chain_config import SupplyChainConfig, Node, Lane
from app.models.sc_entities import Product, InvLevel, InvPolicy
from app.models.customer import Customer


def get_food_dist_config(db: Session) -> Optional[SupplyChainConfig]:
    """Find the Food Dist supply chain configuration."""
    # Look for configs with "Food Dist" in the name
    configs = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.name.ilike("%Food Dist%")
    ).all()

    if configs:
        print(f"Found {len(configs)} Food Dist config(s):")
        for cfg in configs:
            print(f"  - {cfg.id}: {cfg.name}")
        return configs[0]

    # Also check customers
    customers = db.query(Customer).filter(
        Customer.name.ilike("%Food Dist%")
    ).all()

    if customers:
        print(f"Found {len(customers)} Food Dist customer(s):")
        for cust in customers:
            print(f"  - {cust.id}: {cust.name}")
            # Get associated config
            if cust.default_config_id:
                cfg = db.query(SupplyChainConfig).filter_by(
                    id=cust.default_config_id
                ).first()
                if cfg:
                    return cfg

    return None


def generate_food_dist_config(db: Session) -> SupplyChainConfig:
    """Generate the Food Dist configuration."""
    print("\nGenerating Food Dist configuration...")

    from app.services.food_dist_config_generator import FoodDistConfigGenerator

    generator = FoodDistConfigGenerator(db)

    # Run async generation
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(generator.generate())

    print(f"Generated config: {result['config'].name}")
    print(f"  - Customer: {result['customer'].name}")
    print(f"  - Nodes: {len(result['nodes'])}")
    print(f"  - Products: {len(result['products'])}")

    return result['config']


def test_mrp_engine(site_agent, config: SupplyChainConfig, db: Session):
    """Test the MRP engine with Food Dist data."""
    print("\n" + "=" * 60)
    print("Testing MRP Engine")
    print("=" * 60)

    from app.services.powell.engines import GrossRequirement

    # Get products from config
    products = db.query(Product).limit(5).all()

    if not products:
        print("  No products found, creating sample requirements")
        product_ids = ["SKU001", "SKU002", "SKU003"]
    else:
        product_ids = [p.id for p in products[:3]]
        print(f"  Using products: {product_ids}")

    # Create gross requirements
    today = date.today()
    gross_requirements = []
    for prod_id in product_ids:
        gross_requirements.append(GrossRequirement(
            item_id=str(prod_id),
            required_date=today + timedelta(days=7),
            quantity=100,
            source="forecast"
        ))
        gross_requirements.append(GrossRequirement(
            item_id=str(prod_id),
            required_date=today + timedelta(days=14),
            quantity=120,
            source="forecast"
        ))

    # Set up inventory and lead times
    on_hand = {str(prod_id): 50 for prod_id in product_ids}
    lead_times = {str(prod_id): 5 for prod_id in product_ids}

    print(f"\n  Gross Requirements: {len(gross_requirements)}")
    print(f"  On-hand Inventory: {on_hand}")
    print(f"  Lead Times: {lead_times}")

    # Run MRP
    net_reqs, planned_orders = site_agent.mrp_engine.compute_net_requirements(
        gross_requirements=gross_requirements,
        on_hand_inventory=on_hand,
        scheduled_receipts={},
        bom={},
        lead_times=lead_times,
    )

    print(f"\n  Results:")
    print(f"    Net Requirements: {len(net_reqs)}")
    for nr in net_reqs[:3]:
        print(f"      - {nr.item_id}: {nr.net_qty} units on {nr.required_date}")

    print(f"    Planned Orders: {len(planned_orders)}")
    for po in planned_orders[:3]:
        print(f"      - {po.item_id}: {po.quantity} units, order {po.order_date}, receive {po.receipt_date}")

    return len(planned_orders) > 0


def test_aatp_engine(site_agent, config: SupplyChainConfig, db: Session):
    """Test the AATP engine with priority allocations."""
    print("\n" + "=" * 60)
    print("Testing AATP Engine (Priority-Based ATP)")
    print("=" * 60)

    from app.services.powell.engines import ATPAllocation, Order, Priority

    # Load allocations (simulating tGNN output)
    today = date.today()
    allocations = [
        ATPAllocation("PROD001", "DC001", Priority.CRITICAL, 50, today, today),
        ATPAllocation("PROD001", "DC001", Priority.HIGH, 100, today, today),
        ATPAllocation("PROD001", "DC001", Priority.MEDIUM, 200, today, today),
        ATPAllocation("PROD001", "DC001", Priority.LOW, 150, today, today),
        ATPAllocation("PROD001", "DC001", Priority.STANDARD, 100, today, today),
    ]

    site_agent.aatp_engine.load_allocations(allocations)
    summary = site_agent.aatp_engine.get_allocation_summary()

    print(f"\n  Loaded Allocations:")
    print(f"    Total Allocated: {summary['total_allocated']}")
    print(f"    By Priority: {summary['by_priority']}")

    # Test orders at different priorities
    test_orders = [
        ("HIGH priority order (50 units)", Priority.HIGH, 50),
        ("MEDIUM priority order (300 units - exceeds tier)", Priority.MEDIUM, 300),
        ("LOW priority order (200 units)", Priority.LOW, 200),
    ]

    print(f"\n  Testing Orders:")
    for desc, priority, qty in test_orders:
        order = Order(
            order_id=f"TEST-{priority.value}",
            product_id="PROD001",
            location_id="DC001",
            requested_qty=qty,
            requested_date=today,
            priority=priority,
            customer_id="CUST001",
        )

        result = site_agent.aatp_engine.check_availability(order)

        print(f"\n    {desc}:")
        print(f"      Can Fulfill: {result.can_fulfill_full}")
        print(f"      Available: {result.available_qty} / {qty}")
        print(f"      Shortage: {result.shortage_qty}")
        print(f"      Consumption: {[(p.value, q) for p, q in result.consumption_detail]}")

    return True


def test_safety_stock_calculator(site_agent, config: SupplyChainConfig, db: Session):
    """Test the Safety Stock calculator with different policies."""
    print("\n" + "=" * 60)
    print("Testing Safety Stock Calculator")
    print("=" * 60)

    from app.services.powell.engines import SSPolicy, PolicyType, DemandStats

    # Create demand stats (typical for food distribution)
    demand_stats = DemandStats(
        avg_daily_demand=50,  # 50 cases/day
        std_daily_demand=15,  # 30% CV
        avg_daily_forecast=50,
        lead_time_days=3,     # 3-day lead time
    )

    print(f"\n  Demand Stats:")
    print(f"    Avg Daily Demand: {demand_stats.avg_daily_demand}")
    print(f"    Std Dev: {demand_stats.std_daily_demand}")
    print(f"    Lead Time: {demand_stats.lead_time_days} days")

    # Test different policy types
    policies = [
        ("Absolute Level (500 units)", SSPolicy(
            policy_type=PolicyType.ABS_LEVEL,
            fixed_quantity=500,
        )),
        ("Days of Coverage (7 days)", SSPolicy(
            policy_type=PolicyType.DOC_DEM,
            days_of_coverage=7,
        )),
        ("Service Level (95%)", SSPolicy(
            policy_type=PolicyType.SL,
            target_service_level=0.95,
        )),
        ("Service Level (99%)", SSPolicy(
            policy_type=PolicyType.SL,
            target_service_level=0.99,
        )),
    ]

    print(f"\n  Policy Results:")
    for desc, policy in policies:
        result = site_agent.ss_calculator.compute_safety_stock(
            product_id="PROD001",
            location_id="DC001",
            policy=policy,
            stats=demand_stats,
        )

        print(f"\n    {desc}:")
        print(f"      Safety Stock: {result.safety_stock} units")
        print(f"      Reorder Point: {result.reorder_point} units")

    return True


async def test_atp_execution(site_agent, config: SupplyChainConfig, db: Session):
    """Test ATP execution through SiteAgent (with optional TRM)."""
    print("\n" + "=" * 60)
    print("Testing SiteAgent ATP Execution")
    print("=" * 60)

    from app.services.powell.engines import ATPAllocation, Order, Priority

    # Load allocations
    today = date.today()
    allocations = [
        ATPAllocation("PROD001", site_agent.site_key, Priority.MEDIUM, 100, today, today),
    ]
    site_agent.aatp_engine.load_allocations(allocations)

    # Create test order
    order = Order(
        order_id="TEST-ATP-001",
        product_id="PROD001",
        location_id=site_agent.site_key,
        requested_qty=150,  # Exceeds allocation to trigger TRM
        requested_date=today,
        priority=Priority.MEDIUM,
        customer_id="CUST001",
    )

    print(f"\n  Order: {order.requested_qty} units of {order.product_id}")
    print(f"  Available allocation: 100 units (MEDIUM priority)")

    # Execute ATP
    result = await site_agent.execute_atp(order)

    print(f"\n  ATP Result:")
    print(f"    Promised Qty: {result.promised_qty}")
    print(f"    Promise Date: {result.promise_date}")
    print(f"    Source: {result.source}")
    print(f"    Confidence: {result.confidence}")
    print(f"    Explanation: {result.explanation}")

    return True


async def test_cdc_monitor(site_agent, config: SupplyChainConfig, db: Session):
    """Test CDC monitor trigger detection."""
    print("\n" + "=" * 60)
    print("Testing CDC Monitor")
    print("=" * 60)

    from app.services.powell.cdc_monitor import SiteMetrics

    # Normal metrics (should not trigger)
    normal_metrics = SiteMetrics(
        site_key=site_agent.site_key,
        timestamp=datetime.utcnow(),
        demand_cumulative=100,
        forecast_cumulative=100,  # No deviation
        inventory_on_hand=500,
        inventory_target=500,
        service_level=0.96,
        target_service_level=0.95,
        avg_lead_time_actual=3,
        avg_lead_time_expected=3,
        supplier_on_time_rate=0.95,
        backlog_units=0,
        backlog_yesterday=0,
    )

    print(f"\n  Testing Normal Metrics (no deviation):")
    trigger1 = await site_agent.check_cdc_trigger(normal_metrics)
    print(f"    Triggered: {trigger1.triggered}")
    print(f"    Reasons: {[r.value for r in trigger1.reasons]}")
    print(f"    Action: {trigger1.recommended_action.value}")

    # Deviation metrics (should trigger)
    deviation_metrics = SiteMetrics(
        site_key=site_agent.site_key,
        timestamp=datetime.utcnow(),
        demand_cumulative=150,    # 50% above forecast!
        forecast_cumulative=100,
        inventory_on_hand=300,    # 60% of target
        inventory_target=500,
        service_level=0.88,       # Below target
        target_service_level=0.95,
        avg_lead_time_actual=5,   # 67% increase
        avg_lead_time_expected=3,
        supplier_on_time_rate=0.80,  # Poor reliability
        backlog_units=50,
        backlog_yesterday=30,     # Growing backlog
    )

    print(f"\n  Testing Deviation Metrics (multiple issues):")
    trigger2 = await site_agent.check_cdc_trigger(deviation_metrics)
    print(f"    Triggered: {trigger2.triggered}")
    print(f"    Reasons: {[r.value for r in trigger2.reasons]}")
    print(f"    Severity: {trigger2.severity}")
    print(f"    Action: {trigger2.recommended_action.value}")
    print(f"    Message: {trigger2.message}")

    return trigger2.triggered


async def test_inventory_adjustments(site_agent, config: SupplyChainConfig, db: Session):
    """Test TRM inventory adjustments (requires trained model)."""
    print("\n" + "=" * 60)
    print("Testing TRM Inventory Adjustments")
    print("=" * 60)

    if not site_agent.model:
        print("  TRM model not loaded - using default adjustments")

    adjustments = await site_agent.get_inventory_adjustments()

    print(f"\n  Adjustments:")
    print(f"    SS Multiplier: {adjustments['ss_multiplier']:.3f}")
    print(f"    ROP Multiplier: {adjustments['rop_multiplier']:.3f}")
    print(f"    Confidence: {adjustments['confidence']:.3f}")

    # Verify bounded
    assert 0.8 <= adjustments['ss_multiplier'] <= 1.2, "SS multiplier out of bounds"
    assert 0.8 <= adjustments['rop_multiplier'] <= 1.2, "ROP multiplier out of bounds"

    return True


def test_agent_strategy_integration(site_agent, config: SupplyChainConfig, db: Session):
    """Test SiteAgent as a simulation agent strategy."""
    print("\n" + "=" * 60)
    print("Testing Agent Strategy Integration")
    print("=" * 60)

    from app.services.powell.integration import SiteAgentPolicy

    # Create policy
    policy = SiteAgentPolicy(
        site_key="DC001",
        use_trm=site_agent.model is not None,
    )

    # Test different scenarios
    scenarios = [
        ("Normal inventory", {'inventory': 100, 'backlog': 0, 'pipeline_on_order': 50,
                              'last_incoming_order': 30, 'base_stock': 150, 'inventory_position': 150}),
        ("Low inventory", {'inventory': 20, 'backlog': 10, 'pipeline_on_order': 30,
                           'last_incoming_order': 50, 'base_stock': 150, 'inventory_position': 40}),
        ("High backlog", {'inventory': 0, 'backlog': 80, 'pipeline_on_order': 40,
                          'last_incoming_order': 60, 'base_stock': 150, 'inventory_position': -40}),
    ]

    print(f"\n  Testing Order Decisions:")
    for desc, observation in scenarios:
        order = policy.order(observation)
        inv_pos = observation['inventory_position']
        base_stock = observation['base_stock']
        demand = observation['last_incoming_order']

        print(f"\n    {desc}:")
        print(f"      Inv Position: {inv_pos}, Base Stock: {base_stock}, Demand: {demand}")
        print(f"      Order Quantity: {order}")

    return True


async def main():
    parser = argparse.ArgumentParser(description="Test SiteAgent with Food Dist config")
    parser.add_argument("--with-trm", action="store_true", help="Enable TRM adjustments")
    parser.add_argument("--generate-data", action="store_true", help="Generate Food Dist config if not exists")
    parser.add_argument("--checkpoint", type=str, help="Path to model checkpoint")
    args = parser.parse_args()

    print("=" * 60)
    print("SiteAgent Test Suite - Food Dist Configuration")
    print("=" * 60)

    db = SessionLocal()
    try:
        # Find or generate Food Dist config
        config = get_food_dist_config(db)

        if not config and args.generate_data:
            config = generate_food_dist_config(db)
        elif not config:
            print("\nNo Food Dist configuration found.")
            print("Run with --generate-data to create one, or use:")
            print("  python scripts/generate_food_dist_config.py")
            return

        print(f"\nUsing config: {config.name} (ID: {config.id})")

        # Create SiteAgent
        from app.services.powell.site_agent import SiteAgent, SiteAgentConfig

        site_key = "DC001"  # Main distribution center
        agent_config = SiteAgentConfig(
            site_key=site_key,
            use_trm_adjustments=args.with_trm,
            agent_mode="copilot",
            model_checkpoint_path=args.checkpoint,
        )

        site_agent = SiteAgent(agent_config)

        print(f"\nSiteAgent created:")
        print(f"  Site Key: {site_agent.site_key}")
        print(f"  Use TRM: {agent_config.use_trm_adjustments}")
        print(f"  Model Loaded: {site_agent.model is not None}")

        # Run tests
        results = {}

        # Deterministic engine tests
        results["MRP Engine"] = test_mrp_engine(site_agent, config, db)
        results["AATP Engine"] = test_aatp_engine(site_agent, config, db)
        results["Safety Stock"] = test_safety_stock_calculator(site_agent, config, db)

        # Async tests
        results["ATP Execution"] = await test_atp_execution(site_agent, config, db)
        results["CDC Monitor"] = await test_cdc_monitor(site_agent, config, db)
        results["Inventory Adjustments"] = await test_inventory_adjustments(site_agent, config, db)

        # Integration test
        results["Agent Strategy"] = test_agent_strategy_integration(site_agent, config, db)

        # Summary
        print("\n" + "=" * 60)
        print("Test Summary")
        print("=" * 60)

        passed = sum(1 for r in results.values() if r)
        total = len(results)

        for test_name, passed_test in results.items():
            status = "PASS" if passed_test else "FAIL"
            print(f"  [{status}] {test_name}")

        print(f"\n  Total: {passed}/{total} passed")

        if passed == total:
            print("\n  All tests passed!")
        else:
            print("\n  Some tests failed - check output above")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
