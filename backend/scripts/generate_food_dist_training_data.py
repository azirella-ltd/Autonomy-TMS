#!/usr/bin/env python3
"""
Generate synthetic TRM training data for Food Dist customer.

Usage:
    docker compose exec backend python scripts/generate_food_dist_training_data.py
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.db.session import async_session_factory
from app.models.supply_chain_config import SupplyChainConfig
from app.models.tenant import Tenant


async def generate_training_data():
    """Generate synthetic training data for Food Dist."""
    async with async_session_factory() as db:
        # Find Food Dist tenant and config
        result = await db.execute(
            select(Tenant).where(Tenant.name == "Food Dist")
        )
        tenant = result.scalar_one_or_none()

        if not tenant:
            print("ERROR: Food Dist tenant not found")
            return

        print(f"Found Food Dist tenant: id={tenant.id}")

        # Find supply chain config
        result = await db.execute(
            select(SupplyChainConfig).where(
                SupplyChainConfig.tenant_id == tenant.id
            )
        )
        config = result.scalar_one_or_none()

        if not config:
            print("ERROR: No supply chain config found for Food Dist")
            return

        print(f"Found config: id={config.id}, name={config.name}")

        # Import the synthetic data generator
        from app.services.powell.synthetic_trm_data_generator import generate_synthetic_trm_data

        print("\nGenerating synthetic training data...")
        print("  - 365 days of data")
        print("  - 50 orders per day, 20 TRM decisions per day")
        print("  - Generating: forecasts, inventory levels, orders, TRM decisions, outcomes, replay buffer")

        stats = await generate_synthetic_trm_data(
            db=db,
            config_id=config.id,
            tenant_id=tenant.id,
            num_days=365,
            num_orders_per_day=50,
            num_decisions_per_day=20,
            seed=42  # For reproducibility
        )

        print("\n" + "="*60)
        print("TRAINING DATA GENERATION COMPLETE")
        print("="*60)
        print(f"\nTransactional Data:")
        print(f"  Forecasts created: {stats.get('forecasts_created', 0)}")
        print(f"  Inventory snapshots: {stats.get('inventory_snapshots', 0)}")
        print(f"  Orders created: {stats.get('orders_created', 0)}")

        print(f"\nTRM Decisions:")
        print(f"  ATP decisions: {stats.get('atp_decisions', 0)}")
        print(f"  Rebalancing decisions: {stats.get('rebalancing_decisions', 0)}")
        print(f"  PO decisions: {stats.get('po_decisions', 0)}")
        print(f"  Order tracking decisions: {stats.get('order_tracking_decisions', 0)}")

        print(f"\nReplay Buffer:")
        print(f"  Total entries: {stats.get('replay_buffer_entries', 0)}")

        return stats


if __name__ == "__main__":
    print("="*60)
    print("FOOD DIST SYNTHETIC TRAINING DATA GENERATOR")
    print("="*60)
    asyncio.run(generate_training_data())
