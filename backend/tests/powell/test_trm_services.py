"""
Tests for TRM Execution Services

Tests the narrow TRM services that execute within the Powell SDAM framework:
- AllocationService: Priority-based allocation management
- ATPExecutorTRM: Allocated Available-to-Promise decisions
- InventoryRebalancingTRM: Cross-location inventory rebalancing
- POCreationTRM: Purchase Order creation decisions

All tests are pure unit tests with no database dependency.
"""

import pytest
import numpy as np
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from app.services.powell.allocation_service import (
    AllocationService,
    AllocationConfig,
    AllocationCadence,
    ConsumptionResult,
    PriorityAllocation,
    UnfulfillableOrderAction,
)
from app.services.powell.atp_executor import (
    ATPExecutorTRM,
    ATPRequest,
    ATPResponse,
    ATPState,
)
from app.services.powell.inventory_rebalancing_trm import (
    InventoryRebalancingTRM,
    SiteInventoryState,
    TransferLane,
    RebalancingState,
    RebalanceRecommendation,
    RebalanceReason,
)
# POCreationTRM import removed: replaced by FreightProcurementTRM.


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def default_config():
    """Default allocation config with 5 priorities."""
    return AllocationConfig()


@pytest.fixture
def allocation_service(default_config):
    """AllocationService with default configuration."""
    return AllocationService(config=default_config)


@pytest.fixture
def sample_allocations():
    """Sample allocations for product SKU-A at location DC-01."""
    return [
        PriorityAllocation(priority=1, product_id="SKU-A", location_id="DC-01", allocated_qty=300),
        PriorityAllocation(priority=2, product_id="SKU-A", location_id="DC-01", allocated_qty=250),
        PriorityAllocation(priority=3, product_id="SKU-A", location_id="DC-01", allocated_qty=200),
        PriorityAllocation(priority=4, product_id="SKU-A", location_id="DC-01", allocated_qty=150),
        PriorityAllocation(priority=5, product_id="SKU-A", location_id="DC-01", allocated_qty=100),
    ]


@pytest.fixture
def loaded_allocation_service(allocation_service, sample_allocations):
    """AllocationService pre-loaded with sample allocations."""
    today = date.today()
    allocation_service.set_allocations(
        sample_allocations,
        period_start=today,
        period_end=today + timedelta(days=7),
    )
    return allocation_service


@pytest.fixture
def atp_executor(loaded_allocation_service):
    """ATPExecutorTRM with heuristic fallback (no TRM model)."""
    return ATPExecutorTRM(
        allocation_service=loaded_allocation_service,
        trm_model=None,
        use_heuristic_fallback=True,
    )


@pytest.fixture
def site_state_excess():
    """Site inventory state representing excess inventory."""
    return SiteInventoryState(
        site_id="DC-01",
        product_id="SKU-X",
        on_hand=1000,
        in_transit=0,
        committed=100,
        backlog=0,
        demand_forecast=300,
        demand_uncertainty=30,
        safety_stock=100,
        target_dos=15,
    )


@pytest.fixture
def site_state_deficit():
    """Site inventory state representing deficit inventory."""
    return SiteInventoryState(
        site_id="DC-02",
        product_id="SKU-X",
        on_hand=50,
        in_transit=0,
        committed=20,
        backlog=10,
        demand_forecast=300,
        demand_uncertainty=30,
        safety_stock=100,
        target_dos=15,
    )


@pytest.fixture
def transfer_lane():
    """Transfer lane from DC-01 to DC-02."""
    return TransferLane(
        from_site="DC-01",
        to_site="DC-02",
        transfer_time=2.0,
        cost_per_unit=0.5,
    )


@pytest.fixture
def supplier_info():
    """Sample supplier info."""
    return SupplierInfo(
        supplier_id="SUP-01",
        product_id="SKU-A",
        lead_time_days=7,
        lead_time_variability=1.5,
        unit_cost=10.0,
        order_cost=50.0,
        min_order_qty=10,
        max_order_qty=5000,
        order_multiple=5,
        on_time_rate=0.95,
        fill_rate=0.98,
        quality_rate=0.99,
    )


@pytest.fixture
def inventory_position_low():
    """Inventory position below reorder point."""
    return InventoryPosition(
        product_id="SKU-A",
        location_id="DC-01",
        on_hand=50,
        in_transit=10,
        on_order=0,
        committed=20,
        backlog=5,
        safety_stock=100,
        reorder_point=200,
        target_inventory=500,
        average_daily_demand=20,
        demand_variability=5,
    )


@pytest.fixture
def inventory_position_high():
    """Inventory position well above reorder point."""
    return InventoryPosition(
        product_id="SKU-A",
        location_id="DC-01",
        on_hand=800,
        in_transit=100,
        on_order=200,
        committed=50,
        backlog=0,
        safety_stock=100,
        reorder_point=200,
        target_inventory=500,
        average_daily_demand=20,
        demand_variability=5,
    )


# ===========================================================================
# 1. PriorityAllocation Tests (5 tests)
# ===========================================================================

class TestPriorityAllocation:
    """Tests for PriorityAllocation dataclass."""

    def test_available_qty_simple(self):
        """available_qty = allocated - consumed, floored at zero."""
        alloc = PriorityAllocation(
            priority=1, product_id="SKU-A", location_id="DC-01",
            allocated_qty=100, consumed_qty=30,
        )
        assert alloc.available_qty == 70.0

    def test_available_qty_floors_at_zero(self):
        """available_qty never goes negative."""
        alloc = PriorityAllocation(
            priority=1, product_id="SKU-A", location_id="DC-01",
            allocated_qty=50, consumed_qty=80,
        )
        assert alloc.available_qty == 0.0

    def test_utilization(self):
        """utilization = consumed / allocated."""
        alloc = PriorityAllocation(
            priority=2, product_id="SKU-A", location_id="DC-01",
            allocated_qty=200, consumed_qty=100,
        )
        assert alloc.utilization == pytest.approx(0.5)

    def test_utilization_zero_allocated(self):
        """utilization is 0 when allocated is zero (no division error)."""
        alloc = PriorityAllocation(
            priority=3, product_id="SKU-A", location_id="DC-01",
            allocated_qty=0, consumed_qty=0,
        )
        assert alloc.utilization == 0.0

    def test_consume_returns_actual_qty(self):
        """consume() returns actually consumed qty, capped at available."""
        alloc = PriorityAllocation(
            priority=1, product_id="SKU-A", location_id="DC-01",
            allocated_qty=100, consumed_qty=0,
        )
        # Normal consume
        actual = alloc.consume(40)
        assert actual == 40.0
        assert alloc.consumed_qty == 40.0

        # Over-consume: request 80 but only 60 available
        actual = alloc.consume(80)
        assert actual == 60.0
        assert alloc.consumed_qty == 100.0

    def test_to_dict_structure(self):
        """to_dict() returns all expected keys."""
        alloc = PriorityAllocation(
            priority=1, product_id="SKU-A", location_id="DC-01",
            allocated_qty=100, consumed_qty=25,
            demand_source="key_account", generated_by="tgnn",
        )
        d = alloc.to_dict()
        assert d["priority"] == 1
        assert d["product_id"] == "SKU-A"
        assert d["location_id"] == "DC-01"
        assert d["allocated_qty"] == 100
        assert d["consumed_qty"] == 25
        assert d["available_qty"] == 75
        assert d["utilization"] == pytest.approx(0.25)
        assert d["demand_source"] == "key_account"
        assert d["generated_by"] == "tgnn"
        assert "valid_from" in d
        assert "valid_to" in d


# ===========================================================================
# 2. AllocationConfig Tests (3 tests)
# ===========================================================================

class TestAllocationConfig:
    """Tests for AllocationConfig defaults and customization."""

    def test_defaults(self):
        """Default config has expected priority sources and allocation pcts."""
        cfg = AllocationConfig()
        assert cfg.num_priorities == 5
        assert cfg.cadence == AllocationCadence.WEEKLY
        assert cfg.unfulfillable_action == UnfulfillableOrderAction.PARTIAL_FILL
        assert cfg.measure_otif is True
        assert cfg.default_priority_by_source["key_account"] == 1
        assert cfg.default_priority_by_source["spot_market"] == 5

    def test_custom_source_priorities(self):
        """Custom source-to-priority mapping overrides defaults."""
        cfg = AllocationConfig(
            default_priority_by_source={"vip": 1, "standard": 3, "economy": 5}
        )
        assert cfg.default_priority_by_source == {"vip": 1, "standard": 3, "economy": 5}
        # default_allocation_pct should still be populated
        assert len(cfg.default_allocation_pct) == 5

    def test_custom_allocation_pcts(self):
        """Custom allocation percentages override defaults."""
        custom_pct = {1: 0.50, 2: 0.30, 3: 0.20}
        cfg = AllocationConfig(default_allocation_pct=custom_pct)
        assert cfg.default_allocation_pct == custom_pct
        # default_priority_by_source should still be populated
        assert "key_account" in cfg.default_priority_by_source


# ===========================================================================
# 3. AllocationService Tests (12 tests)
# ===========================================================================

class TestAllocationService:
    """Tests for AllocationService."""

    def test_set_allocations_stores_by_product_location(self, allocation_service, sample_allocations):
        """set_allocations indexes allocations by (product_id, location_id)."""
        allocation_service.set_allocations(sample_allocations)
        status = allocation_service.get_allocation_status("SKU-A", "DC-01")
        assert len(status) == 5
        assert status[1]["allocated"] == 300

    def test_set_allocations_clears_previous(self, allocation_service, sample_allocations):
        """set_allocations clears previous allocations before storing new ones."""
        allocation_service.set_allocations(sample_allocations)
        # Set new with only 2 priorities
        new_allocs = [
            PriorityAllocation(priority=1, product_id="SKU-A", location_id="DC-01", allocated_qty=500),
            PriorityAllocation(priority=2, product_id="SKU-A", location_id="DC-01", allocated_qty=500),
        ]
        allocation_service.set_allocations(new_allocs)
        status = allocation_service.get_allocation_status("SKU-A", "DC-01")
        assert len(status) == 2

    def test_generate_default_allocations(self, allocation_service):
        """generate_default_allocations splits total by percentage."""
        allocs = allocation_service.generate_default_allocations(
            product_id="SKU-B", location_id="DC-02", total_available=1000,
        )
        assert len(allocs) == 5
        # Default: 30% + 25% + 20% + 15% + 10% = 100%
        total = sum(a.allocated_qty for a in allocs)
        assert total == pytest.approx(1000.0)
        assert allocs[0].allocated_qty == pytest.approx(300.0)  # P1 = 30%
        assert allocs[4].allocated_qty == pytest.approx(100.0)  # P5 = 10%
        for a in allocs:
            assert a.generated_by == "default"

    def test_consume_full_fulfillment(self, loaded_allocation_service):
        """Full fulfillment from own tier."""
        result = loaded_allocation_service.consume_for_order(
            order_id="ORD-001",
            product_id="SKU-A",
            location_id="DC-01",
            requested_qty=100,
            order_priority=1,
        )
        assert result.fully_fulfilled is True
        assert result.fulfilled_qty == 100
        assert result.fill_rate == pytest.approx(1.0)
        assert 1 in result.consumption_by_priority

    def test_consume_partial_fulfillment(self, loaded_allocation_service):
        """Partial fulfillment when own tier insufficient, borrows from lower tiers."""
        # P3 order requesting 500 units
        # P3 has 200, P5 has 100, P4 has 150 => total reachable = 200+100+150 = 450
        result = loaded_allocation_service.consume_for_order(
            order_id="ORD-002",
            product_id="SKU-A",
            location_id="DC-01",
            requested_qty=500,
            order_priority=3,
        )
        assert result.fully_fulfilled is False
        assert result.fulfilled_qty == 450
        assert result.fill_rate == pytest.approx(0.9)
        # Consumed from P3, P5, P4
        assert 3 in result.consumption_by_priority
        assert 5 in result.consumption_by_priority
        assert 4 in result.consumption_by_priority
        # Should NOT have consumed from P1 or P2
        assert 1 not in result.consumption_by_priority
        assert 2 not in result.consumption_by_priority

    def test_consume_no_allocations(self, allocation_service):
        """No allocations for product/location returns zero fulfillment."""
        result = allocation_service.consume_for_order(
            order_id="ORD-003",
            product_id="SKU-MISSING",
            location_id="DC-99",
            requested_qty=50,
            order_priority=1,
        )
        assert result.fulfilled_qty == 0
        assert result.fully_fulfilled is False

    def test_consume_reject_rollback(self):
        """REJECT action rolls back all consumption on partial fill."""
        reject_config = AllocationConfig(
            unfulfillable_action=UnfulfillableOrderAction.REJECT,
        )
        svc = AllocationService(config=reject_config)
        allocs = [
            PriorityAllocation(priority=1, product_id="SKU-A", location_id="DC-01", allocated_qty=50),
            PriorityAllocation(priority=2, product_id="SKU-A", location_id="DC-01", allocated_qty=30),
        ]
        svc.set_allocations(allocs)

        # Request more than total available (80), so partial fill triggers REJECT
        result = svc.consume_for_order(
            order_id="ORD-004",
            product_id="SKU-A",
            location_id="DC-01",
            requested_qty=100,
            order_priority=1,
        )
        # After rollback
        assert result.fulfilled_qty == 0
        assert result.consumption_by_priority == {}
        assert result.action_taken == UnfulfillableOrderAction.REJECT

        # Verify allocations were restored
        status = svc.get_allocation_status("SKU-A", "DC-01")
        assert status[1]["consumed"] == 0
        assert status[2]["consumed"] == 0

    def test_build_consumption_sequence_p1(self, allocation_service):
        """P1 order with 5 priorities: [1, 5, 4, 3, 2]."""
        seq = allocation_service._build_consumption_sequence(1, 5)
        assert seq == [1, 5, 4, 3, 2]

    def test_build_consumption_sequence_p2(self, allocation_service):
        """P2 order with 5 priorities: [2, 5, 4, 3]."""
        seq = allocation_service._build_consumption_sequence(2, 5)
        assert seq == [2, 5, 4, 3]

    def test_build_consumption_sequence_p3(self, allocation_service):
        """P3 order with 5 priorities: [3, 5, 4]."""
        seq = allocation_service._build_consumption_sequence(3, 5)
        assert seq == [3, 5, 4]

    def test_build_consumption_sequence_p4(self, allocation_service):
        """P4 order with 5 priorities: [4, 5]."""
        seq = allocation_service._build_consumption_sequence(4, 5)
        assert seq == [4, 5]

    def test_build_consumption_sequence_p5(self, allocation_service):
        """P5 order with 5 priorities: [5] (only own tier)."""
        seq = allocation_service._build_consumption_sequence(5, 5)
        assert seq == [5]

    def test_consumption_history_tracking(self, loaded_allocation_service):
        """Consumption history is accumulated for feedback."""
        loaded_allocation_service.consume_for_order(
            "ORD-A", "SKU-A", "DC-01", 50, 1,
        )
        loaded_allocation_service.consume_for_order(
            "ORD-B", "SKU-A", "DC-01", 30, 2,
        )
        feedback = loaded_allocation_service.get_consumption_feedback()
        assert feedback["total_orders"] == 2
        assert feedback["fully_fulfilled"] == 2


# ===========================================================================
# 4. ATPExecutorTRM Tests (8 tests)
# ===========================================================================

class TestATPExecutorTRM:
    """Tests for ATPExecutorTRM."""

    def test_check_atp_heuristic_full_fulfillment(self, atp_executor):
        """Heuristic check: full fulfillment when allocation has enough."""
        request = ATPRequest(
            order_id="ORD-100",
            product_id="SKU-A",
            location_id="DC-01",
            requested_qty=50,
            priority=1,
        )
        response = atp_executor.check_atp(request)
        assert response.can_fulfill is True
        assert response.promised_qty == 50
        assert "Full fulfillment" in response.reasoning

    def test_check_atp_heuristic_partial_fulfillment(self, atp_executor):
        """Heuristic check: partial fulfillment from multiple tiers."""
        # P3 allocation has 200. Request 600. P3=200, P5=100, P4=150 = 450 < 600
        request = ATPRequest(
            order_id="ORD-101",
            product_id="SKU-A",
            location_id="DC-01",
            requested_qty=600,
            priority=3,
        )
        response = atp_executor.check_atp(request)
        assert response.can_fulfill is True
        assert response.promised_qty == 450
        assert "Partial fulfillment" in response.reasoning

    def test_check_atp_no_allocation(self):
        """No allocation for the product/location returns cannot fulfill."""
        svc = AllocationService()
        executor = ATPExecutorTRM(allocation_service=svc, use_heuristic_fallback=True)
        request = ATPRequest(
            order_id="ORD-102",
            product_id="SKU-NONE",
            location_id="DC-99",
            requested_qty=10,
            priority=1,
        )
        response = executor.check_atp(request)
        assert response.can_fulfill is False
        assert response.promised_qty == 0

    def test_check_atp_no_model_and_heuristic_disabled(self):
        """No TRM model + heuristic disabled returns unfulfillable response."""
        svc = AllocationService()
        executor = ATPExecutorTRM(
            allocation_service=svc,
            trm_model=None,
            use_heuristic_fallback=False,
        )
        request = ATPRequest(
            order_id="ORD-103",
            product_id="SKU-A",
            location_id="DC-01",
            requested_qty=10,
            priority=1,
        )
        response = executor.check_atp(request)
        assert response.can_fulfill is False
        assert response.promised_qty == 0
        assert "heuristic disabled" in response.reasoning

    def test_commit_atp_successful(self, atp_executor):
        """commit_atp consumes from allocation service."""
        request = ATPRequest(
            order_id="ORD-200",
            product_id="SKU-A",
            location_id="DC-01",
            requested_qty=100,
            priority=2,
        )
        response = ATPResponse(
            order_id="ORD-200",
            line_id=None,
            can_fulfill=True,
            available_qty=250,
            promised_qty=100,
        )
        result = atp_executor.commit_atp(request, response)
        assert result.fulfilled_qty == 100
        assert result.fully_fulfilled is True

    def test_commit_atp_zero_promised(self, atp_executor):
        """commit_atp with zero promised_qty returns zero fulfillment."""
        request = ATPRequest(
            order_id="ORD-201",
            product_id="SKU-A",
            location_id="DC-01",
            requested_qty=10,
            priority=1,
        )
        response = ATPResponse(
            order_id="ORD-201",
            line_id=None,
            can_fulfill=False,
            available_qty=0,
            promised_qty=0,
        )
        result = atp_executor.commit_atp(request, response)
        assert result.fulfilled_qty == 0

    def test_build_consumption_sequence_p2(self, atp_executor):
        """P2 order with 5 priorities: [2, 5, 4, 3]."""
        seq = atp_executor._build_consumption_sequence(2, 5)
        assert seq == [2, 5, 4, 3]

    def test_build_consumption_sequence_p4(self, atp_executor):
        """P4 order with 5 priorities: [4, 5]."""
        seq = atp_executor._build_consumption_sequence(4, 5)
        assert seq == [4, 5]

    def test_metrics_tracking(self, atp_executor):
        """Metrics are updated after each check_atp call."""
        request = ATPRequest(
            order_id="ORD-300",
            product_id="SKU-A",
            location_id="DC-01",
            requested_qty=50,
            priority=1,
        )
        atp_executor.check_atp(request)
        metrics = atp_executor.get_metrics()
        assert metrics["total_requests"] == 1
        assert metrics["heuristic_decisions"] == 1
        assert metrics["trm_decisions"] == 0


# ===========================================================================
# 5. SiteInventoryState Tests (5 tests)
# ===========================================================================

class TestSiteInventoryState:
    """Tests for SiteInventoryState properties."""

    def test_available(self, site_state_excess):
        """available = max(0, on_hand + in_transit - committed - backlog)."""
        # 1000 + 0 - 100 - 0 = 900
        assert site_state_excess.available == 900.0

    def test_available_floors_at_zero(self):
        """available never goes negative."""
        state = SiteInventoryState(
            site_id="DC-01", product_id="SKU-X",
            on_hand=10, in_transit=0, committed=50, backlog=20,
            demand_forecast=300, demand_uncertainty=30,
            safety_stock=100, target_dos=15,
        )
        assert state.available == 0.0

    def test_days_of_supply(self, site_state_excess):
        """days_of_supply = available / (demand_forecast / 30)."""
        # available = 900, daily demand = 300/30 = 10
        # DOS = 900 / 10 = 90
        assert site_state_excess.days_of_supply == pytest.approx(90.0)

    def test_days_of_supply_zero_forecast(self):
        """days_of_supply returns inf when forecast is zero."""
        state = SiteInventoryState(
            site_id="DC-01", product_id="SKU-X",
            on_hand=100, in_transit=0, committed=0, backlog=0,
            demand_forecast=0, demand_uncertainty=0,
            safety_stock=50, target_dos=15,
        )
        assert state.days_of_supply == float('inf')

    def test_stockout_risk(self, site_state_deficit):
        """stockout_risk is between 0 and 1, higher when available is low."""
        # available = max(0, 50 + 0 - 20 - 10) = 20
        # z = (20 - 300) / max(1, 30) = -280/30 = -9.33
        # risk = max(0, min(1, 0.5 - (-9.33)*0.2)) = max(0, min(1, 0.5 + 1.867)) = 1.0
        assert site_state_deficit.stockout_risk == 1.0

    def test_to_features_shape(self, site_state_excess):
        """to_features returns a float32 array with 12 elements."""
        features = site_state_excess.to_features()
        assert isinstance(features, np.ndarray)
        assert features.dtype == np.float32
        assert features.shape == (12,)


# ===========================================================================
# 6. InventoryRebalancingTRM Tests (4 tests)
# ===========================================================================

class TestInventoryRebalancingTRM:
    """Tests for InventoryRebalancingTRM."""

    def test_evaluate_with_heuristic_finds_transfer(
        self, site_state_excess, site_state_deficit, transfer_lane
    ):
        """Heuristic evaluation identifies transfer from excess to deficit site."""
        trm = InventoryRebalancingTRM(use_heuristic_fallback=True)
        state = RebalancingState(
            product_id="SKU-X",
            site_states={
                "DC-01": site_state_excess,
                "DC-02": site_state_deficit,
            },
            transfer_lanes=[transfer_lane],
        )
        recs = trm.evaluate_rebalancing(state)
        assert len(recs) >= 1
        rec = recs[0]
        assert rec.from_site == "DC-01"
        assert rec.to_site == "DC-02"
        assert rec.quantity > 0
        assert rec.product_id == "SKU-X"

    def test_evaluate_no_imbalance_returns_empty(self):
        """When both sites are balanced, no rebalancing recommended."""
        trm = InventoryRebalancingTRM(use_heuristic_fallback=True)
        balanced = SiteInventoryState(
            site_id="DC-01", product_id="SKU-X",
            on_hand=150, in_transit=0, committed=0, backlog=0,
            demand_forecast=300, demand_uncertainty=30,
            safety_stock=50, target_dos=15,
        )
        balanced2 = SiteInventoryState(
            site_id="DC-02", product_id="SKU-X",
            on_hand=150, in_transit=0, committed=0, backlog=0,
            demand_forecast=300, demand_uncertainty=30,
            safety_stock=50, target_dos=15,
        )
        lane = TransferLane(
            from_site="DC-01", to_site="DC-02",
            transfer_time=2.0, cost_per_unit=0.5,
        )
        state = RebalancingState(
            product_id="SKU-X",
            site_states={"DC-01": balanced, "DC-02": balanced2},
            transfer_lanes=[lane],
        )
        recs = trm.evaluate_rebalancing(state)
        assert len(recs) == 0

    def test_evaluate_multi_lane(self):
        """Multiple lanes with deficit sites each get recommendations."""
        trm = InventoryRebalancingTRM(use_heuristic_fallback=True)
        # Excess site
        excess = SiteInventoryState(
            site_id="DC-01", product_id="SKU-X",
            on_hand=2000, in_transit=0, committed=0, backlog=0,
            demand_forecast=300, demand_uncertainty=30,
            safety_stock=50, target_dos=15,
        )
        # Two deficit sites
        deficit_a = SiteInventoryState(
            site_id="DC-02", product_id="SKU-X",
            on_hand=20, in_transit=0, committed=10, backlog=5,
            demand_forecast=300, demand_uncertainty=30,
            safety_stock=100, target_dos=15,
        )
        deficit_b = SiteInventoryState(
            site_id="DC-03", product_id="SKU-X",
            on_hand=15, in_transit=0, committed=5, backlog=10,
            demand_forecast=300, demand_uncertainty=30,
            safety_stock=100, target_dos=15,
        )
        lanes = [
            TransferLane(from_site="DC-01", to_site="DC-02", transfer_time=2, cost_per_unit=0.5),
            TransferLane(from_site="DC-01", to_site="DC-03", transfer_time=3, cost_per_unit=0.7),
        ]
        state = RebalancingState(
            product_id="SKU-X",
            site_states={"DC-01": excess, "DC-02": deficit_a, "DC-03": deficit_b},
            transfer_lanes=lanes,
        )
        recs = trm.evaluate_rebalancing(state)
        assert len(recs) == 2
        dest_sites = {r.to_site for r in recs}
        assert "DC-02" in dest_sites
        assert "DC-03" in dest_sites

    def test_evaluate_sorted_by_urgency(
        self, site_state_excess, site_state_deficit, transfer_lane
    ):
        """Recommendations are sorted by descending urgency."""
        trm = InventoryRebalancingTRM(use_heuristic_fallback=True)
        state = RebalancingState(
            product_id="SKU-X",
            site_states={
                "DC-01": site_state_excess,
                "DC-02": site_state_deficit,
            },
            transfer_lanes=[transfer_lane],
        )
        recs = trm.evaluate_rebalancing(state)
        for i in range(len(recs) - 1):
            assert recs[i].urgency >= recs[i + 1].urgency


# ===========================================================================
# 8. ATPState.to_features Test (1 test)
# ===========================================================================

class TestATPState:
    """Tests for ATPState feature conversion."""

    def test_to_features_shape_and_values(self):
        """to_features returns float32 ndarray of length 12 (7 base + 5 priority slots)."""
        state = ATPState(
            order_priority=2,
            requested_qty=100.0,
            allocation_available={1: 50.0, 2: 40.0, 3: 30.0},
            current_inventory=500,
            pipeline_inventory=100,
            safety_stock_level=50,
            demand_forecast=200,
            demand_uncertainty=25,
        )
        features = state.to_features()
        assert isinstance(features, np.ndarray)
        assert features.dtype == np.float32
        assert features.shape == (12,)

        # Verify specific positions
        assert features[0] == 2.0   # order_priority
        assert features[1] == 100.0  # requested_qty
        assert features[2] == 500.0  # current_inventory
        assert features[3] == 100.0  # pipeline_inventory
        assert features[4] == 50.0   # safety_stock_level
        assert features[5] == 200.0  # demand_forecast
        assert features[6] == 25.0   # demand_uncertainty
        # Allocation priorities 1-5
        assert features[7] == 50.0   # P1 available
        assert features[8] == 40.0   # P2 available
        assert features[9] == 30.0   # P3 available
        assert features[10] == 0.0   # P4 not present => 0
        assert features[11] == 0.0   # P5 not present => 0


# ===========================================================================
# 9. Additional Edge-Case and Integration Tests
# ===========================================================================

class TestConsumptionResult:
    """Tests for ConsumptionResult properties."""

    def test_fill_rate_full(self):
        """fill_rate = 1.0 when fully fulfilled."""
        result = ConsumptionResult(
            order_id="ORD-X", order_priority=1,
            requested_qty=100, fulfilled_qty=100,
            fully_fulfilled=True,
        )
        assert result.fill_rate == pytest.approx(1.0)
        assert result.shortfall == 0.0

    def test_fill_rate_partial(self):
        """fill_rate reflects partial fulfillment."""
        result = ConsumptionResult(
            order_id="ORD-Y", order_priority=2,
            requested_qty=200, fulfilled_qty=80,
        )
        assert result.fill_rate == pytest.approx(0.4)
        assert result.shortfall == 120.0

    def test_fill_rate_zero_requested(self):
        """fill_rate = 1.0 when requested is zero (no demand)."""
        result = ConsumptionResult(
            order_id="ORD-Z", order_priority=1,
            requested_qty=0, fulfilled_qty=0,
        )
        assert result.fill_rate == 1.0


class TestAllocationServicePeriodManagement:
    """Tests for AllocationService period management."""

    def test_set_allocations_calculates_period_end_weekly(self):
        """When no end date specified, weekly cadence adds 7 days."""
        config = AllocationConfig(cadence=AllocationCadence.WEEKLY)
        svc = AllocationService(config=config)
        today = date.today()
        allocs = [
            PriorityAllocation(priority=1, product_id="P", location_id="L", allocated_qty=100),
        ]
        svc.set_allocations(allocs, period_start=today)
        assert svc._period_end == today + timedelta(weeks=1)

    def test_set_allocations_calculates_period_end_daily(self):
        """When no end date specified, daily cadence adds 1 day."""
        config = AllocationConfig(cadence=AllocationCadence.DAILY)
        svc = AllocationService(config=config)
        today = date.today()
        allocs = [
            PriorityAllocation(priority=1, product_id="P", location_id="L", allocated_qty=100),
        ]
        svc.set_allocations(allocs, period_start=today)
        assert svc._period_end == today + timedelta(days=1)

    def test_reset_for_new_period(self, loaded_allocation_service):
        """reset_for_new_period clears everything."""
        loaded_allocation_service.consume_for_order("O1", "SKU-A", "DC-01", 10, 1)
        loaded_allocation_service.reset_for_new_period()
        assert loaded_allocation_service._allocations == {}
        assert loaded_allocation_service._consumption_history == []
        assert loaded_allocation_service._period_start is None


class TestInventoryPositionProperties:
    """Tests for InventoryPosition dataclass."""

    def test_available(self, inventory_position_low):
        """available = max(0, on_hand - committed - backlog)."""
        # 50 - 20 - 5 = 25
        assert inventory_position_low.available == 25.0

    def test_inventory_position_property(self, inventory_position_low):
        """inventory_position = on_hand + in_transit + on_order - committed - backlog."""
        # 50 + 10 + 0 - 20 - 5 = 35
        assert inventory_position_low.inventory_position == 35.0

    def test_days_of_supply(self, inventory_position_low):
        """days_of_supply = available / average_daily_demand."""
        # 25 / 20 = 1.25
        assert inventory_position_low.days_of_supply == pytest.approx(1.25)

    def test_days_of_supply_zero_demand(self):
        """days_of_supply returns inf when demand is zero."""
        inv = InventoryPosition(
            product_id="P", location_id="L",
            on_hand=100, in_transit=0, on_order=0,
            committed=0, backlog=0,
            safety_stock=50, reorder_point=100,
            target_inventory=200,
            average_daily_demand=0, demand_variability=0,
        )
        assert inv.days_of_supply == float('inf')

    def test_coverage_ratio(self, inventory_position_low):
        """coverage_ratio = inventory_position / target_inventory."""
        # 35 / 500 = 0.07
        assert inventory_position_low.coverage_ratio == pytest.approx(0.07)


class TestATPResponseSerialization:
    """Tests for ATPResponse serialization."""

    def test_to_dict(self):
        """ATPResponse.to_dict() includes all expected fields."""
        resp = ATPResponse(
            order_id="ORD-1",
            line_id="LINE-1",
            can_fulfill=True,
            available_qty=200,
            promised_qty=150,
            consumption_breakdown={1: 100, 2: 50},
            confidence=0.92,
            reasoning="Test reasoning",
        )
        d = resp.to_dict()
        assert d["order_id"] == "ORD-1"
        assert d["line_id"] == "LINE-1"
        assert d["can_fulfill"] is True
        assert d["available_qty"] == 200
        assert d["promised_qty"] == 150
        assert d["consumption_breakdown"] == {1: 100, 2: 50}
        assert d["confidence"] == 0.92
        assert d["reasoning"] == "Test reasoning"


class TestRebalanceRecommendationSerialization:
    """Tests for RebalanceRecommendation serialization."""

    def test_to_dict(self):
        """RebalanceRecommendation.to_dict() includes all expected fields."""
        rec = RebalanceRecommendation(
            from_site="DC-01", to_site="DC-02",
            product_id="SKU-X", quantity=200,
            reason=RebalanceReason.STOCKOUT_RISK,
            urgency=0.8, confidence=0.9,
            expected_service_improvement=0.15,
            expected_cost=100.0, expected_arrival=2.0,
            source_dos_before=45, source_dos_after=35,
            dest_dos_before=3, dest_dos_after=23,
        )
        d = rec.to_dict()
        assert d["from_site"] == "DC-01"
        assert d["to_site"] == "DC-02"
        assert d["reason"] == "stockout_risk"
        assert d["source_dos"]["before"] == 45
        assert d["dest_dos"]["after"] == 23

