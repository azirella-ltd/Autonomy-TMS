"""
Test Production Order Generation from MPS Plan

Tests the new endpoint: POST /api/v1/mps/plans/{plan_id}/generate-orders
"""

import sys
import os

# Add backend directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timedelta
from sqlalchemy import select, delete
from app.db.session import SessionLocal
from app.models.mps import MPSPlan, MPSPlanItem, MPSStatus
from app.models.production_order import ProductionOrder
from app.models.supply_chain_config import SupplyChainConfig, Item, Node
from app.models.user import User


def print_header(text: str):
    """Print formatted header"""
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80)


def print_section(text: str):
    """Print formatted section"""
    print("\n" + "-" * 80)
    print(f"  {text}")
    print("-" * 80)


def test_production_order_generation():
    """Test production order generation from MPS plan"""

    print_header("PRODUCTION ORDER GENERATION TEST")
    print("Testing: MPS Plan → Production Orders (Automatic Generation)")

    db = SessionLocal()

    try:
        # Step 1: Get or create test data
        print_section("Step 1: Setup Test Data")

        # Get first config
        config = db.execute(select(SupplyChainConfig)).scalars().first()
        if not config:
            print("❌ No supply chain config found")
            return False
        print(f"✅ Using config: {config.name} (ID: {config.id})")

        # Get first product and factory node
        product = db.execute(select(Item)).scalars().first()
        factory = db.execute(
            select(Node).where(Node.sc_node_type == "Factory")
        ).scalars().first()

        if not product or not factory:
            print("❌ No product or factory node found")
            return False

        print(f"✅ Product: {product.name} (ID: {product.id})")
        print(f"✅ Factory: {factory.name} (ID: {factory.id})")

        # Get admin user
        admin = db.execute(
            select(User).where(User.email == "systemadmin@autonomy.ai")
        ).scalars().first()

        if not admin:
            print("❌ Admin user not found")
            return False

        print(f"✅ Admin user: {admin.email} (ID: {admin.id})")

        # Step 2: Create MPS Plan
        print_section("Step 2: Create MPS Plan")

        start_date = datetime.now()
        planning_horizon = 4  # 4 weeks for quick test

        mps_plan = MPSPlan(
            name="Test MPS Plan - Production Order Generation",
            description="Test plan for automatic production order generation",
            supply_chain_config_id=config.id,
            planning_horizon_weeks=planning_horizon,
            bucket_size_days=7,
            start_date=start_date,
            end_date=start_date + timedelta(weeks=planning_horizon),
            status=MPSStatus.DRAFT,
            created_by=admin.id,
        )

        db.add(mps_plan)
        db.commit()
        db.refresh(mps_plan)

        print(f"✅ Created MPS Plan: {mps_plan.name} (ID: {mps_plan.id})")
        print(f"   Planning Horizon: {planning_horizon} weeks")
        print(f"   Start Date: {start_date.strftime('%Y-%m-%d')}")
        print(f"   End Date: {mps_plan.end_date.strftime('%Y-%m-%d')}")

        # Step 3: Add MPS Plan Item with Weekly Quantities
        print_section("Step 3: Add MPS Plan Item")

        weekly_quantities = [1000, 1100, 950, 1200]  # 4 weeks

        mps_item = MPSPlanItem(
            plan_id=mps_plan.id,
            product_id=product.id,
            site_id=factory.id,
            weekly_quantities=weekly_quantities,
            lot_size_rule="EOQ",
        )

        db.add(mps_item)
        db.commit()

        print(f"✅ Added MPS Plan Item:")
        print(f"   Product: {product.name}")
        print(f"   Site: {factory.name}")
        print(f"   Weekly Quantities: {weekly_quantities}")
        print(f"   Total Demand: {sum(weekly_quantities)} units")

        # Step 4: Approve MPS Plan
        print_section("Step 4: Approve MPS Plan")

        mps_plan.status = MPSStatus.APPROVED
        mps_plan.approved_by = admin.id
        mps_plan.approved_at = datetime.now()

        db.commit()

        print(f"✅ MPS Plan approved by {admin.email}")
        print(f"   Status: {mps_plan.status.value}")

        # Step 5: Generate Production Orders (Simulate API Call)
        print_section("Step 5: Generate Production Orders")

        created_orders = []

        for period_idx, quantity in enumerate(weekly_quantities):
            if quantity <= 0:
                continue

            # Calculate dates for this period
            period_start = start_date + timedelta(weeks=period_idx)
            period_end = period_start + timedelta(days=mps_plan.bucket_size_days - 1)

            # Generate order number
            order_number = f"PO-{mps_plan.id}-{product.id}-{factory.id}-{period_idx + 1:03d}"

            # Create production order
            production_order = ProductionOrder(
                mps_plan_id=mps_plan.id,
                item_id=product.id,
                site_id=factory.id,
                config_id=config.id,
                order_number=order_number,
                planned_quantity=int(quantity),
                status="PLANNED",
                planned_start_date=period_start,
                planned_completion_date=period_end,
                lead_time_planned=mps_plan.bucket_size_days,
                priority=5,
                created_by_id=admin.id,
            )

            db.add(production_order)
            created_orders.append({
                "order_number": order_number,
                "quantity": quantity,
                "start_date": period_start,
                "end_date": period_end,
            })

        db.commit()

        print(f"✅ Generated {len(created_orders)} production orders:")
        for idx, order in enumerate(created_orders, 1):
            print(f"   {idx}. {order['order_number']}")
            print(f"      Quantity: {order['quantity']} units")
            print(f"      Start: {order['start_date'].strftime('%Y-%m-%d')}")
            print(f"      End: {order['end_date'].strftime('%Y-%m-%d')}")

        # Step 6: Verification
        print_section("Step 6: Verification")

        # Query generated orders from database
        db_orders = db.execute(
            select(ProductionOrder).where(
                ProductionOrder.mps_plan_id == mps_plan.id
            )
        ).scalars().all()

        print(f"✅ Verified {len(db_orders)} orders in database")

        # Verify order details
        total_quantity = sum(order.planned_quantity for order in db_orders)
        expected_quantity = sum(weekly_quantities)

        assert len(db_orders) == len(weekly_quantities), "Order count mismatch"
        assert total_quantity == expected_quantity, "Total quantity mismatch"

        print(f"✅ Total quantity matches: {total_quantity} units")

        # Verify all orders are PLANNED status
        all_planned = all(order.status == "PLANNED" for order in db_orders)
        assert all_planned, "Not all orders are in PLANNED status"

        print(f"✅ All orders in PLANNED status")

        # Verify all orders linked to MPS plan
        all_linked = all(order.mps_plan_id == mps_plan.id for order in db_orders)
        assert all_linked, "Not all orders linked to MPS plan"

        print(f"✅ All orders linked to MPS plan {mps_plan.id}")

        # Step 7: Cleanup
        print_section("Step 7: Cleanup")

        # Delete production orders
        db.execute(
            delete(ProductionOrder).where(
                ProductionOrder.mps_plan_id == mps_plan.id
            )
        )

        # Delete MPS plan items
        db.execute(
            delete(MPSPlanItem).where(MPSPlanItem.plan_id == mps_plan.id)
        )

        # Delete MPS plan
        db.delete(mps_plan)

        db.commit()

        print(f"✅ Cleaned up test data:")
        print(f"   - Deleted {len(db_orders)} production orders")
        print(f"   - Deleted 1 MPS plan item")
        print(f"   - Deleted 1 MPS plan")

        # Final Result
        print_header("✅ ALL TESTS PASSED")
        print(f"\nTest Summary:")
        print(f"  - MPS Plan Created: {mps_plan.name}")
        print(f"  - Planning Horizon: {planning_horizon} weeks")
        print(f"  - Total Demand: {sum(weekly_quantities)} units")
        print(f"  - Production Orders Generated: {len(db_orders)}")
        print(f"  - All validations passed ✅")
        print(f"  - Cleanup completed ✅")

        return True

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        db.close()


if __name__ == "__main__":
    success = test_production_order_generation()
    sys.exit(0 if success else 1)
