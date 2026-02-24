#!/usr/bin/env python3
"""Verify vendor_product table schema and FK references"""

import asyncio
from sqlalchemy import inspect, text
from app.db.session import engine, SessionLocal


async def verify_schema():
    """Verify vendor_product and sourcing_rules schema"""

    async with engine.connect() as conn:
        # Check if vendor_product exists
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'vendor_product'"
        ))
        exists = result.scalar() > 0
        print(f"✓ vendor_product table exists: {exists}")

        if exists:
            # Get column info
            result = await conn.execute(text(
                "SELECT column_name, column_type, is_nullable, column_key "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'vendor_product' "
                "ORDER BY ordinal_position"
            ))
            print("\nvendor_product columns:")
            for row in result:
                nullable = "NULL" if row[2] == "YES" else "NOT NULL"
                key = f" ({row[3]})" if row[3] else ""
                print(f"  {row[0]:<25} {row[1]:<20} {nullable}{key}")

            # Get foreign keys
            result = await conn.execute(text(
                "SELECT constraint_name, column_name, referenced_table_name, referenced_column_name "
                "FROM information_schema.key_column_usage "
                "WHERE table_schema = 'public' AND table_name = 'vendor_product' "
                "AND referenced_table_name IS NOT NULL"
            ))
            print("\nvendor_product foreign keys:")
            for row in result:
                print(f"  {row[1]} -> {row[2]}.{row[3]} (constraint: {row[0]})")

        # Check sourcing_rules new columns
        result = await conn.execute(text(
            "SELECT column_name, column_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'sourcing_rules' "
            "AND column_name IN ('tpartner_id', 'transportation_lane_id', 'production_process_id')"
        ))
        print("\nsourcing_rules new FK columns:")
        for row in result:
            nullable = "NULL" if row[2] == "YES" else "NOT NULL"
            print(f"  {row[0]:<30} {row[1]:<20} {nullable}")

        # Get sourcing_rules foreign keys
        result = await conn.execute(text(
            "SELECT constraint_name, column_name, referenced_table_name, referenced_column_name "
            "FROM information_schema.key_column_usage "
            "WHERE table_schema = 'public' AND table_name = 'sourcing_rules' "
            "AND referenced_table_name IS NOT NULL "
            "AND column_name IN ('tpartner_id', 'transportation_lane_id', 'production_process_id')"
        ))
        print("\nsourcing_rules new foreign keys:")
        for row in result:
            print(f"  {row[1]} -> {row[2]}.{row[3]} (constraint: {row[0]})")


if __name__ == "__main__":
    asyncio.run(verify_schema())
