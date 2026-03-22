"""
Unit tests for the ERP/APS-specific heuristic library.

All functions under test are pure (no DB, no side effects).
Tests verify netting dispatch, lot sizing, order modifications,
BOM scrap, and allocation logic.

See DIGITAL_TWIN.md §8A for algorithmic specification.
"""

import math
import pytest

from app.services.powell.heuristic_library import (
    ReplenishmentState,
    ReplenishmentConfig,
    compute_replenishment,
    explode_bom_with_scrap,
    fair_share_allocate,
    priority_allocate,
    _net_reorder_point,
    _net_forecast_based,
    _net_lot_for_lot,
    _net_period_batching,
    _net_min_max,
    _net_no_planning,
    _apply_lot_sizing,
    _apply_order_modifications,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state(**overrides) -> ReplenishmentState:
    defaults = dict(
        inventory_position=100.0,
        on_hand=100.0,
        backlog=0.0,
        pipeline_qty=0.0,
        avg_daily_demand=10.0,
        demand_cv=0.3,
        lead_time_days=7.0,
        forecast_daily=10.0,
        day_of_week=0,   # Monday
        day_of_month=1,
    )
    defaults.update(overrides)
    return ReplenishmentState(**defaults)


def _config(**overrides) -> ReplenishmentConfig:
    defaults = dict(
        planning_method="REORDER_POINT",
        lot_sizing_rule="LOT_FOR_LOT",
        reorder_point=100.0,
        order_up_to=200.0,
        safety_stock=50.0,
        fixed_lot_size=0.0,
        min_order_quantity=0.0,
        max_order_quantity=0.0,
        order_multiple=0.0,
        review_period_days=7,
        frozen_horizon_days=0,
        max_inventory=0.0,
    )
    defaults.update(overrides)
    return ReplenishmentConfig(**defaults)


# ===================================================================
# NETTING METHODS
# ===================================================================


class TestReorderPoint:

    def test_triggers_below_rop(self):
        s = _state(inventory_position=50.0)
        c = _config(reorder_point=100.0, order_up_to=200.0)
        assert _net_reorder_point(s, c) == 150.0  # 200 - 50

    def test_no_order_at_rop(self):
        s = _state(inventory_position=100.0)
        c = _config(reorder_point=100.0)
        assert _net_reorder_point(s, c) == 0.0

    def test_no_order_above_rop(self):
        s = _state(inventory_position=150.0)
        c = _config(reorder_point=100.0)
        assert _net_reorder_point(s, c) == 0.0

    def test_negative_inventory_position(self):
        s = _state(inventory_position=-20.0)
        c = _config(reorder_point=100.0, order_up_to=200.0)
        assert _net_reorder_point(s, c) == 220.0  # 200 - (-20)


class TestForecastBased:

    def test_covers_review_period(self):
        s = _state(inventory_position=0.0, forecast_daily=10.0)
        c = _config(planning_method="FORECAST_BASED", review_period_days=7, safety_stock=20.0)
        # 10 * 7 + 20 - 0 = 90
        assert _net_forecast_based(s, c) == 90.0

    def test_no_order_when_covered(self):
        s = _state(inventory_position=200.0, forecast_daily=10.0)
        c = _config(planning_method="FORECAST_BASED", review_period_days=7, safety_stock=20.0)
        # 10 * 7 + 20 - 200 = -110 → 0
        assert _net_forecast_based(s, c) == 0.0


class TestLotForLot:

    def test_orders_exact_need(self):
        s = _state(inventory_position=-5.0, avg_daily_demand=10.0)
        c = _config(planning_method="LOT_FOR_LOT", safety_stock=20.0)
        # 10 + 20 - (-5) = 35
        assert _net_lot_for_lot(s, c) == 35.0

    def test_no_order_when_sufficient(self):
        s = _state(inventory_position=100.0, avg_daily_demand=10.0)
        c = _config(planning_method="LOT_FOR_LOT", safety_stock=20.0)
        # 10 + 20 - 100 = -70 → 0
        assert _net_lot_for_lot(s, c) == 0.0


class TestPeriodBatching:

    def test_orders_on_monday_weekly(self):
        s = _state(inventory_position=0.0, avg_daily_demand=10.0, day_of_week=0)
        c = _config(planning_method="PERIOD_BATCHING", lot_sizing_rule="WEEKLY_BATCH",
                     review_period_days=7, safety_stock=20.0)
        # 10 * 7 + 20 - 0 = 90
        assert _net_period_batching(s, c) == 90.0

    def test_no_order_on_wednesday_weekly(self):
        s = _state(inventory_position=0.0, avg_daily_demand=10.0, day_of_week=3)
        c = _config(planning_method="PERIOD_BATCHING", lot_sizing_rule="WEEKLY_BATCH")
        assert _net_period_batching(s, c) == 0.0

    def test_orders_on_first_monthly(self):
        s = _state(inventory_position=0.0, avg_daily_demand=10.0, day_of_month=1)
        c = _config(planning_method="PERIOD_BATCHING", lot_sizing_rule="MONTHLY_BATCH",
                     review_period_days=30, safety_stock=20.0)
        # 10 * 30 + 20 - 0 = 320
        assert _net_period_batching(s, c) == 320.0

    def test_no_order_mid_month(self):
        s = _state(day_of_month=15)
        c = _config(planning_method="PERIOD_BATCHING", lot_sizing_rule="MONTHLY_BATCH")
        assert _net_period_batching(s, c) == 0.0

    def test_daily_batch_always_orders(self):
        s = _state(inventory_position=0.0, avg_daily_demand=10.0, day_of_week=4)
        c = _config(planning_method="PERIOD_BATCHING", lot_sizing_rule="DAILY_BATCH",
                     review_period_days=1, safety_stock=5.0)
        # 10 * 1 + 5 - 0 = 15
        assert _net_period_batching(s, c) == 15.0


class TestMinMax:

    def test_below_min_orders_to_max(self):
        s = _state(inventory_position=40.0)
        c = _config(planning_method="MIN_MAX", reorder_point=50.0, max_inventory=200.0)
        assert _net_min_max(s, c) == 160.0  # 200 - 40

    def test_above_min_no_order(self):
        s = _state(inventory_position=60.0)
        c = _config(planning_method="MIN_MAX", reorder_point=50.0, max_inventory=200.0)
        assert _net_min_max(s, c) == 0.0

    def test_falls_back_to_order_up_to_when_no_max(self):
        s = _state(inventory_position=40.0)
        c = _config(planning_method="MIN_MAX", reorder_point=50.0, max_inventory=0.0, order_up_to=150.0)
        assert _net_min_max(s, c) == 110.0  # 150 - 40


class TestNoPlanning:

    def test_never_orders(self):
        s = _state(inventory_position=-100.0)
        c = _config(planning_method="NO_PLANNING")
        assert _net_no_planning(s, c) == 0.0


# ===================================================================
# LOT SIZING
# ===================================================================


class TestLotSizing:

    def test_lot_for_lot_passthrough(self):
        s = _state()
        c = _config(lot_sizing_rule="LOT_FOR_LOT")
        assert _apply_lot_sizing(75.0, s, c) == 75.0

    def test_fixed_rounds_up(self):
        s = _state()
        c = _config(lot_sizing_rule="FIXED", fixed_lot_size=50.0)
        assert _apply_lot_sizing(75.0, s, c) == 100.0  # ceil(75/50)*50

    def test_fixed_exact_multiple(self):
        s = _state()
        c = _config(lot_sizing_rule="FIXED", fixed_lot_size=50.0)
        assert _apply_lot_sizing(100.0, s, c) == 100.0

    def test_fixed_small_qty(self):
        s = _state()
        c = _config(lot_sizing_rule="FIXED", fixed_lot_size=50.0)
        assert _apply_lot_sizing(1.0, s, c) == 50.0

    def test_replenish_to_max(self):
        s = _state(inventory_position=40.0)
        c = _config(lot_sizing_rule="REPLENISH_TO_MAX", max_inventory=200.0)
        assert _apply_lot_sizing(100.0, s, c) == 160.0  # 200 - 40

    def test_zero_qty_returns_zero(self):
        s = _state()
        c = _config()
        assert _apply_lot_sizing(0.0, s, c) == 0.0

    def test_negative_qty_returns_zero(self):
        s = _state()
        c = _config()
        assert _apply_lot_sizing(-10.0, s, c) == 0.0


# ===================================================================
# ORDER MODIFICATIONS
# ===================================================================


class TestOrderModifications:

    def test_moq_floors(self):
        c = _config(min_order_quantity=100.0)
        assert _apply_order_modifications(30.0, c) == 100.0

    def test_moq_no_effect_above(self):
        c = _config(min_order_quantity=100.0)
        assert _apply_order_modifications(150.0, c) == 150.0

    def test_order_multiple_rounds_up(self):
        c = _config(order_multiple=24.0)
        assert _apply_order_modifications(50.0, c) == 72.0  # ceil(50/24)*24

    def test_order_multiple_exact(self):
        c = _config(order_multiple=24.0)
        assert _apply_order_modifications(48.0, c) == 48.0

    def test_max_qty_caps(self):
        c = _config(max_order_quantity=80.0)
        assert _apply_order_modifications(100.0, c) == 80.0

    def test_moq_then_multiple_then_max(self):
        # MOQ=50, multiple=24, max=80
        # raw=10 → MOQ=50 → multiple=ceil(50/24)*24=72 → max=min(72,80)=72
        c = _config(min_order_quantity=50.0, order_multiple=24.0, max_order_quantity=80.0)
        assert _apply_order_modifications(10.0, c) == 72.0

    def test_zero_returns_zero(self):
        c = _config(min_order_quantity=100.0)
        assert _apply_order_modifications(0.0, c) == 0.0

    def test_negative_returns_zero(self):
        c = _config()
        assert _apply_order_modifications(-5.0, c) == 0.0


# ===================================================================
# FULL DISPATCH (compute_replenishment)
# ===================================================================


class TestComputeReplenishment:

    def test_rop_with_fixed_lot_and_moq(self):
        s = _state(inventory_position=50.0)
        c = _config(
            planning_method="REORDER_POINT",
            lot_sizing_rule="FIXED",
            reorder_point=100.0,
            order_up_to=200.0,
            fixed_lot_size=50.0,
            min_order_quantity=100.0,
        )
        # net: 200-50=150. lot sizing: ceil(150/50)*50=150. MOQ: max(150,100)=150.
        assert compute_replenishment(s, c) == 150.0

    def test_no_planning_returns_zero(self):
        s = _state(inventory_position=-100.0)
        c = _config(planning_method="NO_PLANNING")
        assert compute_replenishment(s, c) == 0.0

    def test_above_rop_returns_zero(self):
        s = _state(inventory_position=150.0)
        c = _config(planning_method="REORDER_POINT", reorder_point=100.0)
        assert compute_replenishment(s, c) == 0.0

    def test_unknown_method_falls_back_to_rop(self):
        s = _state(inventory_position=50.0)
        c = _config(planning_method="UNKNOWN_METHOD", reorder_point=100.0, order_up_to=200.0)
        assert compute_replenishment(s, c) == 150.0

    def test_backward_compatible_defaults(self):
        """Default config (REORDER_POINT + LOT_FOR_LOT) should behave like old hardcoded ROP."""
        s = _state(inventory_position=50.0)
        c = _config()  # all defaults
        expected = 200.0 - 50.0  # order_up_to - IP
        assert compute_replenishment(s, c) == expected


# ===================================================================
# BOM EXPLOSION WITH SCRAP
# ===================================================================


class TestBomExplosionWithScrap:

    def test_no_scrap(self):
        result = explode_bom_with_scrap(100.0, [("COMP1", 2.0, 0.0)])
        assert result == [("COMP1", 200.0)]

    def test_5pct_scrap(self):
        result = explode_bom_with_scrap(100.0, [("COMP1", 2.0, 5.0)])
        assert len(result) == 1
        assert result[0][0] == "COMP1"
        assert abs(result[0][1] - 210.0) < 0.01  # 100 * 2.0 * 1.05

    def test_multiple_components(self):
        result = explode_bom_with_scrap(50.0, [
            ("A", 1.0, 0.0),
            ("B", 3.0, 10.0),
            ("C", 0.5, 2.0),
        ])
        assert len(result) == 3
        assert abs(result[0][1] - 50.0) < 0.01    # 50 * 1.0 * 1.0
        assert abs(result[1][1] - 165.0) < 0.01   # 50 * 3.0 * 1.10
        assert abs(result[2][1] - 25.5) < 0.01    # 50 * 0.5 * 1.02

    def test_none_scrap_treated_as_zero(self):
        result = explode_bom_with_scrap(100.0, [("X", 1.0, None)])
        assert result == [("X", 100.0)]


# ===================================================================
# ALLOCATION
# ===================================================================


class TestFairShareAllocate:

    def test_sufficient_supply(self):
        allocs = fair_share_allocate(100.0, [("A", 60.0, 1), ("B", 40.0, 1)])
        assert allocs["A"] == 60.0
        assert allocs["B"] == 40.0

    def test_shortage_proportional(self):
        allocs = fair_share_allocate(50.0, [("A", 60.0, 1), ("B", 40.0, 1)])
        assert abs(allocs["A"] - 30.0) < 0.01  # 60/100 * 50
        assert abs(allocs["B"] - 20.0) < 0.01  # 40/100 * 50

    def test_priority_waterfall_then_proportional(self):
        allocs = fair_share_allocate(50.0, [("A", 40.0, 1), ("B", 40.0, 2)])
        assert allocs["A"] == 40.0   # Priority 1 gets full demand
        assert allocs["B"] == 10.0   # Priority 2 gets remainder

    def test_zero_supply(self):
        allocs = fair_share_allocate(0.0, [("A", 100.0, 1)])
        assert allocs["A"] == 0.0

    def test_same_priority_fair_share_on_shortage(self):
        allocs = fair_share_allocate(
            30.0,
            [("A", 20.0, 1), ("B", 20.0, 1), ("C", 20.0, 1)],
        )
        assert abs(allocs["A"] - 10.0) < 0.01
        assert abs(allocs["B"] - 10.0) < 0.01
        assert abs(allocs["C"] - 10.0) < 0.01


class TestPriorityAllocate:

    def test_full_waterfall(self):
        allocs = priority_allocate(50.0, [("A", 30.0, 1), ("B", 30.0, 2)])
        assert allocs["A"] == 30.0
        assert allocs["B"] == 20.0

    def test_insufficient_for_first(self):
        allocs = priority_allocate(10.0, [("A", 30.0, 1), ("B", 30.0, 2)])
        assert allocs["A"] == 10.0
        assert allocs["B"] == 0.0

    def test_zero_supply(self):
        allocs = priority_allocate(0.0, [("A", 100.0, 1)])
        assert allocs["A"] == 0.0
