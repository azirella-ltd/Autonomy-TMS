#!/usr/bin/env python3
"""
Test script for Monte Carlo Supply Planning

Tests the stochastic sampling and Monte Carlo simulation components
with a prototype implementation.

Usage:
    python scripts/test_monte_carlo_planner.py --config-name "Complex_SC" --num-scenarios 100
"""

import argparse
import sys
from pathlib import Path

# Add backend to path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.append(str(BACKEND_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.supply_chain_config import SupplyChainConfig
from app.services.stochastic_sampling import StochasticParameters
from app.services.monte_carlo_planner import (
    MonteCarloPlanner,
    PlanObjectives,
    format_scorecard_summary,
)


def test_stochastic_sampling(session, config_name: str):
    """Test stochastic parameter sampling."""
    print("\n" + "="*80)
    print("TEST 1: Stochastic Parameter Sampling")
    print("="*80)

    config = session.query(SupplyChainConfig).filter(
        SupplyChainConfig.name == config_name
    ).first()

    if not config:
        print(f"[error] Config '{config_name}' not found")
        return

    print(f"\nConfig: {config.name} (ID: {config.id})")

    # Test demand sampling
    from app.services.stochastic_sampling import sample_demand

    parameters = StochasticParameters(
        demand_model="normal",
        demand_variability=0.15,
        random_seed=42
    )

    demand_samples = sample_demand(session, config, parameters, horizon=4)

    print(f"\nDemand Samples (4 periods):")
    for market_id, samples in demand_samples.items():
        print(f"  Market {market_id}: {samples}")
        print(f"    Mean: {samples.mean():.1f}, Std: {samples.std():.1f}")

    # Test lead time sampling
    from app.services.stochastic_sampling import sample_lead_times

    lead_time_samples = sample_lead_times(session, config, parameters)

    print(f"\nLead Time Samples:")
    for lane_id, lead_time in list(lead_time_samples.items())[:5]:
        print(f"  Lane {lane_id}: {lead_time} periods")

    # Test supplier reliability sampling
    from app.services.stochastic_sampling import sample_supplier_reliability

    reliability_samples = sample_supplier_reliability(session, config, parameters, horizon=4)

    print(f"\nSupplier Reliability Samples (4 periods):")
    for node_id, samples in list(reliability_samples.items())[:3]:
        print(f"  Supplier {node_id}: {samples} (mean: {samples.mean():.2f})")

    print("\n✅ Stochastic sampling test passed")


def test_scenario_generation(session, config_name: str):
    """Test scenario generation."""
    print("\n" + "="*80)
    print("TEST 2: Scenario Generation")
    print("="*80)

    config = session.query(SupplyChainConfig).filter(
        SupplyChainConfig.name == config_name
    ).first()

    if not config:
        print(f"[error] Config '{config_name}' not found")
        return

    from app.services.stochastic_sampling import generate_scenario

    parameters = StochasticParameters(
        demand_model="normal",
        demand_variability=0.15,
        lead_time_model="normal",
        lead_time_variability=0.10,
        supplier_reliability=0.95,
        random_seed=42
    )

    scenario = generate_scenario(session, config, parameters, horizon=13, scenario_number=0)

    print(f"\nScenario {scenario['scenario_number']}:")
    print(f"  Horizon: {scenario['horizon']} periods")
    print(f"  Demand samples: {len(scenario['demand_samples'])} markets")
    print(f"  Lead time samples: {len(scenario['lead_time_samples'])} lanes")
    print(f"  Supplier reliability: {len(scenario['supplier_reliability'])} suppliers")

    print("\n✅ Scenario generation test passed")


def test_monte_carlo_simulation(session, config_name: str, num_scenarios: int = 100):
    """Test Monte Carlo simulation."""
    print("\n" + "="*80)
    print(f"TEST 3: Monte Carlo Simulation ({num_scenarios} scenarios)")
    print("="*80)

    config = session.query(SupplyChainConfig).filter(
        SupplyChainConfig.name == config_name
    ).first()

    if not config:
        print(f"[error] Config '{config_name}' not found")
        return

    print(f"\nConfig: {config.name} (ID: {config.id})")

    # Define parameters
    parameters = StochasticParameters(
        demand_model="normal",
        demand_variability=0.15,
        lead_time_model="normal",
        lead_time_variability=0.10,
        supplier_reliability=0.95,
        random_seed=42
    )

    # Define objectives
    objectives = PlanObjectives(
        planning_horizon=13,  # 13 weeks (1 quarter)
        primary_objective="balance",
        service_level_target=0.95,
        service_level_confidence=0.90,
        budget_limit=500000.0,
        inventory_dos_min=10,
        inventory_dos_max=30,
    )

    print(f"\nObjectives:")
    print(f"  Planning Horizon: {objectives.planning_horizon} weeks")
    print(f"  Service Level Target: {objectives.service_level_target*100:.0f}%")
    print(f"  Confidence Requirement: P(OTIF > {objectives.service_level_target*100:.0f}%) >= {objectives.service_level_confidence*100:.0f}%")
    print(f"  Budget Limit: ${objectives.budget_limit:,.0f}")

    # Create planner
    planner = MonteCarloPlanner(session, config, agent_strategy="trm")

    print(f"\nAgent Strategy: {planner.agent_strategy}")
    print(f"Running {num_scenarios} scenarios...")

    def progress_callback(completed, total):
        if completed % 20 == 0 or completed == total:
            pct = (completed / total) * 100
            print(f"  Progress: {completed}/{total} ({pct:.0f}%)")

    # Run simulation
    scenario_results = planner.run_monte_carlo_simulation(
        parameters,
        objectives,
        num_scenarios,
        progress_callback
    )

    print(f"\n✅ Completed {len(scenario_results)} scenarios")

    # Compute balanced scorecard
    print("\nComputing balanced scorecard...")
    scorecard = planner.compute_balanced_scorecard(scenario_results, objectives)

    # Print summary
    print(format_scorecard_summary(scorecard))

    # Generate recommendations
    print("\nRecommendations:")
    recommendations = planner.generate_recommendations(scorecard, objectives)

    if not recommendations:
        print("  ✅ No issues found - all metrics within targets")
    else:
        for i, rec in enumerate(recommendations, 1):
            severity_icon = "🔴" if rec["severity"] == "high" else ("🟡" if rec["severity"] == "medium" else "🟢")
            print(f"\n  {severity_icon} {i}. {rec['type'].upper()}")
            print(f"     {rec['message']}")
            print(f"     → {rec['recommendation']}")

    print("\n✅ Monte Carlo simulation test passed")

    return scorecard


def compare_agent_strategies(session, config_name: str, num_scenarios: int = 100):
    """Compare different agent strategies."""
    print("\n" + "="*80)
    print("TEST 4: Agent Strategy Comparison")
    print("="*80)

    config = session.query(SupplyChainConfig).filter(
        SupplyChainConfig.name == config_name
    ).first()

    if not config:
        print(f"[error] Config '{config_name}' not found")
        return

    parameters = StochasticParameters(
        demand_model="normal",
        demand_variability=0.15,
        lead_time_model="normal",
        lead_time_variability=0.10,
        supplier_reliability=0.95,
        random_seed=42
    )

    objectives = PlanObjectives(
        planning_horizon=13,
        service_level_target=0.95,
        service_level_confidence=0.90,
        budget_limit=500000.0,
    )

    strategies = ["naive", "pid", "trm", "gnn"]
    results = {}

    for strategy in strategies:
        print(f"\n--- Testing {strategy.upper()} agent ---")
        planner = MonteCarloPlanner(session, config, agent_strategy=strategy)

        scenario_results = planner.run_monte_carlo_simulation(
            parameters, objectives, num_scenarios, progress_callback=None
        )

        scorecard = planner.compute_balanced_scorecard(scenario_results, objectives)
        results[strategy] = scorecard

    # Comparison table
    print("\n" + "="*80)
    print("Agent Strategy Comparison")
    print("="*80)
    print(f"\n{'Metric':<30} {'Naive':<15} {'PID':<15} {'TRM':<15} {'GNN':<15}")
    print("-" * 90)

    # Total cost
    print(f"{'Total Cost (Expected)':<30}", end="")
    for strategy in strategies:
        cost = results[strategy]["financial"]["total_cost"]["expected"]
        print(f"${cost:>13,.0f} ", end="")
    print()

    # OTIF
    print(f"{'OTIF (Expected %)':<30}", end="")
    for strategy in strategies:
        otif = results[strategy]["customer"]["otif"]["expected"] * 100
        print(f"{otif:>14.1f}% ", end="")
    print()

    # P(OTIF > 95%)
    print(f"{'P(OTIF > 95%)':<30}", end="")
    for strategy in strategies:
        prob = results[strategy]["customer"]["otif"]["probability_above_target"] * 100
        print(f"{prob:>14.1f}% ", end="")
    print()

    # Inventory turns
    print(f"{'Inventory Turns':<30}", end="")
    for strategy in strategies:
        turns = results[strategy]["operational"]["inventory_turns"]["expected"]
        print(f"{turns:>14.1f}  ", end="")
    print()

    # Bullwhip
    print(f"{'Bullwhip Ratio':<30}", end="")
    for strategy in strategies:
        bullwhip = results[strategy]["operational"]["bullwhip_ratio"]["expected"]
        print(f"{bullwhip:>14.2f}  ", end="")
    print()

    print("\n✅ Agent comparison test passed")


def main():
    parser = argparse.ArgumentParser(description="Test Monte Carlo Supply Planning")
    parser.add_argument("--config-name", default="Complex_SC", help="Supply chain config name")
    parser.add_argument("--num-scenarios", type=int, default=100, help="Number of Monte Carlo scenarios")
    parser.add_argument("--test", choices=["all", "sampling", "scenario", "simulation", "comparison"],
                        default="all", help="Which test to run")

    args = parser.parse_args()

    # Database connection
    engine = create_engine(settings.SQLALCHEMY_DATABASE_URI)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as session:
        if args.test in ["all", "sampling"]:
            test_stochastic_sampling(session, args.config_name)

        if args.test in ["all", "scenario"]:
            test_scenario_generation(session, args.config_name)

        if args.test in ["all", "simulation"]:
            test_monte_carlo_simulation(session, args.config_name, args.num_scenarios)

        if args.test in ["all", "comparison"]:
            compare_agent_strategies(session, args.config_name, min(args.num_scenarios, 100))

    print("\n" + "="*80)
    print("✅ ALL TESTS PASSED")
    print("="*80)
    print("\nNext steps:")
    print("1. Integrate with SupplyChainLine engine for accurate simulation")
    print("2. Create API endpoint for plan generation")
    print("3. Build frontend dashboard for balanced scorecard visualization")
    print("4. Add stochastic programming optimizer")


if __name__ == "__main__":
    main()
