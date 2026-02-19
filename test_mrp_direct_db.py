#!/usr/bin/env python3
"""
Direct database test - checks MRP logic without HTTP layer
"""

import sys
sys.path.insert(0, 'backend')

from app.db.session import SessionLocal
from app.models.mps import MPSPlan, MPSPlanItem
from app.models.sc_planning import ProductBom, SourcingRules, InvPolicy, InvLevel, Forecast
from sqlalchemy import select

def main():
    print("=" * 80)
    print("DIRECT DATABASE MRP READINESS CHECK")
    print("=" * 80)

    db = SessionLocal()

    try:
        # Check MPS Plan 2
        print("\n1. MPS Plan Status:")
        mps_plan = db.get(MPSPlan, 2)
        if not mps_plan:
            print("   ❌ MPS Plan 2 not found")
            return

        print(f"   ✅ MPS Plan Found: {mps_plan.name}")
        print(f"      Status: {mps_plan.status}")
        print(f"      Config ID: {mps_plan.supply_chain_config_id}")

        # Check MPS items
        items = db.execute(
            select(MPSPlanItem).where(MPSPlanItem.plan_id == 2)
        ).scalars().all()
        print(f"      MPS Items: {len(items)}")
        for item in items:
            print(f"         - Product {item.product_id} at Site {item.site_id}")

        # Check inventory levels
        print("\n2. Inventory Levels:")
        inv_levels = db.execute(
            select(InvLevel).where(InvLevel.config_id == 2)
        ).scalars().all()
        print(f"   Found {len(inv_levels)} inventory level records")
        if inv_levels:
            for inv in inv_levels[:3]:
                print(f"      - Product {inv.product_id} at Site {inv.site_id}: {inv.on_hand_quantity} units")

        # Check inventory policies
        print("\n3. Inventory Policies:")
        policies = db.execute(
            select(InvPolicy).where(InvPolicy.config_id == 2)
        ).scalars().all()
        print(f"   Found {len(policies)} inventory policy records")
        if policies:
            for policy in policies[:3]:
                print(f"      - Product {policy.product_id} at Site {policy.site_id}: {policy.policy_type}, ss_policy={policy.ss_policy}")

        # Check sourcing rules
        print("\n4. Sourcing Rules:")
        sourcing = db.execute(
            select(SourcingRules).where(SourcingRules.config_id == 2)
        ).scalars().all()
        print(f"   Found {len(sourcing)} sourcing rule records")
        if sourcing:
            for rule in sourcing[:3]:
                print(f"      - Product {rule.product_id}: Site {rule.site_id} <- Site {rule.supplier_site_id} ({rule.sourcing_rule_type})")

        # Check BOMs
        print("\n5. Bills of Materials:")
        boms = db.execute(
            select(ProductBom).where(ProductBom.config_id == 2)
        ).scalars().all()
        print(f"   Found {len(boms)} BOM records")

        # Check forecasts
        print("\n6. Forecasts:")
        forecasts = db.execute(
            select(Forecast).where(Forecast.config_id == 2)
        ).scalars().all()
        print(f"   Found {len(forecasts)} forecast records")
        if forecasts:
            print(f"      Sample: Product {forecasts[0].product_id} on {forecasts[0].forecast_date}: {forecasts[0].forecast_quantity} units")

        print("\n" + "=" * 80)
        print("READINESS CHECK COMPLETE")
        print("=" * 80)

        if len(inv_levels) > 0 and len(policies) > 0 and len(sourcing) > 0 and len(forecasts) > 0:
            print("✅ All required data present - MRP should work!")
        else:
            print("⚠️  Missing data - MRP may fail")

    finally:
        db.close()

if __name__ == "__main__":
    main()
