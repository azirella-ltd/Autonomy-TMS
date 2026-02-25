"""
Migrate existing AWS SC planning data to include customer_id

This script populates the customer_id field for all existing AWS SC planning records
by deriving it from the config_id (which links to supply_chain_configs.customer_id).

This migration is safe to run multiple times (idempotent).

Usage:
    docker compose exec backend python scripts/migrate_aws_sc_group_ids.py
"""

import asyncio
from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.supply_chain_config import SupplyChainConfig


async def migrate_group_ids():
    """Populate customer_id for all AWS SC planning tables"""

    async with SessionLocal() as db:
        print("=" * 80)
        print("AWS SC Multi-Tenancy Migration: Populating customer_id fields")
        print("=" * 80)
        print()

        # Tables that need customer_id populated (all have config_id)
        tables_with_config = [
            'forecast',
            'supply_plan',
            'product_bom',
            'production_process',
            'sourcing_rules',
            'inv_policy',
            'reservation',
            'outbound_order_line',
            'vendor_lead_time',
            'supply_planning_parameters',
            'vendor_product',
            'sourcing_schedule',
            'sourcing_schedule_details',
        ]

        # Tables that need both customer_id and config_id populated
        tables_without_config = [
            'inv_level',
            'trading_partner',
        ]

        # ================================================================
        # STEP 1: Update tables that already have config_id
        # ================================================================
        print("STEP 1: Updating tables with config_id...")
        print("-" * 80)

        for table_name in tables_with_config:
            print(f"\nProcessing {table_name}...")

            # Count records needing update
            count_query = text(f"""
                SELECT COUNT(*) as cnt
                FROM {table_name}
                WHERE config_id IS NOT NULL AND customer_id IS NULL
            """)
            result = await db.execute(count_query)
            count = result.scalar()

            if count == 0:
                print(f"  ✓ No records need updating")
                continue

            print(f"  Found {count} records to update")

            # Update customer_id from config
            update_query = text(f"""
                UPDATE {table_name} t
                INNER JOIN supply_chain_configs sc ON t.config_id = sc.id
                SET t.customer_id = sc.customer_id
                WHERE t.config_id IS NOT NULL
                  AND t.customer_id IS NULL
            """)

            await db.execute(update_query)
            await db.commit()

            # Verify
            verify_query = text(f"""
                SELECT COUNT(*) as cnt
                FROM {table_name}
                WHERE config_id IS NOT NULL AND customer_id IS NULL
            """)
            result = await db.execute(verify_query)
            remaining = result.scalar()

            if remaining == 0:
                print(f"  ✅ Successfully updated {count} records")
            else:
                print(f"  ⚠️  Warning: {remaining} records still have NULL customer_id")

        # ================================================================
        # STEP 2: Update inv_level (needs special handling)
        # ================================================================
        print("\n" + "=" * 80)
        print("STEP 2: Updating inv_level (special case)...")
        print("-" * 80)

        # inv_level doesn't have config_id, need to infer from product_id + site_id
        # For now, we'll skip this or use a default customer if there's ambiguity
        count_query = text("SELECT COUNT(*) as cnt FROM inv_level")
        result = await db.execute(count_query)
        total = result.scalar()
        print(f"  Found {total} total inv_level records")

        if total > 0:
            print("  ⚠️  inv_level migration requires manual handling")
            print("  Recommend: Set config_id/customer_id when creating new inv_level records")

        # ================================================================
        # STEP 3: Update trading_partner (needs special handling)
        # ================================================================
        print("\n" + "=" * 80)
        print("STEP 3: Updating trading_partner (special case)...")
        print("-" * 80)

        # trading_partner doesn't have config_id
        # Need to determine customer_id from related tables (vendor_product, sourcing_rules)
        count_query = text("SELECT COUNT(*) as cnt FROM trading_partner")
        result = await db.execute(count_query)
        total = result.scalar()
        print(f"  Found {total} total trading_partner records")

        if total > 0:
            print("  ⚠️  trading_partner migration requires manual handling")
            print("  Recommend: Set config_id/customer_id when creating new trading_partner records")

        # ================================================================
        # SUMMARY
        # ================================================================
        print("\n" + "=" * 80)
        print("Migration Summary")
        print("=" * 80)

        for table_name in tables_with_config:
            count_query = text(f"""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN customer_id IS NOT NULL THEN 1 ELSE 0 END) as with_group,
                    SUM(CASE WHEN customer_id IS NULL THEN 1 ELSE 0 END) as without_group
                FROM {table_name}
            """)
            result = await db.execute(count_query)
            row = result.fetchone()

            total, with_group, without_group = row[0], row[1] or 0, row[2] or 0

            if total > 0:
                pct = (with_group / total * 100) if total > 0 else 0
                status = "✅" if without_group == 0 else "⚠️"
                print(f"{status} {table_name:35} {with_group:5}/{total:5} ({pct:5.1f}%) have customer_id")

        print()
        print("=" * 80)
        print("✅ Migration Complete!")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(migrate_group_ids())
