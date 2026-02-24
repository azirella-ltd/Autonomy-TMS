"""
Comprehensive tests for SC Planning services.

Tests the three-step AWS SC planning process:
  Step 1: DemandProcessor — forecast/actual/reservation netting
  Step 2: InventoryTargetCalculator — safety stock for 5 policy types + targets
  Step 3: NetRequirementsCalculator — time-phased netting, BOM explosion, sourcing

All database access is mocked via monkeypatch / AsyncMock so that tests run
without PostgreSQL.
"""

import math
import pytest
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Dict, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.sc_planning.demand_processor import DemandProcessor
from app.services.sc_planning.inventory_target_calculator import InventoryTargetCalculator
from app.services.sc_planning.net_requirements_calculator import NetRequirementsCalculator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _date(offset: int = 0) -> date:
    """Return a deterministic base date + offset days."""
    return date(2026, 3, 1) + timedelta(days=offset)


def _make_policy(**overrides) -> SimpleNamespace:
    """Build a minimal InvPolicy-like object with sensible defaults."""
    defaults = dict(
        ss_policy=None,
        ss_quantity=None,
        ss_days=None,
        service_level=None,
        conformal_demand_coverage=0.90,
        conformal_lead_time_coverage=0.90,
        review_period=1,
        reorder_point=None,
        target_qty=None,
        min_qty=None,
        max_qty=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_sourcing_rule(**overrides) -> SimpleNamespace:
    """Build a minimal SourcingRules-like object."""
    defaults = dict(
        sourcing_rule_type="buy",
        priority=1,
        sourcing_priority=1,
        allocation_percent=None,
        lead_time=3,
        supplier_site_id="SITE_SUPPLY",
        tpartner_id=None,
        unit_cost=10.0,
        transportation_lane_id=None,
        production_process_id=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ============================================================================
# DemandProcessor Tests
# ============================================================================


class TestDemandProcessorNetting:
    """Tests for DemandProcessor.process_demand — the core netting logic."""

    @pytest.fixture
    def processor(self):
        return DemandProcessor(config_id=1, group_id=1)

    # -- Test 1 --
    @pytest.mark.asyncio
    async def test_forecast_exceeds_actuals(self, processor):
        """When forecast > actuals, net demand = forecast (actuals consumed)."""
        key = ("PROD_A", "SITE_1", _date(0))

        processor.load_forecasts = AsyncMock(return_value={key: 100.0})
        processor.load_actual_orders = AsyncMock(return_value={key: 60.0})
        processor.load_reservations = AsyncMock(return_value={})

        result = await processor.process_demand(_date(0), planning_horizon=30)

        assert result[key] == 100.0  # forecast wins

    # -- Test 2 --
    @pytest.mark.asyncio
    async def test_actuals_exceed_forecast(self, processor):
        """When actuals > forecast, net demand = actuals."""
        key = ("PROD_A", "SITE_1", _date(0))

        processor.load_forecasts = AsyncMock(return_value={key: 50.0})
        processor.load_actual_orders = AsyncMock(return_value={key: 80.0})
        processor.load_reservations = AsyncMock(return_value={})

        result = await processor.process_demand(_date(0), planning_horizon=30)

        assert result[key] == 80.0  # actuals win

    # -- Test 3 --
    @pytest.mark.asyncio
    async def test_reservations_added_on_top(self, processor):
        """Reservations are added on top of the larger of forecast/actuals."""
        key = ("PROD_A", "SITE_1", _date(0))

        processor.load_forecasts = AsyncMock(return_value={key: 100.0})
        processor.load_actual_orders = AsyncMock(return_value={key: 60.0})
        processor.load_reservations = AsyncMock(return_value={key: 25.0})

        result = await processor.process_demand(_date(0), planning_horizon=30)

        # forecast (100) > actuals (60) → use forecast + reservation
        assert result[key] == 125.0

    # -- Test 4 --
    @pytest.mark.asyncio
    async def test_reservations_with_actuals_exceeding_forecast(self, processor):
        """Reservations added when actuals exceed forecast."""
        key = ("PROD_A", "SITE_1", _date(0))

        processor.load_forecasts = AsyncMock(return_value={key: 50.0})
        processor.load_actual_orders = AsyncMock(return_value={key: 80.0})
        processor.load_reservations = AsyncMock(return_value={key: 10.0})

        result = await processor.process_demand(_date(0), planning_horizon=30)

        # actuals (80) > forecast (50) → use actuals + reservation
        assert result[key] == 90.0

    # -- Test 5 --
    @pytest.mark.asyncio
    async def test_empty_forecasts_and_orders(self, processor):
        """No forecasts, no orders, no reservations → empty result."""
        processor.load_forecasts = AsyncMock(return_value={})
        processor.load_actual_orders = AsyncMock(return_value={})
        processor.load_reservations = AsyncMock(return_value={})

        result = await processor.process_demand(_date(0), planning_horizon=30)

        assert result == {}

    # -- Test 6 --
    @pytest.mark.asyncio
    async def test_multiple_product_site_combinations(self, processor):
        """Multiple product-site combos are processed independently."""
        key_a = ("PROD_A", "SITE_1", _date(0))
        key_b = ("PROD_B", "SITE_2", _date(1))
        key_c = ("PROD_A", "SITE_2", _date(0))

        processor.load_forecasts = AsyncMock(return_value={
            key_a: 100.0,
            key_b: 200.0,
        })
        processor.load_actual_orders = AsyncMock(return_value={
            key_a: 150.0,   # actuals > forecast
            key_b: 50.0,    # actuals < forecast
            key_c: 30.0,    # no forecast for this combo
        })
        processor.load_reservations = AsyncMock(return_value={})

        result = await processor.process_demand(_date(0), planning_horizon=30)

        assert result[key_a] == 150.0  # actuals win
        assert result[key_b] == 200.0  # forecast wins
        assert result[key_c] == 30.0   # only actuals exist → actuals used

    # -- Test 7 --
    @pytest.mark.asyncio
    async def test_only_reservations_present(self, processor):
        """When only reservations exist (no forecast, no actuals), net = reservation."""
        key = ("PROD_X", "SITE_3", _date(5))

        processor.load_forecasts = AsyncMock(return_value={})
        processor.load_actual_orders = AsyncMock(return_value={})
        processor.load_reservations = AsyncMock(return_value={key: 40.0})

        result = await processor.process_demand(_date(0), planning_horizon=30)

        # forecast=0, actuals=0 → actuals not > forecast → use forecast (0) + reservation (40)
        assert result[key] == 40.0

    # -- Test 8 --
    @pytest.mark.asyncio
    async def test_equal_forecast_and_actuals(self, processor):
        """When forecast == actuals, use forecast (actuals not > forecast)."""
        key = ("PROD_A", "SITE_1", _date(0))

        processor.load_forecasts = AsyncMock(return_value={key: 100.0})
        processor.load_actual_orders = AsyncMock(return_value={key: 100.0})
        processor.load_reservations = AsyncMock(return_value={})

        result = await processor.process_demand(_date(0), planning_horizon=30)

        assert result[key] == 100.0


class TestDemandProcessorAggregation:
    """Tests for DemandProcessor.aggregate_demand_by_period."""

    @pytest.fixture
    def processor(self):
        return DemandProcessor(config_id=1, group_id=1)

    # -- Test 9 (bonus aggregation test) --
    @pytest.mark.asyncio
    async def test_aggregate_weekly(self, processor):
        """Daily demand aggregated into 7-day buckets."""
        net_demand = {
            ("PROD_A", "SITE_1", _date(0)): 10.0,
            ("PROD_A", "SITE_1", _date(1)): 15.0,
            ("PROD_A", "SITE_1", _date(7)): 20.0,
        }

        result = await processor.aggregate_demand_by_period(net_demand, period_days=7)

        # Day 0,1 → period 0; Day 7 → period 1
        assert result[("PROD_A", "SITE_1", 0)] == 25.0
        assert result[("PROD_A", "SITE_1", 1)] == 20.0


# ============================================================================
# InventoryTargetCalculator Tests
# ============================================================================


class TestSafetyStockAbsLevel:
    """Test abs_level policy: fixed quantity safety stock."""

    @pytest.fixture
    def calculator(self):
        return InventoryTargetCalculator(config_id=1, group_id=1)

    # -- Test 10 --
    @pytest.mark.asyncio
    async def test_abs_level_returns_fixed_quantity(self, calculator):
        """abs_level policy returns the exact ss_quantity."""
        policy = _make_policy(ss_policy="abs_level", ss_quantity=250.0)
        net_demand = {}

        result = await calculator.calculate_safety_stock(
            policy, "PROD_A", "SITE_1", net_demand, _date(0)
        )

        assert result == 250.0

    # -- Test 11 --
    @pytest.mark.asyncio
    async def test_abs_level_none_quantity_returns_zero(self, calculator):
        """abs_level with ss_quantity=None returns 0."""
        policy = _make_policy(ss_policy="abs_level", ss_quantity=None)

        result = await calculator.calculate_safety_stock(
            policy, "PROD_A", "SITE_1", {}, _date(0)
        )

        assert result == 0.0


class TestSafetyStockDocDem:
    """Test doc_dem policy: days of coverage based on actual demand."""

    @pytest.fixture
    def calculator(self):
        return InventoryTargetCalculator(config_id=1, group_id=1)

    # -- Test 12 --
    @pytest.mark.asyncio
    async def test_doc_dem_basic(self, calculator):
        """doc_dem: SS = avg_daily_demand * days_of_coverage."""
        policy = _make_policy(ss_policy="doc_dem", ss_days=14)

        # Mock the DB-dependent method
        calculator.calculate_avg_daily_demand = AsyncMock(return_value=20.0)

        result = await calculator.calculate_safety_stock(
            policy, "PROD_A", "SITE_1", {}, _date(0)
        )

        # 14 days * 20 units/day = 280
        assert result == 280.0
        calculator.calculate_avg_daily_demand.assert_awaited_once()

    # -- Test 13 --
    @pytest.mark.asyncio
    async def test_doc_dem_zero_days(self, calculator):
        """doc_dem with ss_days=0 returns 0 safety stock."""
        policy = _make_policy(ss_policy="doc_dem", ss_days=0)
        calculator.calculate_avg_daily_demand = AsyncMock(return_value=20.0)

        result = await calculator.calculate_safety_stock(
            policy, "PROD_A", "SITE_1", {}, _date(0)
        )

        assert result == 0.0


class TestSafetyStockDocFcst:
    """Test doc_fcst policy: days of coverage based on forecast."""

    @pytest.fixture
    def calculator(self):
        return InventoryTargetCalculator(config_id=1, group_id=1)

    # -- Test 14 --
    @pytest.mark.asyncio
    async def test_doc_fcst_basic(self, calculator):
        """doc_fcst: SS = avg_daily_forecast * days_of_coverage."""
        policy = _make_policy(ss_policy="doc_fcst", ss_days=7)

        # Build forecast net_demand for 30 days: 10 units per day for the
        # first 30 days for PROD_A @ SITE_1
        net_demand = {
            ("PROD_A", "SITE_1", _date(i)): 10.0
            for i in range(30)
        }

        result = await calculator.calculate_safety_stock(
            policy, "PROD_A", "SITE_1", net_demand, _date(0)
        )

        # avg daily forecast = sum(10 * 30) / 30 = 10.0
        # SS = 7 * 10 = 70.0
        assert result == 70.0

    # -- Test 15 --
    @pytest.mark.asyncio
    async def test_doc_fcst_no_demand(self, calculator):
        """doc_fcst with no matching demand returns 0."""
        policy = _make_policy(ss_policy="doc_fcst", ss_days=14)
        net_demand = {}

        result = await calculator.calculate_safety_stock(
            policy, "PROD_A", "SITE_1", net_demand, _date(0)
        )

        assert result == 0.0


class TestSafetyStockServiceLevel:
    """Test sl (service level) policy using the King Formula."""

    @pytest.fixture
    def calculator(self):
        return InventoryTargetCalculator(config_id=1, group_id=1)

    # -- Test 16 --
    @pytest.mark.asyncio
    async def test_sl_king_formula_95pct(self, calculator):
        """
        King Formula: SS = z * sqrt(LT * sigma_d^2 + d^2 * sigma_LT^2)
        At 95% service level, z ≈ 1.65
        """
        policy = _make_policy(ss_policy="sl", service_level=0.95)

        avg_demand = 50.0
        demand_std = 10.0
        lead_time = 5       # days
        lt_std = 1.0         # days

        calculator.calculate_avg_daily_demand = AsyncMock(return_value=avg_demand)
        calculator.calculate_demand_std_dev = AsyncMock(return_value=demand_std)
        calculator.get_replenishment_lead_time = AsyncMock(return_value=lead_time)
        calculator.get_lead_time_std_dev = AsyncMock(return_value=lt_std)

        result = await calculator.calculate_safety_stock(
            policy, "PROD_A", "SITE_1", {}, _date(0)
        )

        z = 1.65
        demand_var_term = lead_time * (demand_std ** 2)      # 5 * 100 = 500
        lt_var_term = (avg_demand ** 2) * (lt_std ** 2)       # 2500 * 1 = 2500
        expected = z * math.sqrt(demand_var_term + lt_var_term)  # 1.65 * sqrt(3000) ≈ 90.37

        assert abs(result - expected) < 0.01

    # -- Test 17 --
    @pytest.mark.asyncio
    async def test_sl_king_formula_90pct(self, calculator):
        """At 90% service level, z ≈ 1.28."""
        policy = _make_policy(ss_policy="sl", service_level=0.90)

        calculator.calculate_avg_daily_demand = AsyncMock(return_value=50.0)
        calculator.calculate_demand_std_dev = AsyncMock(return_value=10.0)
        calculator.get_replenishment_lead_time = AsyncMock(return_value=5)
        calculator.get_lead_time_std_dev = AsyncMock(return_value=1.0)

        result = await calculator.calculate_safety_stock(
            policy, "PROD_A", "SITE_1", {}, _date(0)
        )

        z = 1.28
        expected = z * math.sqrt(5 * 100 + 2500 * 1)
        assert abs(result - expected) < 0.01

    # -- Test 18 --
    @pytest.mark.asyncio
    async def test_sl_king_formula_99pct(self, calculator):
        """At 99% service level, z ≈ 2.33."""
        policy = _make_policy(ss_policy="sl", service_level=0.99)

        calculator.calculate_avg_daily_demand = AsyncMock(return_value=50.0)
        calculator.calculate_demand_std_dev = AsyncMock(return_value=10.0)
        calculator.get_replenishment_lead_time = AsyncMock(return_value=5)
        calculator.get_lead_time_std_dev = AsyncMock(return_value=1.0)

        result = await calculator.calculate_safety_stock(
            policy, "PROD_A", "SITE_1", {}, _date(0)
        )

        z = 2.33
        expected = z * math.sqrt(5 * 100 + 2500 * 1)
        assert abs(result - expected) < 0.01

    # -- Test 19 --
    @pytest.mark.asyncio
    async def test_sl_zero_lead_time_variance(self, calculator):
        """When lead time variance is 0, formula simplifies to z * sigma_d * sqrt(LT)."""
        policy = _make_policy(ss_policy="sl", service_level=0.95)

        calculator.calculate_avg_daily_demand = AsyncMock(return_value=100.0)
        calculator.calculate_demand_std_dev = AsyncMock(return_value=15.0)
        calculator.get_replenishment_lead_time = AsyncMock(return_value=4)
        calculator.get_lead_time_std_dev = AsyncMock(return_value=0.0)

        result = await calculator.calculate_safety_stock(
            policy, "PROD_A", "SITE_1", {}, _date(0)
        )

        # z * sqrt(LT * sigma_d^2 + 0) = 1.65 * sqrt(4 * 225) = 1.65 * 30 = 49.5
        expected = 1.65 * math.sqrt(4 * 225)
        assert abs(result - expected) < 0.01

    # -- Test 20 --
    @pytest.mark.asyncio
    async def test_sl_zero_demand_variance(self, calculator):
        """When demand variance is 0, only lead time variance contributes."""
        policy = _make_policy(ss_policy="sl", service_level=0.95)

        calculator.calculate_avg_daily_demand = AsyncMock(return_value=100.0)
        calculator.calculate_demand_std_dev = AsyncMock(return_value=0.0)
        calculator.get_replenishment_lead_time = AsyncMock(return_value=4)
        calculator.get_lead_time_std_dev = AsyncMock(return_value=2.0)

        result = await calculator.calculate_safety_stock(
            policy, "PROD_A", "SITE_1", {}, _date(0)
        )

        # z * sqrt(0 + d^2 * sigma_LT^2) = 1.65 * sqrt(10000 * 4) = 1.65 * 200 = 330.0
        expected = 1.65 * math.sqrt(10000 * 4)
        assert abs(result - expected) < 0.01


class TestSafetyStockConformal:
    """Test conformal policy: distribution-free prediction intervals."""

    @pytest.fixture
    def calculator(self):
        return InventoryTargetCalculator(config_id=1, group_id=1)

    # -- Test 21 --
    @pytest.mark.asyncio
    async def test_conformal_returns_positive_safety_stock(self, calculator):
        """Conformal policy returns a dict with positive safety_stock."""
        policy = _make_policy(
            ss_policy="conformal",
            conformal_demand_coverage=0.90,
            conformal_lead_time_coverage=0.90,
        )

        # Build net_demand for average forecast calculation
        net_demand = {
            ("PROD_A", "SITE_1", _date(i)): 20.0
            for i in range(30)
        }

        calculator.get_replenishment_lead_time = AsyncMock(return_value=5)

        # Mock the conformal suite so we don't need the full system
        mock_suite = MagicMock()
        mock_suite.has_demand_predictor.return_value = False  # will use conservative fallback

        with patch(
            "app.services.sc_planning.inventory_target_calculator."
            "InventoryTargetCalculator._calculate_conformal_safety_stock",
            new_callable=AsyncMock,
        ) as mock_calc:
            mock_calc.return_value = {
                "safety_stock": 45.0,
                "reorder_point": 145.0,
                "expected_demand_during_lt": 100.0,
                "worst_case_demand_during_lt": 145.0,
                "service_level_guarantee": 0.81,
                "demand_coverage": 0.90,
                "lead_time_coverage": 0.90,
                "policy_type": "conformal",
            }

            result = await calculator.calculate_safety_stock(
                policy, "PROD_A", "SITE_1", net_demand, _date(0)
            )

            assert result == 45.0


class TestConformalCalculation:
    """Test the _calculate_conformal_safety_stock method directly."""

    @pytest.fixture
    def calculator(self):
        return InventoryTargetCalculator(config_id=1, group_id=1)

    # -- Test 22 --
    @pytest.mark.asyncio
    async def test_conformal_fallback_no_predictor(self, calculator):
        """Without a calibrated predictor, conservative fallback is used."""
        mock_suite = MagicMock()
        mock_suite.has_demand_predictor.return_value = False

        # When has_demand_predictor returns False, the method uses the
        # conservative path directly (demand_upper = mean * LT * 1.3,
        # actual_demand_coverage = 0.80). The ConformalOrchestrator import
        # for staleness is wrapped in try/except and doesn't affect the result.
        result = await calculator._calculate_conformal_safety_stock(
            suite=mock_suite,
            product_id="PROD_A",
            site_id="SITE_1",
            expected_demand_per_period=20.0,
            expected_lead_time=5.0,
            demand_coverage=0.90,
            lead_time_coverage=0.90,
        )

        assert result["safety_stock"] >= 0
        assert result["policy_type"] == "conformal"
        # Joint coverage without predictor = 0.80 * 0.80 = 0.64
        assert result["service_level_guarantee"] == pytest.approx(0.64, abs=0.01)


class TestZScore:
    """Test the get_z_score lookup table."""

    @pytest.fixture
    def calculator(self):
        return InventoryTargetCalculator(config_id=1, group_id=1)

    # -- Test 23 --
    def test_z_score_common_values(self, calculator):
        """Verify z-scores for common service levels."""
        assert calculator.get_z_score(0.50) == 0.00
        assert calculator.get_z_score(0.90) == 1.28
        assert calculator.get_z_score(0.95) == 1.65
        assert calculator.get_z_score(0.99) == 2.33
        assert calculator.get_z_score(0.999) == 3.09

    # -- Test 24 --
    def test_z_score_closest_match(self, calculator):
        """Non-exact service level snaps to closest table entry."""
        # 0.94 is closest to 0.95 → z = 1.65
        assert calculator.get_z_score(0.94) == 1.65
        # 0.91 is closest to 0.90 → z = 1.28
        assert calculator.get_z_score(0.91) == 1.28


class TestHierarchicalOverrideAndTargets:
    """Test target calculation with policy overrides and constraints."""

    @pytest.fixture
    def calculator(self):
        return InventoryTargetCalculator(config_id=1, group_id=1)

    # -- Test 25 --
    @pytest.mark.asyncio
    async def test_target_is_safety_stock_plus_review_period_demand(self, calculator):
        """Target = safety_stock + review_period_demand."""
        policy = _make_policy(ss_policy="abs_level", ss_quantity=100.0, review_period=7)

        net_demand = {
            ("PROD_A", "SITE_1", _date(i)): 10.0
            for i in range(30)
        }

        calculator.get_inventory_policy = AsyncMock(return_value=policy)

        targets = await calculator.calculate_targets(net_demand, _date(0))

        # SS = 100, RPD = 7 days * 10/day = 70 → target = 170
        assert targets[("PROD_A", "SITE_1")] == 170.0

    # -- Test 26 --
    @pytest.mark.asyncio
    async def test_min_qty_constraint(self, calculator):
        """Target is clamped to min_qty if below."""
        policy = _make_policy(
            ss_policy="abs_level", ss_quantity=5.0,
            review_period=1, min_qty=200.0,
        )

        net_demand = {("PROD_A", "SITE_1", _date(0)): 2.0}
        calculator.get_inventory_policy = AsyncMock(return_value=policy)

        targets = await calculator.calculate_targets(net_demand, _date(0))

        # SS=5 + RPD=2 = 7, but min_qty=200 → 200
        assert targets[("PROD_A", "SITE_1")] == 200.0

    # -- Test 27 --
    @pytest.mark.asyncio
    async def test_max_qty_constraint(self, calculator):
        """Target is clamped to max_qty if above."""
        policy = _make_policy(
            ss_policy="abs_level", ss_quantity=500.0,
            review_period=7, max_qty=100.0,
        )

        net_demand = {
            ("PROD_A", "SITE_1", _date(i)): 50.0
            for i in range(30)
        }
        calculator.get_inventory_policy = AsyncMock(return_value=policy)

        targets = await calculator.calculate_targets(net_demand, _date(0))

        # SS=500 + RPD=350 = 850, but max_qty=100 → 100
        assert targets[("PROD_A", "SITE_1")] == 100.0

    # -- Test 28 --
    @pytest.mark.asyncio
    async def test_no_policy_defaults_to_zero(self, calculator):
        """No inventory policy → target = 0."""
        net_demand = {("PROD_A", "SITE_1", _date(0)): 10.0}
        calculator.get_inventory_policy = AsyncMock(return_value=None)

        targets = await calculator.calculate_targets(net_demand, _date(0))

        assert targets[("PROD_A", "SITE_1")] == 0

    # -- Test 29 --
    @pytest.mark.asyncio
    async def test_fallback_reorder_point(self, calculator):
        """Unknown ss_policy with reorder_point set uses reorder_point as SS."""
        policy = _make_policy(
            ss_policy="unknown_type", reorder_point=75.0, review_period=1
        )

        net_demand = {("PROD_A", "SITE_1", _date(0)): 5.0}
        calculator.get_inventory_policy = AsyncMock(return_value=policy)

        targets = await calculator.calculate_targets(net_demand, _date(0))

        # SS=75 (from reorder_point fallback) + RPD=5 = 80
        assert targets[("PROD_A", "SITE_1")] == 80.0

    # -- Test 30 --
    @pytest.mark.asyncio
    async def test_fallback_target_qty_20pct(self, calculator):
        """Unknown ss_policy with target_qty uses 20% of target_qty as SS."""
        policy = _make_policy(
            ss_policy="unknown_type", target_qty=500.0, review_period=1
        )

        net_demand = {("PROD_A", "SITE_1", _date(0)): 5.0}
        calculator.get_inventory_policy = AsyncMock(return_value=policy)

        targets = await calculator.calculate_targets(net_demand, _date(0))

        # SS = 500 * 0.20 = 100 + RPD = 5 → 105
        assert targets[("PROD_A", "SITE_1")] == 105.0


class TestReviewPeriodDemand:
    """Test calculate_review_period_demand."""

    @pytest.fixture
    def calculator(self):
        return InventoryTargetCalculator(config_id=1, group_id=1)

    # -- Test 31 --
    @pytest.mark.asyncio
    async def test_review_period_demand_sums_correctly(self, calculator):
        """Review period demand sums demand within the review window."""
        net_demand = {
            ("PROD_A", "SITE_1", _date(0)): 10.0,
            ("PROD_A", "SITE_1", _date(1)): 15.0,
            ("PROD_A", "SITE_1", _date(2)): 20.0,
            ("PROD_A", "SITE_1", _date(5)): 30.0,  # outside 3-day window
        }

        result = await calculator.calculate_review_period_demand(
            review_period=3,
            product_id="PROD_A",
            site_id="SITE_1",
            net_demand=net_demand,
            start_date=_date(0),
        )

        # Days 0, 1, 2 → 10 + 15 + 20 = 45
        assert result == 45.0


class TestAvgDailyForecast:
    """Test the pure-computation calculate_avg_daily_forecast method."""

    @pytest.fixture
    def calculator(self):
        return InventoryTargetCalculator(config_id=1, group_id=1)

    # -- Test 32 --
    def test_avg_daily_forecast_calculation(self, calculator):
        """Average daily forecast = total demand in horizon / horizon_days."""
        net_demand = {
            ("PROD_A", "SITE_1", _date(i)): 10.0
            for i in range(15)
        }

        result = calculator.calculate_avg_daily_forecast(
            "PROD_A", "SITE_1", net_demand, _date(0), horizon_days=30
        )

        # 15 entries * 10 = 150 total, / 30 days = 5.0
        assert result == 5.0

    # -- Test 33 --
    def test_avg_daily_forecast_empty(self, calculator):
        """Empty demand returns 0."""
        result = calculator.calculate_avg_daily_forecast(
            "PROD_A", "SITE_1", {}, _date(0), horizon_days=30
        )

        assert result == 0.0

    # -- Test 34 --
    def test_avg_daily_forecast_filters_by_product_site(self, calculator):
        """Only demand for the matching product-site is included."""
        net_demand = {
            ("PROD_A", "SITE_1", _date(0)): 100.0,
            ("PROD_B", "SITE_1", _date(0)): 999.0,  # different product
            ("PROD_A", "SITE_2", _date(0)): 888.0,  # different site
        }

        result = calculator.calculate_avg_daily_forecast(
            "PROD_A", "SITE_1", net_demand, _date(0), horizon_days=30
        )

        assert result == pytest.approx(100.0 / 30, abs=0.01)


# ============================================================================
# NetRequirementsCalculator Tests
# ============================================================================


class TestTimePhasedNetting:
    """Test time_phased_netting — the core netting loop."""

    @pytest.fixture
    def calc(self):
        c = NetRequirementsCalculator(config_id=1, group_id=1, planning_horizon=10)
        # Stub out DB-dependent generate_supply_plan to return a mock plan
        return c

    # -- Test 35 --
    @pytest.mark.asyncio
    async def test_basic_netting_no_shortfall(self, calc):
        """Inventory covers all demand → no supply plans generated."""
        net_demand = {
            ("PROD_A", "SITE_1", _date(i)): 10.0
            for i in range(10)
        }

        # Mock generate_supply_plan to track if called
        calc.generate_supply_plan = AsyncMock(return_value=None)

        plans = await calc.time_phased_netting(
            product_id="PROD_A",
            site_id="SITE_1",
            start_date=_date(0),
            opening_inventory=1000.0,  # way more than needed
            scheduled_receipts={},
            net_demand=net_demand,
            target_inventory=50.0,
            scenario_id=None,
        )

        # Inventory starts at 1000, loses 100 total → always above 50 target
        assert plans == []

    # -- Test 36 --
    @pytest.mark.asyncio
    async def test_basic_netting_triggers_replenishment(self, calc):
        """Inventory drops below target → supply plan generated."""
        net_demand = {
            ("PROD_A", "SITE_1", _date(0)): 80.0,
        }

        mock_plan = SimpleNamespace(planned_order_quantity=70.0)
        calc.generate_supply_plan = AsyncMock(return_value=mock_plan)

        plans = await calc.time_phased_netting(
            product_id="PROD_A",
            site_id="SITE_1",
            start_date=_date(0),
            opening_inventory=50.0,
            scheduled_receipts={},
            net_demand=net_demand,
            target_inventory=40.0,
            scenario_id=None,
        )

        # Day 0: 50 + 0 - 80 = -30. That is < 40 target → replenish
        assert len(plans) >= 1

    # -- Test 37 --
    @pytest.mark.asyncio
    async def test_scheduled_receipts_offset_demand(self, calc):
        """Scheduled receipts increase projected inventory."""
        net_demand = {
            ("PROD_A", "SITE_1", _date(0)): 100.0,
        }
        scheduled_receipts = {
            _date(0): 80.0,  # receipt on same day
        }

        calc.generate_supply_plan = AsyncMock(return_value=None)

        plans = await calc.time_phased_netting(
            product_id="PROD_A",
            site_id="SITE_1",
            start_date=_date(0),
            opening_inventory=50.0,
            scheduled_receipts=scheduled_receipts,
            net_demand=net_demand,
            target_inventory=20.0,
            scenario_id=None,
        )

        # Day 0: 50 + 80 - 100 = 30 ≥ 20 target → no replenishment
        assert plans == []


class TestNetReqSourcingRuleSelection:
    """Test sourcing rule priority and type selection."""

    # -- Test 38 --
    @pytest.mark.asyncio
    async def test_highest_priority_rule_selected(self):
        """Among multiple rules, the one with lowest priority number wins."""
        calc = NetRequirementsCalculator(config_id=1, group_id=1, planning_horizon=10)

        rule_high = _make_sourcing_rule(
            sourcing_rule_type="buy", priority=1, lead_time=3
        )
        rule_low = _make_sourcing_rule(
            sourcing_rule_type="transfer", priority=5, lead_time=7
        )

        calc.get_sourcing_rules = AsyncMock(return_value=[rule_high, rule_low])
        calc.create_plan_for_sourcing_rule = AsyncMock(
            return_value=SimpleNamespace(planned_order_quantity=100)
        )

        plan = await calc.generate_supply_plan(
            "PROD_A", "SITE_1", _date(0), 100.0, 0.0, 100.0, None
        )

        # Should call create_plan_for_sourcing_rule with the high-priority rule
        calc.create_plan_for_sourcing_rule.assert_awaited_once()
        called_rule = calc.create_plan_for_sourcing_rule.call_args[0][0]
        assert called_rule.sourcing_rule_type == "buy"
        assert called_rule.priority == 1

    # -- Test 39 --
    @pytest.mark.asyncio
    async def test_no_sourcing_rule_returns_none(self):
        """No sourcing rules → None (no plan generated)."""
        calc = NetRequirementsCalculator(config_id=1, group_id=1, planning_horizon=10)
        calc.get_sourcing_rules = AsyncMock(return_value=[])

        plan = await calc.generate_supply_plan(
            "PROD_A", "SITE_1", _date(0), 100.0, 0.0, 100.0, None
        )

        assert plan is None

    # -- Test 40 --
    @pytest.mark.asyncio
    async def test_manufacture_rule_type(self):
        """Manufacture sourcing rule dispatches to create_manufacture_plan."""
        calc = NetRequirementsCalculator(config_id=1, group_id=1, planning_horizon=10)

        rule = _make_sourcing_rule(sourcing_rule_type="manufacture", priority=1)

        calc.get_sourcing_rules = AsyncMock(return_value=[rule])
        calc.create_plan_for_sourcing_rule = AsyncMock(
            return_value=SimpleNamespace(planned_order_quantity=50)
        )

        await calc.generate_supply_plan(
            "PROD_A", "SITE_1", _date(0), 50.0, 0.0, 50.0, None
        )

        calc.create_plan_for_sourcing_rule.assert_awaited_once()
        called_rule = calc.create_plan_for_sourcing_rule.call_args[0][0]
        assert called_rule.sourcing_rule_type == "manufacture"


class TestBOMExplosion:
    """Test BOM explosion logic."""

    # -- Test 41 --
    @pytest.mark.asyncio
    async def test_cycle_detection_prevents_infinite_loop(self):
        """BOM with circular reference is detected and stops."""
        calc = NetRequirementsCalculator(config_id=1, group_id=1, planning_horizon=10)

        # Simulate a circular BOM by pre-adding a visited key
        calc._visited_boms.add(("PROD_A", "default"))

        # This should return immediately without error
        await calc.explode_bom(
            "PROD_A", 100.0, _date(0), None, "SITE_1", None
        )

        # The BOM key was already visited, so depth should not have changed
        assert calc._bom_traversal_depth == 0

    # -- Test 42 --
    @pytest.mark.asyncio
    async def test_max_depth_prevents_runaway(self):
        """BOM traversal stops at max depth (10 levels)."""
        calc = NetRequirementsCalculator(config_id=1, group_id=1, planning_horizon=10)
        calc._bom_traversal_depth = 10  # At max

        await calc.explode_bom(
            "PROD_DEEP", 100.0, _date(0), None, "SITE_1", None
        )

        # Should not increase depth further
        assert calc._bom_traversal_depth == 10


class TestMultiSourcing:
    """Test multi-sourcing allocation by ratio."""

    # -- Test 43 --
    @pytest.mark.asyncio
    async def test_multi_sourcing_allocation(self):
        """Equal-priority rules split requirement by allocation_percent."""
        calc = NetRequirementsCalculator(config_id=1, group_id=1, planning_horizon=10)

        rule_a = _make_sourcing_rule(
            sourcing_rule_type="buy", priority=1,
            allocation_percent=60, supplier_site_id="VENDOR_A"
        )
        rule_b = _make_sourcing_rule(
            sourcing_rule_type="buy", priority=1,
            allocation_percent=40, supplier_site_id="VENDOR_B"
        )

        calc.get_sourcing_rules = AsyncMock(return_value=[rule_a, rule_b])

        created_plans = []

        async def mock_create(rule, pid, sid, plan_date, qty, proj, tgt, gid):
            plan = SimpleNamespace(planned_order_quantity=qty)
            created_plans.append((rule.supplier_site_id, qty))
            return plan

        calc.create_plan_for_sourcing_rule = AsyncMock(side_effect=mock_create)

        await calc.generate_supply_plan(
            "PROD_A", "SITE_1", _date(0), 100.0, 0.0, 100.0, None
        )

        # Should create plans for both vendors
        assert len(created_plans) == 2

        # Check allocation ratios: 60/100 * 100 = 60, 40/100 * 100 = 40
        quantities = {site: qty for site, qty in created_plans}
        assert quantities["VENDOR_A"] == pytest.approx(60.0)
        assert quantities["VENDOR_B"] == pytest.approx(40.0)
