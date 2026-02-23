"""
Tests for Deterministic Supply Planning Module

Covers:
- DemandForecast, PlanningOrder, InventoryTarget dataclasses
- Safety stock calculation  (SS = z * sigma * sqrt(LT))
- Economic Order Quantity    (EOQ = sqrt(2*D*K / h))
- Order type determination based on node type
- Order cost calculation
- Replenishment order generation via ROP policy
- SupplyPlanService._serialize_orders / _serialize_targets
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest
from scipy.stats import norm

from app.services.deterministic_planner import (
    DemandForecast,
    DeterministicPlanner,
    InventoryTarget,
    OrderType,
    PlanningOrder,
)
from app.services.supply_plan_service import SupplyPlanService
from app.models.supply_chain_config import Node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_planner(planning_horizon: int = 52) -> DeterministicPlanner:
    """Create a DeterministicPlanner with mocked session and config."""
    session = MagicMock()
    config = MagicMock()
    config.id = 1
    config.name = "Test Config"
    return DeterministicPlanner(session, config, planning_horizon)


def _make_node(node_id: int = 1, node_type: str = "retailer") -> SimpleNamespace:
    """Create a lightweight node substitute."""
    return SimpleNamespace(id=node_id, type=node_type, config_id=1)


def _make_item(item_id: int = 1) -> SimpleNamespace:
    """Create a lightweight item substitute."""
    return SimpleNamespace(id=item_id, config_id=1)


# ===================================================================
# 1. DemandForecast dataclass
# ===================================================================

class TestDemandForecast:

    def test_construction_with_all_fields(self):
        """DemandForecast stores all supplied fields correctly."""
        weekly = np.array([10.0, 12.0, 11.0, 9.0])
        fc = DemandForecast(
            item_id=5,
            node_id=7,
            weekly_demand=weekly,
            demand_std_dev=2.5,
            total_demand=42.0,
        )
        assert fc.item_id == 5
        assert fc.node_id == 7
        np.testing.assert_array_equal(fc.weekly_demand, weekly)
        assert fc.demand_std_dev == 2.5
        assert fc.total_demand == 42.0

    def test_weekly_demand_accepts_numpy_array(self):
        """weekly_demand field works as a proper numpy array."""
        weekly = np.arange(1, 53, dtype=float)
        fc = DemandForecast(
            item_id=1,
            node_id=1,
            weekly_demand=weekly,
            demand_std_dev=5.0,
            total_demand=float(weekly.sum()),
        )
        assert len(fc.weekly_demand) == 52
        assert fc.weekly_demand.dtype == np.float64
        np.testing.assert_almost_equal(fc.total_demand, weekly.sum())


# ===================================================================
# 2. PlanningOrder dataclass
# ===================================================================

class TestPlanningOrder:

    def test_construction(self):
        """PlanningOrder stores fields including order type enum."""
        order = PlanningOrder(
            order_type=OrderType.PURCHASE_ORDER,
            item_id=1,
            source_node_id=10,
            destination_node_id=20,
            quantity=150.0,
            planned_week=3,
            delivery_week=5,
            cost=7600.0,
        )
        assert order.order_type == OrderType.PURCHASE_ORDER
        assert order.quantity == 150.0
        assert order.delivery_week == 5

    def test_order_types_are_distinct(self):
        """OrderType enum has three distinct members."""
        assert OrderType.PURCHASE_ORDER.value == "purchase_order"
        assert OrderType.MANUFACTURING_ORDER.value == "manufacturing_order"
        assert OrderType.STOCK_TRANSFER_ORDER.value == "stock_transfer_order"
        assert len(OrderType) == 3


# ===================================================================
# 3. InventoryTarget dataclass
# ===================================================================

class TestInventoryTarget:

    def test_construction(self):
        """InventoryTarget stores safety stock, ROP, and EOQ."""
        tgt = InventoryTarget(
            node_id=1,
            item_id=2,
            safety_stock=32.9,
            reorder_point=132.9,
            order_quantity=316.2,
            review_period=1,
        )
        assert tgt.safety_stock == 32.9
        assert tgt.reorder_point == 132.9
        assert tgt.order_quantity == 316.2

    def test_review_period_default_concept(self):
        """Review period is simply an int field; verify it persists."""
        tgt = InventoryTarget(
            node_id=1, item_id=1,
            safety_stock=0, reorder_point=0,
            order_quantity=1, review_period=4,
        )
        assert tgt.review_period == 4


# ===================================================================
# 4. _calculate_safety_stock  (SS = z * sigma * sqrt(LT))
# ===================================================================

class TestCalculateSafetyStock:

    def test_normal_case_95_service(self):
        """sigma=10, LT=4, SL=0.95 => SS ~ 1.645 * 10 * 2 = 32.90."""
        planner = _make_planner()
        ss = planner._calculate_safety_stock(
            demand_std_dev=10.0,
            lead_time=4,
            service_level=0.95,
        )
        expected = norm.ppf(0.95) * 10.0 * np.sqrt(4)
        assert pytest.approx(ss, rel=1e-4) == expected

    def test_zero_std_dev_returns_zero(self):
        """Zero demand variability means zero safety stock."""
        planner = _make_planner()
        ss = planner._calculate_safety_stock(
            demand_std_dev=0.0,
            lead_time=4,
            service_level=0.95,
        )
        assert ss == 0.0

    def test_high_service_level_99(self):
        """SL=0.99 => z ~ 2.326, larger safety stock."""
        planner = _make_planner()
        ss = planner._calculate_safety_stock(
            demand_std_dev=10.0,
            lead_time=4,
            service_level=0.99,
        )
        expected = norm.ppf(0.99) * 10.0 * np.sqrt(4)
        assert pytest.approx(ss, rel=1e-4) == expected
        # Verify it is larger than 95% case
        ss_95 = planner._calculate_safety_stock(10.0, 4, 0.95)
        assert ss > ss_95

    def test_service_level_50_gives_zero(self):
        """SL=0.50 => z=0 => SS=0."""
        planner = _make_planner()
        ss = planner._calculate_safety_stock(
            demand_std_dev=10.0,
            lead_time=4,
            service_level=0.50,
        )
        # norm.ppf(0.5) == 0.0, so z * sigma * sqrt(LT) == 0
        assert ss == 0.0

    def test_lead_time_one_period(self):
        """LT=1 => sqrt(1) = 1, so SS = z * sigma."""
        planner = _make_planner()
        ss = planner._calculate_safety_stock(
            demand_std_dev=15.0,
            lead_time=1,
            service_level=0.95,
        )
        expected = norm.ppf(0.95) * 15.0 * 1.0
        assert pytest.approx(ss, rel=1e-4) == expected


# ===================================================================
# 5. _calculate_eoq  (EOQ = sqrt(2*D*K / h))
# ===================================================================

class TestCalculateEOQ:

    def test_normal_case(self):
        """D=10000, K=100, h=20 => EOQ = sqrt(100000) ~ 316.23."""
        planner = _make_planner()
        eoq = planner._calculate_eoq(
            annual_demand=10_000,
            ordering_cost=100.0,
            holding_cost=20.0,
        )
        expected = np.sqrt(2 * 10_000 * 100.0 / 20.0)
        assert pytest.approx(eoq, rel=1e-4) == expected

    def test_zero_holding_cost_clips_to_001(self):
        """h=0 is replaced by 0.01 to avoid division by zero."""
        planner = _make_planner()
        eoq = planner._calculate_eoq(
            annual_demand=1000,
            ordering_cost=100.0,
            holding_cost=0.0,
        )
        expected = np.sqrt(2 * 1000 * 100.0 / 0.01)
        assert pytest.approx(eoq, rel=1e-4) == expected

    def test_very_small_demand(self):
        """Very small demand still produces EOQ >= 1."""
        planner = _make_planner()
        eoq = planner._calculate_eoq(
            annual_demand=0.001,
            ordering_cost=100.0,
            holding_cost=20.0,
        )
        # sqrt(2 * 0.001 * 100 / 20) ~ 0.1, floored to 1
        assert eoq >= 1.0

    def test_large_demand(self):
        """Large demand yields proportionally large EOQ."""
        planner = _make_planner()
        eoq = planner._calculate_eoq(
            annual_demand=1_000_000,
            ordering_cost=500.0,
            holding_cost=10.0,
        )
        expected = np.sqrt(2 * 1_000_000 * 500.0 / 10.0)
        assert pytest.approx(eoq, rel=1e-4) == expected

    def test_result_always_at_least_one(self):
        """EOQ is always max(1, computed) -- floor at 1."""
        planner = _make_planner()
        # Negative holding cost is clipped; tiny demand gives tiny EOQ
        eoq = planner._calculate_eoq(
            annual_demand=0.0,
            ordering_cost=0.0,
            holding_cost=100.0,
        )
        assert eoq >= 1.0


# ===================================================================
# 6. _generate_replenishment_orders (ROP policy simulation)
# ===================================================================

class TestGenerateReplenishmentOrders:

    def _setup_planner_for_replenishment(
        self,
        current_inventory: float = 0.0,
        lead_time: int = 2,
        planning_horizon: int = 10,
    ) -> DeterministicPlanner:
        """Build a planner with deterministic mocks for replenishment tests."""
        planner = _make_planner(planning_horizon)
        # Patch helpers to return predictable values
        planner._get_current_inventory = MagicMock(return_value=current_inventory)
        planner._get_pipeline_inventory = MagicMock(return_value=0.0)
        planner._get_lead_time = MagicMock(return_value=lead_time)
        planner._get_source_node = MagicMock(return_value=99)
        return planner

    def test_orders_generated_when_inventory_below_rop(self):
        """An order is placed when starting inventory is below ROP."""
        planner = self._setup_planner_for_replenishment(
            current_inventory=0.0, lead_time=2, planning_horizon=10,
        )
        node = _make_node(1, "retailer")
        item = _make_item(1)
        forecast = DemandForecast(
            item_id=1, node_id=1,
            weekly_demand=np.full(10, 10.0),
            demand_std_dev=2.0,
            total_demand=100.0,
        )

        orders = planner._generate_replenishment_orders(
            node, item, forecast,
            reorder_point=50.0,
            order_quantity=100.0,
        )
        assert len(orders) > 0
        assert all(isinstance(o, PlanningOrder) for o in orders)

    def test_delivery_week_respects_lead_time(self):
        """delivery_week = planned_week + lead_time."""
        planner = self._setup_planner_for_replenishment(
            current_inventory=0.0, lead_time=3, planning_horizon=5,
        )
        node = _make_node(1, "retailer")
        item = _make_item(1)
        forecast = DemandForecast(
            item_id=1, node_id=1,
            weekly_demand=np.full(5, 10.0),
            demand_std_dev=2.0,
            total_demand=50.0,
        )

        orders = planner._generate_replenishment_orders(
            node, item, forecast,
            reorder_point=20.0,
            order_quantity=50.0,
        )
        for order in orders:
            assert order.delivery_week == order.planned_week + 3

    def test_no_orders_if_inventory_always_above_rop(self):
        """If starting inventory is very high, no orders should be placed."""
        planner = self._setup_planner_for_replenishment(
            current_inventory=999_999.0, lead_time=2, planning_horizon=10,
        )
        node = _make_node(1, "retailer")
        item = _make_item(1)
        forecast = DemandForecast(
            item_id=1, node_id=1,
            weekly_demand=np.full(10, 5.0),
            demand_std_dev=1.0,
            total_demand=50.0,
        )

        orders = planner._generate_replenishment_orders(
            node, item, forecast,
            reorder_point=100.0,
            order_quantity=200.0,
        )
        assert len(orders) == 0


# ===================================================================
# 7. _determine_order_type
# ===================================================================

class TestDetermineOrderType:

    def test_manufacturer_node_returns_mo(self):
        """Nodes with 'manufact' in type produce manufacturing orders."""
        planner = _make_planner()
        node = _make_node(node_type="manufacturer")
        assert planner._determine_order_type(node) == OrderType.MANUFACTURING_ORDER

    def test_plant_node_returns_mo(self):
        """Nodes with 'plant' in type also produce manufacturing orders."""
        planner = _make_planner()
        node = _make_node(node_type="plant")
        assert planner._determine_order_type(node) == OrderType.MANUFACTURING_ORDER

    def test_supplier_node_returns_po(self):
        """Supplier-type nodes produce purchase orders."""
        planner = _make_planner()
        node = _make_node(node_type="supplier")
        assert planner._determine_order_type(node) == OrderType.PURCHASE_ORDER

    def test_retailer_node_returns_po(self):
        """Non-manufacturer, non-supplier nodes default to purchase orders."""
        planner = _make_planner()
        node = _make_node(node_type="retailer")
        assert planner._determine_order_type(node) == OrderType.PURCHASE_ORDER

    def test_wholesaler_node_returns_po(self):
        """Wholesaler nodes default to purchase orders."""
        planner = _make_planner()
        node = _make_node(node_type="wholesaler")
        assert planner._determine_order_type(node) == OrderType.PURCHASE_ORDER


# ===================================================================
# 8. _calculate_order_cost
# ===================================================================

class TestCalculateOrderCost:

    def test_cost_formula(self):
        """Cost = 100 (fixed) + quantity * 50."""
        planner = _make_planner()
        cost = planner._calculate_order_cost(OrderType.PURCHASE_ORDER, 10.0)
        assert cost == 100.0 + 10.0 * 50.0

    def test_zero_quantity(self):
        """Zero quantity should still incur the fixed ordering cost."""
        planner = _make_planner()
        cost = planner._calculate_order_cost(OrderType.MANUFACTURING_ORDER, 0.0)
        assert cost == 100.0


# ===================================================================
# 9. SupplyPlanService._serialize_orders / _serialize_targets
# ===================================================================

class TestSerializeOrders:

    def test_serialize_orders_roundtrip(self):
        """Serialized orders produce list of dicts with correct keys."""
        service = SupplyPlanService.__new__(SupplyPlanService)

        orders = [
            PlanningOrder(
                order_type=OrderType.PURCHASE_ORDER,
                item_id=1,
                source_node_id=10,
                destination_node_id=20,
                quantity=200.0,
                planned_week=3,
                delivery_week=5,
                cost=10100.0,
            ),
            PlanningOrder(
                order_type=OrderType.MANUFACTURING_ORDER,
                item_id=2,
                source_node_id=None,
                destination_node_id=30,
                quantity=50.0,
                planned_week=1,
                delivery_week=4,
                cost=2600.0,
            ),
        ]

        result = service._serialize_orders(orders)

        assert len(result) == 2

        first = result[0]
        assert first["order_type"] == "purchase_order"
        assert first["item_id"] == 1
        assert first["source_node_id"] == 10
        assert first["destination_node_id"] == 20
        assert first["quantity"] == 200.0
        assert first["planned_week"] == 3
        assert first["delivery_week"] == 5
        assert first["cost"] == 10100.0

        second = result[1]
        assert second["order_type"] == "manufacturing_order"
        assert second["source_node_id"] is None


class TestSerializeTargets:

    def test_serialize_targets(self):
        """Serialized targets produce list of dicts with correct keys."""
        service = SupplyPlanService.__new__(SupplyPlanService)

        targets = [
            InventoryTarget(
                node_id=1,
                item_id=2,
                safety_stock=32.9,
                reorder_point=132.9,
                order_quantity=316.2,
                review_period=1,
            ),
        ]

        result = service._serialize_targets(targets)

        assert len(result) == 1
        t = result[0]
        assert t["node_id"] == 1
        assert t["item_id"] == 2
        assert t["safety_stock"] == 32.9
        assert t["reorder_point"] == 132.9
        assert t["order_quantity"] == 316.2
        assert t["review_period"] == 1


# ===================================================================
# 10. Integration-style: generate_plan with mocked DB
# ===================================================================

class TestGeneratePlan:

    def _setup_full_planner(self) -> DeterministicPlanner:
        """Create planner with all DB-touching methods mocked out."""
        planner = _make_planner(planning_horizon=10)
        planner._get_lead_time = MagicMock(return_value=2)
        planner._get_item_value = MagicMock(return_value=100.0)
        planner._get_current_inventory = MagicMock(return_value=0.0)
        planner._get_pipeline_inventory = MagicMock(return_value=0.0)
        planner._get_source_node = MagicMock(return_value=None)

        # Mock session.query for Node and Item queries in generate_plan
        node = _make_node(1, "retailer")
        item = _make_item(1)

        query_mock = MagicMock()
        filter_mock = MagicMock()
        filter_mock.all.return_value = [node]

        def query_side_effect(model):
            mock = MagicMock()
            model_name = getattr(model, '__name__', '') or getattr(model, '__tablename__', '')
            if 'Node' in str(model_name) or 'node' in str(model_name) or model is Node:
                mock.filter.return_value.all.return_value = [node]
            else:
                mock.filter.return_value.all.return_value = [item]
            return mock

        planner.session.query.side_effect = query_side_effect
        return planner

    def test_generate_plan_returns_orders_and_targets(self):
        """generate_plan returns a (list, list) tuple."""
        planner = self._setup_full_planner()

        forecasts = {
            (1, 1): DemandForecast(
                item_id=1,
                node_id=1,
                weekly_demand=np.full(10, 20.0),
                demand_std_dev=5.0,
                total_demand=200.0,
            )
        }

        orders, targets = planner.generate_plan(forecasts)

        assert isinstance(orders, list)
        assert isinstance(targets, list)
        assert len(targets) == 1

        tgt = targets[0]
        assert tgt.node_id == 1
        assert tgt.item_id == 1
        assert tgt.safety_stock >= 0
        assert tgt.reorder_point > 0

    def test_generate_plan_skips_missing_forecast_keys(self):
        """Node/item combos without a forecast entry produce no output."""
        planner = self._setup_full_planner()

        # Empty forecast dict -- no (item_id, node_id) keys match
        orders, targets = planner.generate_plan({})

        assert orders == []
        assert targets == []
