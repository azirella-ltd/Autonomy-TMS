"""
Unit Tests for Stochastic Distribution Engine

This script tests all 18 distribution types, 3 sampling strategies, and
the distribution engine functionality.

Run with:
    cd backend
    python scripts/test_distribution_engine.py
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
from scipy import stats as scipy_stats

from app.services.stochastic import (
    DistributionFactory,
    DistributionEngine,
    StochasticVariable,
    IndependentSampling,
    CorrelatedSampling,
    TimeSeriesSampling,
    create_distribution_preview,
    validate_correlation_matrix,
)


def test_deterministic():
    """Test 1: Deterministic distribution"""
    print("\n" + "="*80)
    print("TEST 1: Deterministic Distribution")
    print("="*80)

    config = {'type': 'deterministic', 'value': 7.0}
    dist = DistributionFactory.create(config)

    samples = dist.sample(size=100, seed=42)
    print(f"  ✓ Sampled 100 values")
    print(f"    Mean: {np.mean(samples):.6f} (expected: 7.0)")
    print(f"    Std:  {np.std(samples):.6f} (expected: 0.0)")

    assert np.allclose(samples, 7.0), "All samples should be 7.0"
    assert dist.mean() == 7.0
    assert dist.std() == 0.0
    print("  ✅ TEST 1 PASSED")
    return True


def test_uniform():
    """Test 2: Uniform distribution"""
    print("\n" + "="*80)
    print("TEST 2: Uniform Distribution")
    print("="*80)

    config = {'type': 'uniform', 'min': 5.0, 'max': 10.0}
    dist = DistributionFactory.create(config)

    samples = dist.sample(size=10000, seed=42)
    print(f"  ✓ Sampled 10,000 values")
    print(f"    Mean: {np.mean(samples):.3f} (expected: 7.5)")
    print(f"    Std:  {np.std(samples):.3f} (expected: 1.44)")
    print(f"    Min:  {np.min(samples):.3f} (expected: ≥5.0)")
    print(f"    Max:  {np.max(samples):.3f} (expected: ≤10.0)")

    assert 7.0 < np.mean(samples) < 8.0, "Mean should be ~7.5"
    assert np.min(samples) >= 5.0, "All samples should be ≥5.0"
    assert np.max(samples) <= 10.0, "All samples should be ≤10.0"
    print("  ✅ TEST 2 PASSED")
    return True


def test_discrete_uniform():
    """Test 3: Discrete uniform distribution"""
    print("\n" + "="*80)
    print("TEST 3: Discrete Uniform Distribution")
    print("="*80)

    config = {'type': 'discrete_uniform', 'min': 3, 'max': 12}
    dist = DistributionFactory.create(config)

    samples = dist.sample(size=10000, seed=42)
    print(f"  ✓ Sampled 10,000 values")
    print(f"    Mean: {np.mean(samples):.3f} (expected: 7.5)")
    print(f"    Min:  {np.min(samples)} (expected: 3)")
    print(f"    Max:  {np.max(samples)} (expected: 12)")

    # Check all values are integers
    assert np.all(samples == samples.astype(int)), "All samples should be integers"
    assert 7.0 < np.mean(samples) < 8.0, "Mean should be ~7.5"
    assert np.min(samples) >= 3, "Min should be 3"
    assert np.max(samples) <= 12, "Max should be 12"
    print("  ✅ TEST 3 PASSED")
    return True


def test_normal():
    """Test 4: Normal distribution"""
    print("\n" + "="*80)
    print("TEST 4: Normal Distribution")
    print("="*80)

    config = {'type': 'normal', 'mean': 7.0, 'stddev': 1.5, 'min': 3.0, 'max': 12.0}
    dist = DistributionFactory.create(config)

    samples = dist.sample(size=10000, seed=42)
    print(f"  ✓ Sampled 10,000 values")
    print(f"    Mean: {np.mean(samples):.3f} (expected: ~7.0)")
    print(f"    Std:  {np.std(samples):.3f} (expected: ~1.5)")
    print(f"    Min:  {np.min(samples):.3f} (expected: ≥3.0)")
    print(f"    Max:  {np.max(samples):.3f} (expected: ≤12.0)")

    assert 6.5 < np.mean(samples) < 7.5, "Mean should be ~7.0"
    assert 1.3 < np.std(samples) < 1.7, "Std should be ~1.5"
    assert np.min(samples) >= 3.0, "Min bound enforced"
    assert np.max(samples) <= 12.0, "Max bound enforced"
    print("  ✅ TEST 4 PASSED")
    return True


def test_truncated_normal():
    """Test 5: Truncated normal distribution"""
    print("\n" + "="*80)
    print("TEST 5: Truncated Normal Distribution")
    print("="*80)

    config = {'type': 'truncated_normal', 'mean': 7.0, 'stddev': 2.0, 'min': 4.0, 'max': 10.0}
    dist = DistributionFactory.create(config)

    samples = dist.sample(size=10000, seed=42)
    print(f"  ✓ Sampled 10,000 values")
    print(f"    Mean: {np.mean(samples):.3f}")
    print(f"    Std:  {np.std(samples):.3f}")
    print(f"    Min:  {np.min(samples):.3f} (expected: ≥4.0)")
    print(f"    Max:  {np.max(samples):.3f} (expected: ≤10.0)")

    # All samples must be strictly within bounds
    assert np.all((samples >= 4.0) & (samples <= 10.0)), "All samples within [4, 10]"
    print("  ✅ TEST 5 PASSED")
    return True


def test_triangular():
    """Test 6: Triangular distribution"""
    print("\n" + "="*80)
    print("TEST 6: Triangular Distribution")
    print("="*80)

    config = {'type': 'triangular', 'min': 5.0, 'mode': 7.0, 'max': 12.0}
    dist = DistributionFactory.create(config)

    samples = dist.sample(size=10000, seed=42)
    print(f"  ✓ Sampled 10,000 values")
    print(f"    Mean: {np.mean(samples):.3f} (expected: 8.0)")
    print(f"    Min:  {np.min(samples):.3f} (expected: ≥5.0)")
    print(f"    Max:  {np.max(samples):.3f} (expected: ≤12.0)")

    expected_mean = (5.0 + 7.0 + 12.0) / 3.0
    assert 7.5 < np.mean(samples) < 8.5, f"Mean should be ~{expected_mean:.2f}"
    assert np.min(samples) >= 5.0, "Min bound"
    assert np.max(samples) <= 12.0, "Max bound"
    print("  ✅ TEST 6 PASSED")
    return True


def test_lognormal():
    """Test 7: Lognormal distribution"""
    print("\n" + "="*80)
    print("TEST 7: Lognormal Distribution")
    print("="*80)

    config = {'type': 'lognormal', 'mean_log': 2.0, 'stddev_log': 0.3, 'min': 0.0, 'max': 50.0}
    dist = DistributionFactory.create(config)

    samples = dist.sample(size=10000, seed=42)
    print(f"  ✓ Sampled 10,000 values")
    print(f"    Mean: {np.mean(samples):.3f}")
    print(f"    Std:  {np.std(samples):.3f}")
    print(f"    Min:  {np.min(samples):.3f} (expected: ≥0.0)")
    print(f"    Max:  {np.max(samples):.3f} (expected: ≤50.0)")

    # Lognormal is right-skewed
    assert np.median(samples) < np.mean(samples), "Right-skewed"
    assert np.min(samples) >= 0.0, "Non-negative"
    assert np.max(samples) <= 50.0, "Max bound"
    print("  ✅ TEST 7 PASSED")
    return True


def test_gamma():
    """Test 8: Gamma distribution"""
    print("\n" + "="*80)
    print("TEST 8: Gamma Distribution")
    print("="*80)

    config = {'type': 'gamma', 'shape': 2.0, 'scale': 3.5, 'min': 0.0}
    dist = DistributionFactory.create(config)

    samples = dist.sample(size=10000, seed=42)
    print(f"  ✓ Sampled 10,000 values")
    print(f"    Mean: {np.mean(samples):.3f} (expected: 7.0)")
    print(f"    Std:  {np.std(samples):.3f}")
    print(f"    Min:  {np.min(samples):.3f} (expected: ≥0.0)")

    expected_mean = 2.0 * 3.5
    assert 6.0 < np.mean(samples) < 8.0, f"Mean should be ~{expected_mean}"
    assert np.min(samples) >= 0.0, "Non-negative"
    print("  ✅ TEST 8 PASSED")
    return True


def test_weibull():
    """Test 9: Weibull distribution"""
    print("\n" + "="*80)
    print("TEST 9: Weibull Distribution")
    print("="*80)

    config = {'type': 'weibull', 'shape': 2.0, 'scale': 8.0}
    dist = DistributionFactory.create(config)

    samples = dist.sample(size=10000, seed=42)
    print(f"  ✓ Sampled 10,000 values")
    print(f"    Mean: {np.mean(samples):.3f}")
    print(f"    Std:  {np.std(samples):.3f}")
    print(f"    Min:  {np.min(samples):.3f} (expected: ≥0.0)")

    assert np.min(samples) >= 0.0, "Non-negative"
    print("  ✅ TEST 9 PASSED")
    return True


def test_exponential():
    """Test 10: Exponential distribution"""
    print("\n" + "="*80)
    print("TEST 10: Exponential Distribution")
    print("="*80)

    config = {'type': 'exponential', 'rate': 0.15}
    dist = DistributionFactory.create(config)

    samples = dist.sample(size=10000, seed=42)
    print(f"  ✓ Sampled 10,000 values")
    print(f"    Mean: {np.mean(samples):.3f} (expected: 6.67)")
    print(f"    Std:  {np.std(samples):.3f} (expected: 6.67)")

    expected_mean = 1.0 / 0.15
    assert 6.0 < np.mean(samples) < 7.5, f"Mean should be ~{expected_mean:.2f}"
    assert np.min(samples) >= 0.0, "Non-negative"
    print("  ✅ TEST 10 PASSED")
    return True


def test_beta():
    """Test 11: Beta distribution"""
    print("\n" + "="*80)
    print("TEST 11: Beta Distribution")
    print("="*80)

    config = {'type': 'beta', 'alpha': 90.0, 'beta': 10.0, 'min': 0.85, 'max': 1.0}
    dist = DistributionFactory.create(config)

    samples = dist.sample(size=10000, seed=42)
    print(f"  ✓ Sampled 10,000 values")
    print(f"    Mean: {np.mean(samples):.4f}")
    print(f"    Std:  {np.std(samples):.4f}")
    print(f"    Min:  {np.min(samples):.4f} (expected: ≥0.85)")
    print(f"    Max:  {np.max(samples):.4f} (expected: ≤1.0)")

    assert np.min(samples) >= 0.85, "Min bound"
    assert np.max(samples) <= 1.0, "Max bound"
    assert np.mean(samples) > 0.9, "Should be high (α=90 > β=10)"
    print("  ✅ TEST 11 PASSED")
    return True


def test_poisson():
    """Test 12: Poisson distribution"""
    print("\n" + "="*80)
    print("TEST 12: Poisson Distribution")
    print("="*80)

    config = {'type': 'poisson', 'lambda': 5.0}
    dist = DistributionFactory.create(config)

    samples = dist.sample(size=10000, seed=42)
    print(f"  ✓ Sampled 10,000 values")
    print(f"    Mean: {np.mean(samples):.3f} (expected: 5.0)")
    print(f"    Std:  {np.std(samples):.3f} (expected: 2.24)")

    # Check all values are non-negative integers
    assert np.all(samples >= 0), "Non-negative"
    assert np.all(samples == samples.astype(int)), "Integers"
    assert 4.5 < np.mean(samples) < 5.5, "Mean should be ~5.0"
    print("  ✅ TEST 12 PASSED")
    return True


def test_binomial():
    """Test 13: Binomial distribution"""
    print("\n" + "="*80)
    print("TEST 13: Binomial Distribution")
    print("="*80)

    config = {'type': 'binomial', 'n': 100, 'p': 0.95}
    dist = DistributionFactory.create(config)

    samples = dist.sample(size=10000, seed=42)
    print(f"  ✓ Sampled 10,000 values")
    print(f"    Mean: {np.mean(samples):.3f} (expected: 95.0)")
    print(f"    Std:  {np.std(samples):.3f}")

    expected_mean = 100 * 0.95
    assert 94.0 < np.mean(samples) < 96.0, f"Mean should be ~{expected_mean}"
    assert np.all(samples >= 0) and np.all(samples <= 100), "Range [0, 100]"
    print("  ✅ TEST 13 PASSED")
    return True


def test_negative_binomial():
    """Test 14: Negative binomial distribution"""
    print("\n" + "="*80)
    print("TEST 14: Negative Binomial Distribution")
    print("="*80)

    config = {'type': 'negative_binomial', 'r': 5, 'p': 0.7}
    dist = DistributionFactory.create(config)

    samples = dist.sample(size=10000, seed=42)
    print(f"  ✓ Sampled 10,000 values")
    print(f"    Mean: {np.mean(samples):.3f}")
    print(f"    Std:  {np.std(samples):.3f}")

    assert np.all(samples >= 0), "Non-negative"
    assert np.all(samples == samples.astype(int)), "Integers"
    print("  ✅ TEST 14 PASSED")
    return True


def test_empirical_discrete():
    """Test 15: Empirical discrete distribution"""
    print("\n" + "="*80)
    print("TEST 15: Empirical Discrete Distribution")
    print("="*80)

    config = {
        'type': 'empirical_discrete',
        'values': [5, 7, 10, 14],
        'probabilities': [0.2, 0.5, 0.25, 0.05]
    }
    dist = DistributionFactory.create(config)

    samples = dist.sample(size=10000, seed=42)
    print(f"  ✓ Sampled 10,000 values")
    print(f"    Mean: {np.mean(samples):.3f}")

    # Check only allowed values
    unique_values = np.unique(samples)
    print(f"    Unique values: {unique_values}")
    assert set(unique_values).issubset({5, 7, 10, 14}), "Only specified values"

    # Check probabilities approximately match
    count_7 = np.sum(samples == 7)
    prob_7 = count_7 / len(samples)
    print(f"    P(X=7): {prob_7:.3f} (expected: 0.5)")
    assert 0.45 < prob_7 < 0.55, "Probability of 7 should be ~0.5"
    print("  ✅ TEST 15 PASSED")
    return True


def test_empirical_continuous():
    """Test 16: Empirical continuous distribution"""
    print("\n" + "="*80)
    print("TEST 16: Empirical Continuous Distribution")
    print("="*80)

    original_samples = [6.2, 7.1, 6.8, 7.5, 8.2, 6.5, 7.0, 7.8, 6.9, 7.3] * 10
    config = {
        'type': 'empirical_continuous',
        'samples': original_samples,
        'bandwidth': 0.2
    }
    dist = DistributionFactory.create(config)

    samples = dist.sample(size=1000, seed=42)
    print(f"  ✓ Sampled 1,000 values")
    print(f"    Mean: {np.mean(samples):.3f}")
    print(f"    Std:  {np.std(samples):.3f}")

    # Mean should be close to original samples
    original_mean = np.mean(original_samples)
    assert abs(np.mean(samples) - original_mean) < 0.5, "Mean should be close to original"
    print("  ✅ TEST 16 PASSED")
    return True


def test_mixture():
    """Test 17: Mixture distribution"""
    print("\n" + "="*80)
    print("TEST 17: Mixture Distribution")
    print("="*80)

    config = {
        'type': 'mixture',
        'components': [
            {
                'weight': 0.9,
                'distribution': {'type': 'normal', 'mean': 7.0, 'stddev': 1.0}
            },
            {
                'weight': 0.1,
                'distribution': {'type': 'uniform', 'min': 15.0, 'max': 25.0}
            }
        ]
    }
    dist = DistributionFactory.create(config)

    samples = dist.sample(size=10000, seed=42)
    print(f"  ✓ Sampled 10,000 values")
    print(f"    Mean: {np.mean(samples):.3f}")
    print(f"    Std:  {np.std(samples):.3f}")

    # Should have bimodal distribution
    disruptions = np.sum(samples > 12.0)
    disruption_rate = disruptions / len(samples)
    print(f"    Disruption rate: {disruption_rate:.3f} (expected: ~0.1)")
    assert 0.05 < disruption_rate < 0.15, "~10% disruptions"
    print("  ✅ TEST 17 PASSED")
    return True


def test_categorical():
    """Test 18: Categorical distribution"""
    print("\n" + "="*80)
    print("TEST 18: Categorical Distribution")
    print("="*80)

    config = {
        'type': 'categorical',
        'categories': ['low', 'medium', 'high'],
        'probabilities': [0.2, 0.6, 0.2],
        'mappings': {'low': 5.0, 'medium': 10.0, 'high': 20.0}
    }
    dist = DistributionFactory.create(config)

    samples = dist.sample(size=10000, seed=42)
    print(f"  ✓ Sampled 10,000 values")
    print(f"    Mean: {np.mean(samples):.3f}")

    # Check only mapped values
    unique_values = np.unique(samples)
    print(f"    Unique values: {unique_values}")
    assert set(unique_values).issubset({5.0, 10.0, 20.0}), "Only mapped values"

    # Check probabilities
    count_medium = np.sum(samples == 10.0)
    prob_medium = count_medium / len(samples)
    print(f"    P(medium): {prob_medium:.3f} (expected: 0.6)")
    assert 0.55 < prob_medium < 0.65, "Probability of medium should be ~0.6"
    print("  ✅ TEST 18 PASSED")
    return True


def test_independent_sampling():
    """Test 19: Independent sampling strategy"""
    print("\n" + "="*80)
    print("TEST 19: Independent Sampling Strategy")
    print("="*80)

    engine = DistributionEngine(seed=42)
    strategy = IndependentSampling()

    configs = {
        'lead_time': {'type': 'normal', 'mean': 7.0, 'stddev': 1.5},
        'capacity': {'type': 'uniform', 'min': 80.0, 'max': 120.0}
    }

    sample1 = engine.sample_with_strategy(configs, strategy, seed=42)
    sample2 = engine.sample_with_strategy(configs, strategy, seed=42)

    print(f"  ✓ Sample 1: {sample1}")
    print(f"  ✓ Sample 2: {sample2}")

    # Same seed should give same results
    assert np.isclose(sample1['lead_time'], sample2['lead_time']), "Reproducible with seed"
    print("  ✅ TEST 19 PASSED")
    return True


def test_correlated_sampling():
    """Test 20: Correlated sampling strategy"""
    print("\n" + "="*80)
    print("TEST 20: Correlated Sampling Strategy")
    print("="*80)

    engine = DistributionEngine(seed=42)

    # Negative correlation between lead_time and yield
    correlation_matrix = np.array([
        [1.0, -0.5],
        [-0.5, 1.0]
    ])

    strategy = CorrelatedSampling(
        variables=['lead_time', 'yield'],
        correlation_matrix=correlation_matrix
    )

    configs = {
        'lead_time': {'type': 'normal', 'mean': 7.0, 'stddev': 1.5},
        'yield': {'type': 'beta', 'alpha': 90.0, 'beta': 10.0, 'min': 0.85, 'max': 1.0}
    }

    # Sample many times to check correlation
    lead_times = []
    yields = []

    for i in range(1000):
        sample = engine.sample_with_strategy(configs, strategy, seed=42 + i)
        lead_times.append(sample['lead_time'])
        yields.append(sample['yield'])

    # Calculate empirical correlation
    corr = np.corrcoef(lead_times, yields)[0, 1]
    print(f"  ✓ Sampled 1,000 correlated pairs")
    print(f"    Empirical correlation: {corr:.3f} (expected: ~-0.5)")

    # Correlation should be negative (but won't be exact due to copula method)
    assert corr < 0, "Correlation should be negative"
    print("  ✅ TEST 20 PASSED")
    return True


def test_time_series_sampling():
    """Test 21: Time series sampling strategy"""
    print("\n" + "="*80)
    print("TEST 21: Time Series Sampling Strategy")
    print("="*80)

    engine = DistributionEngine(seed=42)
    strategy = TimeSeriesSampling(ar_coeff=0.7, warmup_periods=10)

    configs = {
        'demand': {'type': 'normal', 'mean': 100.0, 'stddev': 20.0}
    }

    # Sample time series
    samples = []
    for i in range(50):
        sample = engine.sample_with_strategy(configs, strategy, seed=None)
        samples.append(sample['demand'])

    samples_array = np.array(samples)
    print(f"  ✓ Sampled 50 time periods")
    print(f"    Mean: {np.mean(samples_array):.2f} (expected: ~100)")
    print(f"    First 5: {samples_array[:5]}")

    # Calculate autocorrelation at lag 1
    acf_1 = np.corrcoef(samples_array[:-1], samples_array[1:])[0, 1]
    print(f"    Lag-1 ACF: {acf_1:.3f} (expected: ~0.7)")

    # ACF should be positive and reasonably high
    assert acf_1 > 0.3, "Should have positive autocorrelation"
    print("  ✅ TEST 21 PASSED")
    return True


def test_distribution_engine():
    """Test 22: Distribution engine"""
    print("\n" + "="*80)
    print("TEST 22: Distribution Engine")
    print("="*80)

    engine = DistributionEngine(seed=42)

    # Test sample()
    configs = {
        'lead_time': {'type': 'normal', 'mean': 7.0, 'stddev': 1.5},
        'capacity': {'type': 'uniform', 'min': 80.0, 'max': 120.0},
        'yield': None  # Deterministic (None config)
    }

    samples = engine.sample(configs, size=1)
    print(f"  ✓ Single sample: {samples}")
    assert 'lead_time' in samples
    assert 'capacity' in samples
    assert samples['yield'] is None

    # Test sample_or_default()
    value1 = engine.sample_or_default({'type': 'normal', 'mean': 7.0, 'stddev': 1.5}, 7.0, seed=42)
    value2 = engine.sample_or_default(None, 7.0, seed=42)
    print(f"  ✓ sample_or_default with dist: {value1:.2f}")
    print(f"  ✓ sample_or_default without dist: {value2:.2f}")
    assert value2 == 7.0, "Should return default when no config"

    # Test get_distribution_stats()
    stats = engine.get_distribution_stats(configs)
    print(f"  ✓ Distribution stats:")
    for var, stat in stats.items():
        print(f"    {var}: mean={stat['mean']}, std={stat['std']}, type={stat['type']}")

    print("  ✅ TEST 22 PASSED")
    return True


def test_stochastic_variable():
    """Test 23: StochasticVariable helper class"""
    print("\n" + "="*80)
    print("TEST 23: StochasticVariable Helper Class")
    print("="*80)

    # Stochastic variable
    lead_time = StochasticVariable(
        name='lead_time',
        default_value=7.0,
        distribution_config={'type': 'normal', 'mean': 7.0, 'stddev': 1.5}
    )

    print(f"  ✓ Created stochastic variable: {lead_time}")
    assert lead_time.is_stochastic()
    sample = lead_time.sample(seed=42)
    print(f"    Sample: {sample:.2f}")

    stats = lead_time.get_stats()
    print(f"    Stats: {stats}")

    # Deterministic variable
    capacity = StochasticVariable(
        name='capacity',
        default_value=100.0,
        distribution_config=None
    )

    print(f"  ✓ Created deterministic variable: {capacity}")
    assert not capacity.is_stochastic()
    sample = capacity.sample()
    assert sample == 100.0
    print(f"    Sample: {sample:.2f}")

    print("  ✅ TEST 23 PASSED")
    return True


def test_create_distribution_preview():
    """Test 24: Distribution preview helper"""
    print("\n" + "="*80)
    print("TEST 24: Distribution Preview Helper")
    print("="*80)

    config = {'type': 'normal', 'mean': 7.0, 'stddev': 1.5}
    preview = create_distribution_preview(config, num_samples=1000, seed=42)

    print(f"  ✓ Created preview with 1,000 samples")
    print(f"    Mean: {preview['mean']:.3f}")
    print(f"    Std:  {preview['std']:.3f}")
    print(f"    Min:  {preview['min']:.3f}")
    print(f"    Max:  {preview['max']:.3f}")
    print(f"    Percentiles:")
    for p, val in preview['percentiles'].items():
        print(f"      {p}: {val:.3f}")

    assert 'samples' in preview
    assert len(preview['samples']) == 1000
    assert 6.5 < preview['mean'] < 7.5
    print("  ✅ TEST 24 PASSED")
    return True


def test_validate_correlation_matrix():
    """Test 25: Correlation matrix validation"""
    print("\n" + "="*80)
    print("TEST 25: Correlation Matrix Validation")
    print("="*80)

    # Valid matrix
    valid_matrix = [
        [1.0, 0.3, -0.2],
        [0.3, 1.0, 0.5],
        [-0.2, 0.5, 1.0]
    ]

    try:
        validate_correlation_matrix(valid_matrix)
        print(f"  ✓ Valid matrix accepted")
    except ValueError as e:
        print(f"  ✗ Valid matrix rejected: {e}")
        return False

    # Invalid matrix (not symmetric)
    invalid_matrix = [
        [1.0, 0.3],
        [0.5, 1.0]  # 0.5 != 0.3
    ]

    try:
        validate_correlation_matrix(invalid_matrix)
        print(f"  ✗ Invalid matrix accepted (should have failed)")
        return False
    except ValueError as e:
        print(f"  ✓ Invalid matrix rejected: {e}")

    print("  ✅ TEST 25 PASSED")
    return True


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*80)
    print("STOCHASTIC DISTRIBUTION ENGINE TEST SUITE")
    print("="*80)
    print("\nTesting 18 distribution types + 3 sampling strategies + engine\n")

    tests = [
        test_deterministic,
        test_uniform,
        test_discrete_uniform,
        test_normal,
        test_truncated_normal,
        test_triangular,
        test_lognormal,
        test_gamma,
        test_weibull,
        test_exponential,
        test_beta,
        test_poisson,
        test_binomial,
        test_negative_binomial,
        test_empirical_discrete,
        test_empirical_continuous,
        test_mixture,
        test_categorical,
        test_independent_sampling,
        test_correlated_sampling,
        test_time_series_sampling,
        test_distribution_engine,
        test_stochastic_variable,
        test_create_distribution_preview,
        test_validate_correlation_matrix,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"  ❌ TEST FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Total Tests: {len(tests)}")
    print(f"Passed:      {passed} ✅")
    print(f"Failed:      {failed} ❌")
    print(f"Success Rate: {passed / len(tests) * 100:.1f}%")

    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! 🎉")
        print("\nDistribution engine is ready for production use.")
        return True
    else:
        print(f"\n⚠️  {failed} test(s) failed. Please review errors above.")
        return False


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
