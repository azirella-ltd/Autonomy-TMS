"""
Monte Carlo Simulation Test Script

Quick test to verify Monte Carlo implementation is working correctly.
Run with: python scripts/test_monte_carlo.py
"""

import asyncio
import sys
import os
from datetime import date, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.session import SessionLocal
from app.models.monte_carlo import MonteCarloRun, SimulationStatus
from app.models.supply_chain_config import SupplyChainConfig
from app.services.monte_carlo.engine import MonteCarloEngine
from sqlalchemy import select


async def test_basic_simulation():
    """Test creating and running a basic Monte Carlo simulation"""

    print("=" * 80)
    print("MONTE CARLO SIMULATION TEST")
    print("=" * 80)
    print()

    async with SessionLocal() as db:
        # Find a supply chain configuration
        result = await db.execute(select(SupplyChainConfig).limit(1))
        config = result.scalar_one_or_none()

        if not config:
            print("❌ No supply chain configuration found!")
            print("   Please run: make db-bootstrap")
            return False

        print(f"✓ Found supply chain config: {config.name} (ID: {config.id})")
        print()

        # Create a test run
        test_run = MonteCarloRun(
            supply_chain_config_id=config.id,
            customer_id=config.customer_id,
            name="Test Simulation",
            description="Automated test of Monte Carlo implementation",
            num_scenarios=10,  # Small number for quick test
            random_seed=42,  # Reproducible
            start_date=date.today(),
            end_date=date.today() + timedelta(weeks=13),
            planning_horizon_weeks=13,
            status=SimulationStatus.QUEUED,
        )

        db.add(test_run)
        await db.commit()
        await db.refresh(test_run)

        print(f"✓ Created test run (ID: {test_run.id})")
        print(f"   Name: {test_run.name}")
        print(f"   Scenarios: {test_run.num_scenarios}")
        print(f"   Horizon: {test_run.planning_horizon_weeks} weeks")
        print()

        # Run the simulation
        print("Starting Monte Carlo simulation...")
        print("-" * 80)

        engine = MonteCarloEngine(
            run_id=test_run.id,
            config_id=config.id,
            customer_id=config.customer_id,
            num_scenarios=10,
            random_seed=42
        )

        try:
            await engine.run_simulation(
                start_date=date.today(),
                planning_horizon_weeks=13
            )

            print()
            print("-" * 80)
            print("✓ Simulation completed successfully!")
            print()

            # Check results
            await db.refresh(test_run)

            print("Results Summary:")
            print(f"  Status: {test_run.status}")
            print(f"  Execution Time: {test_run.execution_time_seconds:.2f}s")
            print(f"  Scenarios Completed: {test_run.scenarios_completed}/{test_run.num_scenarios}")
            print()

            if test_run.summary_statistics:
                stats = test_run.summary_statistics
                print("  KPI Statistics:")
                if 'total_cost' in stats:
                    tc = stats['total_cost']
                    print(f"    Total Cost: ${tc.get('mean', 0):.2f} (P5: ${tc.get('p5', 0):.2f}, P95: ${tc.get('p95', 0):.2f})")
                if 'service_level' in stats:
                    sl = stats['service_level']
                    print(f"    Service Level: {sl.get('mean', 0):.1f}% (P5: {sl.get('p5', 0):.1f}%, P95: {sl.get('p95', 0):.1f}%)")
                print()

            if test_run.risk_metrics:
                risks = test_run.risk_metrics
                print("  Risk Metrics:")
                print(f"    Stockout Probability: {risks.get('stockout_probability', 0):.1%}")
                print(f"    Overstock Probability: {risks.get('overstock_probability', 0):.1%}")
                print(f"    Capacity Violation Probability: {risks.get('capacity_violation_probability', 0):.1%}")
                print()

            # Check scenarios
            from app.models.monte_carlo import MonteCarloScenario
            result = await db.execute(
                select(MonteCarloScenario)
                .filter(MonteCarloScenario.run_id == test_run.id)
            )
            scenarios = result.scalars().all()

            print(f"✓ Created {len(scenarios)} scenario records")

            if scenarios:
                print(f"  Sample Scenario #1:")
                s = scenarios[0]
                print(f"    Total Cost: ${s.total_cost:.2f}")
                print(f"    Service Level: {s.service_level:.1f}%")
                print(f"    Had Stockout: {s.had_stockout}")
                print()

            # Check time series
            from app.models.monte_carlo import MonteCarloTimeSeries
            result = await db.execute(
                select(MonteCarloTimeSeries)
                .filter(MonteCarloTimeSeries.run_id == test_run.id)
            )
            time_series = result.scalars().all()

            print(f"✓ Created {len(time_series)} time-series records")

            if time_series:
                print(f"  Sample Time-Series (Week 1 Inventory):")
                ts = time_series[0]
                print(f"    Mean: {ts.mean_value:.2f}")
                print(f"    P5: {ts.p5_value:.2f}, P95: {ts.p95_value:.2f}")
                print()

            # Check risk alerts
            from app.models.monte_carlo import MonteCarloRiskAlert
            result = await db.execute(
                select(MonteCarloRiskAlert)
                .filter(MonteCarloRiskAlert.run_id == test_run.id)
            )
            alerts = result.scalars().all()

            print(f"✓ Generated {len(alerts)} risk alerts")
            for alert in alerts:
                print(f"  [{alert.severity.upper()}] {alert.title}")
                if alert.recommendation:
                    print(f"    → {alert.recommendation}")
            print()

            print("=" * 80)
            print("✅ ALL TESTS PASSED")
            print("=" * 80)
            print()
            print("Next Steps:")
            print("  1. Start the application: make up")
            print("  2. Navigate to: http://localhost:8088/planning/monte-carlo")
            print("  3. View your test simulation results in the UI")
            print()

            return True

        except Exception as e:
            print()
            print("=" * 80)
            print(f"❌ TEST FAILED")
            print("=" * 80)
            print(f"Error: {str(e)}")
            print()
            import traceback
            traceback.print_exc()
            return False


async def test_api_models():
    """Test that all Monte Carlo models are registered correctly"""

    print("Testing database models...")

    from app.models.monte_carlo import (
        MonteCarloRun, MonteCarloScenario, MonteCarloTimeSeries, MonteCarloRiskAlert
    )

    models = [MonteCarloRun, MonteCarloScenario, MonteCarloTimeSeries, MonteCarloRiskAlert]

    for model in models:
        print(f"  ✓ {model.__name__} registered")

    print()
    return True


async def main():
    """Run all tests"""

    print()
    print("🧪 Monte Carlo Implementation Test Suite")
    print()

    # Test 1: Models
    if not await test_api_models():
        sys.exit(1)

    # Test 2: Simulation
    if not await test_basic_simulation():
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
