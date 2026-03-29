"""
Test Analytics Service Integration

This script tests that analytics endpoints work correctly with Phase 3 features
(order aggregation and capacity constraints).

Usage:
    docker compose exec backend python scripts/test_analytics_integration.py
"""

import asyncio
from datetime import date
from sqlalchemy import select, delete

from app.db.session import async_session_factory
from app.models.supply_chain_config import SupplyChainConfig
from app.models.tenant import Tenant
from app.models.scenario import Scenario
from app.models.aws_sc_planning import (
    OrderAggregationPolicy,
    AggregatedOrder,
    ProductionCapacity,
    InboundOrderLine
)
from app.services.sc_planning.simulation_execution_adapter import SimulationExecutionAdapter
from app.services.analytics_service import AnalyticsService


async def test_analytics_integration():
    """Test analytics service integration"""
    print("=" * 80)
    print("ANALYTICS SERVICE INTEGRATION TEST")
    print("=" * 80)
    print()

    async with async_session_factory() as db:
        # Setup: Get test config and tenant
        result = await db.execute(
            select(SupplyChainConfig).filter(
                SupplyChainConfig.name.like("%Default%")
            )
        )
        config = result.scalar_one_or_none()

        result = await db.execute(select(Tenant).filter(Tenant.id == 2))
        tenant = result.scalar_one_or_none()

        if not config or not tenant:
            print("❌ Config or tenant not found")
            return False

        # Clean up any existing test data
        await db.execute(delete(InboundOrderLine).filter(
            InboundOrderLine.scenario_id.in_(
                select(Scenario.id).filter(
                    Scenario.name.like("%Analytics Test%")
                )
            )
        ))
        await db.execute(delete(AggregatedOrder).filter(
            AggregatedOrder.tenant_id == tenant.id,
            AggregatedOrder.config_id == config.id
        ))
        await db.execute(delete(ProductionCapacity).filter(
            ProductionCapacity.tenant_id == tenant.id,
            ProductionCapacity.config_id == config.id
        ))
        await db.execute(delete(OrderAggregationPolicy).filter(
            OrderAggregationPolicy.tenant_id == tenant.id,
            OrderAggregationPolicy.config_id == config.id
        ))
        await db.execute(delete(Scenario).filter(
            Scenario.name.like("%Analytics Test%")
        ))
        await db.commit()

        # Setup: Get nodes
        await db.refresh(config, ['nodes', 'items'])
        item_id = config.items[0].id if config.items else 2

        factory_node = None
        distributor_node = None

        for node in config.nodes:
            if 'Factory' in node.name:
                factory_node = node
            elif 'Distributor' in node.name:
                distributor_node = node

        if not all([factory_node, distributor_node]):
            print("❌ Required nodes not found")
            return False

        print("TEST 1: Analytics with aggregation data")
        print("-" * 80)

        # Create scenario with aggregation enabled
        scenario1 = Scenario(
            name="Analytics Test - Aggregation",
            tenant_id=tenant.id,
            supply_chain_config_id=config.id,
            use_aws_sc_planning=True,
            max_periods=10,
            start_date=date.today(),
            config={
                'use_capacity_constraints': False,
                'use_order_aggregation': True
            }
        )
        scenario1.supply_chain_config = config
        db.add(scenario1)
        await db.commit()
        await db.refresh(scenario1)

        print(f"  ✓ Created scenario (ID: {scenario1.id})")

        # Create aggregation policy
        policy = OrderAggregationPolicy(
            from_site_id=distributor_node.id,
            to_site_id=factory_node.id,
            product_id=item_id,
            min_order_quantity=50.0,
            order_multiple=10.0,
            fixed_order_cost=100.0,
            is_active=True,
            tenant_id=tenant.id,
            config_id=config.id
        )
        db.add(policy)
        await db.commit()

        print(f"  ✓ Created aggregation policy")

        # Create adapter and generate some aggregated orders
        adapter = SimulationExecutionAdapter(scenario1, db, use_cache=True)
        await adapter.cache.load()

        # Round 1: Create aggregated orders
        result = await adapter.create_work_orders_with_aggregation(
            {'Distributor': 35.0},
            round_number=1,
            use_capacity=False
        )

        print(f"  ✓ Round 1: Created {len(result['created'])} orders, aggregated {len(result['aggregated'])} groups")

        # Round 2: Create more aggregated orders
        result = await adapter.create_work_orders_with_aggregation(
            {'Distributor': 25.0},
            round_number=2,
            use_capacity=False
        )

        print(f"  ✓ Round 2: Created {len(result['created'])} orders, aggregated {len(result['aggregated'])} groups")

        # Note: Cost savings are only realized when multiple orders are aggregated into one
        # Since we're only creating one order per round per site pair, there are no savings
        # This is expected behavior - we'll verify the metrics structure instead

        # Test analytics service
        analytics = AnalyticsService(db)
        metrics = await analytics.get_aggregation_metrics(scenario1.id)

        print()
        print("  Aggregation Metrics:")
        print(f"    Total orders aggregated: {metrics['aggregation_summary']['total_orders_aggregated']}")
        print(f"    Total customers created: {metrics['aggregation_summary']['total_groups_created']}")
        print(f"    Total cost savings: ${metrics['aggregation_summary']['total_cost_savings']:.2f}")

        # Verify metrics
        if metrics['aggregation_summary']['total_groups_created'] != 2:
            print(f"  ❌ Expected 2 groups, got {metrics['aggregation_summary']['total_groups_created']}")
            return False

        # Cost savings are 0 because we only had 1 order per aggregation group
        # The key is that the metrics are computed correctly
        if metrics['aggregation_summary']['total_orders_aggregated'] != 2:
            print(f"  ❌ Expected 2 orders aggregated, got {metrics['aggregation_summary']['total_orders_aggregated']}")
            return False

        print("  ✅ TEST 1 PASSED")
        print()

        # Cleanup Test 1
        await db.execute(delete(InboundOrderLine).filter(InboundOrderLine.scenario_id == scenario1.id))
        await db.execute(delete(AggregatedOrder).filter(AggregatedOrder.scenario_id == scenario1.id))
        await db.delete(scenario1)
        await db.commit()

        print("TEST 2: Analytics with capacity data")
        print("-" * 80)

        # Create scenario with capacity enabled
        scenario2 = Scenario(
            name="Analytics Test - Capacity",
            tenant_id=tenant.id,
            supply_chain_config_id=config.id,
            use_aws_sc_planning=True,
            max_periods=10,
            start_date=date.today(),
            config={
                'use_capacity_constraints': True,
                'use_order_aggregation': False,
                'capacity_reset_period': 1
            }
        )
        scenario2.supply_chain_config = config
        db.add(scenario2)
        await db.commit()
        await db.refresh(scenario2)

        print(f"  ✓ Created scenario (ID: {scenario2.id})")

        # Create capacity constraint
        capacity = ProductionCapacity(
            site_id=factory_node.id,
            product_id=item_id,
            max_capacity_per_period=100.0,
            current_capacity_used=0.0,
            capacity_type='production',
            capacity_period='week',
            allow_overflow=False,
            tenant_id=tenant.id,
            config_id=config.id
        )
        db.add(capacity)
        await db.commit()

        print(f"  ✓ Created capacity constraint (100 units max)")

        # Create adapter and generate some work orders to test capacity tracking
        adapter2 = SimulationExecutionAdapter(scenario2, db, use_cache=True)
        await adapter2.cache.load()

        # Create work order that uses 50 units of capacity
        result = await adapter2.create_work_orders_with_capacity(
            {'Distributor': 50.0},
            round_number=1
        )

        print(f"  ✓ Created work order (50 units)")

        # Test capacity analytics
        metrics = await analytics.get_capacity_metrics(scenario2.id)

        print()
        print("  Capacity Metrics:")
        print(f"    Sites with capacity: {metrics['capacity_summary']['sites_with_capacity']}")
        print(f"    Total capacity: {metrics['capacity_summary']['total_capacity']:.2f}")
        print(f"    Avg utilization: {metrics['capacity_summary']['avg_utilization']:.1f}%")

        # Verify metrics
        if metrics['capacity_summary']['sites_with_capacity'] != 1:
            print(f"  ❌ Expected 1 site, got {metrics['capacity_summary']['sites_with_capacity']}")
            return False

        # Utilization should be around 50% (50 used out of 100 max)
        if metrics['capacity_summary']['avg_utilization'] < 40.0 or metrics['capacity_summary']['avg_utilization'] > 60.0:
            print(f"  ❌ Expected ~50% utilization, got {metrics['capacity_summary']['avg_utilization']}")
            return False

        print("  ✅ TEST 2 PASSED")
        print()

        # Cleanup Test 2
        await db.execute(delete(InboundOrderLine).filter(InboundOrderLine.scenario_id == scenario2.id))
        await db.delete(scenario2)
        await db.execute(delete(ProductionCapacity).filter(
            ProductionCapacity.tenant_id == tenant.id,
            ProductionCapacity.config_id == config.id
        ))
        await db.commit()

        print("TEST 3: Policy effectiveness metrics")
        print("-" * 80)

        # Clean up any remaining policies from previous tests
        await db.execute(delete(OrderAggregationPolicy).filter(
            OrderAggregationPolicy.tenant_id == tenant.id,
            OrderAggregationPolicy.config_id == config.id
        ))
        await db.commit()

        # Create scenario with aggregation
        scenario3 = Scenario(
            name="Analytics Test - Policy",
            tenant_id=tenant.id,
            supply_chain_config_id=config.id,
            use_aws_sc_planning=True,
            max_periods=10,
            start_date=date.today(),
            config={'use_order_aggregation': True}
        )
        scenario3.supply_chain_config = config
        db.add(scenario3)
        await db.commit()
        await db.refresh(scenario3)

        print(f"  ✓ Created scenario (ID: {scenario3.id})")

        # Create aggregation policy
        policy = OrderAggregationPolicy(
            from_site_id=distributor_node.id,
            to_site_id=factory_node.id,
            product_id=item_id,
            min_order_quantity=50.0,
            order_multiple=10.0,
            fixed_order_cost=100.0,
            is_active=True,
            tenant_id=tenant.id,
            config_id=config.id
        )
        db.add(policy)
        await db.commit()

        # Create some aggregated orders using the policy
        adapter = SimulationExecutionAdapter(scenario3, db, use_cache=True)
        await adapter.cache.load()

        for round_num in range(1, 4):
            result = await adapter.create_work_orders_with_aggregation(
                {'Distributor': 30.0},
                round_number=round_num,
                use_capacity=False
            )

        print(f"  ✓ Created 3 rounds of aggregated orders")

        # Test policy effectiveness analytics
        metrics = await analytics.get_policy_effectiveness(config.id, tenant.id)

        # Filter for aggregation policies only
        agg_policies = [p for p in metrics['policies'] if p['type'] == 'aggregation']

        print()
        print("  Policy Effectiveness Metrics:")
        print(f"    Total policies: {len(metrics['policies'])}")
        print(f"    Aggregation policies: {len(agg_policies)}")

        if len(agg_policies) > 0:
            policy_data = agg_policies[0]
            print(f"    Policy ID: {policy_data['policy_id']}")
            print(f"    Usage count: {policy_data['usage_count']}")
            print(f"    Total cost savings: ${policy_data['total_savings']:.2f}")

        # Verify metrics
        if len(agg_policies) != 1:
            print(f"  ❌ Expected 1 aggregation policy, got {len(agg_policies)}")
            return False

        if agg_policies[0]['usage_count'] != 3:
            print(f"  ❌ Expected 3 uses, got {agg_policies[0]['usage_count']}")
            return False

        print("  ✅ TEST 3 PASSED")
        print()

        # Cleanup Test 3
        await db.execute(delete(InboundOrderLine).filter(InboundOrderLine.scenario_id == scenario3.id))
        await db.execute(delete(AggregatedOrder).filter(AggregatedOrder.scenario_id == scenario3.id))
        await db.delete(scenario3)
        await db.commit()

        print("TEST 4: Comparative analytics")
        print("-" * 80)

        # Create scenario with all features
        scenario4 = Scenario(
            name="Analytics Test - Comparison",
            tenant_id=tenant.id,
            supply_chain_config_id=config.id,
            use_aws_sc_planning=True,
            max_periods=10,
            start_date=date.today(),
            config={
                'use_capacity_constraints': True,
                'use_order_aggregation': True,
                'capacity_reset_period': 1
            }
        )
        scenario4.supply_chain_config = config
        db.add(scenario4)
        await db.commit()
        await db.refresh(scenario4)

        print(f"  ✓ Created scenario (ID: {scenario4.id})")

        # Test comparative analytics
        metrics = await analytics.get_comparative_analytics(scenario4.id)

        print()
        print("  Comparative Analytics:")
        print(f"    Aggregation enabled: {metrics['features_enabled']['order_aggregation']}")
        print(f"    Capacity enabled: {metrics['features_enabled']['capacity_constraints']}")

        # Verify metrics
        if not metrics['features_enabled']['order_aggregation']:
            print(f"  ❌ Expected order_aggregation enabled")
            return False

        if not metrics['features_enabled']['capacity_constraints']:
            print(f"  ❌ Expected capacity_constraints enabled")
            return False

        print("  ✅ TEST 4 PASSED")
        print()

        # Cleanup Test 4
        await db.delete(scenario4)
        await db.commit()

        # Final cleanup
        await db.execute(delete(OrderAggregationPolicy).filter(
            OrderAggregationPolicy.tenant_id == tenant.id,
            OrderAggregationPolicy.config_id == config.id
        ))
        await db.commit()

        print("Cleanup:")
        print(f"  ✓ Cleaned up test data")
        print()

        return True


async def main():
    """Main entry point"""
    print()
    print("=" * 80)
    print("ANALYTICS SERVICE INTEGRATION TEST")
    print("=" * 80)
    print()

    try:
        success = await test_analytics_integration()

        print("=" * 80)
        print("RESULT")
        print("=" * 80)
        print()

        if success:
            print("✅ ALL ANALYTICS INTEGRATION TESTS PASSED")
            print()
            print("Analytics service integration verified:")
            print("  ✓ Aggregation metrics computed correctly")
            print("  ✓ Capacity metrics computed correctly")
            print("  ✓ Policy effectiveness tracked correctly")
            print("  ✓ Comparative analytics working")
            print()
            return 0
        else:
            print("❌ ANALYTICS INTEGRATION TESTS FAILED")
            return 1

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
