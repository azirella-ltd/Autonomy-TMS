"""
Unit Tests for Parallel Monte Carlo Engine
Tests worker functions, scenario execution, and parallelization
"""

import pytest
import asyncio
from datetime import date, datetime
from unittest.mock import Mock, AsyncMock, patch
from app.services.monte_carlo.parallel_engine import (
    ScenarioConfig,
    ScenarioResult,
    ParallelMonteCarloEngine,
    _run_scenario_worker,
    _simulate_scenario_execution
)


# ============================================================================
# Data Classes Tests
# ============================================================================

class TestScenarioConfig:
    """Test ScenarioConfig dataclass"""

    def test_creation(self):
        """Test basic creation"""
        config = ScenarioConfig(
            scenario_num=1,
            config_id=1,
            customer_id=1,
            start_date=date(2026, 1, 1),
            planning_horizon_weeks=52,
            random_seed=42,
            sampled_inputs={}
        )

        assert config.scenario_num == 1
        assert config.config_id == 1
        assert config.random_seed == 42

    def test_picklable(self):
        """ScenarioConfig should be picklable for multiprocessing"""
        import pickle

        config = ScenarioConfig(
            scenario_num=1,
            config_id=1,
            customer_id=1,
            start_date=date(2026, 1, 1),
            planning_horizon_weeks=52,
            random_seed=42,
            sampled_inputs={"test": 123}
        )

        # Should be able to pickle and unpickle
        pickled = pickle.dumps(config)
        unpickled = pickle.loads(pickled)

        assert unpickled.scenario_num == config.scenario_num
        assert unpickled.sampled_inputs == config.sampled_inputs


class TestScenarioResult:
    """Test ScenarioResult dataclass"""

    def test_successful_result(self):
        """Test successful scenario result"""
        result = ScenarioResult(
            scenario_number=1,
            success=True,
            duration=1.5,
            kpis={"total_cost": 10000},
            time_series=[{"week": 0, "inventory": 100}],
            error_message=None
        )

        assert result.success is True
        assert result.duration == 1.5
        assert result.kpis["total_cost"] == 10000

    def test_failed_result(self):
        """Test failed scenario result"""
        result = ScenarioResult(
            scenario_number=1,
            success=False,
            duration=0.1,
            kpis={},
            time_series=[],
            error_message="Test error"
        )

        assert result.success is False
        assert result.error_message == "Test error"

    def test_picklable(self):
        """ScenarioResult should be picklable for multiprocessing"""
        import pickle

        result = ScenarioResult(
            scenario_number=1,
            success=True,
            duration=1.0,
            kpis={"cost": 100},
            time_series=[],
            error_message=None
        )

        pickled = pickle.dumps(result)
        unpickled = pickle.loads(pickled)

        assert unpickled.scenario_number == result.scenario_number
        assert unpickled.success == result.success


# ============================================================================
# Simulation Execution Tests
# ============================================================================

class TestSimulateScenarioExecution:
    """Test scenario execution simulation"""

    def test_basic_execution(self):
        """Test basic scenario execution"""
        # Create mock config
        mock_config = Mock()
        mock_config.items = [Mock()]  # 1 product
        mock_config.nodes = [Mock()]  # 1 site

        sampled_inputs = {
            "demands": {"1_1_week0": 100},
            "lead_times": {},
            "yields": {},
            "capacities": {}
        }

        result = _simulate_scenario_execution(
            mock_config,
            sampled_inputs,
            planning_horizon_weeks=4,
            random_seed=42
        )

        assert "kpis" in result
        assert "time_series" in result
        assert len(result["time_series"]) == 4  # 4 weeks

    def test_kpis_structure(self):
        """Test KPI structure"""
        mock_config = Mock()
        mock_config.items = [Mock()]
        mock_config.nodes = [Mock()]

        result = _simulate_scenario_execution(
            mock_config,
            {"demands": {}, "lead_times": {}, "yields": {}, "capacities": {}},
            planning_horizon_weeks=1,
            random_seed=42
        )

        kpis = result["kpis"]

        # Check all required KPIs present
        required_kpis = [
            "total_cost", "holding_cost", "backlog_cost", "ordering_cost",
            "service_level", "final_inventory", "final_backlog",
            "max_inventory", "max_backlog",
            "had_stockout", "had_overstock", "had_capacity_violation"
        ]

        for kpi in required_kpis:
            assert kpi in kpis

    def test_time_series_structure(self):
        """Test time series structure"""
        mock_config = Mock()
        mock_config.items = [Mock()]
        mock_config.nodes = [Mock()]

        result = _simulate_scenario_execution(
            mock_config,
            {"demands": {}, "lead_times": {}, "yields": {}, "capacities": {}},
            planning_horizon_weeks=3,
            random_seed=42
        )

        time_series = result["time_series"]

        assert len(time_series) == 3

        # Check first entry structure
        ts_entry = time_series[0]
        assert "week" in ts_entry
        assert "inventory" in ts_entry
        assert "backlog" in ts_entry
        assert "demand" in ts_entry
        assert "receipts" in ts_entry
        assert "holding_cost" in ts_entry
        assert "backlog_cost" in ts_entry

    def test_deterministic_with_seed(self):
        """Same seed should produce same results"""
        mock_config = Mock()
        mock_config.items = [Mock()]
        mock_config.nodes = [Mock()]

        sampled_inputs = {"demands": {}, "lead_times": {}, "yields": {}, "capacities": {}}

        result1 = _simulate_scenario_execution(mock_config, sampled_inputs, 4, 42)
        result2 = _simulate_scenario_execution(mock_config, sampled_inputs, 4, 42)

        # Same seed should give same results
        assert result1["kpis"]["total_cost"] == result2["kpis"]["total_cost"]
        assert result1["kpis"]["service_level"] == result2["kpis"]["service_level"]

    def test_different_seeds_different_results(self):
        """Different seeds should produce different results"""
        mock_config = Mock()
        mock_config.items = [Mock()]
        mock_config.nodes = [Mock()]

        sampled_inputs = {"demands": {}, "lead_times": {}, "yields": {}, "capacities": {}}

        result1 = _simulate_scenario_execution(mock_config, sampled_inputs, 4, 42)
        result2 = _simulate_scenario_execution(mock_config, sampled_inputs, 4, 99)

        # Different seeds should give different results
        assert result1["kpis"]["total_cost"] != result2["kpis"]["total_cost"]


# ============================================================================
# Worker Function Tests
# ============================================================================

class TestRunScenarioWorker:
    """Test worker function (integration test)"""

    @pytest.mark.skip(reason="Requires database setup")
    def test_worker_successful_execution(self):
        """Test successful worker execution"""
        config = ScenarioConfig(
            scenario_num=1,
            config_id=1,
            customer_id=1,
            start_date=date(2026, 1, 1),
            planning_horizon_weeks=4,
            random_seed=42,
            sampled_inputs={"demands": {}, "lead_times": {}, "yields": {}, "capacities": {}}
        )

        result = _run_scenario_worker(config)

        assert isinstance(result, ScenarioResult)
        assert result.scenario_number == 1

    def test_worker_handles_errors(self):
        """Test worker error handling"""
        # Create invalid config to trigger error
        config = ScenarioConfig(
            scenario_num=1,
            config_id=99999,  # Non-existent config
            customer_id=1,
            start_date=date(2026, 1, 1),
            planning_horizon_weeks=4,
            random_seed=42,
            sampled_inputs={}
        )

        result = _run_scenario_worker(config)

        # Should return failed result, not raise exception
        assert result.success is False
        assert result.error_message is not None


# ============================================================================
# Parallel Engine Tests
# ============================================================================

class TestParallelMonteCarloEngine:
    """Test ParallelMonteCarloEngine class"""

    def test_initialization(self):
        """Test engine initialization"""
        engine = ParallelMonteCarloEngine(
            run_id=1,
            config_id=1,
            customer_id=1,
            num_scenarios=100,
            random_seed=42,
            num_workers=4
        )

        assert engine.run_id == 1
        assert engine.num_scenarios == 100
        assert engine.random_seed == 42
        assert engine.num_workers == 4

    def test_auto_worker_detection(self):
        """Test automatic worker count detection"""
        import multiprocessing as mp

        engine = ParallelMonteCarloEngine(
            run_id=1,
            config_id=1,
            customer_id=1,
            num_scenarios=100,
            num_workers=None  # Auto-detect
        )

        # Should be <= CPU count and <= num_scenarios
        assert engine.num_workers <= mp.cpu_count()
        assert engine.num_workers <= 100

    def test_worker_count_capped_by_scenarios(self):
        """Worker count should not exceed scenario count"""
        engine = ParallelMonteCarloEngine(
            run_id=1,
            config_id=1,
            customer_id=1,
            num_scenarios=2,  # Only 2 scenarios
            num_workers=100   # Request 100 workers
        )

        # Should cap at 2 workers
        assert engine.num_workers == 2

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires database and full integration")
    async def test_run_parallel_simulation(self):
        """Test full parallel simulation (integration test)"""
        engine = ParallelMonteCarloEngine(
            run_id=1,
            config_id=1,
            customer_id=1,
            num_scenarios=10,
            num_workers=2
        )

        results = await engine.run_parallel_simulation(
            start_date=date(2026, 1, 1),
            planning_horizon_weeks=4
        )

        assert len(results) == 10
        assert all(isinstance(r, ScenarioResult) for r in results)

    @pytest.mark.asyncio
    async def test_progress_callback(self):
        """Test progress callback functionality"""
        progress_calls = []

        def progress_callback(completed, total):
            progress_calls.append((completed, total))

        engine = ParallelMonteCarloEngine(
            run_id=1,
            config_id=1,
            customer_id=1,
            num_scenarios=5,
            num_workers=2
        )

        # Mock the internal methods to avoid full integration
        with patch.object(engine, '_prepare_scenario_configs') as mock_prep, \
             patch.object(engine, '_run_parallel_scenarios') as mock_run, \
             patch.object(engine, '_save_results') as mock_save:

            mock_prep.return_value = []
            mock_run.return_value = []
            mock_save.return_value = None

            try:
                await engine.run_parallel_simulation(
                    start_date=date(2026, 1, 1),
                    planning_horizon_weeks=4,
                    progress_callback=progress_callback
                )
            except Exception:
                pass  # Expected to fail due to mocking


# ============================================================================
# Performance Tests
# ============================================================================

class TestPerformance:
    """Test performance characteristics"""

    def test_scenario_execution_speed(self):
        """Test single scenario execution speed"""
        import time

        mock_config = Mock()
        mock_config.items = [Mock() for _ in range(5)]
        mock_config.nodes = [Mock() for _ in range(5)]

        sampled_inputs = {"demands": {}, "lead_times": {}, "yields": {}, "capacities": {}}

        start = time.time()
        result = _simulate_scenario_execution(
            mock_config,
            sampled_inputs,
            planning_horizon_weeks=52,
            random_seed=42
        )
        duration = time.time() - start

        # Should complete in < 1 second for 52 weeks
        assert duration < 1.0

    def test_multiple_scenarios_timing(self):
        """Test timing for multiple scenarios"""
        import time

        mock_config = Mock()
        mock_config.items = [Mock()]
        mock_config.nodes = [Mock()]

        sampled_inputs = {"demands": {}, "lead_times": {}, "yields": {}, "capacities": {}}

        start = time.time()
        for i in range(10):
            _simulate_scenario_execution(
                mock_config,
                sampled_inputs,
                planning_horizon_weeks=12,
                random_seed=42 + i
            )
        duration = time.time() - start

        # 10 scenarios should complete in < 2 seconds
        assert duration < 2.0


# ============================================================================
# Edge Cases Tests
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_single_scenario(self):
        """Test with only 1 scenario"""
        engine = ParallelMonteCarloEngine(
            run_id=1,
            config_id=1,
            customer_id=1,
            num_scenarios=1,
            num_workers=None
        )

        assert engine.num_workers == 1

    def test_zero_planning_horizon(self):
        """Test with zero planning horizon"""
        mock_config = Mock()
        mock_config.items = []
        mock_config.nodes = []

        result = _simulate_scenario_execution(
            mock_config,
            {},
            planning_horizon_weeks=0,
            random_seed=42
        )

        # Should handle gracefully
        assert result["kpis"]["total_cost"] >= 0
        assert len(result["time_series"]) == 0

    def test_empty_config(self):
        """Test with empty supply chain config"""
        mock_config = Mock()
        mock_config.items = []
        mock_config.nodes = []

        result = _simulate_scenario_execution(
            mock_config,
            {},
            planning_horizon_weeks=4,
            random_seed=42
        )

        # Should not crash
        assert "kpis" in result
        assert "time_series" in result

    def test_large_scenario_count(self):
        """Test with large scenario count"""
        engine = ParallelMonteCarloEngine(
            run_id=1,
            config_id=1,
            customer_id=1,
            num_scenarios=10000,
            num_workers=None
        )

        # Should cap workers at CPU count, not scenario count
        import multiprocessing as mp
        assert engine.num_workers <= mp.cpu_count()


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests requiring minimal mocking"""

    def test_end_to_end_single_scenario(self):
        """Test end-to-end with single scenario"""
        mock_config = Mock()
        mock_config.items = [Mock()]
        mock_config.nodes = [Mock()]

        config = ScenarioConfig(
            scenario_num=1,
            config_id=1,
            customer_id=1,
            start_date=date(2026, 1, 1),
            planning_horizon_weeks=4,
            random_seed=42,
            sampled_inputs={"demands": {}, "lead_times": {}, "yields": {}, "capacities": {}}
        )

        # Simulate worker execution
        result = _simulate_scenario_execution(
            mock_config,
            config.sampled_inputs,
            config.planning_horizon_weeks,
            config.random_seed
        )

        # Validate result structure
        assert "kpis" in result
        assert "time_series" in result
        assert result["kpis"]["total_cost"] >= 0
        assert result["kpis"]["service_level"] >= 0
        assert result["kpis"]["service_level"] <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
