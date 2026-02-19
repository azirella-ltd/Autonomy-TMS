#!/usr/bin/env python3
"""
Flag key materials in BOM data.

This script identifies and flags key materials in the product_bom table.
Key materials are critical components that require planning at the MPS level:
- Long lead time items (>4 weeks / 28 days)
- Bottleneck/constrained resources
- High-value components
- Strategic materials with limited suppliers
"""

import sys
from pathlib import Path

# Add backend to Python path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
import os

# Database connection
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+psycopg2://autonomy_user:change-me-user@db:5432/autonomy')
engine = create_engine(DATABASE_URL)


def list_bom_entries():
    """List all BOM entries with current key material flags."""
    with Session(engine) as db:
        query = text("""
            SELECT
                pb.id,
                parent.name as parent_product,
                component.name as component_product,
                pb.component_quantity,
                pb.scrap_percentage,
                pb.is_key_material
            FROM product_bom pb
            JOIN items parent ON pb.parent_product_id = parent.id
            JOIN items component ON pb.component_product_id = component.id
            ORDER BY parent.name, component.name
        """)

        result = db.execute(query).fetchall()
        print(f"\nTotal BOM entries: {len(result)}\n")

        if not result:
            print("No BOM entries found in database.")
            return []

        for row in result:
            bom_id, parent, component, qty, scrap, is_key = row
            print(f"ID {bom_id}: {parent} -> {component} (qty: {qty}, scrap: {scrap}%, key: {is_key})")

        return result


def flag_key_materials_by_criteria():
    """
    Flag key materials based on common criteria:
    1. Long lead time (>28 days)
    2. Strategic bottleneck components
    3. High-value components
    """
    with Session(engine) as db:
        # Strategy 1: Flag components with long lead times (>28 days)
        query_long_lead_time = text("""
            UPDATE product_bom pb
            SET is_key_material = 'true'
            WHERE pb.component_product_id IN (
                SELECT vlt.product_id
                FROM vendor_lead_times vlt
                WHERE vlt.lead_time_days > 28
            )
        """)

        result1 = db.execute(query_long_lead_time)
        print(f"\nFlagged {result1.rowcount} components with long lead times (>28 days)")

        # Strategy 2: Flag components that appear in multiple BOMs (critical shared components)
        # These are often bottleneck materials
        query_shared_components = text("""
            UPDATE product_bom pb1
            SET is_key_material = 'true'
            WHERE pb1.component_product_id IN (
                SELECT pb2.component_product_id
                FROM product_bom pb2
                GROUP BY pb2.component_product_id
                HAVING COUNT(DISTINCT pb2.parent_product_id) >= 2
            )
        """)

        result2 = db.execute(query_shared_components)
        print(f"Flagged {result2.rowcount} shared components (used in 2+ products)")

        db.commit()
        print("\nKey material flagging complete!")


def flag_specific_materials(component_names: list):
    """Flag specific materials by component name."""
    with Session(engine) as db:
        for component_name in component_names:
            query = text("""
                UPDATE product_bom pb
                SET is_key_material = 'true'
                WHERE pb.component_product_id IN (
                    SELECT id FROM items WHERE name = :component_name
                )
            """)
            result = db.execute(query, {"component_name": component_name})
            print(f"Flagged {result.rowcount} BOM entries for component '{component_name}'")

        db.commit()
        print("\nManual flagging complete!")


def main():
    print("=" * 80)
    print("MPS Key Material Flagging Script")
    print("=" * 80)

    # Step 1: List current BOM entries
    print("\n[1] Current BOM Entries:")
    bom_entries = list_bom_entries()

    if not bom_entries:
        print("\nNo BOM data found. Please ensure BOM data is loaded.")
        return

    # Step 2: Flag key materials automatically
    print("\n[2] Auto-flagging key materials:")
    flag_key_materials_by_criteria()

    # Step 3: Show updated entries
    print("\n[3] Updated BOM Entries:")
    list_bom_entries()

    print("\n" + "=" * 80)
    print("Key Material Flagging Complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
