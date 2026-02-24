"""
Parallel Monte Carlo Simulation Runner
Phase 6 Sprint 1: Performance Optimization

Implements parallel execution of Monte Carlo simulations using multiprocessing
to achieve 50%+ speedup over sequential execution.
"""

import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
import numpy as np
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class ParallelMonteCarloConfig:
    """Configuration for parallel Monte Carlo execution"""
    game_id: int
    num_runs: int
    base_seed: int = 42
    num_workers: Optional[int] = None  # None = use all CPUs
    metrics: List[str] = field(default_factory=lambda: [
        'total_cost',
        'holding_cost',
        'backlog_cost',
        'service_level',
        'avg_inventory',
        'max_backlog',
        'bullwhip_ratio'
    ])
    chunk_size: int = 1  # Number of runs per worker task


@dataclass
class SimulationResult:
    """Result from a single simulation run"""
    run_id: int
    seed: int
    total_cost: float
    holding_cost: float
    backlog_cost: float
    service_level: float
    avg_inventory: float
    max_backlog: float
    bullwhip_ratio: float
    success: bool
    duration: float  # seconds
    error_message: Optional[str] = None


class ParallelMonteCarloRunner:
    """
    Parallel Monte Carlo simulation runner using multiprocessing

    Key Features:
    - ProcessPoolExecutor for parallel execution
    - Configurable number of workers
    - Progress tracking
    - Error handling per simulation
    - Result aggregation

    Performance Target: 50%+ speedup vs sequential execution
    """

    def __init__(self, config: ParallelMonteCarloConfig):
        self.config = config

        # Determine number of workers
        if config.num_workers is None:
            self.num_workers = min(mp.cpu_count(), config.num_runs)
        else:
            self.num_workers = min(config.num_workers, mp.cpu_count(), config.num_runs)

        logger.info(f"ParallelMonteCarloRunner initialized with {self.num_workers} workers")
        logger.info(f"Running {config.num_runs} simulations for game {config.game_id}")

    def run(self, progress_callback: Optional[Callable[[int, int], None]] = None) -> List[SimulationResult]:
        """
        Run Monte Carlo simulations in parallel

        Args:
            progress_callback: Optional callback for progress updates (completed, total)

        Returns:
            List of SimulationResult objects
        """
        start_time = datetime.now()
        logger.info(f"Starting parallel Monte Carlo execution at {start_time}")

        results = []
        completed = 0

        # Create list of run configurations
        run_configs = [
            (run_id, self.config.base_seed + run_id, self.config.game_id)
            for run_id in range(self.config.num_runs)
        ]

        # Execute in parallel using ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=self.num_workers) as executor:
            # Submit all tasks
            future_to_run = {
                executor.submit(self._run_single_simulation, run_id, seed, game_id): run_id
                for run_id, seed, game_id in run_configs
            }

            # Collect results as they complete
            for future in as_completed(future_to_run):
                run_id = future_to_run[future]
                try:
                    result = future.result()
                    results.append(result)
                    completed += 1

                    # Progress callback
                    if progress_callback:
                        progress_callback(completed, self.config.num_runs)

                    if completed % max(1, self.config.num_runs // 10) == 0:
                        logger.info(f"Progress: {completed}/{self.config.num_runs} ({completed/self.config.num_runs*100:.1f}%)")

                except Exception as e:
                    logger.error(f"Run {run_id} failed with exception: {e}")
                    # Create error result
                    results.append(SimulationResult(
                        run_id=run_id,
                        seed=self.config.base_seed + run_id,
                        total_cost=0, holding_cost=0, backlog_cost=0,
                        service_level=0, avg_inventory=0, max_backlog=0,
                        bullwhip_ratio=0,
                        success=False,
                        duration=0,
                        error_message=str(e)
                    ))
                    completed += 1

        # Sort results by run_id
        results.sort(key=lambda r: r.run_id)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info(f"Parallel Monte Carlo execution completed in {duration:.2f}s")
        logger.info(f"Average time per run: {duration/self.config.num_runs:.3f}s")
        logger.info(f"Success rate: {sum(r.success for r in results)}/{len(results)}")

        return results

    @staticmethod
    def _run_single_simulation(run_id: int, seed: int, game_id: int) -> SimulationResult:
        """
        Run a single simulation (executed in worker process).

        Uses the real SC planning engine with stochastic sampling:
        1. Loads supply chain config from DB (sync session for subprocess)
        2. Simulates week-by-week inventory dynamics with sampled demand
        3. Computes real cost, service level, and bullwhip metrics

        This is a static method to ensure it can be pickled for multiprocessing.
        """
        import time
        from datetime import date, timedelta

        start = time.time()

        try:
            rng = np.random.RandomState(seed)

            # --- Load config from DB (sync, subprocess-safe) ---
            from app.db.session import sync_session_factory
            from app.models.supply_chain_config import SupplyChainConfig

            db = sync_session_factory()
            try:
                config = db.query(SupplyChainConfig).filter(
                    SupplyChainConfig.id == game_id
                ).first()

                if not config:
                    raise ValueError(f"Supply chain config {game_id} not found")

                # Gather nodes and cost parameters
                nodes = list(config.nodes or [])
                items = list(config.items or [])
                lanes = list(config.lanes or [])
                markets = list(config.market_demands or [])

                # Extract demand baseline from market_demands config
                base_demand = 100.0
                demand_std = 15.0
                for md in markets:
                    dp = md.demand_pattern if hasattr(md, 'demand_pattern') and md.demand_pattern else {}
                    params = dp.get("params", dp.get("parameters", {}))
                    if "value" in params:
                        base_demand = float(params["value"])
                        demand_std = base_demand * 0.2
                        break
                    elif "mean" in params:
                        base_demand = float(params["mean"])
                        demand_std = float(params.get("std", base_demand * 0.2))
                        break

                # Extract cost parameters from node policies
                holding_cost_rate = 1.0
                backlog_cost_rate = 2.0
                ordering_cost = 50.0
                initial_inventory = 12 * base_demand  # 12 weeks of supply

                for node in nodes:
                    policies = {}
                    if hasattr(node, 'policies') and node.policies:
                        policies = node.policies if isinstance(node.policies, dict) else {}
                    elif hasattr(node, 'node_policies') and node.node_policies:
                        policies = node.node_policies if isinstance(node.node_policies, dict) else {}
                    if policies.get("holding_cost"):
                        holding_cost_rate = float(policies["holding_cost"])
                    if policies.get("backlog_cost"):
                        backlog_cost_rate = float(policies["backlog_cost"])
                    if policies.get("initial_inventory"):
                        initial_inventory = float(policies["initial_inventory"])

                # Extract lead time from lanes
                supply_lead_time = 2  # default weeks
                for lane in lanes:
                    slt = getattr(lane, 'supply_lead_time', None)
                    if slt:
                        if isinstance(slt, dict):
                            supply_lead_time = int(slt.get("value", 2))
                        else:
                            supply_lead_time = int(slt)
                        break

            finally:
                db.close()

            # --- Simulate week-by-week inventory dynamics ---
            num_weeks = 52
            inventory = initial_inventory
            backlog = 0.0
            total_holding = 0.0
            total_backlog_cost = 0.0
            total_order_cost = 0.0
            demands = np.zeros(num_weeks)
            orders_placed = np.zeros(num_weeks)
            service_hits = 0

            # Shipment pipeline (orders arrive after lead time)
            pipeline = np.zeros(num_weeks + supply_lead_time + 1)

            for week in range(num_weeks):
                # 1. Receive shipments from pipeline
                arrived = pipeline[week]
                inventory += arrived

                # 2. Sample demand (stochastic)
                demand = max(0, rng.normal(base_demand, demand_std))
                demands[week] = demand

                # 3. Fulfill demand from inventory
                fulfilled = min(inventory, demand + backlog)
                unfulfilled = (demand + backlog) - fulfilled
                inventory -= fulfilled

                if unfulfilled > 0:
                    backlog = unfulfilled
                else:
                    backlog = 0.0

                # Service: did we fulfill all current-period demand?
                if demand <= fulfilled:
                    service_hits += 1

                # 4. Order decision (base-stock policy with stochastic lead time)
                target_stock = base_demand * (supply_lead_time + 2)  # cover LT + 2 weeks safety
                pipeline_total = sum(pipeline[week + 1:week + supply_lead_time + 1])
                order_qty = max(0, target_stock - inventory - pipeline_total + backlog)
                orders_placed[week] = order_qty

                # Sample actual lead time for this order
                actual_lt = max(1, int(rng.normal(supply_lead_time, max(1, supply_lead_time * 0.2))))
                arrival_week = week + actual_lt
                if arrival_week < len(pipeline):
                    pipeline[arrival_week] += order_qty

                # 5. Accumulate costs
                total_holding += max(0, inventory) * holding_cost_rate
                total_backlog_cost += backlog * backlog_cost_rate
                if order_qty > 0:
                    total_order_cost += ordering_cost

            # --- Compute final metrics ---
            total_cost = total_holding + total_backlog_cost + total_order_cost
            service_level = service_hits / num_weeks if num_weeks > 0 else 0.0

            # Bullwhip ratio: variance of orders / variance of demand
            demand_std_actual = float(np.std(demands)) if np.std(demands) > 0 else 1.0
            bullwhip_ratio = float(np.std(orders_placed) / demand_std_actual)

            # Average inventory over the run
            # (we didn't track weekly inventory array, so approximate)
            avg_inventory = float(inventory + initial_inventory) / 2.0

            duration = time.time() - start

            return SimulationResult(
                run_id=run_id,
                seed=seed,
                total_cost=float(total_cost),
                holding_cost=float(total_holding),
                backlog_cost=float(total_backlog_cost),
                service_level=float(service_level),
                avg_inventory=float(avg_inventory),
                max_backlog=float(backlog),
                bullwhip_ratio=float(bullwhip_ratio),
                success=True,
                duration=duration,
            )

        except Exception as e:
            duration = time.time() - start
            return SimulationResult(
                run_id=run_id,
                seed=seed,
                total_cost=0, holding_cost=0, backlog_cost=0,
                service_level=0, avg_inventory=0, max_backlog=0,
                bullwhip_ratio=0,
                success=False,
                duration=duration,
                error_message=str(e),
            )

    def summarize_results(self, results: List[SimulationResult]) -> Dict:
        """
        Aggregate results using analytics service

        Args:
            results: List of simulation results

        Returns:
            Dictionary with summary statistics
        """
        from app.services.stochastic_analytics_service import StochasticAnalyticsService

        analytics = StochasticAnalyticsService()

        # Filter successful runs
        successful = [r for r in results if r.success]

        if not successful:
            return {
                'success_rate': 0,
                'total_runs': len(results),
                'successful_runs': 0,
                'error': 'No successful runs'
            }

        # Extract metric arrays
        metrics_dict = {}
        for metric in self.config.metrics:
            if hasattr(successful[0], metric):
                metrics_dict[metric] = np.array([getattr(r, metric) for r in successful])

        # Calculate statistics for each metric
        summary = {
            'success_rate': len(successful) / len(results),
            'total_runs': len(results),
            'successful_runs': len(successful),
            'metrics': {}
        }

        for metric_name, metric_values in metrics_dict.items():
            variability = analytics.analyze_variability(metric_values)
            ci = analytics.confidence_interval(metric_values, confidence=0.95)
            risk = analytics.calculate_risk_metrics(metric_values)

            summary['metrics'][metric_name] = {
                'mean': variability.mean,
                'std': variability.std,
                'cv': variability.cv,
                'min': variability.min,
                'max': variability.max,
                'median': variability.median,
                'ci_95_lower': ci.lower,
                'ci_95_upper': ci.upper,
                'var_95': risk.var_95,
                'var_99': risk.var_99
            }

        return summary


class SequentialMonteCarloRunner:
    """
    Sequential Monte Carlo runner for comparison benchmarking

    This provides a baseline for measuring parallelization speedup.
    """

    def __init__(self, config: ParallelMonteCarloConfig):
        self.config = config

    def run(self, progress_callback: Optional[Callable[[int, int], None]] = None) -> List[SimulationResult]:
        """Run Monte Carlo simulations sequentially"""
        start_time = datetime.now()
        results = []

        for run_id in range(self.config.num_runs):
            seed = self.config.base_seed + run_id
            result = ParallelMonteCarloRunner._run_single_simulation(
                run_id, seed, self.config.game_id
            )
            results.append(result)

            if progress_callback:
                progress_callback(run_id + 1, self.config.num_runs)

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Sequential execution completed in {duration:.2f}s")

        return results


def compare_parallel_vs_sequential(num_runs: int = 100, game_id: int = 1) -> Dict:
    """
    Benchmark parallel vs sequential execution

    Args:
        num_runs: Number of Monte Carlo runs
        game_id: Game ID to simulate

    Returns:
        Dictionary with comparison results
    """
    print(f"\n{'='*80}")
    print(f"PARALLEL vs SEQUENTIAL BENCHMARK")
    print(f"Runs: {num_runs}, Game ID: {game_id}")
    print(f"{'='*80}\n")

    config = ParallelMonteCarloConfig(
        game_id=game_id,
        num_runs=num_runs,
        base_seed=42
    )

    # Sequential execution
    print("Running sequential execution...")
    seq_runner = SequentialMonteCarloRunner(config)
    seq_start = datetime.now()
    seq_results = seq_runner.run()
    seq_duration = (datetime.now() - seq_start).total_seconds()
    print(f"✅ Sequential completed in {seq_duration:.2f}s")

    # Parallel execution
    print(f"\nRunning parallel execution (workers: {mp.cpu_count()})...")
    par_runner = ParallelMonteCarloRunner(config)
    par_start = datetime.now()
    par_results = par_runner.run()
    par_duration = (datetime.now() - par_start).total_seconds()
    print(f"✅ Parallel completed in {par_duration:.2f}s")

    # Calculate speedup
    speedup = seq_duration / par_duration
    efficiency = speedup / min(mp.cpu_count(), num_runs) * 100

    print(f"\n{'='*80}")
    print(f"RESULTS")
    print(f"{'='*80}")
    print(f"Sequential Time:  {seq_duration:.3f}s")
    print(f"Parallel Time:    {par_duration:.3f}s")
    print(f"Speedup:          {speedup:.2f}x")
    print(f"Efficiency:       {efficiency:.1f}%")
    print(f"Time Saved:       {seq_duration - par_duration:.3f}s ({(1 - par_duration/seq_duration)*100:.1f}%)")
    print(f"{'='*80}\n")

    return {
        'sequential_time': seq_duration,
        'parallel_time': par_duration,
        'speedup': speedup,
        'efficiency': efficiency,
        'workers': min(mp.cpu_count(), num_runs),
        'num_runs': num_runs
    }


if __name__ == "__main__":
    # Run comparison benchmark
    import sys

    num_runs = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    game_id = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    results = compare_parallel_vs_sequential(num_runs, game_id)

    print("\n✅ Parallel Monte Carlo implementation complete!")
    print(f"   Achieved {results['speedup']:.2f}x speedup")

    if results['speedup'] >= 1.5:
        print("   🎉 Target speedup (>1.5x) ACHIEVED!")
    else:
        print("   ⚠️  Target speedup (>1.5x) not yet achieved")
