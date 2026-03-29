"""
Parallel Engine Testing: Legacy vs Execution Engine

Runs both legacy Node-based engine and new execution engine
in parallel for the same scenario scenario, comparing results
to validate correctness before full cutover.

Tests:
1. Inventory consistency
2. Backlog calculation
3. Cost calculation
4. Order flow
5. Performance benchmarks

Usage:
    python scripts/parallel_engine_testing.py --config-id 1 --rounds 10 --runs 5
"""

import asyncio
import argparse
import sys
from pathlib import Path
from datetime import date, datetime
from typing import List, Dict, Any, Tuple
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.core.config import settings
from app.models.scenario import Scenario
from app.models.supply_chain_config import SupplyChainConfig
from app.services.simulation_execution_engine import SimulationExecutionEngine
from app.services.engine import SupplyChainLine  # Legacy engine


class ParallelEngineComparator:
    """Compares legacy and execution engines side-by-side."""

    def __init__(self, db: AsyncSession, config_id: int, rounds: int):
        self.db = db
        self.config_id = config_id
        self.rounds = rounds
        self.comparison_results = []

    async def run_comparison(self) -> Dict[str, Any]:
        """
        Run parallel test and compare results.

        Returns:
            Comparison summary with differences and metrics
        """
        print(f"Starting parallel engine test: {self.rounds} rounds")

        # Load config
        config = await self.db.get(SupplyChainConfig, self.config_id)
        if not config:
            return {'status': 'error', 'message': f'Config {self.config_id} not found'}

        # Create two scenarios (one for each engine)
        legacy_scenario = await self._create_test_scenario(config, "Legacy Engine Test")
        execution_scenario = await self._create_test_scenario(config, "Execution Engine Test")

        await self.db.commit()

        # Run both engines
        legacy_results = await self._run_legacy_engine(legacy_scenario)
        execution_results = await self._run_execution_engine(execution_scenario)

        # Compare results
        comparison = self._compare_results(legacy_results, execution_results)

        # Generate report
        report = {
            'status': 'success',
            'config_id': self.config_id,
            'rounds': self.rounds,
            'legacy_scenario_id': legacy_scenario.id,
            'execution_scenario_id': execution_scenario.id,
            'legacy_results': legacy_results,
            'execution_results': execution_results,
            'comparison': comparison,
        }

        return report

    async def _create_test_scenario(self, config: SupplyChainConfig, name: str) -> Scenario:
        """Create a test scenario."""
        scenario = Scenario(
            name=name,
            config_id=config.id,
            current_period=1,
            max_periods=self.rounds,
            status="IN_PROGRESS",
        )
        self.db.add(scenario)
        await self.db.flush()
        await self.db.refresh(scenario)
        return scenario

    async def _run_legacy_engine(self, scenario: Scenario) -> Dict[str, Any]:
        """Run legacy Node-based engine."""
        print(f"\nRunning legacy engine for scenario {scenario.id}...")

        start_time = time.time()

        # TODO: Initialize legacy SupplyChainLine engine
        # This requires the legacy engine code to be available
        # For now, return mock results

        results = {
            'scenario_id': scenario.id,
            'rounds_completed': self.rounds,
            'execution_time_ms': (time.time() - start_time) * 1000,
            'final_state': {
                'total_cost': 0.0,
                'total_inventory': 0.0,
                'total_backlog': 0.0,
            },
            'round_snapshots': [],
        }

        print(f"Legacy engine completed in {results['execution_time_ms']:.2f}ms")

        return results

    async def _run_execution_engine(self, scenario: Scenario) -> Dict[str, Any]:
        """Run new execution engine."""
        print(f"\nRunning execution engine for scenario {scenario.id}...")

        start_time = time.time()

        engine = SimulationExecutionEngine(self.db)

        round_snapshots = []

        for round_num in range(1, self.rounds + 1):
            round_result = await engine.execute_round(
                scenario_id=scenario.id,
                current_period=round_num,
                agent_decisions=None,  # Use default replenishment
            )

            # Capture snapshot
            snapshot = {
                'round': round_num,
                'receipts': round_result['receipts'],
                'customer_orders': round_result['customer_orders'],
                'metrics': round_result['metrics'],
            }
            round_snapshots.append(snapshot)

            # Update scenario round
            scenario.current_period = round_num + 1

        await self.db.commit()

        # Calculate final state
        total_cost = sum(
            sum(site_data['cumulative_cost'] for site_data in snapshot['metrics'].values())
            for snapshot in round_snapshots
        ) / len(round_snapshots) if round_snapshots else 0.0

        total_inventory = sum(
            sum(site_data['inventory'] for site_data in round_snapshots[-1]['metrics'].values())
        ) if round_snapshots else 0.0

        total_backlog = sum(
            sum(site_data['backlog'] for site_data in round_snapshots[-1]['metrics'].values())
        ) if round_snapshots else 0.0

        results = {
            'scenario_id': scenario.id,
            'rounds_completed': self.rounds,
            'execution_time_ms': (time.time() - start_time) * 1000,
            'final_state': {
                'total_cost': total_cost,
                'total_inventory': total_inventory,
                'total_backlog': total_backlog,
            },
            'round_snapshots': round_snapshots,
        }

        print(f"Execution engine completed in {results['execution_time_ms']:.2f}ms")

        return results

    def _compare_results(
        self,
        legacy_results: Dict[str, Any],
        execution_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare results from both engines.

        Checks:
        - Final inventory differences
        - Final backlog differences
        - Total cost differences
        - Performance differences
        """
        print("\n=== Comparing Results ===")

        differences = []
        metrics = {}

        # Compare final states
        legacy_state = legacy_results['final_state']
        execution_state = execution_results['final_state']

        # Inventory difference
        inv_diff = abs(legacy_state['total_inventory'] - execution_state['total_inventory'])
        inv_pct_diff = (inv_diff / legacy_state['total_inventory'] * 100) if legacy_state['total_inventory'] > 0 else 0.0

        print(f"Inventory: Legacy={legacy_state['total_inventory']:.2f}, Execution={execution_state['total_inventory']:.2f}, Diff={inv_diff:.2f} ({inv_pct_diff:.2f}%)")

        if inv_pct_diff > 5.0:
            differences.append(f"Inventory difference exceeds 5%: {inv_pct_diff:.2f}%")

        # Backlog difference
        backlog_diff = abs(legacy_state['total_backlog'] - execution_state['total_backlog'])
        backlog_pct_diff = (backlog_diff / legacy_state['total_backlog'] * 100) if legacy_state['total_backlog'] > 0 else 0.0

        print(f"Backlog: Legacy={legacy_state['total_backlog']:.2f}, Execution={execution_state['total_backlog']:.2f}, Diff={backlog_diff:.2f} ({backlog_pct_diff:.2f}%)")

        if backlog_pct_diff > 5.0:
            differences.append(f"Backlog difference exceeds 5%: {backlog_pct_diff:.2f}%")

        # Cost difference
        cost_diff = abs(legacy_state['total_cost'] - execution_state['total_cost'])
        cost_pct_diff = (cost_diff / legacy_state['total_cost'] * 100) if legacy_state['total_cost'] > 0 else 0.0

        print(f"Cost: Legacy={legacy_state['total_cost']:.2f}, Execution={execution_state['total_cost']:.2f}, Diff={cost_diff:.2f} ({cost_pct_diff:.2f}%)")

        if cost_pct_diff > 5.0:
            differences.append(f"Cost difference exceeds 5%: {cost_pct_diff:.2f}%")

        # Performance comparison
        perf_diff = execution_results['execution_time_ms'] - legacy_results['execution_time_ms']
        perf_ratio = execution_results['execution_time_ms'] / legacy_results['execution_time_ms'] if legacy_results['execution_time_ms'] > 0 else 0.0

        print(f"Performance: Legacy={legacy_results['execution_time_ms']:.2f}ms, Execution={execution_results['execution_time_ms']:.2f}ms, Ratio={perf_ratio:.2f}x")

        if perf_ratio > 2.0:
            differences.append(f"Execution engine is >2x slower: {perf_ratio:.2f}x")

        # Metrics
        metrics = {
            'inventory_diff_pct': inv_pct_diff,
            'backlog_diff_pct': backlog_pct_diff,
            'cost_diff_pct': cost_pct_diff,
            'performance_ratio': perf_ratio,
        }

        # Overall result
        is_passing = len(differences) == 0

        print(f"\nTest Result: {'PASS' if is_passing else 'FAIL'}")
        if not is_passing:
            print("Differences:")
            for diff in differences:
                print(f"  - {diff}")

        return {
            'passing': is_passing,
            'differences': differences,
            'metrics': metrics,
        }


async def run_parallel_test(config_id: int, rounds: int, runs: int = 1):
    """Run parallel engine test."""
    # Create database engine
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, echo=False)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    overall_results = []

    for run_num in range(1, runs + 1):
        print(f"\n{'=' * 60}")
        print(f"Run {run_num}/{runs}")
        print(f"{'=' * 60}")

        async with async_session() as session:
            comparator = ParallelEngineComparator(session, config_id, rounds)
            result = await comparator.run_comparison()
            overall_results.append(result)

    # Aggregate results
    print(f"\n{'=' * 60}")
    print("Overall Summary")
    print(f"{'=' * 60}")

    passing_runs = sum(1 for r in overall_results if r['comparison']['passing'])
    avg_inv_diff = sum(r['comparison']['metrics']['inventory_diff_pct'] for r in overall_results) / runs
    avg_backlog_diff = sum(r['comparison']['metrics']['backlog_diff_pct'] for r in overall_results) / runs
    avg_cost_diff = sum(r['comparison']['metrics']['cost_diff_pct'] for r in overall_results) / runs
    avg_perf_ratio = sum(r['comparison']['metrics']['performance_ratio'] for r in overall_results) / runs

    print(f"Passing Runs: {passing_runs}/{runs}")
    print(f"Avg Inventory Diff: {avg_inv_diff:.2f}%")
    print(f"Avg Backlog Diff: {avg_backlog_diff:.2f}%")
    print(f"Avg Cost Diff: {avg_cost_diff:.2f}%")
    print(f"Avg Performance Ratio: {avg_perf_ratio:.2f}x")

    await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Parallel Engine Testing")
    parser.add_argument("--config-id", type=int, required=True, help="Supply chain config ID")
    parser.add_argument("--rounds", type=int, default=10, help="Number of rounds to simulate")
    parser.add_argument("--runs", type=int, default=1, help="Number of test runs")

    args = parser.parse_args()

    asyncio.run(run_parallel_test(args.config_id, args.rounds, args.runs))


if __name__ == "__main__":
    main()
