#!/usr/bin/env python3
"""
Performance Benchmarking Suite
Phase 6 Sprint 1: Performance Optimization

Benchmarks:
1. Monte Carlo execution time
2. Analytics service performance
3. Distribution sampling performance
4. Database query performance
"""

import sys
import time
import numpy as np
from pathlib import Path
from typing import Dict, List
from dataclasses import dataclass
import statistics

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.stochastic import DistributionEngine
from app.services.stochastic_analytics_service import StochasticAnalyticsService


@dataclass
class BenchmarkResult:
    """Result of a single benchmark"""
    name: str
    iterations: int
    total_time: float
    avg_time: float
    min_time: float
    max_time: float
    std_time: float
    throughput: float  # operations per second


class PerformanceBenchmark:
    """Performance benchmarking suite"""

    def __init__(self):
        self.results: List[BenchmarkResult] = []
        self.engine = DistributionEngine(seed=42)
        self.analytics = StochasticAnalyticsService()

    def benchmark(self, name: str, func, iterations: int = 100):
        """Run a benchmark and record results"""
        print(f"\n{'='*80}")
        print(f"Benchmark: {name}")
        print(f"Iterations: {iterations}")
        print(f"{'='*80}")

        times = []
        for i in range(iterations):
            start = time.time()
            func()
            end = time.time()
            times.append(end - start)

            if (i + 1) % max(1, iterations // 10) == 0:
                print(f"Progress: {i+1}/{iterations} ({(i+1)/iterations*100:.1f}%)")

        total_time = sum(times)
        avg_time = statistics.mean(times)
        min_time = min(times)
        max_time = max(times)
        std_time = statistics.stdev(times) if len(times) > 1 else 0
        throughput = iterations / total_time

        result = BenchmarkResult(
            name=name,
            iterations=iterations,
            total_time=total_time,
            avg_time=avg_time,
            min_time=min_time,
            max_time=max_time,
            std_time=std_time,
            throughput=throughput
        )

        self.results.append(result)
        self.print_result(result)
        return result

    def print_result(self, result: BenchmarkResult):
        """Print benchmark result"""
        print(f"\nResults:")
        print(f"  Total Time:    {result.total_time:.3f}s")
        print(f"  Average Time:  {result.avg_time*1000:.3f}ms")
        print(f"  Min Time:      {result.min_time*1000:.3f}ms")
        print(f"  Max Time:      {result.max_time*1000:.3f}ms")
        print(f"  Std Dev:       {result.std_time*1000:.3f}ms")
        print(f"  Throughput:    {result.throughput:.2f} ops/sec")

    # ========================================================================
    # Distribution Sampling Benchmarks
    # ========================================================================

    def bench_normal_sampling(self):
        """Benchmark normal distribution sampling"""
        config = {
            'var': {
                'type': 'normal',
                'mean': 100.0,
                'stddev': 15.0,
                'min': 50.0,
                'max': 150.0
            }
        }

        def sample():
            self.engine.sample(config, size=1000)

        self.benchmark("Normal Distribution Sampling (1000 samples)", sample, iterations=100)

    def bench_mixture_sampling(self):
        """Benchmark mixture distribution sampling"""
        config = {
            'var': {
                'type': 'mixture',
                'components': [
                    {
                        'weight': 0.9,
                        'distribution': {'type': 'normal', 'mean': 7, 'stddev': 1}
                    },
                    {
                        'weight': 0.1,
                        'distribution': {'type': 'normal', 'mean': 30, 'stddev': 5}
                    }
                ]
            }
        }

        def sample():
            self.engine.sample(config, size=1000)

        self.benchmark("Mixture Distribution Sampling (1000 samples)", sample, iterations=100)

    def bench_empirical_sampling(self):
        """Benchmark empirical distribution sampling"""
        config = {
            'var': {
                'type': 'empirical_continuous',
                'samples': list(np.random.lognormal(2, 0.5, 500))
            }
        }

        def sample():
            self.engine.sample(config, size=1000)

        self.benchmark("Empirical Distribution Sampling (1000 samples)", sample, iterations=50)

    # ========================================================================
    # Analytics Service Benchmarks
    # ========================================================================

    def bench_variability_analysis(self):
        """Benchmark variability analysis"""
        samples = np.random.normal(100, 15, 1000)

        def analyze():
            self.analytics.analyze_variability(samples)

        self.benchmark("Variability Analysis (1000 samples)", analyze, iterations=1000)

    def bench_variability_analysis_large(self):
        """Benchmark variability analysis with large dataset"""
        samples = np.random.normal(100, 15, 10000)

        def analyze():
            self.analytics.analyze_variability(samples)

        self.benchmark("Variability Analysis (10000 samples)", analyze, iterations=500)

    def bench_confidence_interval(self):
        """Benchmark confidence interval calculation"""
        samples = np.random.normal(100, 15, 1000)

        def calc_ci():
            self.analytics.confidence_interval(samples, confidence=0.95)

        self.benchmark("Confidence Interval (1000 samples)", calc_ci, iterations=1000)

    def bench_bootstrap_ci(self):
        """Benchmark bootstrap confidence interval"""
        samples = np.random.exponential(10, 100)

        def calc_bootstrap():
            self.analytics.bootstrap_confidence_interval(
                samples,
                statistic_func=np.mean,
                confidence=0.95,
                n_bootstrap=1000
            )

        self.benchmark("Bootstrap CI (100 samples, 1000 bootstraps)", calc_bootstrap, iterations=50)

    def bench_risk_metrics(self):
        """Benchmark risk metrics calculation"""
        samples = np.random.lognormal(9, 0.3, 1000)

        def calc_risk():
            self.analytics.calculate_risk_metrics(samples)

        self.benchmark("Risk Metrics (1000 samples)", calc_risk, iterations=1000)

    def bench_distribution_fit(self):
        """Benchmark distribution fit testing"""
        samples = np.random.normal(0, 1, 1000)

        def test_fit():
            self.analytics.kolmogorov_smirnov_test(samples, distribution='norm')

        self.benchmark("K-S Distribution Fit Test (1000 samples)", test_fit, iterations=500)

    def bench_scenario_comparison(self):
        """Benchmark scenario comparison"""
        scenarios = {
            'Baseline': np.random.normal(10000, 1500, 100),
            'Optimized': np.random.normal(9000, 1200, 100),
            'Risky': np.random.normal(11000, 2500, 100)
        }

        def compare():
            self.analytics.compare_scenarios(scenarios, metric='total_cost')

        self.benchmark("Scenario Comparison (3 scenarios, 100 samples each)", compare, iterations=200)

    # ========================================================================
    # Monte Carlo Benchmarks
    # ========================================================================

    def bench_monte_carlo_small(self):
        """Benchmark small Monte Carlo simulation"""
        # Simulate running 10 Monte Carlo runs
        def run_mc():
            for _ in range(10):
                samples = np.random.normal(100, 15, 52)  # 52 weeks
                self.analytics.analyze_variability(samples)

        self.benchmark("Monte Carlo Simulation (10 runs)", run_mc, iterations=20)

    def bench_monte_carlo_medium(self):
        """Benchmark medium Monte Carlo simulation"""
        # Simulate running 50 Monte Carlo runs
        def run_mc():
            for _ in range(50):
                samples = np.random.normal(100, 15, 52)  # 52 weeks
                self.analytics.analyze_variability(samples)

        self.benchmark("Monte Carlo Simulation (50 runs)", run_mc, iterations=5)

    # ========================================================================
    # Summary and Reporting
    # ========================================================================

    def print_summary(self):
        """Print summary of all benchmarks"""
        print(f"\n{'='*80}")
        print("BENCHMARK SUMMARY")
        print(f"{'='*80}")
        print(f"\n{'Benchmark':<60} {'Avg Time':<15} {'Throughput':<15}")
        print(f"{'-'*60} {'-'*15} {'-'*15}")

        for result in self.results:
            print(f"{result.name:<60} {result.avg_time*1000:>10.3f} ms  {result.throughput:>10.2f} ops/s")

        print(f"\n{'='*80}")
        print(f"Total benchmarks: {len(self.results)}")
        print(f"{'='*80}\n")

    def export_results(self, filename: str = "benchmark_results.txt"):
        """Export results to file"""
        with open(filename, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write("PERFORMANCE BENCHMARK RESULTS\n")
            f.write("Phase 6 Sprint 1: Performance Optimization\n")
            f.write("=" * 80 + "\n\n")

            for result in self.results:
                f.write(f"Benchmark: {result.name}\n")
                f.write(f"  Iterations:    {result.iterations}\n")
                f.write(f"  Total Time:    {result.total_time:.3f}s\n")
                f.write(f"  Average Time:  {result.avg_time*1000:.3f}ms\n")
                f.write(f"  Min Time:      {result.min_time*1000:.3f}ms\n")
                f.write(f"  Max Time:      {result.max_time*1000:.3f}ms\n")
                f.write(f"  Std Dev:       {result.std_time*1000:.3f}ms\n")
                f.write(f"  Throughput:    {result.throughput:.2f} ops/sec\n")
                f.write("\n")

            f.write("=" * 80 + "\n")
            f.write("SUMMARY\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"{'Benchmark':<60} {'Avg Time':<15} {'Throughput':<15}\n")
            f.write(f"{'-'*60} {'-'*15} {'-'*15}\n")

            for result in self.results:
                f.write(f"{result.name:<60} {result.avg_time*1000:>10.3f} ms  {result.throughput:>10.2f} ops/s\n")

        print(f"\n✅ Results exported to {filename}")


def main():
    """Run all benchmarks"""
    print("=" * 80)
    print("PERFORMANCE BENCHMARKING SUITE")
    print("Phase 6 Sprint 1: Performance Optimization")
    print("=" * 80)

    benchmark = PerformanceBenchmark()

    # Distribution Sampling Benchmarks
    print("\n" + "=" * 80)
    print("DISTRIBUTION SAMPLING BENCHMARKS")
    print("=" * 80)
    benchmark.bench_normal_sampling()
    benchmark.bench_mixture_sampling()
    benchmark.bench_empirical_sampling()

    # Analytics Service Benchmarks
    print("\n" + "=" * 80)
    print("ANALYTICS SERVICE BENCHMARKS")
    print("=" * 80)
    benchmark.bench_variability_analysis()
    benchmark.bench_variability_analysis_large()
    benchmark.bench_confidence_interval()
    benchmark.bench_bootstrap_ci()
    benchmark.bench_risk_metrics()
    benchmark.bench_distribution_fit()
    benchmark.bench_scenario_comparison()

    # Monte Carlo Benchmarks
    print("\n" + "=" * 80)
    print("MONTE CARLO SIMULATION BENCHMARKS")
    print("=" * 80)
    benchmark.bench_monte_carlo_small()
    benchmark.bench_monte_carlo_medium()

    # Summary
    benchmark.print_summary()

    # Export results
    benchmark.export_results("benchmark_baseline_results.txt")

    print("\n✅ Benchmarking complete!")
    print("\nNext steps:")
    print("  1. Review baseline performance metrics")
    print("  2. Identify optimization opportunities")
    print("  3. Implement parallel Monte Carlo execution")
    print("  4. Add analytics caching layer")
    print("  5. Re-run benchmarks to measure improvements")


if __name__ == "__main__":
    main()
