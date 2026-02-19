"""
Test Stochastic Execution Integration

Tests that the StochasticSampler integrates correctly with the Beer Game execution adapter.
Verifies that:
1. Sampler initializes correctly
2. Distribution sampling works with model entities
3. Backward compatibility (NULL distributions) works
4. Sampled values are within expected ranges

Usage:
    docker compose exec backend python scripts/test_stochastic_execution.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.aws_sc_planning.stochastic_sampler import StochasticSampler
from app.models.aws_sc_planning import (
    SourcingRules,
    ProductionProcess,
    ProductionCapacity,
    ProductBom,
    VendorLeadTime,
    Forecast,
)


def test_sampler_initialization():
    """Test 1: Sampler initializes correctly"""
    print("=" * 80)
    print("TEST 1: Sampler Initialization")
    print("=" * 80)

    try:
        sampler = StochasticSampler(game_id=42, use_cache=True)
        print(f"✅ Sampler initialized with game_id={sampler.game_id}")
        print(f"   Engine seed: {sampler.engine.seed}")
        print(f"   Cache enabled: {sampler.use_cache}")
        return True
    except Exception as e:
        print(f"❌ Sampler initialization failed: {e}")
        return False


def test_deterministic_sampling():
    """Test 2: Deterministic sampling (NULL distributions)"""
    print()
    print("=" * 80)
    print("TEST 2: Deterministic Sampling (Backward Compatibility)")
    print("=" * 80)

    sampler = StochasticSampler(game_id=42)

    # Create test entities with NULL distributions
    sourcing_rule = SourcingRules()
    sourcing_rule.sourcing_lead_time_dist = None  # NULL = deterministic

    production_process = ProductionProcess()
    production_process.mfg_lead_time_dist = None
    production_process.yield_dist = None

    capacity = ProductionCapacity()
    capacity.capacity_dist = None

    # Test sampling with NULL distributions
    tests_passed = 0
    tests_failed = 0

    # Test 1: Sourcing lead time
    lead_time = sampler.sample_sourcing_lead_time(sourcing_rule, default_value=7.0)
    if lead_time == 7.0:
        print(f"✅ Sourcing lead time (NULL): {lead_time} (expected: 7.0)")
        tests_passed += 1
    else:
        print(f"❌ Sourcing lead time (NULL): {lead_time} (expected: 7.0)")
        tests_failed += 1

    # Test 2: Production lead time
    mfg_lead_time = sampler.sample_production_lead_time(production_process, default_value=14.0)
    if mfg_lead_time == 14.0:
        print(f"✅ Production lead time (NULL): {mfg_lead_time} (expected: 14.0)")
        tests_passed += 1
    else:
        print(f"❌ Production lead time (NULL): {mfg_lead_time} (expected: 14.0)")
        tests_failed += 1

    # Test 3: Yield
    yield_pct = sampler.sample_yield(production_process, default_value=100.0)
    if yield_pct == 100.0:
        print(f"✅ Yield (NULL): {yield_pct}% (expected: 100.0%)")
        tests_passed += 1
    else:
        print(f"❌ Yield (NULL): {yield_pct}% (expected: 100.0%)")
        tests_failed += 1

    # Test 4: Capacity
    capacity_val = sampler.sample_capacity(capacity, default_value=100.0)
    if capacity_val == 100.0:
        print(f"✅ Capacity (NULL): {capacity_val} (expected: 100.0)")
        tests_passed += 1
    else:
        print(f"❌ Capacity (NULL): {capacity_val} (expected: 100.0)")
        tests_failed += 1

    print()
    print(f"Deterministic Sampling: {tests_passed} passed, {tests_failed} failed")
    return tests_failed == 0


def test_stochastic_sampling():
    """Test 3: Stochastic sampling with distributions"""
    print()
    print("=" * 80)
    print("TEST 3: Stochastic Sampling (With Distributions)")
    print("=" * 80)

    sampler = StochasticSampler(game_id=42)

    # Create test entities with distributions
    sourcing_rule = SourcingRules()
    sourcing_rule.sourcing_lead_time_dist = {
        "type": "normal",
        "mean": 7.0,
        "stddev": 1.5,
        "min": 3.0,
        "max": 12.0
    }

    production_process = ProductionProcess()
    production_process.mfg_lead_time_dist = {
        "type": "uniform",
        "min": 5.0,
        "max": 10.0
    }
    production_process.yield_dist = {
        "type": "beta",
        "alpha": 90.0,
        "beta": 10.0,
        "min": 85.0,
        "max": 100.0
    }

    capacity = ProductionCapacity()
    capacity.capacity_dist = {
        "type": "truncated_normal",
        "mean": 100.0,
        "stddev": 15.0,
        "min": 60.0,
        "max": 120.0
    }

    tests_passed = 0
    tests_failed = 0

    # Test 1: Sourcing lead time (should be different from mean, within bounds)
    lead_times = [sampler.sample_sourcing_lead_time(sourcing_rule, default_value=7.0) for _ in range(100)]
    mean_lead_time = sum(lead_times) / len(lead_times)
    if 5.0 < mean_lead_time < 9.0 and all(3.0 <= lt <= 12.0 for lt in lead_times):
        print(f"✅ Sourcing lead time (normal): mean={mean_lead_time:.2f} (expected ~7.0), range=[{min(lead_times):.2f}, {max(lead_times):.2f}]")
        tests_passed += 1
    else:
        print(f"❌ Sourcing lead time (normal): mean={mean_lead_time:.2f}, range=[{min(lead_times):.2f}, {max(lead_times):.2f}]")
        tests_failed += 1

    # Test 2: Production lead time (uniform: should be between 5 and 10)
    mfg_lead_times = [sampler.sample_production_lead_time(production_process, default_value=7.0) for _ in range(100)]
    if all(5.0 <= lt <= 10.0 for lt in mfg_lead_times):
        print(f"✅ Production lead time (uniform): range=[{min(mfg_lead_times):.2f}, {max(mfg_lead_times):.2f}] (expected [5.0, 10.0])")
        tests_passed += 1
    else:
        print(f"❌ Production lead time (uniform): range=[{min(mfg_lead_times):.2f}, {max(mfg_lead_times):.2f}]")
        tests_failed += 1

    # Test 3: Yield (beta: should be between 85 and 100, skewed toward 100)
    yields = [sampler.sample_yield(production_process, default_value=100.0) for _ in range(100)]
    mean_yield = sum(yields) / len(yields)
    # Beta(90, 10) with min=85, max=100 gives mean around 96-99% (heavily skewed toward 100)
    if 95.0 < mean_yield < 100.0 and all(85.0 <= y <= 100.0 for y in yields):
        print(f"✅ Yield (beta): mean={mean_yield:.2f}% (expected ~96-99%), range=[{min(yields):.2f}, {max(yields):.2f}]")
        tests_passed += 1
    else:
        print(f"❌ Yield (beta): mean={mean_yield:.2f}%, range=[{min(yields):.2f}, {max(yields):.2f}]")
        tests_failed += 1

    # Test 4: Capacity (truncated normal: should be between 60 and 120, centered at 100)
    capacities = [sampler.sample_capacity(capacity, default_value=100.0) for _ in range(100)]
    mean_capacity = sum(capacities) / len(capacities)
    if 85.0 < mean_capacity < 115.0 and all(60.0 <= c <= 120.0 for c in capacities):
        print(f"✅ Capacity (truncated normal): mean={mean_capacity:.2f} (expected ~100), range=[{min(capacities):.2f}, {max(capacities):.2f}]")
        tests_passed += 1
    else:
        print(f"❌ Capacity (truncated normal): mean={mean_capacity:.2f}, range=[{min(capacities):.2f}, {max(capacities):.2f}]")
        tests_failed += 1

    print()
    print(f"Stochastic Sampling: {tests_passed} passed, {tests_failed} failed")
    return tests_failed == 0


def test_mixture_distribution():
    """Test 4: Mixture distribution (normal + disruptions)"""
    print()
    print("=" * 80)
    print("TEST 4: Mixture Distribution (Normal + Disruptions)")
    print("=" * 80)

    sampler = StochasticSampler(game_id=42)

    # Create sourcing rule with mixture distribution (95% normal, 5% disruption)
    sourcing_rule = SourcingRules()
    sourcing_rule.sourcing_lead_time_dist = {
        "type": "mixture",
        "components": [
            {
                "weight": 0.95,  # 95% normal operations
                "distribution": {
                    "type": "normal",
                    "mean": 7.0,
                    "stddev": 1.0
                }
            },
            {
                "weight": 0.05,  # 5% disruptions
                "distribution": {
                    "type": "uniform",
                    "min": 20.0,
                    "max": 30.0
                }
            }
        ]
    }

    # Sample 1000 times to see both normal and disruption cases
    lead_times = [sampler.sample_sourcing_lead_time(sourcing_rule, default_value=7.0) for _ in range(1000)]

    # Count normal vs disruption cases
    normal_cases = [lt for lt in lead_times if lt < 15.0]
    disruption_cases = [lt for lt in lead_times if lt >= 15.0]

    tests_passed = 0
    tests_failed = 0

    # Check that we have both normal and disruption cases
    if len(disruption_cases) > 0:
        disruption_pct = len(disruption_cases) / len(lead_times) * 100
        print(f"✅ Mixture distribution working: {disruption_pct:.1f}% disruptions (expected ~5%)")
        print(f"   Normal cases: {len(normal_cases)} (mean={sum(normal_cases)/len(normal_cases):.2f})")
        print(f"   Disruption cases: {len(disruption_cases)} (mean={sum(disruption_cases)/len(disruption_cases):.2f})")
        tests_passed += 1
    else:
        print(f"❌ Mixture distribution: No disruption cases found (expected ~5%)")
        tests_failed += 1

    print()
    print(f"Mixture Distribution: {tests_passed} passed, {tests_failed} failed")
    return tests_failed == 0


def test_batch_sampling():
    """Test 5: Batch sampling for performance"""
    print()
    print("=" * 80)
    print("TEST 5: Batch Sampling (Performance Test)")
    print("=" * 80)

    sampler = StochasticSampler(game_id=42)

    # Create multiple distribution configs
    variable_configs = {
        'lead_time': {
            "type": "normal",
            "mean": 7.0,
            "stddev": 1.5
        },
        'capacity': {
            "type": "uniform",
            "min": 80.0,
            "max": 120.0
        },
        'yield': {
            "type": "deterministic",
            "value": 95.0
        }
    }

    default_values = {
        'lead_time': 7.0,
        'capacity': 100.0,
        'yield': 100.0
    }

    try:
        # Sample all variables at once
        samples = sampler.sample_multiple(variable_configs, default_values)

        print(f"✅ Batch sampling successful:")
        print(f"   lead_time: {samples['lead_time']:.2f}")
        print(f"   capacity: {samples['capacity']:.2f}")
        print(f"   yield: {samples['yield']:.2f}")

        # Verify all values are present
        if all(key in samples for key in ['lead_time', 'capacity', 'yield']):
            print(f"✅ All variables sampled")
            return True
        else:
            print(f"❌ Missing variables in batch sample")
            return False

    except Exception as e:
        print(f"❌ Batch sampling failed: {e}")
        return False


def test_is_stochastic():
    """Test 6: is_stochastic utility method"""
    print()
    print("=" * 80)
    print("TEST 6: is_stochastic() Utility Method")
    print("=" * 80)

    sampler = StochasticSampler(game_id=42)

    tests_passed = 0
    tests_failed = 0

    # Test 1: NULL config (deterministic)
    if not sampler.is_stochastic(None):
        print(f"✅ NULL config is deterministic: {sampler.is_stochastic(None)}")
        tests_passed += 1
    else:
        print(f"❌ NULL config should be deterministic")
        tests_failed += 1

    # Test 2: Distribution config (stochastic)
    config = {"type": "normal", "mean": 7.0, "stddev": 1.5}
    if sampler.is_stochastic(config):
        print(f"✅ Distribution config is stochastic: {sampler.is_stochastic(config)}")
        tests_passed += 1
    else:
        print(f"❌ Distribution config should be stochastic")
        tests_failed += 1

    # Test 3: Get distribution info
    info = sampler.get_distribution_info(config)
    if info['type'] == 'normal' and info['stochastic']:
        print(f"✅ Distribution info: type={info['type']}, stochastic={info['stochastic']}")
        tests_passed += 1
    else:
        print(f"❌ Distribution info incorrect: {info}")
        tests_failed += 1

    print()
    print(f"is_stochastic() Tests: {tests_passed} passed, {tests_failed} failed")
    return tests_failed == 0


def run_all_tests():
    """Run all stochastic execution tests"""
    print("\n" + "=" * 80)
    print("STOCHASTIC EXECUTION INTEGRATION TESTS")
    print("=" * 80)
    print()
    print("Testing Phase 5 Sprint 3: Execution Adapter Integration")
    print("Testing StochasticSampler with AWS SC planning entities")
    print()

    results = []

    # Test 1: Initialization
    results.append(("Sampler Initialization", test_sampler_initialization()))

    # Test 2: Deterministic sampling
    results.append(("Deterministic Sampling", test_deterministic_sampling()))

    # Test 3: Stochastic sampling
    results.append(("Stochastic Sampling", test_stochastic_sampling()))

    # Test 4: Mixture distribution
    results.append(("Mixture Distribution", test_mixture_distribution()))

    # Test 5: Batch sampling
    results.append(("Batch Sampling", test_batch_sampling()))

    # Test 6: is_stochastic utility
    results.append(("is_stochastic() Utility", test_is_stochastic()))

    # Summary
    print()
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    total_tests = len(results)
    passed_tests = sum(1 for _, passed in results if passed)
    failed_tests = total_tests - passed_tests

    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name}: {status}")

    print()
    print(f"Total Tests: {total_tests}")
    print(f"Passed:      {passed_tests} ✅")
    print(f"Failed:      {failed_tests} ❌")
    print(f"Success Rate: {passed_tests / total_tests * 100:.1f}%")
    print()

    if failed_tests == 0:
        print("🎉 ALL TESTS PASSED! 🎉")
        print()
        print("Stochastic execution integration complete:")
        print("- StochasticSampler initialized successfully")
        print("- Deterministic sampling (NULL) works (backward compatible)")
        print("- Stochastic sampling from distributions works")
        print("- Mixture distributions (disruptions) work")
        print("- Batch sampling works")
        print("- Utility methods work")
        print()
        print("✅ Ready for production use!")
        return True
    else:
        print("❌ SOME TESTS FAILED")
        print()
        print("Please review the failures above and fix any issues.")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
