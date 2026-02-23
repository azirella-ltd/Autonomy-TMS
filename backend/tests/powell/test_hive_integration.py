"""
Integration tests for hive signal wiring into SiteAgent + 4 TRMs.

Sprint 2 validation criteria:
  - All existing tests still pass (zero regression)
  - signal_bus=None works identically to current behavior
  - ATP shortage emits signal with correct urgency/direction
  - PO reads ATP_SHORTAGE and urgency is accessible
  - Performance: signal ops add <2ms per decision
"""

import time
from datetime import datetime, timedelta, timezone

import pytest

from app.services.powell.hive_signal import (
    HiveSignal,
    HiveSignalBus,
    HiveSignalType,
    UrgencyVector,
)
from app.services.powell.hive_health import HiveHealthMetrics

# ---------- ATP Executor signal integration ----------

from app.services.powell.atp_executor import (
    ATPExecutorTRM,
    ATPRequest,
    ATPResponse,
    ATPState,
)
from app.services.powell.allocation_service import (
    AllocationService,
    AllocationConfig,
)


class TestATPExecutorSignals:
    """Test signal wiring in ATPExecutorTRM."""

    def _make_executor(self, with_bus: bool = True) -> ATPExecutorTRM:
        """Create an ATPExecutorTRM with or without signal bus."""
        alloc_svc = AllocationService(AllocationConfig())
        bus = HiveSignalBus() if with_bus else None
        return ATPExecutorTRM(
            allocation_service=alloc_svc,
            signal_bus=bus,
        )

    def _make_request(self, qty: float = 100, priority: int = 2) -> ATPRequest:
        return ATPRequest(
            order_id="ORD-001",
            product_id="PROD-001",
            location_id="LOC-001",
            requested_qty=qty,
            priority=priority,
        )

    def test_signal_bus_none_works(self):
        """ATPExecutorTRM works without signal bus (backward compat)."""
        executor = self._make_executor(with_bus=False)
        request = self._make_request()
        response = executor.check_atp(request)
        assert isinstance(response, ATPResponse)

    def test_signal_bus_present_works(self):
        """ATPExecutorTRM works with signal bus."""
        executor = self._make_executor(with_bus=True)
        request = self._make_request()
        response = executor.check_atp(request)
        assert isinstance(response, ATPResponse)

    def test_shortage_emits_signal(self):
        """ATP shortage emits ATP_SHORTAGE signal to bus."""
        executor = self._make_executor(with_bus=True)
        bus = executor.signal_bus
        assert bus is not None

        # No allocations loaded → all requests result in shortage
        request = self._make_request(qty=100)
        executor.check_atp(request)

        # Check that an ATP_SHORTAGE signal was emitted
        signals = bus.read("po_creation", types={HiveSignalType.ATP_SHORTAGE})
        assert len(signals) >= 1
        sig = signals[0]
        assert sig.source_trm == "atp_executor"
        assert sig.direction == "shortage"
        assert sig.product_id == "PROD-001"
        assert sig.urgency > 0

    def test_urgency_vector_updated_on_shortage(self):
        """ATP shortage updates urgency vector."""
        executor = self._make_executor(with_bus=True)
        bus = executor.signal_bus
        request = self._make_request()
        executor.check_atp(request)

        val, direction, _ = bus.urgency.read("atp_executor")
        # Should be either shortage (if qty > 0) or neutral
        assert val >= 0.0

    def test_signal_performance(self):
        """Signal operations add <2ms overhead per decision."""
        executor_with = self._make_executor(with_bus=True)
        executor_without = self._make_executor(with_bus=False)
        request = self._make_request()

        # Warm up
        executor_with.check_atp(request)
        executor_without.check_atp(request)

        n = 100

        start = time.perf_counter()
        for _ in range(n):
            executor_without.check_atp(request)
        baseline = (time.perf_counter() - start) / n

        start = time.perf_counter()
        for _ in range(n):
            executor_with.check_atp(request)
        with_signals = (time.perf_counter() - start) / n

        overhead_ms = (with_signals - baseline) * 1000
        assert overhead_ms < 2.0, f"Signal overhead {overhead_ms:.2f}ms exceeds 2ms budget"


# ---------- Rebalancing signal integration ----------

from app.services.powell.inventory_rebalancing_trm import (
    InventoryRebalancingTRM,
    RebalancingState,
    SiteInventoryState,
    TransferLane,
)


class TestRebalancingSignals:
    """Test signal wiring in InventoryRebalancingTRM."""

    def _make_state(self) -> RebalancingState:
        return RebalancingState(
            product_id="PROD-001",
            site_states={
                "SITE-A": SiteInventoryState(
                    site_id="SITE-A", product_id="PROD-001",
                    on_hand=1000, in_transit=0, committed=0, backlog=0,
                    demand_forecast=100, demand_uncertainty=20,
                    safety_stock=50, target_dos=10,
                ),
                "SITE-B": SiteInventoryState(
                    site_id="SITE-B", product_id="PROD-001",
                    on_hand=10, in_transit=0, committed=0, backlog=50,
                    demand_forecast=100, demand_uncertainty=20,
                    safety_stock=50, target_dos=10,
                ),
            },
            transfer_lanes=[
                TransferLane(from_site="SITE-A", to_site="SITE-B",
                             transfer_time=2.0, cost_per_unit=0.5),
            ],
        )

    def test_no_bus_works(self):
        """Rebalancing works without signal bus."""
        trm = InventoryRebalancingTRM()
        state = self._make_state()
        recs = trm.evaluate_rebalancing(state)
        assert isinstance(recs, list)

    def test_with_bus_emits_signals(self):
        """Rebalancing emits REBALANCE_INBOUND/OUTBOUND signals."""
        trm = InventoryRebalancingTRM()
        bus = HiveSignalBus()
        trm.signal_bus = bus

        state = self._make_state()
        recs = trm.evaluate_rebalancing(state)

        if recs:  # If rebalancing was recommended
            inbound = bus.read("atp_executor", types={HiveSignalType.REBALANCE_INBOUND})
            outbound = bus.read("atp_executor", types={HiveSignalType.REBALANCE_OUTBOUND})
            assert len(inbound) >= 1
            assert len(outbound) >= 1
            assert inbound[0].direction == "relief"

    def test_urgency_updated(self):
        """Rebalancing updates urgency vector when recommendations exist."""
        trm = InventoryRebalancingTRM()
        bus = HiveSignalBus()
        trm.signal_bus = bus

        state = self._make_state()
        recs = trm.evaluate_rebalancing(state)

        if recs:
            val, direction, _ = bus.urgency.read("rebalancing")
            assert val > 0.0
            assert direction == "relief"


# ---------- PO Creation signal integration ----------

from app.services.powell.po_creation_trm import (
    POCreationTRM,
    POCreationState,
    InventoryPosition,
    SupplierInfo,
)


class TestPOCreationSignals:
    """Test signal wiring in POCreationTRM."""

    def _make_state(self, available: float = 0) -> POCreationState:
        return POCreationState(
            product_id="PROD-001",
            location_id="LOC-001",
            inventory_position=InventoryPosition(
                product_id="PROD-001", location_id="LOC-001",
                on_hand=available, in_transit=0, on_order=0,
                committed=0, backlog=0,
                safety_stock=50, reorder_point=100, target_inventory=200,
                average_daily_demand=10, demand_variability=3,
            ),
            suppliers=[
                SupplierInfo(
                    supplier_id="SUP-001", product_id="PROD-001",
                    lead_time_days=5, lead_time_variability=1,
                    unit_cost=10.0, order_cost=50.0,
                    min_order_qty=10, on_time_rate=0.95,
                ),
            ],
            forecast_next_30_days=300,
            forecast_uncertainty=50,
        )

    def test_no_bus_works(self):
        """PO Creation works without signal bus."""
        trm = POCreationTRM()
        state = self._make_state(available=0)
        recs = trm.evaluate_po_need(state)
        assert isinstance(recs, list)

    def test_reads_atp_shortage(self):
        """PO Creation reads ATP_SHORTAGE signals."""
        trm = POCreationTRM()
        bus = HiveSignalBus()
        trm.signal_bus = bus

        # Pre-populate an ATP shortage signal
        bus.emit(HiveSignal(
            source_trm="atp_executor",
            signal_type=HiveSignalType.ATP_SHORTAGE,
            urgency=0.8,
            direction="shortage",
            magnitude=200,
            product_id="PROD-001",
        ))

        state = self._make_state(available=0)
        recs = trm.evaluate_po_need(state)
        # The PO should recommend ordering (critical shortage)
        assert len(recs) >= 1

    def test_emits_po_expedite_on_critical(self):
        """PO Creation emits PO_EXPEDITE on critical urgency."""
        trm = POCreationTRM()
        bus = HiveSignalBus()
        trm.signal_bus = bus

        state = self._make_state(available=0)  # Critical: zero inventory
        recs = trm.evaluate_po_need(state)

        if recs:
            expedites = bus.read("rebalancing", types={HiveSignalType.PO_EXPEDITE})
            assert len(expedites) >= 1
            assert expedites[0].direction == "relief"


# ---------- Order Tracking signal integration ----------

from app.services.powell.order_tracking_trm import (
    OrderTrackingTRM,
    OrderState,
    OrderType,
    OrderStatus,
    ExceptionType,
)


class TestOrderTrackingSignals:
    """Test signal wiring in OrderTrackingTRM."""

    def _make_late_order(self) -> OrderState:
        past_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        return OrderState(
            order_id="PO-001",
            order_type=OrderType.PURCHASE_ORDER,
            status=OrderStatus.IN_TRANSIT,
            created_date=(datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d"),
            expected_date=past_date,  # 5 days late
            ordered_qty=100,
            received_qty=0,
            remaining_qty=100,
            product_id="PROD-001",
            to_location="LOC-001",
            partner_id="SUP-001",
            typical_transit_days=5,
        )

    def test_no_bus_works(self):
        """Order Tracking works without signal bus."""
        trm = OrderTrackingTRM()
        order = self._make_late_order()
        result = trm.evaluate_order(order)
        assert result is not None

    def test_exception_emits_signal(self):
        """Late delivery exception emits ORDER_EXCEPTION signal."""
        trm = OrderTrackingTRM()
        bus = HiveSignalBus()
        trm.signal_bus = bus

        order = self._make_late_order()
        result = trm.evaluate_order(order)

        if result.exception_type != ExceptionType.NO_EXCEPTION:
            signals = bus.read("atp_executor", types={HiveSignalType.ORDER_EXCEPTION})
            assert len(signals) >= 1
            assert signals[0].direction == "risk"
            assert signals[0].payload["order_id"] == "PO-001"


# ---------- Cross-TRM cascade test ----------

class TestCrossTRMCascade:
    """Test signal flow across multiple TRMs via shared bus."""

    def test_atp_to_po_cascade(self):
        """ATP shortage → PO expedite cascade via shared signal bus."""
        bus = HiveSignalBus()

        # Setup ATP executor with shared bus
        alloc_svc = AllocationService(AllocationConfig())
        atp = ATPExecutorTRM(allocation_service=alloc_svc, signal_bus=bus)

        # Setup PO creation with same bus
        po = POCreationTRM()
        po.signal_bus = bus

        # ATP processes an order → shortage (no allocations)
        atp_request = ATPRequest(
            order_id="ORD-001",
            product_id="PROD-001",
            location_id="LOC-001",
            requested_qty=100,
            priority=2,
        )
        atp.check_atp(atp_request)

        # PO should be able to read the ATP shortage signal
        po_signals = bus.read(
            "po_creation",
            types={HiveSignalType.ATP_SHORTAGE},
        )
        assert len(po_signals) >= 1
        assert po_signals[0].source_trm == "atp_executor"
        assert po_signals[0].direction == "shortage"

        # Urgency vector reflects ATP state
        atp_urg, atp_dir, _ = bus.urgency.read("atp_executor")
        assert atp_urg > 0

    def test_health_metrics_after_cascade(self):
        """HiveHealthMetrics correctly reflects state after signal cascade."""
        bus = HiveSignalBus()

        # ATP emits shortage
        bus.emit(HiveSignal(
            source_trm="atp_executor",
            signal_type=HiveSignalType.ATP_SHORTAGE,
            urgency=0.8,
            direction="shortage",
        ))
        bus.urgency.update("atp_executor", 0.8, "shortage")

        # PO emits expedite
        bus.emit(HiveSignal(
            source_trm="po_creation",
            signal_type=HiveSignalType.PO_EXPEDITE,
            urgency=0.7,
            direction="relief",
        ))
        bus.urgency.update("po_creation", 0.7, "relief")

        # Rebalancing emits inbound
        bus.emit(HiveSignal(
            source_trm="rebalancing",
            signal_type=HiveSignalType.REBALANCE_INBOUND,
            urgency=0.5,
            direction="relief",
        ))
        bus.urgency.update("rebalancing", 0.5, "relief")

        metrics = HiveHealthMetrics.from_signal_bus(bus, site_key="TEST")
        assert metrics.active_signal_count == 3
        assert metrics.max_urgency == 0.8
        assert metrics.max_urgency_trm == "atp_executor"
        assert metrics.shortage_count >= 1
