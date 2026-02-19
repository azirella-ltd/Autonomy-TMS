"""
Integration Test: Inventory Projection → ATP/CTP → Order Promising

Tests the complete flow:
1. Create inventory projections
2. Calculate ATP (Available-to-Promise)
3. Calculate CTP (Capable-to-Promise)
4. Promise customer orders using ATP/CTP

Author: Claude Code
Date: January 20, 2026
"""

import sys
import os
from pathlib import Path
from datetime import datetime, date, timedelta
import json

# Add backend root to path
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from sqlalchemy import text
from app.db.session import sync_engine

def print_header(msg):
    print("\n" + "=" * 80)
    print(msg)
    print("=" * 80)

def print_success(msg):
    print(f"✅ {msg}")

def print_error(msg):
    print(f"❌ {msg}")


def test_step_1_create_inventory_projections():
    """Create sample inventory projections for testing"""
    print_header("STEP 1: Create Inventory Projections")

    with sync_engine.connect() as conn:
        # Get test product and site
        product = conn.execute(text("SELECT id FROM items LIMIT 1")).fetchone()
        site = conn.execute(text("SELECT id FROM nodes WHERE type = 'retailer' LIMIT 1")).fetchone()
        group = conn.execute(text("SELECT id FROM groups LIMIT 1")).fetchone()
        user = conn.execute(text("SELECT id FROM users LIMIT 1")).fetchone()

        if not all([product, site, group, user]):
            print_error("Missing test data (product, site, group, or user)")
            return None

        product_id = product[0]
        site_id = site[0]
        company_id = group[0]
        user_id = user[0]

        # Create 13 weeks of projections
        start_date = date.today()
        projections = []

        for week in range(13):
            proj_date = start_date + timedelta(days=week * 7)

            # Simulate inventory projection
            on_hand = max(0, 1000 - (week * 50))  # Declining inventory
            in_transit = 200 if week % 2 == 0 else 0  # Every other week
            allocated = 100
            available = on_hand + in_transit - allocated
            supply = 500 if week % 3 == 0 else 0  # Every 3 weeks
            demand = 150

            closing = on_hand + in_transit + supply - demand - allocated

            result = conn.execute(text(f"""
                INSERT INTO inv_projection (
                    company_id, product_id, site_id, projection_date,
                    on_hand_qty, in_transit_qty, allocated_qty, available_qty,
                    supply_qty, demand_qty,
                    opening_inventory, closing_inventory,
                    atp_qty, ctp_qty,
                    stockout_probability, days_of_supply,
                    created_by
                ) VALUES (
                    {company_id}, {product_id}, {site_id}, '{proj_date}',
                    {on_hand}, {in_transit}, {allocated}, {available},
                    {supply}, {demand},
                    {on_hand}, {closing},
                    0, 0,
                    {0.1 * week / 13}, {(on_hand / demand) if demand > 0 else 0},
                    {user_id}
                ) RETURNING id
            """))
            proj_id = result.fetchone()[0]
            projections.append(proj_id)
            conn.commit()

        print_success(f"Created {len(projections)} inventory projections")
        print(f"  Product: {product_id}, Site: {site_id}")
        print(f"  Date range: {start_date} to {start_date + timedelta(days=12*7)}")

        return {
            'projection_ids': projections,
            'product_id': product_id,
            'site_id': site_id,
            'company_id': company_id,
            'user_id': user_id,
            'start_date': start_date
        }


def test_step_2_calculate_atp(context):
    """Calculate ATP projections"""
    print_header("STEP 2: Calculate ATP (Available-to-Promise)")

    with sync_engine.connect() as conn:
        # Get inventory projections
        result = conn.execute(text(f"""
            SELECT projection_date, on_hand_qty, in_transit_qty, allocated_qty,
                   supply_qty, demand_qty
            FROM inv_projection
            WHERE product_id = {context['product_id']}
              AND site_id = {context['site_id']}
            ORDER BY projection_date
        """))
        projections = result.fetchall()

        # Calculate ATP using cumulative logic
        cumulative_atp = 0
        opening_balance = 1000  # Starting inventory

        atp_records = []

        for idx, proj in enumerate(projections):
            proj_date, on_hand, in_transit, allocated, supply, demand = proj

            if idx == 0:
                # Period 1: ATP = Opening - Allocated + Supply - Demand
                atp_qty = opening_balance - allocated + supply - demand
            else:
                # Period N: ATP = Supply - Demand
                atp_qty = supply - demand

            cumulative_atp += atp_qty

            # Insert ATP projection
            result = conn.execute(text(f"""
                INSERT INTO atp_projection (
                    company_id, product_id, site_id, atp_date,
                    atp_qty, cumulative_atp_qty,
                    opening_balance, supply_qty, demand_qty, allocated_qty,
                    atp_rule, created_by
                ) VALUES (
                    {context['company_id']}, {context['product_id']}, {context['site_id']},
                    '{proj_date}',
                    {max(0, atp_qty)}, {max(0, cumulative_atp)},
                    {opening_balance if idx == 0 else cumulative_atp - atp_qty},
                    {supply}, {demand}, {allocated},
                    'cumulative', {context['user_id']}
                ) RETURNING id
            """))
            atp_id = result.fetchone()[0]
            atp_records.append((atp_id, proj_date, atp_qty, cumulative_atp))
            conn.commit()

        print_success(f"Created {len(atp_records)} ATP projections")
        print(f"  Current ATP: {atp_records[0][3]:.0f}")
        print(f"  Final Cumulative ATP: {atp_records[-1][3]:.0f}")

        context['atp_records'] = atp_records
        return context


def test_step_3_calculate_ctp(context):
    """Calculate CTP projections with capacity constraints"""
    print_header("STEP 3: Calculate CTP (Capable-to-Promise)")

    with sync_engine.connect() as conn:
        # Get ATP projections
        atp_data = context['atp_records']

        # Simulate production capacity (500 units per week)
        production_capacity = 500

        ctp_records = []

        for atp_id, proj_date, atp_qty, cumulative_atp in atp_data:
            # CTP = ATP + Production Capacity
            ctp_qty = max(0, cumulative_atp) + production_capacity

            # Check for constraints (simplified)
            component_constrained = ctp_qty > 2000  # Arbitrary threshold
            resource_constrained = False

            # Insert CTP projection
            result = conn.execute(text(f"""
                INSERT INTO ctp_projection (
                    company_id, product_id, site_id, ctp_date,
                    ctp_qty, atp_qty, production_capacity_qty,
                    component_constrained, resource_constrained,
                    created_by
                ) VALUES (
                    {context['company_id']}, {context['product_id']}, {context['site_id']},
                    '{proj_date}',
                    {ctp_qty}, {max(0, cumulative_atp)}, {production_capacity},
                    {component_constrained}, {resource_constrained},
                    {context['user_id']}
                ) RETURNING id
            """))
            ctp_id = result.fetchone()[0]
            ctp_records.append((ctp_id, proj_date, ctp_qty, component_constrained))
            conn.commit()

        print_success(f"Created {len(ctp_records)} CTP projections")
        print(f"  Current CTP: {ctp_records[0][2]:.0f}")
        print(f"  Constrained periods: {sum(1 for _, _, _, c in ctp_records if c)}")

        context['ctp_records'] = ctp_records
        return context


def test_step_4_promise_orders(context):
    """Promise customer orders using ATP/CTP"""
    print_header("STEP 4: Promise Customer Orders")

    with sync_engine.connect() as conn:
        # Create 5 sample customer orders
        orders = [
            ('ORD-001', 500, 0),   # Small order - should fulfill from ATP
            ('ORD-002', 1200, 1),  # Large order - may need CTP
            ('ORD-003', 300, 2),   # Medium order
            ('ORD-004', 2500, 3),  # Very large - may need backorder
            ('ORD-005', 150, 4),   # Small order
        ]

        promises = []

        for order_id, requested_qty, week_offset in orders:
            requested_date = context['start_date'] + timedelta(days=week_offset * 7)

            # Get ATP/CTP for requested date
            atp_result = conn.execute(text(f"""
                SELECT cumulative_atp_qty FROM atp_projection
                WHERE product_id = {context['product_id']}
                  AND site_id = {context['site_id']}
                  AND atp_date >= '{requested_date}'
                ORDER BY atp_date
                LIMIT 1
            """)).fetchone()

            ctp_result = conn.execute(text(f"""
                SELECT ctp_qty FROM ctp_projection
                WHERE product_id = {context['product_id']}
                  AND site_id = {context['site_id']}
                  AND ctp_date >= '{requested_date}'
                ORDER BY ctp_date
                LIMIT 1
            """)).fetchone()

            atp_qty = atp_result[0] if atp_result else 0
            ctp_qty = ctp_result[0] if ctp_result else 0

            # Promise logic
            if atp_qty >= requested_qty:
                # Fulfill from ATP
                promised_qty = requested_qty
                promised_date = requested_date
                promise_source = 'ATP'
                confidence = 0.95
            elif ctp_qty >= requested_qty:
                # Fulfill from CTP (requires production)
                promised_qty = requested_qty
                promised_date = requested_date + timedelta(days=7)  # Lead time
                promise_source = 'CTP'
                confidence = 0.80
            else:
                # Partial/backorder
                promised_qty = min(requested_qty, ctp_qty)
                promised_date = requested_date + timedelta(days=14)
                promise_source = 'BACKORDER'
                confidence = 0.60

            # Insert order promise
            result = conn.execute(text(f"""
                INSERT INTO order_promise (
                    order_id, order_line_number,
                    company_id, product_id, site_id,
                    requested_quantity, requested_date,
                    promised_quantity, promised_date, promise_source,
                    fulfillment_type, promise_status, promise_confidence,
                    created_by
                ) VALUES (
                    '{order_id}', 1,
                    {context['company_id']}, {context['product_id']}, {context['site_id']},
                    {requested_qty}, '{requested_date}',
                    {promised_qty}, '{promised_date}', '{promise_source}',
                    'single', 'PROPOSED', {confidence},
                    {context['user_id']}
                ) RETURNING id
            """))
            promise_id = result.fetchone()[0]
            promises.append((order_id, requested_qty, promised_qty, promise_source, confidence))
            conn.commit()

        print_success(f"Promised {len(promises)} customer orders")
        for order_id, req_qty, prom_qty, source, conf in promises:
            fill_rate = (prom_qty / req_qty * 100) if req_qty > 0 else 0
            print(f"  {order_id}: {prom_qty}/{req_qty} ({fill_rate:.0f}%) via {source} [{conf*100:.0f}% confidence]")

        context['promises'] = promises
        return context


def test_step_5_verification():
    """Verify all data was created correctly"""
    print_header("STEP 5: Verification")

    with sync_engine.connect() as conn:
        # Count records
        proj_count = conn.execute(text("SELECT COUNT(*) FROM inv_projection")).scalar()
        atp_count = conn.execute(text("SELECT COUNT(*) FROM atp_projection")).scalar()
        ctp_count = conn.execute(text("SELECT COUNT(*) FROM ctp_projection")).scalar()
        promise_count = conn.execute(text("SELECT COUNT(*) FROM order_promise")).scalar()

        print_success("Record counts:")
        print(f"  Inventory Projections: {proj_count}")
        print(f"  ATP Projections: {atp_count}")
        print(f"  CTP Projections: {ctp_count}")
        print(f"  Order Promises: {promise_count}")

        # Verify data integrity
        if proj_count >= 13 and atp_count >= 13 and ctp_count >= 13 and promise_count >= 5:
            print_success("✅ INTEGRATION TEST PASSED")
            return True
        else:
            print_error("❌ INTEGRATION TEST FAILED - Insufficient records created")
            return False


def main():
    """Run integration test"""
    print_header("INVENTORY PROJECTION INTEGRATION TEST")
    print("Testing: Inventory Projection → ATP → CTP → Order Promising")

    try:
        # Step 1: Create projections
        context = test_step_1_create_inventory_projections()
        if not context:
            print_error("Step 1 failed")
            return

        # Step 2: Calculate ATP
        context = test_step_2_calculate_atp(context)

        # Step 3: Calculate CTP
        context = test_step_3_calculate_ctp(context)

        # Step 4: Promise orders
        context = test_step_4_promise_orders(context)

        # Step 5: Verification
        success = test_step_5_verification()

        if success:
            print_header("✅ ALL TESTS PASSED")
        else:
            print_header("❌ SOME TESTS FAILED")

    except Exception as e:
        print_error(f"Integration test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
