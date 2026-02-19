"""
End-to-End Integration Test: Complete Planning Flow

Tests the complete planning workflow:
1. Demand forecast generation
2. MPS plan creation
3. Lot sizing optimization
4. Capacity constraint checking
5. Production order generation

This simulates a real planner workflow from demand to execution.

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

def print_info(msg):
    print(f"ℹ️  {msg}")


def test_step_1_demand_forecast():
    """Step 1: Generate or load demand forecast"""
    print_header("STEP 1: Demand Forecast")

    # For this test, we'll create synthetic demand data
    # In reality, this would come from demand planning/forecasting module

    start_date = date.today()
    demand_schedule = []

    # Generate 13 weeks of demand with trend and seasonality
    for week in range(13):
        base = 1000
        trend = week * 10  # Growth trend
        seasonality = 200 if week % 4 == 0 else 0  # Monthly peaks
        import random
        random.seed(42 + week)
        noise = random.randint(-50, 50)
        demand = max(0, base + trend + seasonality + noise)
        demand_schedule.append(demand)

    total_demand = sum(demand_schedule)
    avg_demand = total_demand / len(demand_schedule)

    print_success(f"Generated {len(demand_schedule)}-week demand forecast")
    print(f"  Total Demand: {total_demand:,} units")
    print(f"  Average Weekly: {avg_demand:.0f} units")
    print(f"  Peak Week: {max(demand_schedule):,} units")
    print(f"  First 5 weeks: {demand_schedule[:5]}")

    return {
        'start_date': start_date,
        'demand_schedule': demand_schedule,
        'total_demand': total_demand,
        'avg_demand': avg_demand
    }


def test_step_2_create_mps_plan(context):
    """Step 2: Create MPS plan based on demand"""
    print_header("STEP 2: Create MPS Plan")

    with sync_engine.connect() as conn:
        # Get test configuration
        result = conn.execute(text("SELECT id, name FROM supply_chain_configs LIMIT 1"))
        config = result.fetchone()

        if not config:
            print_error("No supply chain configuration found")
            return None

        config_id, config_name = config

        # Get factory node
        result = conn.execute(text(f"""
            SELECT id, name FROM nodes
            WHERE config_id = {config_id} AND type = 'factory'
            LIMIT 1
        """))
        factory = result.fetchone()

        if not factory:
            print_error("No factory node found")
            return None

        factory_id, factory_name = factory

        # Get product
        result = conn.execute(text("SELECT id, name FROM items LIMIT 1"))
        product = result.fetchone()

        if not product:
            print_error("No product found")
            return None

        product_id, product_name = product

        # Get user
        result = conn.execute(text("SELECT id FROM users LIMIT 1"))
        user = result.fetchone()
        user_id = user[0] if user else 1

        # Create MPS Plan
        start_date = context['start_date']
        end_date = start_date + timedelta(weeks=13)

        result = conn.execute(text(f"""
            INSERT INTO mps_plans (
                supply_chain_config_id, name, description,
                planning_horizon_weeks, bucket_size_days,
                start_date, end_date, status, created_by
            ) VALUES (
                {config_id}, 'E2E Test MPS Plan', 'End-to-end integration test',
                13, 7,
                '{start_date}', '{end_date}', 'DRAFT', {user_id}
            ) RETURNING id
        """))
        mps_plan_id = result.fetchone()[0]
        conn.commit()

        # Add MPS Plan Item with demand schedule
        weekly_quantities_json = json.dumps(context['demand_schedule'])

        conn.execute(text(f"""
            INSERT INTO mps_plan_items (
                plan_id, product_id, site_id, weekly_quantities
            ) VALUES (
                {mps_plan_id}, {product_id}, {factory_id}, '{weekly_quantities_json}'
            )
        """))
        conn.commit()

        print_success(f"Created MPS Plan ID: {mps_plan_id}")
        print(f"  Configuration: {config_name}")
        print(f"  Factory: {factory_name}")
        print(f"  Product: {product_name}")
        print(f"  Planning Horizon: 13 weeks")

        context['mps_plan_id'] = mps_plan_id
        context['config_id'] = config_id
        context['factory_id'] = factory_id
        context['product_id'] = product_id
        context['product_name'] = product_name

        return context


def test_step_3_apply_lot_sizing(context):
    """Step 3: Apply lot sizing to optimize batch sizes"""
    print_header("STEP 3: Apply Lot Sizing Optimization")

    from app.services.lot_sizing import (
        LotSizingInput,
        compare_algorithms,
    )

    # Setup cost parameters
    setup_cost = 500.0  # $500 per setup
    holding_cost = 2.0   # $2 per unit per week
    unit_cost = 50.0

    inputs = LotSizingInput(
        demand_schedule=context['demand_schedule'],
        start_date=context['start_date'],
        period_days=7,
        setup_cost=setup_cost,
        holding_cost_per_unit_per_period=holding_cost,
        unit_cost=unit_cost,
        annual_demand=context['total_demand'] * 4  # Annualize (13 weeks × 4)
    )

    # Compare algorithms
    algorithms = ['LFL', 'EOQ', 'POQ', 'PPB']
    results = compare_algorithms(inputs, algorithms)

    # Find best
    best_algo = min(results.keys(), key=lambda k: results[k].total_cost)
    best_result = results[best_algo]

    print_success(f"Compared {len(algorithms)} lot sizing algorithms")
    print(f"\n  Results:")
    for algo, result in results.items():
        marker = "  👑" if algo == best_algo else "    "
        print(f"{marker} {algo}: ${result.total_cost:,.2f} total cost ({result.number_of_orders} orders)")

    lfl_cost = results['LFL'].total_cost
    savings = lfl_cost - best_result.total_cost
    savings_pct = (savings / lfl_cost * 100) if lfl_cost > 0 else 0

    print(f"\n  Best Algorithm: {best_algo}")
    print(f"  Total Cost: ${best_result.total_cost:,.2f}")
    print(f"  Cost Savings: ${savings:,.2f} ({savings_pct:.1f}% vs LFL)")
    print(f"  Production Orders: {best_result.number_of_orders}")

    context['lot_sizing_results'] = results
    context['best_algorithm'] = best_algo
    context['best_result'] = best_result
    context['lot_sized_plan'] = best_result.order_schedule

    return context


def test_step_4_capacity_check(context):
    """Step 4: Check capacity constraints with RCCP"""
    print_header("STEP 4: Capacity Constraint Check (RCCP)")

    from app.services.capacity_constrained_mps import (
        CapacityConstrainedMPS,
        MPSProductionPlan,
        ResourceRequirement,
    )

    # Define resource requirements
    resources = [
        ResourceRequirement(
            resource_id="assembly_line",
            resource_name="Assembly Line",
            units_per_product=0.5,  # 0.5 hours per unit
            available_capacity=600,  # 600 hours per week
            utilization_target=0.85
        ),
        ResourceRequirement(
            resource_id="labor",
            resource_name="Production Labor",
            units_per_product=0.25,
            available_capacity=400,
            utilization_target=0.90
        ),
        ResourceRequirement(
            resource_id="packaging",
            resource_name="Packaging Line",
            units_per_product=0.1,
            available_capacity=200,
            utilization_target=0.80
        )
    ]

    # Create MPS plan from lot sizing result
    mps_plan = MPSProductionPlan(
        product_id=context['product_id'],
        product_name=context['product_name'],
        planned_quantities=context['lot_sized_plan'].copy(),
        resource_requirements=resources
    )

    # Check capacity
    rccp = CapacityConstrainedMPS(context['start_date'], 7)
    result = rccp.generate_feasible_plan(mps_plan, strategy="level")

    print_success(f"Capacity check completed")
    print(f"  Plan Feasible: {'✅ Yes' if result.is_feasible else '❌ No'}")
    print(f"  Bottleneck Resources: {', '.join(result.bottleneck_resources) or 'None'}")
    print(f"  Total Production Reduction: {result.total_shortage:.0f} units")

    if not result.is_feasible:
        print(f"\n  Utilization Summary:")
        for resource_id, util in result.utilization_summary.items():
            status = "✅" if util < 95 else "⚠️"
            print(f"    {status} {resource_id}: {util:.1f}% avg utilization")

        print(f"\n  Recommendations:")
        for rec in result.recommendations:
            print(f"    • {rec}")

    context['capacity_result'] = result
    context['feasible_plan'] = result.feasible_plan
    context['is_feasible'] = result.is_feasible

    return context


def test_step_5_create_production_orders(context):
    """Step 5: Generate production orders from feasible plan"""
    print_header("STEP 5: Generate Production Orders")

    with sync_engine.connect() as conn:
        # Get user
        result = conn.execute(text("SELECT id FROM users LIMIT 1"))
        user = result.fetchone()
        user_id = user[0] if user else 1

        production_orders = []
        start_date = context['start_date']

        for week_num, quantity in enumerate(context['feasible_plan']):
            if quantity <= 0:
                continue

            order_number = f"E2E-PO-{week_num+1:03d}"
            planned_start = start_date + timedelta(days=week_num * 7)
            planned_completion = planned_start + timedelta(days=5)

            result = conn.execute(text(f"""
                INSERT INTO production_orders (
                    order_number, item_id, site_id, config_id,
                    planned_quantity, planned_start_date, planned_completion_date,
                    status, priority, created_by_id
                ) VALUES (
                    '{order_number}', {context['product_id']}, {context['factory_id']},
                    {context['config_id']}, {quantity},
                    '{planned_start}', '{planned_completion}',
                    'PLANNED', 5, {user_id}
                ) RETURNING id
            """))
            order_id = result.fetchone()[0]
            conn.commit()

            production_orders.append({
                'id': order_id,
                'order_number': order_number,
                'quantity': quantity,
                'week': week_num + 1
            })

        print_success(f"Created {len(production_orders)} production orders")

        if production_orders:
            print(f"  First 5 orders:")
            for order in production_orders[:5]:
                print(f"    • {order['order_number']}: {order['quantity']:.0f} units (Week {order['week']})")

        context['production_orders'] = production_orders

        return context


def test_step_6_verification(context):
    """Step 6: Verify end-to-end flow"""
    print_header("STEP 6: Verification")

    checks = [
        ('Demand Forecast', 'demand_schedule' in context),
        ('MPS Plan Created', 'mps_plan_id' in context),
        ('Lot Sizing Applied', 'best_algorithm' in context),
        ('Capacity Check Completed', 'capacity_result' in context),
        ('Production Orders Generated', 'production_orders' in context and len(context['production_orders']) > 0),
    ]

    all_passed = all(check[1] for check in checks)

    for check_name, passed in checks:
        status = "✅" if passed else "❌"
        print(f"  {status} {check_name}")

    if all_passed:
        print_success("\n✅ ALL END-TO-END TESTS PASSED")

        # Summary
        print("\n  Flow Summary:")
        print(f"    1. Demand Forecast: {context['total_demand']:,} units over 13 weeks")
        print(f"    2. MPS Plan: ID {context['mps_plan_id']}")
        print(f"    3. Lot Sizing: {context['best_algorithm']} (${context['best_result'].total_cost:,.2f})")
        print(f"    4. Capacity Check: {'Feasible' if context['is_feasible'] else 'Constrained'}")
        print(f"    5. Production Orders: {len(context['production_orders'])} orders created")

        return True
    else:
        print_error("\n❌ SOME TESTS FAILED")
        return False


def cleanup_test_data(context):
    """Clean up test data"""
    print_header("Cleanup")

    if not context:
        return

    with sync_engine.connect() as conn:
        # Delete in reverse dependency order
        if 'production_orders' in context:
            conn.execute(text("DELETE FROM production_orders WHERE order_number LIKE 'E2E-PO-%'"))

        if 'mps_plan_id' in context:
            conn.execute(text(f"DELETE FROM mps_plan_items WHERE plan_id = {context['mps_plan_id']}"))
            conn.execute(text(f"DELETE FROM mps_plans WHERE id = {context['mps_plan_id']}"))

        conn.commit()

    print_success("Test data cleaned up")


def main():
    """Run complete end-to-end integration test"""
    print_header("END-TO-END PLANNING INTEGRATION TEST")
    print("Testing: Demand → MPS → Lot Sizing → Capacity → Production Orders")

    context = {}

    try:
        # Step 1: Demand Forecast
        context = test_step_1_demand_forecast()

        # Step 2: MPS Plan
        context = test_step_2_create_mps_plan(context)
        if not context:
            return False

        # Step 3: Lot Sizing
        context = test_step_3_apply_lot_sizing(context)

        # Step 4: Capacity Check
        context = test_step_4_capacity_check(context)

        # Step 5: Production Orders
        context = test_step_5_create_production_orders(context)

        # Step 6: Verification
        success = test_step_6_verification(context)

        # Cleanup
        cleanup_test_data(context)

        if success:
            print_header("✅ END-TO-END INTEGRATION TEST COMPLETE")
            return True
        else:
            print_header("❌ END-TO-END INTEGRATION TEST FAILED")
            return False

    except Exception as e:
        print_error(f"Integration test failed: {e}")
        import traceback
        traceback.print_exc()

        # Attempt cleanup
        try:
            cleanup_test_data(context)
        except:
            pass

        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
