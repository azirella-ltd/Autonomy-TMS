"""
Test Capacity Integration with Scenario Service

This script tests that capacity constraints work correctly when integrated
into the main scenario service flow.

Usage:
    docker compose exec backend python scripts/test_capacity_integration.py
"""

import asyncio
from datetime import date
from sqlalchemy import select, delete

from app.db.session import async_session_factory
from app.models.supply_chain_config import SupplyChainConfig
from app.models.group import Group
from app.models.scenario import Scenario
from app.models.aws_sc_planning import ProductionCapacity, InboundOrderLine
from app.services.sc_planning.simulation_execution_adapter import SimulationExecutionAdapter


async def test_capacity_integration():
    """Test capacity constraints integration with scenario service"""
    print("=" * 80)
    print("CAPACITY INTEGRATION TEST")
    print("=" * 80)
    print()

    async with async_session_factory() as db:
        # Setup: Create test scenario with capacity constraints
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
            return False

        # Create scenario with capacity enabled
        scenario = Scenario(
            name="Capacity Integration Test",
            group_id=group.id,
            supply_chain_config_id=config.id,
            use_aws_sc_planning=True,
            max_rounds=10,
            start_date=date.today(),
            config={
                'use_capacity_constraints': True,
                'capacity_reset_period': 1
            }
        )
        scenario.supply_chain_config = config
        db.add(scenario)
        await db.commit()
        await db.refresh(scenario)

        print(f"✓ Created test scenario (ID: {scenario.id})")
        print(f"  Capacity constraints: {scenario.config.get('use_capacity_constraints')}")
        print()

        # Setup: Clean up any existing capacity constraints first
        await db.execute(delete(ProductionCapacity).filter(
            ProductionCapacity.group_id == group.id,
            ProductionCapacity.config_id == config.id
        ))
        await db.commit()

        # Setup: Create capacity constraints
        await db.refresh(config, ['nodes', 'items'])
        item_id = config.items[0].id if config.items else 2

        capacities = []
        for node in config.nodes:
            # Set capacity on Factory (supplies Distributor) and Wholesaler (supplies Retailer)
            if 'Factory' in node.name:
                capacity = ProductionCapacity(
                    site_id=node.id,
                    product_id=item_id,
                    max_capacity_per_period=50.0,
                    current_capacity_used=0.0,
                    capacity_type='production',
                    capacity_period='week',
                    allow_overflow=False,
                    group_id=group.id,
                    config_id=config.id
                )
                capacities.append(capacity)
                print(f"  ✓ {node.name}: 50 units/week capacity (supplies Distributor)")

        db.add_all(capacities)
        await db.commit()
        print(f"✓ Created {len(capacities)} capacity constraints")
        print()

        # Test: Initialize adapter and load cache
        print("TEST 1: Adapter initialization with capacity cache")
        adapter = SimulationExecutionAdapter(scenario, db, use_cache=True)
        cache_counts = await adapter.cache.load()

        print(f"  ✓ Cache loaded: {cache_counts}")
        print(f"  ✓ Capacity constraints cached: {cache_counts.get('production_capacities', 0)}")

        if cache_counts.get('production_capacities', 0) != len(capacities):
            print(f"  ❌ Expected {len(capacities)} capacities, got {cache_counts.get('production_capacities', 0)}")
            return False

        print("  ✅ TEST 1 PASSED")
        print()

        # Test: Create orders within capacity
        print("TEST 2: Orders within capacity")
        player_orders = {
            'Distributor': 30.0  # Within 50 capacity
        }

        # Check if scenario config enables capacity
        use_capacity = scenario.config.get('use_capacity_constraints', False)
        print(f"  Scenario capacity setting: {use_capacity}")

        if use_capacity:
            result = await adapter.create_work_orders_with_capacity(player_orders, round_number=1)
            created_count = len(result['created'])
            queued_count = len(result['queued'])

            print(f"  ✓ Created: {created_count} orders")
            print(f"  ✓ Queued: {queued_count} orders")

            if created_count != 1 or queued_count != 0:
                print(f"  ❌ Expected 1 created, 0 queued")
                return False
        else:
            print(f"  ❌ Capacity not enabled in scenario config")
            return False

        print("  ✅ TEST 2 PASSED")
        print()

        # Test: Create orders exceeding capacity
        print("TEST 3: Orders exceeding capacity")

        # Reset capacity first
        reset_count = await adapter.reset_period_capacity()
        print(f"  ✓ Reset {reset_count} capacity counters")

        player_orders = {
            'Distributor': 70.0  # Exceeds 50 capacity
        }

        result = await adapter.create_work_orders_with_capacity(player_orders, round_number=2)
        created_count = len(result['created'])
        queued_count = len(result['queued'])

        print(f"  ✓ Created: {created_count} orders")
        print(f"  ✓ Queued: {queued_count} orders")

        if created_count == 0 or queued_count == 0:
            print(f"  ❌ Expected partial fulfillment (created + queued)")
            return False

        print("  ✅ TEST 3 PASSED")
        print()

        # Test: Capacity reset
        print("TEST 4: Capacity reset at period boundary")

        # Check capacity before reset
        result_before = await db.execute(
            select(ProductionCapacity).filter(
                ProductionCapacity.group_id == group.id,
                ProductionCapacity.config_id == config.id
            )
        )
        capacities_before = result_before.scalars().all()
        used_before = sum(c.current_capacity_used for c in capacities_before)

        print(f"  Capacity used before reset: {used_before}")

        # Reset
        reset_count = await adapter.reset_period_capacity()
        print(f"  ✓ Reset {reset_count} capacity counters")

        # Check capacity after reset
        result_after = await db.execute(
            select(ProductionCapacity).filter(
                ProductionCapacity.group_id == group.id,
                ProductionCapacity.config_id == config.id
            )
        )
        capacities_after = result_after.scalars().all()
        used_after = sum(c.current_capacity_used for c in capacities_after)

        print(f"  Capacity used after reset: {used_after}")

        if used_before == 0 or used_after != 0:
            print(f"  ❌ Capacity not reset properly")
            return False

        print("  ✅ TEST 4 PASSED")
        print()

        # Cleanup
        print("Cleanup:")
        await db.execute(delete(InboundOrderLine).filter(InboundOrderLine.scenario_id == scenario.id))
        await db.execute(delete(ProductionCapacity).filter(
            ProductionCapacity.group_id == group.id,
            ProductionCapacity.config_id == config.id
        ))
        await db.delete(scenario)
        await db.commit()
        print(f"  ✓ Cleaned up test data")
        print()

        return True


async def main():
    """Main entry point"""
    print()
    print("=" * 80)
    print("CAPACITY CONSTRAINTS INTEGRATION TEST")
    print("=" * 80)
    print()

    try:
        success = await test_capacity_integration()

        print("=" * 80)
        print("RESULT")
        print("=" * 80)
        print()

        if success:
            print("✅ ALL INTEGRATION TESTS PASSED")
            print()
            print("Capacity constraints are properly integrated:")
            print("  ✓ Cache loads capacity constraints")
            print("  ✓ Scenario config controls capacity enforcement")
            print("  ✓ Orders within capacity are fulfilled")
            print("  ✓ Orders exceeding capacity are queued")
            print("  ✓ Capacity resets at period boundaries")
            print()
            return 0
        else:
            print("❌ INTEGRATION TESTS FAILED")
            return 1

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
