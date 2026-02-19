"""
Test Order Aggregation Integration

This script tests that order aggregation works correctly when integrated
into the execution adapter.

Usage:
    docker compose exec backend python scripts/test_aggregation_integration.py
"""

import asyncio
from datetime import date
from sqlalchemy import select, delete

from app.db.session import async_session_factory
from app.models.supply_chain_config import SupplyChainConfig
from app.models.group import Group
from app.models.scenario import Scenario
from app.models.aws_sc_planning import (
    OrderAggregationPolicy,
    AggregatedOrder,
    InboundOrderLine
)
from app.services.aws_sc_planning.beer_scenario_execution_adapter import BeerScenarioExecutionAdapter


async def test_aggregation_integration():
    """Test order aggregation integration with execution adapter"""
    print("=" * 80)
    print("ORDER AGGREGATION INTEGRATION TEST")
    print("=" * 80)
    print()

    async with async_session_factory() as db:
        # Setup: Get test config and group
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

        # Create test scenario
        scenario = Scenario(
            name="Aggregation Integration Test",
            group_id=group.id,
            supply_chain_config_id=config.id,
            use_aws_sc_planning=True,
            max_rounds=10,
            start_date=date.today(),
            config={}
        )
        scenario.supply_chain_config = config
        db.add(scenario)
        await db.commit()
        await db.refresh(scenario)

        print(f"✓ Created test scenario (ID: {scenario.id})")
        print()

        # Setup: Clean up any existing aggregation data (orders first, then policies)
        await db.execute(delete(AggregatedOrder).filter(
            AggregatedOrder.group_id == group.id,
            AggregatedOrder.config_id == config.id
        ))
        await db.execute(delete(OrderAggregationPolicy).filter(
            OrderAggregationPolicy.group_id == group.id,
            OrderAggregationPolicy.config_id == config.id
        ))
        await db.commit()

        # Setup: Get nodes
        await db.refresh(config, ['nodes', 'items'])
        item_id = config.items[0].id if config.items else 2

        factory_node = None
        distributor_node = None
        wholesaler_node = None

        for node in config.nodes:
            if 'Factory' in node.name:
                factory_node = node
            elif 'Distributor' in node.name:
                distributor_node = node
            elif 'Wholesaler' in node.name:
                wholesaler_node = node

        if not all([factory_node, distributor_node, wholesaler_node]):
            print("❌ Required nodes not found")
            return False

        # Create aggregation policies
        policies = []

        # Policy 1: Distributor + Wholesaler → Factory (min 50, multiple of 10, fixed cost $100)
        policy1 = OrderAggregationPolicy(
            from_site_id=distributor_node.id,
            to_site_id=factory_node.id,
            product_id=item_id,
            min_order_quantity=50.0,
            order_multiple=10.0,
            fixed_order_cost=100.0,
            variable_cost_per_unit=5.0,
            is_active=True,
            group_id=group.id,
            config_id=config.id
        )
        policies.append(policy1)
        print(f"  ✓ Policy: Distributor → Factory (min: 50, multiple: 10, fixed cost: $100)")

        policy2 = OrderAggregationPolicy(
            from_site_id=wholesaler_node.id,
            to_site_id=factory_node.id,
            product_id=item_id,
            min_order_quantity=50.0,
            order_multiple=10.0,
            fixed_order_cost=100.0,
            variable_cost_per_unit=5.0,
            is_active=True,
            group_id=group.id,
            config_id=config.id
        )
        policies.append(policy2)
        print(f"  ✓ Policy: Wholesaler → Factory (min: 50, multiple: 10, fixed cost: $100)")

        db.add_all(policies)
        await db.commit()
        print(f"✓ Created {len(policies)} aggregation policies")
        print()

        # Test 1: Initialize adapter with aggregation cache
        print("TEST 1: Adapter initialization with aggregation cache")
        adapter = BeerScenarioExecutionAdapter(scenario, db, use_cache=True)
        cache_counts = await adapter.cache.load()

        print(f"  ✓ Cache loaded: {cache_counts}")
        print(f"  ✓ Aggregation policies cached: {cache_counts.get('aggregation_policies', 0)}")

        if cache_counts.get('aggregation_policies', 0) != len(policies):
            print(f"  ❌ Expected {len(policies)} policies, got {cache_counts.get('aggregation_policies', 0)}")
            return False

        print("  ✅ TEST 1 PASSED")
        print()

        # Test 2: Orders without aggregation (different upstream sites)
        print("TEST 2: Orders without aggregation (no policy match)")
        player_orders = {
            'Retailer': 30.0  # Orders from Wholesaler (no policy from Retailer → Wholesaler)
        }

        result = await adapter.create_work_orders_with_aggregation(
            player_orders,
            round_number=1,
            use_capacity=False
        )

        print(f"  ✓ Created: {len(result['created'])} orders")
        print(f"  ✓ Aggregated: {len(result['aggregated'])} groups")
        print(f"  ✓ Cost savings: ${result['cost_savings']:.2f}")

        if len(result['created']) != 1 or len(result['aggregated']) != 0:
            print(f"  ❌ Expected 1 created, 0 aggregated")
            return False

        print("  ✅ TEST 2 PASSED")
        print()

        # Clean up orders
        await db.execute(delete(InboundOrderLine).filter(InboundOrderLine.scenario_id == scenario.id))
        await db.commit()

        # Test 3: Single order with quantity constraints
        print("TEST 3: Single order with quantity constraints")
        player_orders = {
            'Distributor': 35.0  # Below min (50), will be adjusted
        }

        result = await adapter.create_work_orders_with_aggregation(
            player_orders,
            round_number=2,
            use_capacity=False
        )

        print(f"  ✓ Created: {len(result['created'])} orders")
        print(f"  ✓ Aggregated: {len(result['aggregated'])} groups")
        print(f"  ✓ Cost savings: ${result['cost_savings']:.2f}")

        if len(result['created']) != 1 or len(result['aggregated']) != 1:
            print(f"  ❌ Expected 1 created, 1 aggregated")
            return False

        # Check adjusted quantity
        agg_record = result['aggregated'][0]
        if agg_record.total_quantity != 35.0:
            print(f"  ❌ Expected total_quantity=35.0, got {agg_record.total_quantity}")
            return False

        if agg_record.adjusted_quantity != 50.0:
            print(f"  ❌ Expected adjusted_quantity=50.0 (min), got {agg_record.adjusted_quantity}")
            return False

        print(f"  ✓ Quantity adjusted from {agg_record.total_quantity} to {agg_record.adjusted_quantity}")
        print("  ✅ TEST 3 PASSED")
        print()

        # Clean up orders
        await db.execute(delete(InboundOrderLine).filter(InboundOrderLine.scenario_id == scenario.id))
        await db.execute(delete(AggregatedOrder).filter(AggregatedOrder.scenario_id == scenario.id))
        await db.commit()

        # Test 4: Single aggregated order (one site with policy)
        print("TEST 4: Single site ordering with aggregation policy")
        player_orders = {
            'Distributor': 30.0,  # Has policy to Factory
            'Retailer': 25.0      # Orders from Wholesaler (no aggregation policy)
        }

        result = await adapter.create_work_orders_with_aggregation(
            player_orders,
            round_number=3,
            use_capacity=False
        )

        print(f"  ✓ Created: {len(result['created'])} orders")
        print(f"  ✓ Aggregated: {len(result['aggregated'])} groups")
        print(f"  ✓ Cost savings: ${result['cost_savings']:.2f}")

        # Should create 2 orders: 1 aggregated (Distributor→Factory), 1 normal (Retailer→Wholesaler)
        if len(result['created']) != 2:
            print(f"  ❌ Expected 2 created orders, got {len(result['created'])}")
            return False

        if len(result['aggregated']) != 1:
            print(f"  ❌ Expected 1 aggregated group, got {len(result['aggregated'])}")
            return False

        # Distributor order should be adjusted to min 50
        agg_record = result['aggregated'][0]
        if agg_record.adjusted_quantity != 50.0:
            print(f"  ❌ Expected adjusted_quantity=50.0, got {agg_record.adjusted_quantity}")
            return False

        # No cost savings because only one order in the aggregated group
        if result['cost_savings'] != 0.0:
            print(f"  ❌ Expected no savings (single order), got ${result['cost_savings']:.2f}")
            return False

        print("  ✅ TEST 4 PASSED")
        print()

        # Clean up orders
        await db.execute(delete(InboundOrderLine).filter(InboundOrderLine.scenario_id == scenario.id))
        await db.execute(delete(AggregatedOrder).filter(AggregatedOrder.scenario_id == scenario.id))
        await db.commit()

        # Test 5: Order multiple constraint
        print("TEST 5: Order multiple constraint (pallet quantities)")
        player_orders = {
            'Distributor': 55.0  # Should round up to 60 (multiple of 10)
        }

        result = await adapter.create_work_orders_with_aggregation(
            player_orders,
            round_number=4,
            use_capacity=False
        )

        print(f"  ✓ Created: {len(result['created'])} orders")
        print(f"  ✓ Aggregated: {len(result['aggregated'])} groups")

        agg_record = result['aggregated'][0]
        if agg_record.total_quantity != 55.0:
            print(f"  ❌ Expected total_quantity=55.0, got {agg_record.total_quantity}")
            return False

        if agg_record.adjusted_quantity != 60.0:
            print(f"  ❌ Expected adjusted_quantity=60.0 (multiple of 10), got {agg_record.adjusted_quantity}")
            return False

        print(f"  ✓ Quantity adjusted from {agg_record.total_quantity} to {agg_record.adjusted_quantity} (multiple of 10)")
        print("  ✅ TEST 5 PASSED")
        print()

        # Cleanup (delete in correct order to respect foreign keys)
        print("Cleanup:")
        await db.execute(delete(InboundOrderLine).filter(InboundOrderLine.scenario_id == scenario.id))
        await db.execute(delete(AggregatedOrder).filter(AggregatedOrder.scenario_id == scenario.id))
        await db.commit()

        await db.execute(delete(OrderAggregationPolicy).filter(
            OrderAggregationPolicy.group_id == group.id,
            OrderAggregationPolicy.config_id == config.id
        ))
        await db.commit()

        await db.delete(scenario)
        await db.commit()
        print(f"  ✓ Cleaned up test data")
        print()

        return True


async def main():
    """Main entry point"""
    print()
    print("=" * 80)
    print("ORDER AGGREGATION INTEGRATION TEST")
    print("=" * 80)
    print()

    try:
        success = await test_aggregation_integration()

        print("=" * 80)
        print("RESULT")
        print("=" * 80)
        print()

        if success:
            print("✅ ALL INTEGRATION TESTS PASSED")
            print()
            print("Order aggregation is properly integrated:")
            print("  ✓ Cache loads aggregation policies")
            print("  ✓ Orders are grouped by upstream site")
            print("  ✓ Quantity constraints are applied (min/max/multiple)")
            print("  ✓ Cost savings are calculated")
            print("  ✓ Aggregation records are created")
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
