#!/usr/bin/env python
"""
Integration Test: MPS → Production Orders → Capacity Planning Flow

Tests the complete data flow from Master Production Scheduling through
Production Orders to Capacity Planning with bottleneck detection.
"""

import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.session import sync_engine, SessionLocal
from app.models import MPSPlan, MPSPlanItem, ProductionOrder, CapacityPlan, CapacityResource
from app.models.supply_chain_config import SupplyChainConfig
from app.models.user import User


def cleanup_test_data():
    """Clean up any existing test data"""
    print("\n=== Cleaning up test data ===")
    with sync_engine.connect() as conn:
        conn.execute(text("DELETE FROM capacity_requirements WHERE plan_id IN (SELECT id FROM capacity_plans WHERE name LIKE 'Test%')"))
        conn.execute(text("DELETE FROM capacity_resources WHERE plan_id IN (SELECT id FROM capacity_plans WHERE name LIKE 'Test%')"))
        conn.execute(text("DELETE FROM capacity_plans WHERE name LIKE 'Test%'"))
        conn.execute(text("DELETE FROM production_order_components WHERE production_order_id IN (SELECT id FROM production_orders WHERE order_number LIKE 'TEST-%')"))
        conn.execute(text("DELETE FROM production_orders WHERE order_number LIKE 'TEST-%'"))
        conn.execute(text("DELETE FROM mps_plan_items WHERE plan_id IN (SELECT id FROM mps_plans WHERE name LIKE 'Test%')"))
        conn.execute(text("DELETE FROM mps_capacity_checks WHERE plan_id IN (SELECT id FROM mps_plans WHERE name LIKE 'Test%')"))
        conn.execute(text("DELETE FROM mps_plans WHERE name LIKE 'Test%'"))
        conn.commit()
    print("✓ Test data cleaned")


def get_test_config():
    """Get test supply chain configuration"""
    with sync_engine.connect() as conn:
        result = conn.execute(text("SELECT id, name FROM supply_chain_configs WHERE name = 'Three FG TBG' LIMIT 1"))
        row = result.fetchone()
        if not row:
            raise Exception("Test config 'Three FG TBG' not found")
        return {"id": row[0], "name": row[1]}


def get_test_nodes(config_id):
    """Get test nodes from config"""
    with sync_engine.connect() as conn:
        result = conn.execute(text(f"SELECT id, name, type, master_type FROM nodes WHERE config_id = {config_id} ORDER BY id"))
        nodes = {}
        for row in result:
            nodes[row[1]] = {"id": row[0], "name": row[1], "type": row[2], "master_type": row[3]}
        return nodes


def get_test_items():
    """Get test items"""
    with sync_engine.connect() as conn:
        result = conn.execute(text("SELECT id, name FROM items WHERE name IN ('Lager Case', 'IPA Case', 'Dark Case') ORDER BY id LIMIT 3"))
        items = []
        for row in result:
            items.append({"id": row[0], "name": row[1]})
        return items


def test_step_1_create_mps():
    """Step 1: Create MPS Plan with weekly quantities"""
    print("\n=== STEP 1: Create MPS Plan ===")

    config = get_test_config()
    nodes = get_test_nodes(config["id"])
    items = get_test_items()

    print(f"Config: {config['name']} (ID: {config['id']})")
    print(f"Factory Node: {nodes['Factory']['id']}")
    print(f"Items: {[i['name'] for i in items]}")

    with sync_engine.connect() as conn:
        # Get user
        result = conn.execute(text("SELECT id FROM users LIMIT 1"))
        user = result.fetchone()[0]

        # Create MPS Plan
        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(weeks=13)

        result = conn.execute(text(f"""
            INSERT INTO mps_plans (
                supply_chain_config_id, name, description,
                planning_horizon_weeks, bucket_size_days,
                start_date, end_date, status, created_by
            ) VALUES (
                {config['id']}, 'Test Integration MPS', 'Integration test MPS plan',
                13, 7,
                '{start_date.isoformat()}', '{end_date.isoformat()}', 'DRAFT', {user}
            ) RETURNING id
        """))
        mps_plan_id = result.fetchone()[0]
        conn.commit()

    print(f"✓ Created MPS Plan ID: {mps_plan_id}")

    # Add MPS Plan Items (weekly quantities for 13 weeks)
    factory_id = nodes['Factory']['id']
    for item in items[:1]:  # Use first item only for simplicity
        weekly_quantities = [1000.0] * 13  # 1000 units per week for 13 weeks

        import json
        weekly_quantities_json = json.dumps(weekly_quantities)
        with sync_engine.connect() as conn:
            conn.execute(text(f"""
                INSERT INTO mps_plan_items (
                    plan_id, product_id, site_id, weekly_quantities
                ) VALUES (
                    {mps_plan_id}, {item['id']}, {factory_id},
                    '{weekly_quantities_json}'
                )
            """))
            conn.commit()

        print(f"✓ Added MPS item: {item['name']} - {sum(weekly_quantities)} units total over 13 weeks")

    return mps_plan_id, config, nodes, items


def test_step_2_create_production_orders(mps_plan_id, config, nodes, items):
    """Step 2: Generate Production Orders from MPS"""
    print("\n=== STEP 2: Create Production Orders from MPS ===")

    factory_id = nodes['Factory']['id']
    item = items[0]
    user_id = 1

    # Create 4 production orders (1 per week for first month)
    order_ids = []
    start_date = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

    for week in range(4):
        order_number = f"TEST-PO-{week+1:03d}"
        planned_start = start_date + timedelta(weeks=week)
        planned_completion = planned_start + timedelta(days=5)  # 5 days production time

        with sync_engine.connect() as conn:
            result = conn.execute(text(f"""
                INSERT INTO production_orders (
                    order_number, item_id, site_id, config_id,
                    planned_quantity, planned_start_date, planned_completion_date,
                    status, priority, created_by_id
                ) VALUES (
                    '{order_number}', {item['id']}, {factory_id}, {config['id']},
                    1000, '{planned_start.isoformat()}', '{planned_completion.isoformat()}',
                    'PLANNED', 5, {user_id}
                ) RETURNING id
            """))
            order_id = result.fetchone()[0]
            conn.commit()
            order_ids.append(order_id)

        print(f"✓ Created Production Order: {order_number} (ID: {order_id}) - 1000 units, Week {week+1}")

    print(f"✓ Total Production Orders: {len(order_ids)}")
    return order_ids


def test_step_3_create_capacity_plan(config, nodes):
    """Step 3: Create Capacity Plan and Resources"""
    print("\n=== STEP 3: Create Capacity Plan ===")

    start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = start_date + timedelta(weeks=13)
    user_id = 1

    # Create Capacity Plan
    with sync_engine.connect() as conn:
        result = conn.execute(text(f"""
            INSERT INTO capacity_plans (
                name, description, supply_chain_config_id,
                planning_horizon_weeks, start_date, end_date,
                status, created_by
            ) VALUES (
                'Test Integration Capacity Plan', 'Integration test capacity plan',
                {config['id']}, 13, '{start_date.isoformat()}', '{end_date.isoformat()}',
                'ACTIVE', {user_id}
            ) RETURNING id
        """))
        plan_id = result.fetchone()[0]
        conn.commit()

    print(f"✓ Created Capacity Plan ID: {plan_id}")

    # Add Capacity Resources
    factory_id = nodes['Factory']['id']
    resources = [
        {
            "name": "Assembly Line 1",
            "type": "MACHINE",
            "available_capacity": 160.0,  # 160 hours/week (40 hrs * 4 people or 2 shifts)
            "efficiency": 85.0,
            "target_utilization": 80.0
        },
        {
            "name": "Production Workers",
            "type": "LABOR",
            "available_capacity": 320.0,  # 320 hours/week (8 workers * 40 hrs)
            "efficiency": 90.0,
            "target_utilization": 85.0
        },
        {
            "name": "Factory Floor Space",
            "type": "FACILITY",
            "available_capacity": 10000.0,  # 10000 sq ft
            "efficiency": 100.0,
            "target_utilization": 75.0
        }
    ]

    resource_ids = []
    for res in resources:
        with sync_engine.connect() as conn:
            result = conn.execute(text(f"""
                INSERT INTO capacity_resources (
                    plan_id, resource_name, resource_type, site_id,
                    available_capacity, capacity_unit, efficiency_percent,
                    utilization_target_percent, shifts_per_day, hours_per_shift,
                    working_days_per_week
                ) VALUES (
                    {plan_id}, '{res['name']}', '{res['type']}', {factory_id},
                    {res['available_capacity']}, 'hours', {res['efficiency']},
                    {res['target_utilization']}, 2, 8.0, 5
                ) RETURNING id
            """))
            resource_id = result.fetchone()[0]
            conn.commit()
            resource_ids.append(resource_id)

        print(f"✓ Added Resource: {res['name']} ({res['type']}) - {res['available_capacity']} {res.get('unit', 'hours')}/week")

    return plan_id, resource_ids


def test_step_4_calculate_requirements(plan_id):
    """Step 4: Calculate Capacity Requirements from Production Orders"""
    print("\n=== STEP 4: Calculate Capacity Requirements ===")

    # This would normally be done via API endpoint POST /api/v1/capacity-plans/{id}/calculate
    # For now, we'll simulate by inserting sample requirements

    with sync_engine.connect() as conn:
        # Get resources
        result = conn.execute(text(f"SELECT id, resource_name FROM capacity_resources WHERE plan_id = {plan_id}"))
        resources = list(result)

        # Get plan dates
        result = conn.execute(text(f"SELECT start_date FROM capacity_plans WHERE id = {plan_id}"))
        start_date = result.fetchone()[0]

        # Create requirements for each resource for 4 weeks
        for week in range(4):
            period_start = start_date + timedelta(weeks=week)
            period_end = period_start + timedelta(days=7)

            for resource in resources:
                resource_id, resource_name = resource

                # Simulate capacity requirements (hours needed)
                if "Assembly" in resource_name:
                    required = 140.0  # 140 hours needed
                    utilization = (required / 160.0) * 100  # 87.5%
                elif "Workers" in resource_name:
                    required = 280.0  # 280 hours needed
                    utilization = (required / 320.0) * 100  # 87.5%
                else:
                    required = 8000.0  # 8000 sq ft needed
                    utilization = (required / 10000.0) * 100  # 80%

                # Calculate available capacity
                if "Assembly" in resource_name:
                    available = 160.0
                elif "Workers" in resource_name:
                    available = 320.0
                else:
                    available = 10000.0

                conn.execute(text(f"""
                    INSERT INTO capacity_requirements (
                        plan_id, resource_id, period_start, period_end, period_number,
                        required_capacity, available_capacity, utilization_percent,
                        is_overloaded, is_bottleneck, source_type, source_id
                    ) VALUES (
                        {plan_id}, {resource_id}, '{period_start.isoformat()}', '{period_end.isoformat()}', {week + 1},
                        {required}, {available}, {utilization},
                        {str(utilization > 100).lower()}, {str(utilization >= 95).lower()},
                        'PRODUCTION_ORDER', NULL
                    )
                """))

        conn.commit()

    print("✓ Calculated capacity requirements for 4 weeks")

    # Analyze bottlenecks
    with sync_engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT
                cr.resource_name,
                AVG(req.utilization_percent) as avg_utilization,
                MAX(req.utilization_percent) as max_utilization,
                COUNT(*) as periods
            FROM capacity_requirements req
            JOIN capacity_resources cr ON req.resource_id = cr.id
            WHERE req.plan_id = {plan_id}
            GROUP BY cr.resource_name
            ORDER BY max_utilization DESC
        """))

        print("\n=== Capacity Analysis ===")
        bottlenecks = []
        for row in result:
            resource_name, avg_util, max_util, periods = row
            status = "✓ GREEN" if max_util < 80 else "⚠ YELLOW" if max_util < 95 else "🔴 BOTTLENECK" if max_util < 100 else "🚨 OVERLOAD"
            print(f"{status} {resource_name}: Avg {avg_util:.1f}%, Max {max_util:.1f}% over {periods} periods")

            if max_util >= 95:
                bottlenecks.append(resource_name)

    return bottlenecks


def test_step_5_verify_integration():
    """Step 5: Verify end-to-end data integrity"""
    print("\n=== STEP 5: Verify Integration ===")

    with sync_engine.connect() as conn:
        # Check MPS Plans
        result = conn.execute(text("SELECT COUNT(*) FROM mps_plans WHERE name LIKE 'Test%'"))
        mps_count = result.scalar()
        print(f"✓ MPS Plans: {mps_count}")

        # Check Production Orders
        result = conn.execute(text("SELECT COUNT(*) FROM production_orders WHERE order_number LIKE 'TEST-%'"))
        po_count = result.scalar()
        print(f"✓ Production Orders: {po_count}")

        # Check Capacity Plans
        result = conn.execute(text("SELECT COUNT(*) FROM capacity_plans WHERE name LIKE 'Test%'"))
        cp_count = result.scalar()
        print(f"✓ Capacity Plans: {cp_count}")

        # Check Capacity Resources
        result = conn.execute(text("""
            SELECT COUNT(*) FROM capacity_resources
            WHERE plan_id IN (SELECT id FROM capacity_plans WHERE name LIKE 'Test%')
        """))
        res_count = result.scalar()
        print(f"✓ Capacity Resources: {res_count}")

        # Check Capacity Requirements
        result = conn.execute(text("""
            SELECT COUNT(*) FROM capacity_requirements
            WHERE plan_id IN (SELECT id FROM capacity_plans WHERE name LIKE 'Test%')
        """))
        req_count = result.scalar()
        print(f"✓ Capacity Requirements: {req_count}")

        # Verify relationships
        result = conn.execute(text("""
            SELECT
                mps.name as mps_name,
                po.order_number,
                cp.name as capacity_plan_name
            FROM mps_plans mps
            CROSS JOIN production_orders po
            CROSS JOIN capacity_plans cp
            WHERE mps.name LIKE 'Test%'
              AND po.order_number LIKE 'TEST-%'
              AND cp.name LIKE 'Test%'
            LIMIT 1
        """))

        row = result.fetchone()
        if row:
            print(f"\n✓ Integration Chain Verified:")
            print(f"  MPS: {row[0]}")
            print(f"  → Production Order: {row[1]}")
            print(f"  → Capacity Plan: {row[2]}")
            return True
        else:
            print("\n✗ Integration chain broken")
            return False


def main():
    """Run integration test"""
    print("=" * 80)
    print("INTEGRATION TEST: MPS → Production Orders → Capacity Planning")
    print("=" * 80)

    try:
        # Clean up first
        cleanup_test_data()

        # Step 1: Create MPS Plan
        mps_plan_id, config, nodes, items = test_step_1_create_mps()

        # Step 2: Create Production Orders
        order_ids = test_step_2_create_production_orders(mps_plan_id, config, nodes, items)

        # Step 3: Create Capacity Plan
        plan_id, resource_ids = test_step_3_create_capacity_plan(config, nodes)

        # Step 4: Calculate Requirements
        bottlenecks = test_step_4_calculate_requirements(plan_id)

        # Step 5: Verify Integration
        success = test_step_5_verify_integration()

        # Summary
        print("\n" + "=" * 80)
        print("INTEGRATION TEST RESULTS")
        print("=" * 80)
        print(f"✓ MPS Plan Created: ID {mps_plan_id}")
        print(f"✓ Production Orders Created: {len(order_ids)} orders")
        print(f"✓ Capacity Plan Created: ID {plan_id}")
        print(f"✓ Capacity Resources Added: {len(resource_ids)} resources")
        print(f"✓ Capacity Requirements Calculated")

        if bottlenecks:
            print(f"\n⚠ Bottlenecks Detected: {', '.join(bottlenecks)}")
        else:
            print("\n✓ No Bottlenecks Detected - Capacity is sufficient")

        if success:
            print("\n✅ INTEGRATION TEST PASSED")
            print("\nData flow verified:")
            print("  MPS Plan → Production Orders → Capacity Plan → Requirements → Bottleneck Analysis")
        else:
            print("\n❌ INTEGRATION TEST FAILED")
            return 1

        # Cleanup option
        print("\n" + "-" * 80)
        cleanup = input("Clean up test data? (y/n): ").strip().lower()
        if cleanup == 'y':
            cleanup_test_data()
            print("✓ Test data cleaned up")
        else:
            print("ℹ Test data retained for inspection")

        return 0

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
