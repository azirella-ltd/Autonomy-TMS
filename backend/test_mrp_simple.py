#!/usr/bin/env python3
"""
Direct MRP test - check database state
"""

from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.mps import MPSPlan, MPSPlanItem
from app.models.mrp import MRPRun
from app.models.purchase_order import PurchaseOrder
from app.models.transfer_order import TransferOrder

def main():
    print("=" * 80)
    print("DATABASE STATE CHECK")
    print("=" * 80)

    db = SessionLocal()

    try:
        # Check MPS plan
        print("\n1. MPS Plan Status:")
        mps_plan = db.get(MPSPlan, 2)
        if mps_plan:
            print(f"   ✅ MPS Plan 2 found")
            print(f"      Name: {mps_plan.name}")
            print(f"      Status: {mps_plan.status}")
            print(f"      Config ID: {mps_plan.supply_chain_config_id}")
        else:
            print("   ❌ MPS Plan 2 not found")

        # Get MPS items
        items = db.execute(
            select(MPSPlanItem).where(MPSPlanItem.plan_id == 2)
        ).scalars().all()
        print(f"      Items: {len(items)}")

        # Check MRP runs
        print("\n2. MRP Runs:")
        mrp_runs = db.execute(
            select(MRPRun).order_by(MRPRun.created_at.desc()).limit(3)
        ).scalars().all()
        print(f"   Found {len(mrp_runs)} MRP runs")
        for run in mrp_runs:
            print(f"      - {run.run_id}: {run.status}")

        # Check POs
        print("\n3. Purchase Orders:")
        pos = db.execute(
            select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc()).limit(3)
        ).scalars().all()
        print(f"   Found {len(pos)} POs")
        for po in pos:
            print(f"      - {po.po_number}: {po.status}")
            print(f"         company_id={po.company_id}, order_type={po.order_type}")

        # Check TOs
        print("\n4. Transfer Orders:")
        tos = db.execute(
            select(TransferOrder).order_by(TransferOrder.created_at.desc()).limit(3)
        ).scalars().all()
        print(f"   Found {len(tos)} TOs")
        for to in tos:
            print(f"      - {to.to_number}: {to.status}")
            print(f"         company_id={to.company_id}, order_type={to.order_type}")

        print("\n" + "=" * 80)
        print("STATE CHECK COMPLETE")
        print("=" * 80)

    finally:
        db.close()

if __name__ == "__main__":
    main()
