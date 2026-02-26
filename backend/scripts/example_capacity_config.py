"""
Example: Setting up Capacity Constraints

This script demonstrates how to configure capacity constraints for different
supply chain scenarios.

Usage:
    docker compose exec backend python scripts/example_capacity_config.py
"""

import asyncio
from datetime import date
from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.supply_chain_config import SupplyChainConfig
from app.models.tenant import Tenant
from app.models.scenario import Scenario
from app.models.aws_sc_planning import ProductionCapacity


async def example_1_strict_capacity():
    """
    Example 1: Strict Capacity Constraints (No Overflow)

    Scenario: Traditional manufacturing with hard capacity limits
    - Factory: 100 units/week (production capacity)
    - Distributor: 150 units/week (transfer capacity)
    - Wholesaler: 200 units/week (transfer capacity)
    - No overflow allowed - excess orders are queued
    """
    print("=" * 80)
    print("EXAMPLE 1: Strict Capacity Constraints")
    print("=" * 80)
    print()

    async with async_session_factory() as db:
        # Get config
        result = await db.execute(
            select(SupplyChainConfig).filter(
                SupplyChainConfig.name.like("%Default%")
            )
        )
        config = result.scalar_one_or_none()

        if not config:
            print("❌ No config found")
            return

        await db.refresh(config, ['nodes'])

        print(f"Supply Chain: {config.name}")
        print(f"Nodes: {[n.name for n in config.nodes]}")
        print()

        # Create capacity constraints
        capacities = []
        item_id = 2  # Assuming item ID 2 exists

        for node in config.nodes:
            if 'Factory' in node.name:
                capacity = ProductionCapacity(
                    site_id=node.id,
                    product_id=item_id,
                    max_capacity_per_period=100.0,
                    current_capacity_used=0.0,
                    capacity_type='production',
                    capacity_period='week',
                    allow_overflow=False,  # Strict limit
                    customer_id=2,
                    config_id=config.id
                )
                capacities.append(capacity)
                print(f"✓ {node.name}: 100 units/week (strict, no overflow)")

            elif 'Distributor' in node.name:
                capacity = ProductionCapacity(
                    site_id=node.id,
                    product_id=item_id,
                    max_capacity_per_period=150.0,
                    current_capacity_used=0.0,
                    capacity_type='transfer',
                    capacity_period='week',
                    allow_overflow=False,
                    customer_id=2,
                    config_id=config.id
                )
                capacities.append(capacity)
                print(f"✓ {node.name}: 150 units/week (strict, no overflow)")

            elif 'Wholesaler' in node.name:
                capacity = ProductionCapacity(
                    site_id=node.id,
                    product_id=item_id,
                    max_capacity_per_period=200.0,
                    current_capacity_used=0.0,
                    capacity_type='transfer',
                    capacity_period='week',
                    allow_overflow=False,
                    customer_id=2,
                    config_id=config.id
                )
                capacities.append(capacity)
                print(f"✓ {node.name}: 200 units/week (strict, no overflow)")

        print()
        print(f"Total capacity constraints: {len(capacities)}")
        print()
        print("Behavior:")
        print("  - Orders within capacity: Fulfilled immediately")
        print("  - Orders exceeding capacity: Queued for next period")
        print("  - Partial fulfillment: Order split if partial capacity available")
        print()


async def example_2_flexible_capacity():
    """
    Example 2: Flexible Capacity with Overflow

    Scenario: Service-based supply chain with surge pricing
    - Warehouse: 300 units/week base, overflow @ 1.5x cost
    - Distribution Center: 400 units/week base, overflow @ 1.3x cost
    - Allows exceeding capacity with cost penalties
    """
    print("=" * 80)
    print("EXAMPLE 2: Flexible Capacity with Overflow")
    print("=" * 80)
    print()

    async with async_session_factory() as db:
        result = await db.execute(
            select(SupplyChainConfig).filter(
                SupplyChainConfig.name.like("%Default%")
            )
        )
        config = result.scalar_one_or_none()

        if not config:
            print("❌ No config found")
            return

        await db.refresh(config, ['nodes'])

        print(f"Supply Chain: {config.name}")
        print()

        capacities = []
        item_id = 2

        for node in config.nodes:
            if 'Distributor' in node.name:
                capacity = ProductionCapacity(
                    site_id=node.id,
                    product_id=item_id,
                    max_capacity_per_period=300.0,
                    current_capacity_used=0.0,
                    capacity_type='transfer',
                    capacity_period='week',
                    allow_overflow=True,  # Overflow allowed
                    overflow_cost_multiplier=1.5,  # 50% premium
                    customer_id=2,
                    config_id=config.id
                )
                capacities.append(capacity)
                print(f"✓ {node.name}: 300 units/week base, overflow @ 1.5x cost")

            elif 'Wholesaler' in node.name:
                capacity = ProductionCapacity(
                    site_id=node.id,
                    product_id=item_id,
                    max_capacity_per_period=400.0,
                    current_capacity_used=0.0,
                    capacity_type='transfer',
                    capacity_period='week',
                    allow_overflow=True,
                    overflow_cost_multiplier=1.3,  # 30% premium
                    customer_id=2,
                    config_id=config.id
                )
                capacities.append(capacity)
                print(f"✓ {node.name}: 400 units/week base, overflow @ 1.3x cost")

        print()
        print(f"Total capacity constraints: {len(capacities)}")
        print()
        print("Behavior:")
        print("  - Orders within capacity: Standard cost")
        print("  - Orders exceeding capacity: Fulfilled with premium pricing")
        print("  - Example: 450 unit order on 300 capacity = 1.5x cost")
        print()


async def example_3_product_specific_capacity():
    """
    Example 3: Product-Specific Capacity

    Scenario: Multi-product manufacturing with shared capacity
    - Product A: 60 units/week capacity
    - Product B: 40 units/week capacity
    - Different products have different capacity allocations
    """
    print("=" * 80)
    print("EXAMPLE 3: Product-Specific Capacity")
    print("=" * 80)
    print()

    async with async_session_factory() as db:
        result = await db.execute(
            select(SupplyChainConfig).filter(
                SupplyChainConfig.name.like("%Default%")
            )
        )
        config = result.scalar_one_or_none()

        if not config:
            print("❌ No config found")
            return

        await db.refresh(config, ['nodes'])

        print(f"Supply Chain: {config.name}")
        print()

        capacities = []

        # Find factory node
        factory = next((n for n in config.nodes if 'Factory' in n.name), None)

        if factory:
            # Product A capacity
            capacity_a = ProductionCapacity(
                site_id=factory.id,
                product_id=2,  # Product A
                max_capacity_per_period=60.0,
                current_capacity_used=0.0,
                capacity_type='production',
                capacity_period='week',
                allow_overflow=False,
                customer_id=2,
                config_id=config.id
            )
            capacities.append(capacity_a)
            print(f"✓ {factory.name} - Product A: 60 units/week")

            # Product B capacity
            capacity_b = ProductionCapacity(
                site_id=factory.id,
                product_id=3,  # Product B (would need to create this)
                max_capacity_per_period=40.0,
                current_capacity_used=0.0,
                capacity_type='production',
                capacity_period='week',
                allow_overflow=False,
                customer_id=2,
                config_id=config.id
            )
            capacities.append(capacity_b)
            print(f"✓ {factory.name} - Product B: 40 units/week")

        print()
        print(f"Total capacity constraints: {len(capacities)}")
        print()
        print("Behavior:")
        print("  - Each product has independent capacity allocation")
        print("  - Product A and Product B don't compete for capacity")
        print("  - Useful for multi-SKU manufacturing scenarios")
        print()


async def example_4_scenario_configuration():
    """
    Example 4: Creating a Scenario with Capacity Constraints

    Shows how to configure a scenario to use capacity constraints
    """
    print("=" * 80)
    print("EXAMPLE 4: Scenario Configuration with Capacity")
    print("=" * 80)
    print()

    async with async_session_factory() as db:
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
            return

        # Create scenario with capacity constraints enabled
        scenario = Scenario(
            name="Capacity Constrained Scenario",
            tenant_id=tenant.id,
            supply_chain_config_id=config.id,
            use_aws_sc_planning=True,
            max_rounds=10,
            start_date=date.today(),
            config={
                'use_capacity_constraints': True,  # Enable capacity constraints
                'capacity_reset_period': 1,  # Reset every round (weekly)
                'show_capacity_warnings': True  # Notify scenario_users of capacity issues
            }
        )

        print("Scenario Configuration:")
        print(f"  Name: {scenario.name}")
        print(f"  AWS SC Planning: {scenario.use_aws_sc_planning}")
        print(f"  Capacity Constraints: {scenario.config['use_capacity_constraints']}")
        print(f"  Capacity Reset Period: {scenario.config['capacity_reset_period']} rounds")
        print()

        print("Scenario config JSON:")
        print(f"  {scenario.config}")
        print()

        print("This scenario will:")
        print("  1. Check capacity limits when creating work orders")
        print("  2. Queue orders that exceed capacity")
        print("  3. Reset capacity counters every round (weekly)")
        print("  4. Warn scenario_users when capacity is exceeded")
        print()

        # Note: Don't actually create the scenario in this example
        print("(Scenario not created - this is just an example)")
        print()


async def main():
    """Main entry point"""
    print()
    print("=" * 80)
    print("CAPACITY CONSTRAINTS CONFIGURATION EXAMPLES")
    print("=" * 80)
    print()

    await example_1_strict_capacity()
    await example_2_flexible_capacity()
    await example_3_product_specific_capacity()
    await example_4_scenario_configuration()

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    print("Capacity Constraint Options:")
    print("  1. Strict Capacity: Hard limits, queue excess orders")
    print("  2. Flexible Capacity: Allow overflow with cost premiums")
    print("  3. Product-Specific: Different capacities per product")
    print("  4. Site-Wide: Single capacity for all products")
    print()
    print("Scenario Configuration:")
    print("  - Set use_capacity_constraints: true in scenario.config")
    print("  - Set capacity_reset_period: N (rounds between resets)")
    print("  - Create ProductionCapacity records for each constrained site")
    print()
    print("For more details, see:")
    print("  - AWS_SC_PHASE3_SPRINT2_COMPLETE.md")
    print("  - backend/scripts/test_capacity_constraints.py")
    print()


if __name__ == "__main__":
    asyncio.run(main())
