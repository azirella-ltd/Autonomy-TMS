"""
Seed Default Inventory Policies for Complex_SC

Creates default base_stock inventory policies for all product-site combinations.
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


async def seed_inv_policies():
    """Seed default inventory policies"""

    print("=" * 80)
    print("Seeding Default Inventory Policies for Complex_SC")
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

        # Get all nodes and items
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

        # Clear existing policies for this config
        print("Clearing existing inventory policies...")
        await db.execute(delete(InvPolicy).filter(InvPolicy.config_id == config_id))
        await db.commit()
        print("✓ Cleared existing policies")
        print()

        # Create default policies for all product-site combinations
        # where the site is inventory or manufacturer type
        print("Creating default inventory policies...")

        policy_count = 0
        relevant_nodes = [n for n in nodes if n.master_type in ['inventory', 'manufacturer', 'customer']]

        # Create policies in batches of 100 to avoid parameter limit
        batch_size = 100
        batch = []

        for item in items:
            for node in relevant_nodes:
                # Default base_stock policy with reasonable values
                policy = InvPolicy(
                    product_id=item.id,
                    site_id=node.id,
                    policy_type='base_stock',
                    target_qty=100.0,  # Target 100 units
                    min_qty=20.0,      # Min 20 units
                    max_qty=200.0,     # Max 200 units
                    reorder_point=30.0, # Reorder at 30
                    order_qty=70.0,    # Order 70 units
                    review_period=7,   # Weekly review
                    service_level=0.95, # 95% service level
                    holding_cost=1.0,  # $1/unit/period holding
                    backlog_cost=10.0, # $10/unit/period backlog
                    selling_price=50.0, # $50/unit selling price
                    eff_start_date=datetime(2026, 1, 1),  # Explicit date
                    eff_end_date=datetime(2099, 12, 31),  # Far future
                    config_id=config_id
                )
                batch.append(policy)
                policy_count += 1

                if len(batch) >= batch_size:
                    db.add_all(batch)
                    await db.commit()
                    print(f"  Inserted {policy_count} policies...")
                    batch = []

        # Insert remaining policies
        if batch:
            db.add_all(batch)
            await db.commit()

        print(f"✓ Created {policy_count} default inventory policies")
        print()

        print("=" * 80)
        print("✅ Inventory Policy Seeding Complete")
        print("=" * 80)
        print()
        print(f"Created policies for {len(items)} products × {len(relevant_nodes)} sites")
        print()


if __name__ == "__main__":
    asyncio.run(seed_inv_policies())
