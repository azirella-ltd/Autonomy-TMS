"""
Seed AWS SC Policy Types for Complex_SC

Demonstrates all 4 AWS SC standard safety stock policy types:
1. abs_level - Absolute safety stock quantity
2. doc_dem - Days of coverage based on actual demand
3. doc_fcst - Days of coverage based on forecast
4. sl - Service level with z-score calculation

Reference: https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/non-transactional.html
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.models.supply_chain_config import SupplyChainConfig, Site, Item
from app.models.aws_sc_planning import InvPolicy
from sqlalchemy import select, delete
from datetime import datetime


async def seed_policy_types():
    """Seed inventory policies with all 4 AWS SC policy types"""

    print("=" * 80)
    print("Seeding AWS SC Policy Types for Complex_SC")
    print("=" * 80)
    print()

    async with SessionLocal() as db:
        # Get Complex_SC configuration
        result = await db.execute(
            select(SupplyChainConfig).filter(
                SupplyChainConfig.name == "Complex_SC"
            )
        )
        config = result.scalar_one_or_none()

        if not config:
            print("❌ Complex_SC configuration not found")
            return

        config_id = config.id
        print(f"✓ Found Complex_SC (ID: {config_id})")
        print()

        # Get nodes and items
        nodes_result = await db.execute(
            select(Site).filter(Site.config_id == config_id)
        )
        nodes = list(nodes_result.scalars().all())

        items_result = await db.execute(
            select(Item).filter(Item.config_id == config_id)
        )
        items = list(items_result.scalars().all())

        print(f"✓ Loaded {len(nodes)} nodes and {len(items)} items")
        print()

        # Clear existing policies
        print("Clearing existing inventory policies...")
        await db.execute(delete(InvPolicy).filter(InvPolicy.config_id == config_id))
        await db.commit()
        print("✓ Cleared existing policies")
        print()

        # Create policy examples for each type
        print("Creating AWS SC policy type examples...")
        print()

        policies = []
        relevant_nodes = [n for n in nodes if n.master_type in ['inventory', 'manufacturer', 'customer']]

        # Policy Type 1: abs_level (Absolute Level)
        # Fixed safety stock quantity - simplest policy
        print("Policy Type 1: abs_level (Absolute Safety Stock)")
        print("  Use case: Stable products with known safety stock requirements")
        for item in items[:10]:  # First 10 items
            for node in relevant_nodes[:3]:  # First 3 nodes
                policy = InvPolicy(
                    product_id=item.id,
                    site_id=node.id,
                    policy_type='base_stock',

                    # AWS SC Policy Type fields
                    ss_policy='abs_level',
                    ss_quantity=50.0,  # Fixed 50 units safety stock

                    # Traditional fields (for backward compatibility)
                    target_qty=150.0,
                    min_qty=50.0,
                    max_qty=250.0,
                    reorder_point=50.0,  # Matches ss_quantity
                    order_qty=100.0,
                    review_period=7,
                    service_level=0.95,
                    holding_cost=1.0,
                    backlog_cost=10.0,
                    selling_price=50.0,
                    eff_start_date=datetime(2026, 1, 1),
                    eff_end_date=datetime(2099, 12, 31),
                    config_id=config_id
                )
                policies.append(policy)
        print(f"  ✓ Created {len(policies)} abs_level policies")
        print()

        # Policy Type 2: doc_dem (Days of Coverage - Demand)
        # Safety stock based on actual historical demand
        print("Policy Type 2: doc_dem (Days of Coverage - Demand)")
        print("  Use case: Products with stable demand patterns")
        start_count = len(policies)
        for item in items[10:20]:  # Next 10 items
            for node in relevant_nodes[3:6]:  # Next 3 nodes
                policy = InvPolicy(
                    product_id=item.id,
                    site_id=node.id,
                    policy_type='base_stock',

                    # AWS SC Policy Type fields
                    ss_policy='doc_dem',
                    ss_days=14,  # 14 days of demand coverage

                    # Traditional fields
                    target_qty=150.0,
                    min_qty=50.0,
                    max_qty=250.0,
                    review_period=7,
                    service_level=0.95,
                    holding_cost=1.0,
                    backlog_cost=10.0,
                    selling_price=50.0,
                    eff_start_date=datetime(2026, 1, 1),
                    eff_end_date=datetime(2099, 12, 31),
                    config_id=config_id
                )
                policies.append(policy)
        print(f"  ✓ Created {len(policies) - start_count} doc_dem policies")
        print()

        # Policy Type 3: doc_fcst (Days of Coverage - Forecast)
        # Safety stock based on forecast
        print("Policy Type 3: doc_fcst (Days of Coverage - Forecast)")
        print("  Use case: New products or products with changing demand")
        start_count = len(policies)
        for item in items[20:30]:  # Next 10 items
            for node in relevant_nodes[6:9]:  # Next 3 nodes
                policy = InvPolicy(
                    product_id=item.id,
                    site_id=node.id,
                    policy_type='base_stock',

                    # AWS SC Policy Type fields
                    ss_policy='doc_fcst',
                    ss_days=21,  # 21 days of forecast coverage

                    # Traditional fields
                    target_qty=150.0,
                    min_qty=50.0,
                    max_qty=250.0,
                    review_period=7,
                    service_level=0.95,
                    holding_cost=1.0,
                    backlog_cost=10.0,
                    selling_price=50.0,
                    eff_start_date=datetime(2026, 1, 1),
                    eff_end_date=datetime(2099, 12, 31),
                    config_id=config_id
                )
                policies.append(policy)
        print(f"  ✓ Created {len(policies) - start_count} doc_fcst policies")
        print()

        # Policy Type 4: sl (Service Level)
        # Probabilistic safety stock with z-score calculation
        print("Policy Type 4: sl (Service Level with z-score)")
        print("  Use case: High-value or critical products requiring specific service levels")
        start_count = len(policies)
        for item in items[30:40]:  # Next 10 items
            for node in relevant_nodes[9:12]:  # Next 3 nodes
                policy = InvPolicy(
                    product_id=item.id,
                    site_id=node.id,
                    policy_type='base_stock',

                    # AWS SC Policy Type fields
                    ss_policy='sl',
                    # No ss_days or ss_quantity - calculated from service_level

                    # Traditional fields
                    target_qty=150.0,
                    min_qty=50.0,
                    max_qty=250.0,
                    review_period=7,
                    service_level=0.98,  # 98% service level → z-score of 2.05
                    holding_cost=1.0,
                    backlog_cost=10.0,
                    selling_price=50.0,
                    eff_start_date=datetime(2026, 1, 1),
                    eff_end_date=datetime(2099, 12, 31),
                    config_id=config_id
                )
                policies.append(policy)
        print(f"  ✓ Created {len(policies) - start_count} sl policies")
        print()

        # Fill remaining with default abs_level policies
        print("Creating remaining policies with abs_level (default)...")
        default_count = 0
        for item in items:
            for node in relevant_nodes:
                # Check if we already have a policy for this combo
                has_policy = any(
                    p.product_id == item.id and p.site_id == node.id
                    for p in policies
                )
                if not has_policy:
                    policy = InvPolicy(
                        product_id=item.id,
                        site_id=node.id,
                        policy_type='base_stock',

                        # AWS SC Policy Type fields (default abs_level)
                        ss_policy='abs_level',
                        ss_quantity=30.0,  # Default 30 units

                        # Traditional fields
                        target_qty=100.0,
                        min_qty=20.0,
                        max_qty=200.0,
                        reorder_point=30.0,
                        order_qty=70.0,
                        review_period=7,
                        service_level=0.95,
                        holding_cost=1.0,
                        backlog_cost=10.0,
                        selling_price=50.0,
                        eff_start_date=datetime(2026, 1, 1),
                        eff_end_date=datetime(2099, 12, 31),
                        config_id=config_id
                    )
                    policies.append(policy)
                    default_count += 1

        print(f"  ✓ Added {default_count} default abs_level policies")
        print()

        # Insert all policies
        print("Inserting policies...")
        # Insert in batches to avoid parameter limits
        batch_size = 100
        for i in range(0, len(policies), batch_size):
            batch = policies[i:i+batch_size]
            db.add_all(batch)
            await db.commit()
            print(f"  Inserted {min(i+batch_size, len(policies))}/{len(policies)} policies...")

        print(f"✓ Created {len(policies)} total inventory policies")
        print()

        print("=" * 80)
        print("✅ AWS SC Policy Type Seeding Complete")
        print("=" * 80)
        print()
        print("Policy Type Distribution:")
        abs_level_count = len([p for p in policies if p.ss_policy == 'abs_level'])
        doc_dem_count = len([p for p in policies if p.ss_policy == 'doc_dem'])
        doc_fcst_count = len([p for p in policies if p.ss_policy == 'doc_fcst'])
        sl_count = len([p for p in policies if p.ss_policy == 'sl'])

        print(f"  - abs_level (Absolute):             {abs_level_count:4d} policies")
        print(f"  - doc_dem (Days of Demand):         {doc_dem_count:4d} policies")
        print(f"  - doc_fcst (Days of Forecast):      {doc_fcst_count:4d} policies")
        print(f"  - sl (Service Level):               {sl_count:4d} policies")
        print(f"  - Total:                            {len(policies):4d} policies")
        print()
        print("AWS SC Compliance: Policy types fully implemented! 🎉")
        print()


if __name__ == "__main__":
    asyncio.run(seed_policy_types())
