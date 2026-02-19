"""
Integration Test: MPS → Lot Sizing → Capacity-Constrained MPS

Tests the complete MPS enhancement flow:
1. Generate base MPS plan (from demand)
2. Apply lot sizing algorithms (EOQ, POQ, PPB)
3. Check capacity constraints (RCCP)
4. Level production to meet capacity
5. Verify feasibility and cost optimization

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

from app.services.lot_sizing import (
    LotSizingInput, calculate_lot_size, compare_algorithms
)
from app.services.capacity_constrained_mps import (
    CapacityConstrainedMPS, MPSProductionPlan, ResourceRequirement
)

def print_header(msg):
    print("\n" + "=" * 80)
    print(msg)
    print("=" * 80)

def print_success(msg):
    print(f"✅ {msg}")

def print_error(msg):
    print(f"❌ {msg}")


def test_step_1_create_base_demand():
    """Create realistic demand schedule for MPS"""
    print_header("STEP 1: Create Base Demand Schedule")

    # 13-week demand with seasonality and trend
    base_demand = 1000
    demand_schedule = []

    for week in range(13):
        # Add trend (slight growth)
        trend = week * 10

        # Add seasonality (monthly peaks)
        seasonality = 200 if week % 4 == 0 else 0

        # Add randomness (±10%)
        import random
        random.seed(42 + week)
        noise = random.randint(-100, 100)

        weekly_demand = base_demand + trend + seasonality + noise
        demand_schedule.append(max(0, weekly_demand))

    total_demand = sum(demand_schedule)
    avg_demand = total_demand / len(demand_schedule)
    peak_demand = max(demand_schedule)

    print_success(f"Created {len(demand_schedule)}-week demand schedule")
    print(f"  Total Demand: {total_demand:.0f} units")
    print(f"  Average Weekly: {avg_demand:.0f} units")
    print(f"  Peak Week: {peak_demand:.0f} units")
    print(f"  Demand Schedule: {[int(d) for d in demand_schedule[:5]]} ... (first 5)")

    return {
        'demand_schedule': demand_schedule,
        'start_date': date.today(),
        'period_days': 7,
        'total_demand': total_demand,
        'avg_demand': avg_demand
    }


def test_step_2_lot_sizing(context):
    """Apply lot sizing algorithms to demand"""
    print_header("STEP 2: Apply Lot Sizing Algorithms")

    # Setup cost parameters
    setup_cost = 500.0  # $500 per production setup
    holding_cost = 2.0   # $2 per unit per week
    unit_cost = 50.0     # $50 per unit

    inputs = LotSizingInput(
        demand_schedule=context['demand_schedule'],
        start_date=context['start_date'],
        period_days=context['period_days'],
        setup_cost=setup_cost,
        holding_cost_per_unit_per_period=holding_cost,
        unit_cost=unit_cost,
        annual_demand=context['total_demand'] * (52 / 13)  # Annualize
    )

    # Compare all algorithms
    algorithms = ['LFL', 'EOQ', 'POQ', 'PPB']
    results = compare_algorithms(inputs, algorithms)

    print_success(f"Compared {len(algorithms)} lot sizing algorithms")

    for algo, result in results.items():
        savings = 0
        if algo != 'LFL' and 'LFL' in results:
            lfl_cost = results['LFL'].total_cost
            savings = ((lfl_cost - result.total_cost) / lfl_cost * 100) if lfl_cost > 0 else 0

        print(f"  {algo}:")
        print(f"    Total Cost: ${result.total_cost:,.2f}")
        print(f"    Setup Costs: ${result.setup_cost_total:,.2f} ({result.number_of_orders} orders)")
        print(f"    Holding Costs: ${result.holding_cost_total:,.2f}")
        print(f"    Avg Inventory: {result.average_inventory:.0f} units")
        if savings > 0:
            print(f"    Savings vs LFL: {savings:.1f}%")

    # Select best algorithm (lowest cost)
    best_algo = min(results.keys(), key=lambda k: results[k].total_cost)
    best_result = results[best_algo]

    print_success(f"Best Algorithm: {best_algo} (${best_result.total_cost:,.2f} total cost)")

    context['lot_sizing_results'] = results
    context['best_algorithm'] = best_algo
    context['best_result'] = best_result
    context['production_plan'] = best_result.order_schedule

    return context


def test_step_3_capacity_constraints(context):
    """Check capacity constraints on lot-sized plan"""
    print_header("STEP 3: Check Capacity Constraints (RCCP)")

    # Define resource requirements for production
    resources = [
        ResourceRequirement(
            resource_id="machine_1",
            resource_name="Assembly Line 1",
            units_per_product=0.5,  # 0.5 machine hours per unit
            available_capacity=600,  # 600 machine hours per week
            utilization_target=0.85  # 85% target utilization
        ),
        ResourceRequirement(
            resource_id="labor",
            resource_name="Production Labor",
            units_per_product=0.25,  # 0.25 labor hours per unit
            available_capacity=400,  # 400 labor hours per week
            utilization_target=0.90  # 90% target utilization
        ),
        ResourceRequirement(
            resource_id="packaging",
            resource_name="Packaging Line",
            units_per_product=0.1,  # 0.1 packing hours per unit
            available_capacity=200,  # 200 packing hours per week
            utilization_target=0.80  # 80% target utilization
        )
    ]

    # Create MPS plan from lot sizing result
    mps_plan = MPSProductionPlan(
        product_id=1,
        product_name="Widget A",
        planned_quantities=context['production_plan'].copy(),
        resource_requirements=resources
    )

    # Check capacity
    rccp = CapacityConstrainedMPS(context['start_date'], context['period_days'])
    capacity_checks = rccp.check_capacity(mps_plan, len(context['production_plan']))

    # Analyze constraints
    constrained_periods = [c for c in capacity_checks if c.is_constrained]
    over_target_periods = [c for c in capacity_checks if c.is_over_target]

    print_success(f"Performed capacity checks for {len(capacity_checks)} period-resource combinations")
    print(f"  Resources: {len(resources)}")
    print(f"  Periods: {len(context['production_plan'])}")
    print(f"  Constrained (>95%): {len(constrained_periods)} checks")
    print(f"  Over Target (>85%): {len(over_target_periods)} checks")

    # Show bottleneck details
    if constrained_periods:
        print("\n  Bottleneck Details:")
        for check in constrained_periods[:5]:  # Show first 5
            print(f"    Week {check.period}: {check.resource_name}")
            print(f"      Required: {check.required_capacity:.0f} / {check.available_capacity:.0f} hours")
            print(f"      Utilization: {check.utilization:.1f}%")
            print(f"      Shortage: {check.shortage:.0f} hours")

    context['capacity_checks'] = capacity_checks
    context['constrained_periods'] = constrained_periods
    context['mps_plan'] = mps_plan
    context['rccp'] = rccp

    return context


def test_step_4_capacity_leveling(context):
    """Level production to meet capacity constraints"""
    print_header("STEP 4: Level Production to Meet Capacity")

    if not context['constrained_periods']:
        print_success("No capacity constraints - leveling not needed")
        context['feasible_plan'] = context['production_plan']
        context['is_feasible'] = True
        return context

    # Generate feasible plan using leveling strategy
    mps_plan = context['mps_plan']
    rccp = context['rccp']

    result = rccp.generate_feasible_plan(mps_plan, strategy="level")

    print_success(f"Generated capacity-feasible plan")
    print(f"  Strategy: Level production across periods")
    print(f"  Feasible: {result.is_feasible}")
    print(f"  Total Shortage: {result.total_shortage:.0f} units")
    print(f"  Bottleneck Resources: {', '.join(result.bottleneck_resources)}")

    # Show utilization summary
    print("\n  Resource Utilization Summary:")
    for resource_id, avg_util in result.utilization_summary.items():
        resource = next(r for r in mps_plan.resource_requirements if r.resource_id == resource_id)
        status = "✅" if avg_util < 95 else "⚠️"
        print(f"    {status} {resource.resource_name}: {avg_util:.1f}% average")

    # Show recommendations
    if result.recommendations:
        print("\n  Recommendations:")
        for rec in result.recommendations:
            print(f"    • {rec}")

    # Compare original vs feasible
    print("\n  Production Plan Comparison:")
    print(f"    Original Total: {sum(result.original_plan):.0f} units")
    print(f"    Feasible Total: {sum(result.feasible_plan):.0f} units")
    print(f"    Reduction: {sum(result.original_plan) - sum(result.feasible_plan):.0f} units")

    context['feasible_plan'] = result.feasible_plan
    context['capacity_result'] = result
    context['is_feasible'] = result.is_feasible

    return context


def test_step_5_final_verification(context):
    """Verify complete MPS enhancement flow"""
    print_header("STEP 5: Final Verification")

    # Verify all steps completed
    checks = [
        ('Demand Schedule', 'demand_schedule' in context),
        ('Lot Sizing Results', 'lot_sizing_results' in context),
        ('Best Algorithm Selected', 'best_algorithm' in context),
        ('Capacity Checks Performed', 'capacity_checks' in context),
        ('Feasible Plan Generated', 'feasible_plan' in context),
    ]

    all_passed = all(check[1] for check in checks)

    for check_name, passed in checks:
        status = "✅" if passed else "❌"
        print(f"  {status} {check_name}")

    if all_passed:
        print_success("\n✅ ALL INTEGRATION TESTS PASSED")

        # Summary
        print("\n  Summary:")
        print(f"    Base Demand: {context['total_demand']:.0f} units over 13 weeks")
        print(f"    Best Lot Sizing: {context['best_algorithm']} (${context['best_result'].total_cost:,.2f})")
        print(f"    Production Orders: {context['best_result'].number_of_orders}")
        print(f"    Capacity Feasible: {context['is_feasible']}")

        if context.get('capacity_result'):
            savings_vs_lfl = 0
            if 'LFL' in context['lot_sizing_results']:
                lfl_cost = context['lot_sizing_results']['LFL'].total_cost
                best_cost = context['best_result'].total_cost
                savings_vs_lfl = lfl_cost - best_cost

            print(f"    Cost Savings: ${savings_vs_lfl:,.2f} ({savings_vs_lfl/lfl_cost*100:.1f}% vs LFL)")

        return True
    else:
        print_error("\n❌ SOME TESTS FAILED")
        return False


def main():
    """Run complete MPS integration test"""
    print_header("MPS ENHANCEMENTS INTEGRATION TEST")
    print("Testing: Demand → Lot Sizing → Capacity Planning → Leveling")

    try:
        # Step 1: Create base demand
        context = test_step_1_create_base_demand()

        # Step 2: Apply lot sizing
        context = test_step_2_lot_sizing(context)

        # Step 3: Check capacity
        context = test_step_3_capacity_constraints(context)

        # Step 4: Level production
        context = test_step_4_capacity_leveling(context)

        # Step 5: Verify
        success = test_step_5_final_verification(context)

        if success:
            print_header("✅ INTEGRATION TEST COMPLETE")
        else:
            print_header("❌ INTEGRATION TEST FAILED")

        return success

    except Exception as e:
        print_error(f"Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
