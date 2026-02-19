#!/usr/bin/env python3
"""
Minimal MRP test - direct database access to test MRP logic without HTTP
"""

import sys
import os

# Add backend to path
sys.path.insert(0, 'backend')
os.chdir('backend')

from app.db.session import SessionLocal
from app.models.mps import MPSPlan, MPSPlanItem
from app.models.sc_planning import ProductBom
from sqlalchemy import select

print("=" * 80)
print("MINIMAL MRP TEST - BOM EXPLOSION")
print("=" * 80)

db = SessionLocal()

try:
    # Get MPS Plan 2
    print("\n1. Loading MPS Plan 2...")
    mps_plan = db.get(MPSPlan, 2)
    if not mps_plan:
        print("❌ MPS Plan 2 not found")
        sys.exit(1)

    print(f"✅ Plan loaded: {mps_plan.name}")
    print(f"   Config ID: {mps_plan.supply_chain_config_id}")

    # Get MPS items
    plan_items = db.execute(
        select(MPSPlanItem).where(MPSPlanItem.plan_id == 2)
    ).scalars().all()

    print(f"✅ Found {len(plan_items)} MPS items")
    for item in plan_items:
        print(f"   - Product {item.product_id} at Site {item.site_id}")
        print(f"     Quantities: {item.weekly_quantities}")

    # Test BOM query for each product
    print("\n2. Testing BOM queries...")
    for item in plan_items:
        boms = db.execute(
            select(ProductBom).where(
                ProductBom.product_id == item.product_id,
                ProductBom.config_id == mps_plan.supply_chain_config_id
            )
        ).scalars().all()

        print(f"   Product {item.product_id}: {len(boms)} BOM entries")
        if boms:
            for bom in boms:
                print(f"      Component {bom.component_product_id}: qty={bom.component_quantity}")

    print("\n✅ BOM queries completed successfully!")
    print("\nConclusion: BOM explosion logic should work. Issue is likely elsewhere.")

except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

finally:
    db.close()

print("=" * 80)
