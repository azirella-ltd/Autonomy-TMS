#!/usr/bin/env python3
"""
Benchmark Parallel Monte Carlo Performance
Sprint 7: Performance Optimization

Compares sequential vs parallel Monte Carlo execution and measures speedup.

Usage:
    python scripts/benchmark_parallel_monte_carlo.py [--scenarios 100] [--horizon 52]
"""

import sys
import os
import argparse
import asyncio
from datetime import date, datetime
import multiprocessing as mp

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.monte_carlo.parallel_engine import (
    ParallelMonteCarloEngine,
    compare_sequential_vs_parallel
)
from app.services.monte_carlo.engine import MonteCarloEngine
from app.models.monte_carlo import MonteCarloRun, SimulationStatus
from app.db.session import SessionLocal


async def create_test_runs(num_runs: int = 2) -> list[int]:
    """Create test MonteCarloRun records"""
    async with SessionLocal() as db:
        run_ids = []

        for i in range(num_runs):
            run = MonteCarloRun(
                config_id=1,  # Assuming Default TBG config exists
                customer_id=1,
                num_scenarios=0,  # Will be set by engine
                status=SimulationStatus.PENDING,
                start_date=date.today(),
                planning_horizon_weeks=52
            )
            db.add(run)
            await db.flush()
            run_ids.append(run.id)

        await db.commit()
        return run_ids


async def benchmark_sequential(
    run_id: int,
    config_id: int,
    customer_id: int,
    num_scenarios: int,
    planning_horizon_weeks: int
) -> float:
    """Run sequential benchmark"""
    print("\n" + "="*80)
    print("🐌 SEQUENTIAL MONTE CARLO EXECUTION")
    print("="*80)

    engine = MonteCarloEngine(
        run_id=run_id,
        config_id=config_id,
        customer_id=customer_id,
        num_scenarios=num_scenarios,
        random_seed=42
    )

    start_time = datetime.now()
    await engine.run_simulation(date.today(), planning_horizon_weeks)
    duration = (datetime.now() - start_time).total_seconds()

    print(f"\n✅ Sequential execution completed in {duration:.2f}s")
    print(f"   Throughput: {num_scenarios / duration:.1f} scenarios/sec")

    return duration


async def benchmark_parallel(
    run_id: int,
    config_id: int,
    customer_id: int,
    num_scenarios: int,
    planning_horizon_weeks: int,
    num_workers: int = None
) -> float:
    """Run parallel benchmark"""
    print("\n" + "="*80)
    print(f"⚡ PARALLEL MONTE CARLO EXECUTION ({num_workers or mp.cpu_count()} workers)")
    print("="*80)

    engine = ParallelMonteCarloEngine(
        run_id=run_id,
        config_id=config_id,
        customer_id=customer_id,
        num_scenarios=num_scenarios,
        random_seed=42,
        num_workers=num_workers
    )

    start_time = datetime.now()
    results = await engine.run_parallel_simulation(
        date.today(),
        planning_horizon_weeks
    )
    duration = (datetime.now() - start_time).total_seconds()

    successful = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)

    print(f"\n✅ Parallel execution completed in {duration:.2f}s")
    print(f"   Successful: {successful}/{num_scenarios}")
    print(f"   Failed: {failed}/{num_scenarios}")
    print(f"   Throughput: {num_scenarios / duration:.1f} scenarios/sec")

    return duration


def print_comparison(seq_time: float, par_time: float, num_scenarios: int):
    """Print comparison results"""
    speedup = seq_time / par_time
    efficiency = (speedup / mp.cpu_count()) * 100
    time_saved = seq_time - par_time
    percent_saved = (1 - par_time / seq_time) * 100

    print("\n" + "="*80)
    print("📊 PERFORMANCE COMPARISON")
    print("="*80)
    print(f"Configuration:")
    print(f"  Scenarios:        {num_scenarios}")
    print(f"  CPU Cores:        {mp.cpu_count()}")
    print()
    print(f"Sequential:")
    print(f"  Time:             {seq_time:.2f}s")
    print(f"  Throughput:       {num_scenarios / seq_time:.1f} scenarios/sec")
    print()
    print(f"Parallel:")
    print(f"  Time:             {par_time:.2f}s")
    print(f"  Throughput:       {num_scenarios / par_time:.1f} scenarios/sec")
    print()
    print(f"Improvement:")
    print(f"  Speedup:          {speedup:.2f}x")
    print(f"  Efficiency:       {efficiency:.1f}%")
    print(f"  Time Saved:       {time_saved:.2f}s ({percent_saved:.1f}%)")
    print("="*80)

    # Performance assessment
    if speedup >= 3.0:
        print("🎉 EXCELLENT: Speedup ≥3x achieved!")
    elif speedup >= 2.0:
        print("✅ GOOD: Speedup ≥2x achieved")
    elif speedup >= 1.5:
        print("✓ MODERATE: Speedup ≥1.5x achieved")
    else:
        print("⚠️  WARNING: Speedup below 1.5x target")

    print()

    # Cost analysis (assuming $0.10 per CPU-hour)
    cost_per_cpu_hour = 0.10
    seq_cost = (seq_time / 3600) * cost_per_cpu_hour
    par_cost = (par_time / 3600) * cost_per_cpu_hour * mp.cpu_count()
    cost_savings = seq_cost - par_cost

    print("💰 Cost Analysis (assuming $0.10/CPU-hour):")
    print(f"  Sequential cost:  ${seq_cost:.4f}")
    print(f"  Parallel cost:    ${par_cost:.4f}")
    if cost_savings > 0:
        print(f"  Savings:          ${cost_savings:.4f} ({cost_savings/seq_cost*100:.1f}%)")
    else:
        print(f"  Additional cost:  ${abs(cost_savings):.4f}")


async def main(args):
    """Main benchmark execution"""
    print("\n" + "="*80)
    print("PARALLEL MONTE CARLO BENCHMARK")
    print("="*80)
    print(f"Scenarios:        {args.scenarios}")
    print(f"Planning Horizon: {args.horizon} weeks")
    print(f"Config ID:        {args.config_id}")
    print(f"Tenant ID:           {args.customer_id}")
    print(f"CPU Cores:        {mp.cpu_count()}")
    print("="*80)

    # Create test run records
    print("\n📝 Creating test run records...")
    run_ids = await create_test_runs(num_runs=2)
    print(f"✅ Created runs: {run_ids}")

    # Sequential benchmark
    seq_time = await benchmark_sequential(
        run_id=run_ids[0],
        config_id=args.config_id,
        customer_id=args.customer_id,
        num_scenarios=args.scenarios,
        planning_horizon_weeks=args.horizon
    )

    # Parallel benchmark
    par_time = await benchmark_parallel(
        run_id=run_ids[1],
        config_id=args.config_id,
        customer_id=args.customer_id,
        num_scenarios=args.scenarios,
        planning_horizon_weeks=args.horizon,
        num_workers=args.workers
    )

    # Print comparison
    print_comparison(seq_time, par_time, args.scenarios)

    print("\n✅ Benchmark complete!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Benchmark parallel Monte Carlo performance"
    )
    parser.add_argument(
        "--scenarios",
        type=int,
        default=100,
        help="Number of scenarios to simulate (default: 100)"
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=52,
        help="Planning horizon in weeks (default: 52)"
    )
    parser.add_argument(
        "--config-id",
        type=int,
        default=1,
        help="Supply chain config ID (default: 1)"
    )
    parser.add_argument(
        "--customer-id",
        type=int,
        default=1,
        help="Tenant ID (default: 1)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of parallel workers (default: auto-detect)"
    )

    args = parser.parse_args()

    # Run benchmark
    asyncio.run(main(args))
