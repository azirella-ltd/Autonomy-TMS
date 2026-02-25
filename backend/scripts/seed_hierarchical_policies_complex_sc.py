"""
Seed Hierarchical Inventory Policies for Complex_SC

Demonstrates AWS SC 6-level hierarchical override logic:
1. product_id + site_id (most specific)
2. product_group_id + site_id
3. product_id + dest_geo_id
4. product_group_id + dest_geo_id
5. segment_id
6. company_id (company-wide default)
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.models.supply_chain_config import SupplyChainConfig, Node, Item
from app.models.aws_sc_planning import InvPolicy
from sqlalchemy import select, delete
from datetime import datetime


async def seed_hierarchical_policies():
    """Seed inventory policies with hierarchical override examples"""

    print("=" * 80)
    print("Seeding Hierarchical Inventory Policies for Complex_SC")
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
            select(Node).filter(Node.config_id == config_id)
        )
        nodes = list(nodes_result.scalars().all())

        items_result = await db.execute(
            select(Item).filter(Item.config_id == config_id)
        )
        items = list(items_result.scalars().all())

        print(f"✓ Loaded {len(nodes)} nodes and {len(items)} items")
        print()

        # Update nodes with hierarchical fields for demonstration
        print("Adding hierarchical identifiers to nodes...")
        for node in nodes[:3]:  # First 3 nodes
            node.geo_id = "1"  # North America
            node.segment_id = "PREMIUM"
            node.company_id = "ACME_CORP"
        for node in nodes[3:6]:  # Next 3 nodes
            node.geo_id = "2"  # Europe
            node.segment_id = "STANDARD"
            node.company_id = "ACME_CORP"
        await db.commit()
        print("✓ Updated node hierarchy fields")
        print()

        # Update items with product_group_id
        print("Adding product customers to items...")
        for idx, item in enumerate(items):
            item.product_group_id = (idx % 3) + 1  # Groups 1, 2, 3
        await db.commit()
        print("✓ Updated item product groups")
        print()

        # Clear existing policies
        print("Clearing existing inventory policies...")
        await db.execute(delete(InvPolicy).filter(InvPolicy.config_id == config_id))
        await db.commit()
        print("✓ Cleared existing policies")
        print()

        # Create hierarchical policy examples
        print("Creating hierarchical inventory policies...")
        print()

        policies = []
        relevant_nodes = [n for n in nodes if n.master_type in ['inventory', 'manufacturer', 'market_demand']]

        # Level 1: Product + Site specific policies (highest priority)
        print("Level 1: Product + Site specific policies")
        for item in items[:2]:  # First 2 items
            for node in relevant_nodes[:2]:  # First 2 nodes
                policy = InvPolicy(
                    product_id=item.id,
                    site_id=node.id,
                    policy_type='base_stock',
                    target_qty=150.0,
                    min_qty=30.0,
                    max_qty=250.0,
                    reorder_point=40.0,
                    order_qty=80.0,
                    review_period=7,
                    service_level=0.98,
                    holding_cost=1.5,
                    backlog_cost=15.0,
                    selling_price=60.0,
                    eff_start_date=datetime(2026, 1, 1),
                    eff_end_date=datetime(2099, 12, 31),
                    config_id=config_id
                )
                policies.append(policy)
                print(f"  ✓ Level 1: Product {item.id} @ Site {node.id}")

        print()

        # Level 2: Product Group + Site policies
        print("Level 2: Product Group + Site policies")
        for node in relevant_nodes[2:4]:  # Next 2 nodes
            policy = InvPolicy(
                product_group_id="1",  # Product group 1
                site_id=node.id,
                policy_type='base_stock',
                target_qty=120.0,
                min_qty=25.0,
                max_qty=220.0,
                reorder_point=35.0,
                order_qty=75.0,
                review_period=7,
                service_level=0.96,
                holding_cost=1.2,
                backlog_cost=12.0,
                selling_price=55.0,
                eff_start_date=datetime(2026, 1, 1),
                eff_end_date=datetime(2099, 12, 31),
                config_id=config_id
            )
            policies.append(policy)
            print(f"  ✓ Level 2: Product Group 1 @ Site {node.id}")

        print()

        # Level 3: Product + Geography policies
        print("Level 3: Product + Geography policies")
        for item in items[2:4]:  # Next 2 items
            policy = InvPolicy(
                product_id=item.id,
                dest_geo_id="1",  # North America
                policy_type='base_stock',
                target_qty=110.0,
                min_qty=22.0,
                max_qty=210.0,
                reorder_point=33.0,
                order_qty=72.0,
                review_period=7,
                service_level=0.95,
                holding_cost=1.1,
                backlog_cost=11.0,
                selling_price=52.0,
                eff_start_date=datetime(2026, 1, 1),
                eff_end_date=datetime(2099, 12, 31),
                config_id=config_id
            )
            policies.append(policy)
            print(f"  ✓ Level 3: Product {item.id} @ Geography 1 (North America)")

        print()

        # Level 4: Product Group + Geography policies
        print("Level 4: Product Group + Geography policies")
        policy = InvPolicy(
            product_group_id="2",  # Product group 2
            dest_geo_id="2",  # Europe
            policy_type='base_stock',
            target_qty=105.0,
            min_qty=21.0,
            max_qty=205.0,
            reorder_point=31.0,
            order_qty=71.0,
            review_period=7,
            service_level=0.94,
            holding_cost=1.05,
            backlog_cost=10.5,
            selling_price=51.0,
            eff_start_date=datetime(2026, 1, 1),
            eff_end_date=datetime(2099, 12, 31),
            config_id=config_id
        )
        policies.append(policy)
        print(f"  ✓ Level 4: Product Group 2 @ Geography 2 (Europe)")

        print()

        # Level 5: Segment-level policies
        print("Level 5: Segment-level policies")
        policy = InvPolicy(
            segment_id="PREMIUM",
            policy_type='base_stock',
            target_qty=130.0,
            min_qty=26.0,
            max_qty=230.0,
            reorder_point=36.0,
            order_qty=76.0,
            review_period=7,
            service_level=0.97,
            holding_cost=1.3,
            backlog_cost=13.0,
            selling_price=58.0,
            eff_start_date=datetime(2026, 1, 1),
            eff_end_date=datetime(2099, 12, 31),
            config_id=config_id
        )
        policies.append(policy)
        print(f"  ✓ Level 5: Segment PREMIUM")

        print()

        # Level 6: Company-wide default policy (lowest priority)
        print("Level 6: Company-wide default policy")
        policy = InvPolicy(
            company_id="ACME_CORP",
            policy_type='base_stock',
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
        print(f"  ✓ Level 6: Company ACME_CORP (default)")

        print()

        # Fill remaining product-site combinations with Level 1 policies
        print("Creating remaining product-site policies...")
        policy_count = len(policies)

        for item in items:
            for node in relevant_nodes:
                # Check if we already have a Level 1 policy for this combo
                has_policy = any(
                    p.product_id == item.id and p.site_id == node.id
                    for p in policies
                )
                if not has_policy:
                    policy = InvPolicy(
                        product_id=item.id,
                        site_id=node.id,
                        policy_type='base_stock',
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

        print(f"  ✓ Added {len(policies) - policy_count} default policies")
        print()

        # Insert all policies
        print("Inserting policies...")
        db.add_all(policies)
        await db.commit()
        print(f"✓ Created {len(policies)} total inventory policies")
        print()

        print("=" * 80)
        print("✅ Hierarchical Inventory Policy Seeding Complete")
        print("=" * 80)
        print()
        print("Policy Distribution:")
        print(f"  - Total policies: {len(policies)}")
        print(f"  - Level 1 (Product + Site): ~{len([p for p in policies if p.product_id and p.site_id])}")
        print(f"  - Level 2 (Product Group + Site): ~{len([p for p in policies if p.product_group_id and p.site_id])}")
        print(f"  - Level 3 (Product + Geography): ~{len([p for p in policies if p.product_id and p.dest_geo_id])}")
        print(f"  - Level 4 (Product Group + Geography): ~{len([p for p in policies if p.product_group_id and p.dest_geo_id])}")
        print(f"  - Level 5 (Segment): ~{len([p for p in policies if p.segment_id and not p.product_id])}")
        print(f"  - Level 6 (Company Default): ~{len([p for p in policies if p.company_id and not p.product_id and not p.segment_id])}")
        print()


if __name__ == "__main__":
    asyncio.run(seed_hierarchical_policies())
