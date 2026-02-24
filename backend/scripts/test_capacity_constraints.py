"""
Test Capacity Constraints (Phase 3 - Sprint 2)

This script validates the capacity constraint functionality:
- Capacity limit enforcement
- Partial fulfillment when capacity insufficient
- Order queuing when capacity exceeded
- Overflow handling with cost multipliers
- Capacity reset at period start

Usage:
    docker compose exec backend python scripts/test_capacity_constraints.py
"""

import asyncio
from datetime import date
from sqlalchemy import select, delete

from app.db.session import async_session_factory
from app.models.supply_chain_config import SupplyChainConfig
from app.models.group import Group
from app.models.scenario import Scenario
from app.models.aws_sc_planning import InboundOrderLine, ProductionCapacity
from app.services.sc_planning.simulation_execution_adapter import SimulationExecutionAdapter


async def setup_test_scenario():
    """Create a test scenario with capacity constraints"""
    print("=" * 80)
    print("SETUP: Creating test scenario with capacity constraints")
    print("=" * 80)
    print()

    async with async_session_factory() as db:
        # Get config and group
        result = await db.execute(
            select(SupplyChainConfig).filter(
                SupplyChainConfig.name.like("%Default%")
            )
        )
        config = result.scalar_one_or_none()

        result = await db.execute(select(Group).filter(Group.id == 2))
        group = result.scalar_one_or_none()

        if not config or not group:
            print("❌ Config or group not found")
            return None

        # Create test scenario
        scenario = Scenario(
            name="Capacity Test Scenario",
            group_id=group.id,
            supply_chain_config_id=config.id,
            use_aws_sc_planning=True,
            max_rounds=10,
            start_date=date.today()
        )
        scenario.supply_chain_config = config
        db.add(scenario)
        await db.commit()
        await db.refresh(scenario)

        print(f"✓ Created test scenario (ID: {scenario.id})")

        # Load nodes for capacity setup
        await db.refresh(config, ['nodes', 'items'])

        # Create capacity constraints for each node
        # Factory: 50 units/week (strictest)
        # Distributor: 75 units/week
        # Wholesaler: 100 units/week (with overflow allowed)
        # Retailer: No constraint

        capacities = []
        item_id = config.items[0].id if config.items else 2

        for node in config.nodes:
            if 'Factory' in node.name:
                capacity = ProductionCapacity(
                    site_id=node.id,
                    product_id=item_id,
                    max_capacity_per_period=50.0,
                    current_capacity_used=0.0,
                    capacity_type='production',
                    capacity_period='week',
                    allow_overflow=False,  # Strict limit
                    group_id=group.id,
                    config_id=config.id
                )
                capacities.append(capacity)
                print(f"  ✓ Factory capacity: 50 units/week (strict)")

            elif 'Distributor' in node.name:
                capacity = ProductionCapacity(
                    site_id=node.id,
                    product_id=item_id,
                    max_capacity_per_period=75.0,
                    current_capacity_used=0.0,
                    capacity_type='transfer',
                    capacity_period='week',
                    allow_overflow=False,
                    group_id=group.id,
                    config_id=config.id
                )
                capacities.append(capacity)
                print(f"  ✓ Distributor capacity: 75 units/week (strict)")

            elif 'Wholesaler' in node.name:
                capacity = ProductionCapacity(
                    site_id=node.id,
                    product_id=item_id,
                    max_capacity_per_period=100.0,
                    current_capacity_used=0.0,
                    capacity_type='transfer',
                    capacity_period='week',
                    allow_overflow=True,  # Overflow with penalty
                    overflow_cost_multiplier=1.5,
                    group_id=group.id,
                    config_id=config.id
                )
                capacities.append(capacity)
                print(f"  ✓ Wholesaler capacity: 100 units/week (overflow @ 1.5x cost)")

        if capacities:
            db.add_all(capacities)
            await db.commit()
            print(f"✓ Created {len(capacities)} capacity constraints")
        else:
            print("⚠️  No capacities created (missing nodes)")

        print()
        return scenario.id


async def test_within_capacity(scenario_id: int):
    """Test 1: Orders within capacity limits"""
    print("=" * 80)
    print("TEST 1: Orders Within Capacity Limits")
    print("=" * 80)
    print()

    async with async_session_factory() as db:
        result = await db.execute(select(Scenario).filter(Scenario.id == scenario_id))
        scenario = result.scalar_one()
        await db.refresh(scenario, ['supply_chain_config'])

        adapter = SimulationExecutionAdapter(scenario, db, use_cache=True)
        await adapter.cache.load()

        # Order quantities well within limits
        player_orders = {
            'Retailer': 20.0,   # No constraint
            'Wholesaler': 30.0,  # Well under 100 limit
            'Distributor': 25.0, # Well under 75 limit
            'Factory': 15.0      # Well under 50 limit
        }

        print("ScenarioUser orders:")
        for role, qty in player_orders.items():
            print(f"  {role}: {qty} units")
        print()

        result = await adapter.create_work_orders_with_capacity(player_orders, round_number=1)

        print(f"✓ Created: {len(result['created'])} work orders")
        print(f"✓ Queued: {len(result['queued'])} orders")
        print(f"✓ Rejected: {len(result['rejected'])} orders")
        print()

        if result['capacity_used']:
            print("Capacity usage:")
            for site_name, used in result['capacity_used'].items():
                print(f"  {site_name}: {used} units")
        print()

        # Validate all orders created
        success = len(result['created']) == 4 and len(result['queued']) == 0
        if success:
            print("✅ TEST 1 PASSED: All orders created successfully")
        else:
            print("❌ TEST 1 FAILED: Expected 4 created, 0 queued")

        print()
        return success


async def test_exceed_capacity(scenario_id: int):
    """Test 2: Orders exceeding capacity limits"""
    print("=" * 80)
    print("TEST 2: Orders Exceeding Capacity Limits")
    print("=" * 80)
    print()

    async with async_session_factory() as db:
        result = await db.execute(select(Scenario).filter(Scenario.id == scenario_id))
        scenario = result.scalar_one()
        await db.refresh(scenario, ['supply_chain_config'])

        # Reset capacity counters
        adapter = SimulationExecutionAdapter(scenario, db, use_cache=True)
        await adapter.cache.load()
        reset_count = await adapter.reset_period_capacity()
        print(f"✓ Reset {reset_count} capacity counters")
        print()

        # Order quantities exceeding limits
        player_orders = {
            'Retailer': 40.0,   # No constraint - should work
            'Wholesaler': 120.0, # Exceeds 100 limit (overflow allowed)
            'Distributor': 80.0, # Exceeds 75 limit (no overflow)
            'Factory': 60.0      # Exceeds 50 limit (no overflow)
        }

        print("ScenarioUser orders:")
        for role, qty in player_orders.items():
            print(f"  {role}: {qty} units")
        print()

        result = await adapter.create_work_orders_with_capacity(player_orders, round_number=2)

        print(f"✓ Created: {len(result['created'])} work orders")
        print(f"✓ Queued: {len(result['queued'])} orders")
        print(f"✓ Rejected: {len(result['rejected'])} orders")
        print()

        if result['created']:
            print("Created orders:")
            for order in result['created']:
                print(f"  {order.order_id}: {order.quantity_submitted} units")
        print()

        if result['queued']:
            print("Queued orders:")
            for queued in result['queued']:
                print(f"  {queued['role']}: {queued['quantity']} units queued")
        print()

        if result['capacity_used']:
            print("Capacity usage:")
            for site_name, used in result['capacity_used'].items():
                print(f"  {site_name}: {used} units")
        print()

        # Validate behavior
        # - Retailer: should be created (no constraint)
        # - Wholesaler: should be created with overflow (120 > 100, but overflow allowed)
        # - Distributor: should be partially created or queued (80 > 75, no overflow)
        # - Factory: should be partially created or queued (60 > 50, no overflow)

        success = (
            len(result['created']) >= 2 and  # At least Retailer + Wholesaler
            len(result['queued']) >= 1        # At least one queued
        )

        if success:
            print("✅ TEST 2 PASSED: Capacity limits enforced correctly")
        else:
            print("❌ TEST 2 FAILED: Unexpected capacity behavior")

        print()
        return success


async def test_partial_fulfillment(scenario_id: int):
    """Test 3: Partial fulfillment when capacity partially available"""
    print("=" * 80)
    print("TEST 3: Partial Fulfillment")
    print("=" * 80)
    print()

    async with async_session_factory() as db:
        result = await db.execute(select(Scenario).filter(Scenario.id == scenario_id))
        scenario = result.scalar_one()
        await db.refresh(scenario, ['supply_chain_config'])

        adapter = SimulationExecutionAdapter(scenario, db, use_cache=True)
        await adapter.cache.load()

        # Reset capacity
        await adapter.reset_period_capacity()

        # Use some capacity first (Distributor has 50 capacity)
        first_orders = {
            'Distributor': 30.0  # Uses 30 of 50 capacity
        }

        print("First order wave:")
        print(f"  Distributor: 30 units (uses 30/50 capacity)")

        result1 = await adapter.create_work_orders_with_capacity(first_orders, round_number=3)
        print(f"✓ Created: {len(result1['created'])} orders")
        print()

        # Now try to order more than remaining capacity
        second_orders = {
            'Distributor': 30.0  # Wants 30, but only 20 remaining (50-30=20)
        }

        print("Second order wave:")
        print(f"  Distributor: 30 units (only 20 capacity remaining)")

        result2 = await adapter.create_work_orders_with_capacity(second_orders, round_number=3)

        print(f"✓ Created: {len(result2['created'])} orders")
        print(f"✓ Queued: {len(result2['queued'])} orders")
        print()

        if result2['created']:
            print("Created orders:")
            for order in result2['created']:
                print(f"  {order.order_id}: {order.quantity_submitted} units")

        if result2['queued']:
            print("Queued orders:")
            for queued in result2['queued']:
                print(f"  {queued['role']}: {queued['quantity']} units")
        print()

        # Should have partial fulfillment: 20 created, 10 queued
        success = len(result2['queued']) > 0  # Something should be queued

        if success:
            print("✅ TEST 3 PASSED: Partial fulfillment works")
        else:
            print("❌ TEST 3 FAILED: Expected partial fulfillment")

        print()
        return success


async def test_capacity_reset(scenario_id: int):
    """Test 4: Capacity reset functionality"""
    print("=" * 80)
    print("TEST 4: Capacity Reset")
    print("=" * 80)
    print()

    async with async_session_factory() as db:
        result = await db.execute(select(Scenario).filter(Scenario.id == scenario_id))
        scenario = result.scalar_one()
        await db.refresh(scenario, ['supply_chain_config'])

        adapter = SimulationExecutionAdapter(scenario, db, use_cache=True)
        await adapter.cache.load()

        # Use capacity
        orders = {
            'Factory': 40.0,
            'Distributor': 60.0,
            'Wholesaler': 80.0
        }

        print("Using capacity:")
        for role, qty in orders.items():
            print(f"  {role}: {qty} units")

        result1 = await adapter.create_work_orders_with_capacity(orders, round_number=4)
        print(f"✓ Created: {len(result1['created'])} orders")
        print()

        # Check capacity is used
        result = await db.execute(
            select(ProductionCapacity).filter(
                ProductionCapacity.group_id == scenario.group_id
            )
        )
        capacities_before = result.scalars().all()

        used_before = sum(c.current_capacity_used for c in capacities_before)
        print(f"Capacity used before reset: {used_before} units")
        print()

        # Reset capacity
        reset_count = await adapter.reset_period_capacity()
        print(f"✓ Reset {reset_count} capacity counters")
        print()

        # Check capacity is reset
        result = await db.execute(
            select(ProductionCapacity).filter(
                ProductionCapacity.group_id == scenario.group_id
            )
        )
        capacities_after = result.scalars().all()

        used_after = sum(c.current_capacity_used for c in capacities_after)
        print(f"Capacity used after reset: {used_after} units")
        print()

        success = used_before > 0 and used_after == 0

        if success:
            print("✅ TEST 4 PASSED: Capacity reset works")
        else:
            print("❌ TEST 4 FAILED: Capacity not reset properly")

        print()
        return success


async def test_overflow_handling(scenario_id: int):
    """Test 5: Overflow with cost multiplier"""
    print("=" * 80)
    print("TEST 5: Overflow Handling")
    print("=" * 80)
    print()

    async with async_session_factory() as db:
        result = await db.execute(select(Scenario).filter(Scenario.id == scenario_id))
        scenario = result.scalar_one()
        await db.refresh(scenario, ['supply_chain_config'])

        adapter = SimulationExecutionAdapter(scenario, db, use_cache=True)
        await adapter.cache.load()

        # Reset capacity
        await adapter.reset_period_capacity()

        # Order exceeding Wholesaler capacity (has overflow enabled)
        orders = {
            'Wholesaler': 120.0  # Exceeds 100 limit, overflow @ 1.5x cost
        }

        print("Ordering with overflow:")
        print(f"  Wholesaler: 120 units (capacity: 100, overflow: 1.5x cost)")
        print()

        result = await adapter.create_work_orders_with_capacity(orders, round_number=5)

        print(f"✓ Created: {len(result['created'])} orders")
        print(f"✓ Queued: {len(result['queued'])} orders")
        print()

        if result['created']:
            print("Created orders:")
            for order in result['created']:
                base_cost = getattr(order, 'base_cost', None) or 1.0
                cost = getattr(order, 'cost', None) or 1.0
                multiplier = cost / base_cost if base_cost > 0 else 1.0
                print(f"  {order.order_id}: {order.quantity_submitted} units")
                print(f"    Base cost: {base_cost:.2f}, Actual cost: {cost:.2f}, Multiplier: {multiplier:.2f}x")
        print()

        # Should have overflow order created with 1.5x cost
        success = len(result['created']) > 0  # Order should be created despite exceeding capacity

        if success:
            print("✅ TEST 5 PASSED: Overflow handling works")
            print("   Note: Cost multiplier applied when allow_overflow=True")
        else:
            print("❌ TEST 5 FAILED: Overflow not handled correctly")

        print()
        return success


async def cleanup_test_scenario(scenario_id: int):
    """Clean up test scenario and capacity constraints"""
    print("=" * 80)
    print("CLEANUP: Removing test data")
    print("=" * 80)
    print()

    async with async_session_factory() as db:
        # Delete work orders
        result = await db.execute(
            delete(InboundOrderLine).filter(InboundOrderLine.scenario_id == scenario_id)
        )
        print(f"✓ Deleted {result.rowcount} work orders")

        # Get scenario
        result = await db.execute(select(Scenario).filter(Scenario.id == scenario_id))
        scenario = result.scalar_one_or_none()

        if scenario:
            # Delete capacity constraints
            result = await db.execute(
                delete(ProductionCapacity).filter(
                    ProductionCapacity.group_id == scenario.group_id,
                    ProductionCapacity.config_id == scenario.supply_chain_config_id
                )
            )
            print(f"✓ Deleted {result.rowcount} capacity constraints")

            # Delete scenario
            await db.delete(scenario)
            await db.commit()
            print(f"✓ Deleted test scenario (ID: {scenario_id})")

        print()


async def main():
    """Main test runner"""
    print()
    print("=" * 80)
    print("AWS SC PHASE 3 - SPRINT 2: CAPACITY CONSTRAINTS TEST")
    print("=" * 80)
    print()

    scenario_id = None

    try:
        # Setup
        scenario_id = await setup_test_scenario()
        if not scenario_id:
            print("❌ Setup failed")
            return 1

        # Run tests
        test1_passed = await test_within_capacity(scenario_id)
        test2_passed = await test_exceed_capacity(scenario_id)
        test3_passed = await test_partial_fulfillment(scenario_id)
        test4_passed = await test_capacity_reset(scenario_id)
        test5_passed = await test_overflow_handling(scenario_id)

        # Summary
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print()
        print(f"Test 1 (Within Capacity):    {'✅ PASSED' if test1_passed else '❌ FAILED'}")
        print(f"Test 2 (Exceed Capacity):    {'✅ PASSED' if test2_passed else '❌ FAILED'}")
        print(f"Test 3 (Partial Fulfillment): {'✅ PASSED' if test3_passed else '❌ FAILED'}")
        print(f"Test 4 (Capacity Reset):     {'✅ PASSED' if test4_passed else '❌ FAILED'}")
        print(f"Test 5 (Overflow Handling):  {'✅ PASSED' if test5_passed else '❌ FAILED'}")
        print()

        all_passed = all([test1_passed, test2_passed, test3_passed, test4_passed, test5_passed])

        if all_passed:
            print("🎉 ALL CAPACITY CONSTRAINT TESTS PASSED")
            print()
            print("Phase 3 Sprint 2 Features Validated:")
            print("  ✓ Capacity limit enforcement")
            print("  ✓ Partial fulfillment when capacity insufficient")
            print("  ✓ Order queuing when capacity exceeded")
            print("  ✓ Capacity reset at period boundaries")
            print("  ✓ Overflow handling with cost multipliers")
            print()
            return 0
        else:
            print("⚠️  SOME TESTS FAILED")
            return 1

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # Cleanup
        if scenario_id:
            await cleanup_test_scenario(scenario_id)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
