"""
Tests for Deterministic Engines

Tests the 100% deterministic MRP, AATP, and Safety Stock engines.
"""

import pytest
from datetime import date, timedelta
from typing import Dict, List

from app.services.powell.engines import (
    MRPEngine,
    MRPConfig,
    GrossRequirement,
    NetRequirement,
    PlannedOrder,
    AATPEngine,
    AATPConfig,
    ATPAllocation,
    Order,
    ATPResult,
    Priority,
    BufferCalculator,
    BufferConfig,
    BufferPolicy,
    SSResult,
    DemandStats,
    PolicyType,
)


class TestMRPEngine:
    """Tests for MRP Engine"""

    @pytest.fixture
    def mrp_engine(self):
        config = MRPConfig(
            planning_horizon_days=30,
            lot_sizing_rule="lot_for_lot",
        )
        return MRPEngine("SITE001", config)

    def test_simple_netting(self, mrp_engine):
        """Test basic MRP netting without BOM"""
        today = date.today()

        gross_requirements = [
            GrossRequirement(
                item_id="ITEM001",
                required_date=today + timedelta(days=7),
                quantity=100,
                source="demand"
            )
        ]

        on_hand = {"ITEM001": 30}
        scheduled_receipts = {}
        bom = {}
        lead_times = {"ITEM001": 3}

        nets, planned = mrp_engine.compute_net_requirements(
            gross_requirements=gross_requirements,
            on_hand_inventory=on_hand,
            scheduled_receipts=scheduled_receipts,
            bom=bom,
            lead_times=lead_times,
        )

        assert len(nets) == 1
        assert nets[0].net_qty == 70  # 100 - 30 = 70

        assert len(planned) == 1
        assert planned[0].quantity == 70
        assert planned[0].receipt_date == today + timedelta(days=7)
        assert planned[0].order_date == today + timedelta(days=4)  # 7 - 3 = 4
        assert planned[0].order_type == "purchase"

    def test_netting_with_scheduled_receipts(self, mrp_engine):
        """Test netting with scheduled receipts"""
        today = date.today()

        gross_requirements = [
            GrossRequirement(
                item_id="ITEM001",
                required_date=today + timedelta(days=7),
                quantity=100,
                source="demand"
            )
        ]

        on_hand = {"ITEM001": 30}
        scheduled_receipts = {"ITEM001": [(today + timedelta(days=5), 50)]}
        bom = {}
        lead_times = {"ITEM001": 3}

        nets, planned = mrp_engine.compute_net_requirements(
            gross_requirements=gross_requirements,
            on_hand_inventory=on_hand,
            scheduled_receipts=scheduled_receipts,
            bom=bom,
            lead_times=lead_times,
        )

        # With receipt: on_hand(30) + receipt(50) = 80, need 100, net = 20
        assert len(planned) == 1
        assert planned[0].quantity == 20

    def test_bom_explosion(self, mrp_engine):
        """Test BOM explosion creates dependent demand"""
        today = date.today()

        gross_requirements = [
            GrossRequirement(
                item_id="FG001",  # Finished good
                required_date=today + timedelta(days=14),
                quantity=10,
                source="demand"
            )
        ]

        on_hand = {"FG001": 0, "COMP001": 0}
        scheduled_receipts = {}
        bom = {"FG001": [("COMP001", 2.0)]}  # 2 components per FG
        lead_times = {"FG001": 5, "COMP001": 7}

        nets, planned = mrp_engine.compute_net_requirements(
            gross_requirements=gross_requirements,
            on_hand_inventory=on_hand,
            scheduled_receipts=scheduled_receipts,
            bom=bom,
            lead_times=lead_times,
        )

        # Should have planned orders for both FG and component
        fg_orders = [p for p in planned if p.item_id == "FG001"]
        comp_orders = [p for p in planned if p.item_id == "COMP001"]

        assert len(fg_orders) == 1
        assert fg_orders[0].quantity == 10
        assert fg_orders[0].order_type == "manufacture"

        assert len(comp_orders) == 1
        assert comp_orders[0].quantity == 20  # 10 * 2 = 20

    def test_determinism(self, mrp_engine):
        """Test that same inputs produce same outputs"""
        today = date.today()

        gross_requirements = [
            GrossRequirement(
                item_id="ITEM001",
                required_date=today + timedelta(days=7),
                quantity=100,
                source="demand"
            )
        ]

        on_hand = {"ITEM001": 30}

        # Run twice
        nets1, planned1 = mrp_engine.compute_net_requirements(
            gross_requirements=gross_requirements,
            on_hand_inventory=on_hand,
            scheduled_receipts={},
            bom={},
            lead_times={"ITEM001": 3},
        )

        nets2, planned2 = mrp_engine.compute_net_requirements(
            gross_requirements=gross_requirements,
            on_hand_inventory=on_hand,
            scheduled_receipts={},
            bom={},
            lead_times={"ITEM001": 3},
        )

        # Results should be identical
        assert len(nets1) == len(nets2)
        assert len(planned1) == len(planned2)
        assert planned1[0].quantity == planned2[0].quantity


class TestAATPEngine:
    """Tests for Allocated ATP Engine"""

    @pytest.fixture
    def aatp_engine(self):
        return AATPEngine("SITE001")

    @pytest.fixture
    def sample_allocations(self):
        today = date.today()
        return [
            ATPAllocation("PROD001", "SITE001", Priority.CRITICAL, 100, today, today),
            ATPAllocation("PROD001", "SITE001", Priority.HIGH, 200, today, today),
            ATPAllocation("PROD001", "SITE001", Priority.MEDIUM, 300, today, today),
            ATPAllocation("PROD001", "SITE001", Priority.LOW, 200, today, today),
            ATPAllocation("PROD001", "SITE001", Priority.STANDARD, 200, today, today),
        ]

    def test_full_availability(self, aatp_engine, sample_allocations):
        """Test order fully fulfilled from own tier"""
        aatp_engine.load_allocations(sample_allocations)

        order = Order(
            order_id="ORD001",
            product_id="PROD001",
            location_id="SITE001",
            requested_qty=50,
            requested_date=date.today(),
            priority=Priority.MEDIUM,
            customer_id="CUST001",
        )

        result = aatp_engine.check_availability(order)

        assert result.can_fulfill_full
        assert result.available_qty == 50
        assert result.shortage_qty == 0
        # Should consume from own tier first
        assert result.consumption_detail[0] == (Priority.MEDIUM, 50)

    def test_consumption_sequence(self, aatp_engine, sample_allocations):
        """Test consumption follows priority rules"""
        aatp_engine.load_allocations(sample_allocations)

        # Order that exceeds own tier
        order = Order(
            order_id="ORD001",
            product_id="PROD001",
            location_id="SITE001",
            requested_qty=400,  # More than MEDIUM tier (300)
            requested_date=date.today(),
            priority=Priority.MEDIUM,
            customer_id="CUST001",
        )

        result = aatp_engine.check_availability(order)

        assert result.can_fulfill_full
        assert result.available_qty == 400

        # Consumption sequence for P3: [3, 5, 4]
        # Should consume: MEDIUM(300), then STANDARD(100)
        assert (Priority.MEDIUM, 300) in result.consumption_detail
        # Then from lower priorities

    def test_cannot_consume_above_tier(self, aatp_engine, sample_allocations):
        """Test that orders cannot consume from higher priority tiers"""
        aatp_engine.load_allocations(sample_allocations)

        # LOW priority order
        order = Order(
            order_id="ORD001",
            product_id="PROD001",
            location_id="SITE001",
            requested_qty=500,  # More than LOW(200) + STANDARD(200)
            requested_date=date.today(),
            priority=Priority.LOW,
            customer_id="CUST001",
        )

        result = aatp_engine.check_availability(order)

        # Can only consume from LOW(200) and STANDARD(200) = 400
        assert not result.can_fulfill_full
        assert result.available_qty == 400
        assert result.shortage_qty == 100

        # Should NOT consume from MEDIUM, HIGH, or CRITICAL
        consumed_priorities = [p for p, _ in result.consumption_detail]
        assert Priority.MEDIUM not in consumed_priorities
        assert Priority.HIGH not in consumed_priorities
        assert Priority.CRITICAL not in consumed_priorities

    def test_commit_consumption(self, aatp_engine, sample_allocations):
        """Test that commit reduces allocations"""
        aatp_engine.load_allocations(sample_allocations)

        order = Order(
            order_id="ORD001",
            product_id="PROD001",
            location_id="SITE001",
            requested_qty=50,
            requested_date=date.today(),
            priority=Priority.MEDIUM,
            customer_id="CUST001",
        )

        result = aatp_engine.check_availability(order)
        aatp_engine.commit_consumption(order, result)

        # Check remaining allocation
        available = aatp_engine.get_available_by_priority("PROD001", "SITE001")
        assert available[Priority.MEDIUM] == 250  # 300 - 50

    def test_no_allocations(self, aatp_engine):
        """Test behavior when no allocations exist"""
        order = Order(
            order_id="ORD001",
            product_id="PROD001",
            location_id="SITE001",
            requested_qty=50,
            requested_date=date.today(),
            priority=Priority.MEDIUM,
            customer_id="CUST001",
        )

        result = aatp_engine.check_availability(order)

        assert not result.can_fulfill_full
        assert result.available_qty == 0
        assert result.shortage_qty == 50


class TestBufferCalculator:
    """Tests for Buffer Calculator"""

    @pytest.fixture
    def ss_calculator(self):
        return BufferCalculator("SITE001")

    @pytest.fixture
    def demand_stats(self):
        return DemandStats(
            avg_daily_demand=100,
            std_daily_demand=20,
            avg_daily_forecast=100,
            lead_time_days=7,
        )

    def test_abs_level_policy(self, ss_calculator, demand_stats):
        """Test fixed safety stock policy"""
        policy = BufferPolicy(
            policy_type=PolicyType.ABS_LEVEL,
            fixed_quantity=500,
        )

        result = ss_calculator.compute_safety_stock(
            "PROD001", "SITE001", policy, demand_stats
        )

        assert result.safety_stock == 500
        assert result.policy_type == PolicyType.ABS_LEVEL
        # ROP = SS + DDLT = 500 + 100*7 = 1200
        assert result.reorder_point == 1200

    def test_doc_dem_policy(self, ss_calculator, demand_stats):
        """Test days of coverage (demand) policy"""
        policy = BufferPolicy(
            policy_type=PolicyType.DOC_DEM,
            days_of_coverage=14,
        )

        result = ss_calculator.compute_safety_stock(
            "PROD001", "SITE001", policy, demand_stats
        )

        # SS = avg_demand * days = 100 * 14 = 1400
        assert result.safety_stock == 1400
        assert result.policy_type == PolicyType.DOC_DEM

    def test_service_level_policy(self, ss_calculator, demand_stats):
        """Test service level policy"""
        policy = BufferPolicy(
            policy_type=PolicyType.SL,
            target_service_level=0.95,
        )

        result = ss_calculator.compute_safety_stock(
            "PROD001", "SITE001", policy, demand_stats
        )

        # SS = z * σ * √L = 1.645 * 20 * √7 ≈ 87
        assert 80 < result.safety_stock < 95
        assert result.policy_type == PolicyType.SL

    def test_bounds_applied(self, ss_calculator, demand_stats):
        """Test min/max bounds are applied"""
        policy = BufferPolicy(
            policy_type=PolicyType.ABS_LEVEL,
            fixed_quantity=100,
            min_ss=200,  # Higher than fixed
            max_ss=500,
        )

        result = ss_calculator.compute_safety_stock(
            "PROD001", "SITE001", policy, demand_stats
        )

        # Should be clamped to min
        assert result.safety_stock == 200

    def test_seasonal_factor(self, ss_calculator, demand_stats):
        """Test seasonal factor multiplier"""
        policy = BufferPolicy(
            policy_type=PolicyType.ABS_LEVEL,
            fixed_quantity=100,
            seasonal_factor=1.5,  # Peak season
        )

        result = ss_calculator.compute_safety_stock(
            "PROD001", "SITE001", policy, demand_stats
        )

        # 100 * 1.5 = 150
        assert result.safety_stock == 150

    def test_z_score_interpolation(self, ss_calculator):
        """Test z-score lookup with interpolation"""
        # Exact lookup
        assert ss_calculator._get_z_score(0.95) == pytest.approx(1.645, abs=0.001)

        # Interpolated
        z = ss_calculator._get_z_score(0.925)
        assert 1.28 < z < 1.65  # Between 90% and 95%


class TestEngineIntegration:
    """Integration tests across engines"""

    def test_mrp_to_aatp_flow(self):
        """Test MRP output can feed AATP allocations"""
        # MRP generates planned orders
        mrp = MRPEngine("SITE001", MRPConfig())

        today = date.today()
        gross = [GrossRequirement("ITEM001", today + timedelta(days=7), 100, "demand")]

        _, planned = mrp.compute_net_requirements(
            gross_requirements=gross,
            on_hand_inventory={"ITEM001": 0},
            scheduled_receipts={},
            bom={},
            lead_times={"ITEM001": 3},
        )

        assert len(planned) > 0

        # Planned orders can be converted to allocations
        aatp = AATPEngine("SITE001")
        allocations = [
            ATPAllocation(
                product_id=po.item_id,
                location_id="SITE001",
                priority=Priority.MEDIUM,
                allocated_qty=po.quantity,
                period_start=po.receipt_date,
                period_end=po.receipt_date,
            )
            for po in planned
        ]

        aatp.load_allocations(allocations)
        summary = aatp.get_allocation_summary()

        assert summary['total_allocated'] == 100

    def test_ss_to_mrp_flow(self):
        """Test safety stock feeds into MRP as requirement"""
        ss_calc = BufferCalculator("SITE001")

        stats = DemandStats(
            avg_daily_demand=50,
            std_daily_demand=10,
            avg_daily_forecast=50,
            lead_time_days=5,
        )

        policy = BufferPolicy(
            policy_type=PolicyType.SL,
            target_service_level=0.95,
        )

        result = ss_calc.compute_safety_stock("ITEM001", "SITE001", policy, stats)

        # SS can be used in MRP
        mrp = MRPEngine("SITE001", MRPConfig())

        today = date.today()
        gross = [GrossRequirement("ITEM001", today + timedelta(days=10), 100, "demand")]

        nets, planned = mrp.compute_net_requirements(
            gross_requirements=gross,
            on_hand_inventory={"ITEM001": 0},
            scheduled_receipts={},
            bom={},
            lead_times={"ITEM001": 5},
            safety_stocks={"ITEM001": result.safety_stock},
        )

        # Planned quantity should cover both gross requirement and safety stock
        total_planned = sum(p.quantity for p in planned)
        assert total_planned >= 100 + result.safety_stock
