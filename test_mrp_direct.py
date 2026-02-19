#!/usr/bin/env python3
"""
Direct MRP test - bypasses web auth by using database directly
"""

import sys
sys.path.insert(0, '/app')  # For Docker container path

from datetime import datetime
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.models.mps import MPSPlan, MPSPlanItem
from app.models.mrp import MRPRun
from app.models.purchase_order import PurchaseOrder
from app.models.transfer_order import TransferOrder
from app.core.config import settings

def main():
    print("=" * 80)
    print("DIRECT MRP TEST (Database Connection)")
    print("=" * 80)

    # Create database connection
    DATABASE_URL = f"postgresql+psycopg2://{settings.MARIADB_USER}:{settings.MARIADB_PASSWORD}@{settings.MARIADB_HOST}:{settings.MARIADB_PORT}/{settings.MARIADB_DATABASE}"
    engine = create_engine(DATABASE_URL)

    print(f"\nConnecting to database...")
    print(f"Host: {settings.MARIADB_HOST}")
    print(f"Database: {settings.MARIADB_DATABASE}")

    with Session(engine) as db:
        # Check MPS plan
        print("\n" + "=" * 80)
        print("STEP 1: Check MPS Plan Status")
        print("=" * 80)

        mps_plan = db.get(MPSPlan, 2)
        if not mps_plan:
            print("❌ MPS Plan 2 not found")
            return

        print(f"✅ MPS Plan Found:")
        print(f"   ID: {mps_plan.id}")
        print(f"   Name: {mps_plan.name}")
        print(f"   Status: {mps_plan.status}")
        print(f"   Config ID: {mps_plan.supply_chain_config_id}")
        print(f"   Horizon: {mps_plan.planning_horizon_weeks} weeks")

        # Get MPS items
        items = db.execute(
            select(MPSPlanItem).where(MPSPlanItem.plan_id == 2)
        ).scalars().all()

        print(f"   Items: {len(items)}")
        for item in items:
            print(f"      - Product {item.product_id} at Site {item.site_id}: {item.weekly_quantities}")

        # Check existing MRP runs
        print("\n" + "=" * 80)
        print("STEP 2: Check Existing MRP Runs")
        print("=" * 80)

        mrp_runs = db.execute(
            select(MRPRun).order_by(MRPRun.created_at.desc()).limit(5)
        ).scalars().all()

        print(f"Found {len(mrp_runs)} MRP runs")
        for run in mrp_runs:
            print(f"   - Run {run.run_id}: {run.status} ({run.created_at})")

        # Check existing POs
        print("\n" + "=" * 80)
        print("STEP 3: Check Existing Purchase Orders")
        print("=" * 80)

        pos = db.execute(
            select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc()).limit(5)
        ).scalars().all()

        print(f"Found {len(pos)} purchase orders")
        for po in pos:
            print(f"   - PO {po.po_number}: {po.status}")
            print(f"      AWS SC Fields: company_id={po.company_id}, order_type={po.order_type}")

        # Check existing TOs
        print("\n" + "=" * 80)
        print("STEP 4: Check Existing Transfer Orders")
        print("=" * 80)

        tos = db.execute(
            select(TransferOrder).order_by(TransferOrder.created_at.desc()).limit(5)
        ).scalars().all()

        print(f"Found {len(tos)} transfer orders")
        for to in tos:
            print(f"   - TO {to.to_number}: {to.status}")
            print(f"      AWS SC Fields: company_id={to.company_id}, order_type={to.order_type}")

        print("\n" + "=" * 80)
        print("TEST COMPLETED")
        print("=" * 80)
        print("\nNext Steps:")
        print("1. MRP endpoint needs proper authentication fix")
        print("2. Once auth is fixed, run: POST /api/mrp/run with mps_plan_id=2")
        print("3. This will generate POs and TOs with AWS SC compliance fields")

if __name__ == "__main__":
    main()
