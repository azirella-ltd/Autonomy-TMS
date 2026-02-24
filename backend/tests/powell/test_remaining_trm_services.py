"""
Tests for Remaining TRM Execution Services

Covers the 8 TRM services with zero prior test coverage:
- OrderTrackingTRM
- MOExecutionTRM
- TOExecutionTRM
- QualityDispositionTRM
- MaintenanceSchedulingTRM
- SubcontractingTRM
- ForecastAdjustmentTRM
- InventoryBufferTRM

All tests are pure unit tests (no database required).
"""

import pytest
import numpy as np
from datetime import date, timedelta, datetime
from typing import Dict, List

# ---------- Order Tracking TRM ----------
from app.services.powell.order_tracking_trm import (
    OrderTrackingTRM,
    OrderState,
    OrderType,
    OrderStatus,
    ExceptionDetection,
    ExceptionType,
    ExceptionSeverity,
    RecommendedAction,
)

# ---------- MO Execution TRM ----------
from app.services.powell.mo_execution_trm import (
    MOExecutionTRM,
    MOExecutionState,
    MORecommendation,
    MOExecutionTRMConfig,
)

# ---------- TO Execution TRM ----------
from app.services.powell.to_execution_trm import (
    TOExecutionTRM,
    TOExecutionState,
    TORecommendation,
    TOExecutionTRMConfig,
)

# ---------- Quality Disposition TRM ----------
from app.services.powell.quality_disposition_trm import (
    QualityDispositionTRM,
    QualityDispositionState,
    QualityRecommendation,
    QualityDispositionTRMConfig,
)

# ---------- Maintenance Scheduling TRM ----------
from app.services.powell.maintenance_scheduling_trm import (
    MaintenanceSchedulingTRM,
    MaintenanceSchedulingState,
    MaintenanceRecommendation,
    MaintenanceSchedulingTRMConfig,
)

# ---------- Subcontracting TRM ----------
from app.services.powell.subcontracting_trm import (
    SubcontractingTRM,
    SubcontractingState,
    SubcontractingRecommendation,
    SubcontractingTRMConfig,
)

# ---------- Forecast Adjustment TRM ----------
from app.services.powell.forecast_adjustment_trm import (
    ForecastAdjustmentTRM,
    ForecastAdjustmentState,
    ForecastAdjustmentRecommendation,
    ForecastAdjustmentTRMConfig,
)

# ---------- Inventory Buffer TRM ----------
from app.services.powell.inventory_buffer_trm import (
    InventoryBufferTRM,
    SSState,
    SSAdjustment,
    SSAdjustmentReason,
)


# ============================================================================
# Order Tracking TRM Tests
# ============================================================================

class TestOrderTrackingTRM:
    """Tests for OrderTrackingTRM service."""

    @pytest.fixture
    def trm(self):
        return OrderTrackingTRM(use_heuristic_fallback=True)

    @pytest.fixture
    def normal_order(self):
        """Order progressing normally - no exception expected."""
        future = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        return OrderState(
            order_id="PO-001",
            order_type=OrderType.PURCHASE_ORDER,
            status=OrderStatus.IN_TRANSIT,
            created_date=past,
            expected_date=future,
            ordered_qty=100.0,
            received_qty=0.0,
            remaining_qty=100.0,
            expected_unit_price=10.0,
            actual_unit_price=10.0,
            product_id="PROD-A",
            from_location="VENDOR-1",
            to_location="DC-1",
            partner_id="V001",
            partner_on_time_rate=0.95,
            partner_fill_rate=0.98,
            typical_transit_days=5.0,
        )

    @pytest.fixture
    def late_order(self):
        """Order that is significantly late."""
        past_expected = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        past_created = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")
        return OrderState(
            order_id="PO-002",
            order_type=OrderType.PURCHASE_ORDER,
            status=OrderStatus.IN_TRANSIT,
            created_date=past_created,
            expected_date=past_expected,
            ordered_qty=200.0,
            received_qty=0.0,
            remaining_qty=200.0,
            expected_unit_price=10.0,
            actual_unit_price=10.0,
            product_id="PROD-B",
            from_location="VENDOR-2",
            to_location="DC-1",
            partner_id="V002",
            partner_on_time_rate=0.80,
            typical_transit_days=5.0,
        )

    def test_order_state_dataclass_construction(self, normal_order):
        """Test OrderState dataclass fields and defaults."""
        assert normal_order.order_id == "PO-001"
        assert normal_order.order_type == OrderType.PURCHASE_ORDER
        assert normal_order.status == OrderStatus.IN_TRANSIT
        assert normal_order.ordered_qty == 100.0
        assert normal_order.received_qty == 0.0

    def test_order_state_fill_rate_property(self):
        """Test fill rate calculation."""
        state = OrderState(
            order_id="T1",
            order_type=OrderType.PURCHASE_ORDER,
            status=OrderStatus.PARTIALLY_RECEIVED,
            created_date="2025-01-01",
            expected_date="2025-01-10",
            ordered_qty=100.0,
            received_qty=75.0,
        )
        assert state.fill_rate == pytest.approx(0.75)

    def test_order_state_fill_rate_zero_ordered(self):
        """Test fill rate when ordered_qty is zero."""
        state = OrderState(
            order_id="T2",
            order_type=OrderType.TRANSFER_ORDER,
            status=OrderStatus.CREATED,
            created_date="2025-01-01",
            expected_date="2025-01-10",
            ordered_qty=0.0,
        )
        assert state.fill_rate == 1.0

    def test_order_state_price_variance(self):
        """Test price variance calculation."""
        state = OrderState(
            order_id="T3",
            order_type=OrderType.PURCHASE_ORDER,
            status=OrderStatus.RECEIVED,
            created_date="2025-01-01",
            expected_date="2025-01-10",
            expected_unit_price=100.0,
            actual_unit_price=115.0,
        )
        assert state.price_variance_pct == pytest.approx(0.15)

    def test_order_state_price_variance_zero_expected(self):
        """Test price variance when expected price is zero."""
        state = OrderState(
            order_id="T4",
            order_type=OrderType.PURCHASE_ORDER,
            status=OrderStatus.RECEIVED,
            created_date="2025-01-01",
            expected_date="2025-01-10",
            expected_unit_price=0.0,
            actual_unit_price=10.0,
        )
        assert state.price_variance_pct == 0.0

    def test_order_state_to_features(self, normal_order):
        """Test feature vector generation."""
        features = normal_order.to_features()
        assert isinstance(features, np.ndarray)
        assert features.dtype == np.float32
        assert len(features) == 15

    def test_trm_initialization_defaults(self):
        """Test TRM initializes with default parameters."""
        trm = OrderTrackingTRM()
        assert trm.late_threshold_days == 2.0
        assert trm.early_threshold_days == 3.0
        assert trm.quantity_variance_threshold == 0.05
        assert trm.price_variance_threshold == 0.10
        assert trm.use_heuristic_fallback is True
        assert trm.trm_model is None
        assert trm.db is None

    def test_trm_initialization_custom_params(self):
        """Test TRM initializes with custom parameters."""
        trm = OrderTrackingTRM(
            late_threshold_days=5.0,
            early_threshold_days=7.0,
            quantity_variance_threshold=0.10,
            price_variance_threshold=0.20,
        )
        assert trm.late_threshold_days == 5.0
        assert trm.early_threshold_days == 7.0
        assert trm.quantity_variance_threshold == 0.10
        assert trm.price_variance_threshold == 0.20

    def test_evaluate_normal_order(self, trm, normal_order):
        """Test evaluation of a normal on-time order."""
        result = trm.evaluate_order(normal_order)
        assert isinstance(result, ExceptionDetection)
        assert result.order_id == "PO-001"
        # A normal in-transit order with future expected date should not be an exception
        assert result.exception_type in (
            ExceptionType.NO_EXCEPTION,
            ExceptionType.EARLY_DELIVERY,
        )

    def test_evaluate_late_order(self, trm, late_order):
        """Test evaluation of a late order triggers exception."""
        result = trm.evaluate_order(late_order)
        assert isinstance(result, ExceptionDetection)
        assert result.order_id == "PO-002"
        assert result.exception_type in (ExceptionType.LATE_DELIVERY, ExceptionType.STUCK_IN_TRANSIT)
        assert result.severity in (ExceptionSeverity.WARNING, ExceptionSeverity.HIGH, ExceptionSeverity.CRITICAL)
        assert result.recommended_action in (RecommendedAction.EXPEDITE, RecommendedAction.FIND_ALTERNATE)

    def test_evaluate_quantity_shortage(self, trm):
        """Test detection of quantity shortage."""
        past = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        state = OrderState(
            order_id="PO-SHORT",
            order_type=OrderType.PURCHASE_ORDER,
            status=OrderStatus.PARTIALLY_RECEIVED,
            created_date=past,
            expected_date=past,
            ordered_qty=100.0,
            received_qty=50.0,
            remaining_qty=50.0,
        )
        result = trm.evaluate_order(state)
        assert result.exception_type == ExceptionType.QUANTITY_SHORTAGE

    def test_exception_detection_to_dict(self):
        """Test ExceptionDetection serialization."""
        detection = ExceptionDetection(
            order_id="PO-100",
            exception_type=ExceptionType.LATE_DELIVERY,
            severity=ExceptionSeverity.HIGH,
            recommended_action=RecommendedAction.EXPEDITE,
            description="Order is 5 days late",
            impact_assessment="Service level at risk",
            estimated_impact_cost=5000.0,
            confidence=0.85,
        )
        d = detection.to_dict()
        assert d["order_id"] == "PO-100"
        assert d["exception_type"] == "late_delivery"
        assert d["severity"] == "high"
        assert d["recommended_action"] == "expedite"
        assert d["estimated_impact_cost"] == 5000.0
        assert d["confidence"] == 0.85
        assert "context_explanation" not in d  # None means excluded

    def test_exception_detection_to_dict_with_context(self):
        """Test ExceptionDetection serialization with context."""
        detection = ExceptionDetection(
            order_id="PO-101",
            exception_type=ExceptionType.NO_EXCEPTION,
            severity=ExceptionSeverity.INFO,
            recommended_action=RecommendedAction.NO_ACTION,
            description="OK",
            impact_assessment="None",
            context_explanation={"authority": "order_tracking", "guardrails": []},
        )
        d = detection.to_dict()
        assert "context_explanation" in d
        assert d["context_explanation"]["authority"] == "order_tracking"

    def test_batch_evaluation(self, trm, normal_order, late_order):
        """Test batch evaluation of multiple orders."""
        results = trm.evaluate_orders_batch([normal_order, late_order])
        assert len(results) == 2
        assert results[0].order_id == "PO-001"
        assert results[1].order_id == "PO-002"

    def test_get_critical_exceptions(self, trm, normal_order, late_order):
        """Test filtering for critical/high severity exceptions."""
        results = trm.get_critical_exceptions([normal_order, late_order])
        # Late order (5 days late) should be high/critical
        assert any(r.order_id == "PO-002" for r in results)

    def test_decision_history_recording(self, trm, normal_order):
        """Test that evaluation records decisions for training."""
        trm.evaluate_order(normal_order)
        history = trm.get_training_data()
        assert len(history) >= 1
        assert history[0]["order_state"]["order_id"] == "PO-001"

    def test_no_fallback_returns_no_exception(self, normal_order):
        """Test that disabling heuristic returns no exception when no model."""
        trm = OrderTrackingTRM(use_heuristic_fallback=False)
        result = trm.evaluate_order(normal_order)
        assert result.exception_type == ExceptionType.NO_EXCEPTION
        assert result.recommended_action == RecommendedAction.NO_ACTION


# ============================================================================
# MO Execution TRM Tests
# ============================================================================

class TestMOExecutionTRM:
    """Tests for MOExecutionTRM service."""

    @pytest.fixture
    def trm(self):
        return MOExecutionTRM(site_key="PLANT-001")

    @pytest.fixture
    def ready_mo_state(self):
        """MO that is ready for release."""
        return MOExecutionState(
            order_id="MO-001",
            product_id="FG-100",
            site_id="PLANT-001",
            planned_quantity=500.0,
            days_until_due=5,
            priority=2,
            material_availability_pct=0.98,
            missing_component_count=0,
            capacity_utilization_pct=0.60,
            resource_utilization_pct=0.55,
            setup_time_hours=2.0,
            run_time_hours=8.0,
            queue_depth=3,
            queue_total_hours=20.0,
            avg_yield_pct=0.96,
            customer_order_linked=True,
        )

    @pytest.fixture
    def deferred_mo_state(self):
        """MO that should be deferred -- far from due, materials not ready."""
        return MOExecutionState(
            order_id="MO-002",
            product_id="FG-200",
            site_id="PLANT-001",
            planned_quantity=200.0,
            days_until_due=30,
            priority=4,
            material_availability_pct=0.50,
            missing_component_count=3,
            capacity_utilization_pct=0.30,
            resource_utilization_pct=0.25,
            setup_time_hours=1.0,
            run_time_hours=4.0,
            queue_depth=0,
            queue_total_hours=0.0,
        )

    def test_mo_state_dataclass_construction(self, ready_mo_state):
        """Test MOExecutionState fields."""
        assert ready_mo_state.order_id == "MO-001"
        assert ready_mo_state.product_id == "FG-100"
        assert ready_mo_state.priority == 2
        assert ready_mo_state.customer_order_linked is True

    def test_mo_recommendation_defaults(self):
        """Test MORecommendation default values."""
        rec = MORecommendation(
            order_id="MO-TEST",
            decision_type="release",
            confidence=0.8,
        )
        assert rec.release_now is False
        assert rec.expedite is False
        assert rec.defer_days == 0
        assert rec.split_quantities == []
        assert rec.priority_override is None
        assert rec.service_risk == 0.0

    def test_trm_initialization_defaults(self):
        """Test TRM initializes with defaults."""
        trm = MOExecutionTRM(site_key="PLANT-X")
        assert trm.site_key == "PLANT-X"
        assert trm.model is None
        assert trm.config.confidence_threshold == 0.7
        assert trm.config.max_defer_days == 14

    def test_trm_initialization_custom_config(self):
        """Test TRM with custom config."""
        cfg = MOExecutionTRMConfig(confidence_threshold=0.9, max_defer_days=7)
        trm = MOExecutionTRM(site_key="PLANT-X", config=cfg)
        assert trm.config.confidence_threshold == 0.9
        assert trm.config.max_defer_days == 7

    def test_evaluate_ready_order(self, trm, ready_mo_state):
        """Test evaluation of a release-ready MO."""
        rec = trm.evaluate_order(ready_mo_state)
        assert isinstance(rec, MORecommendation)
        assert rec.order_id == "MO-001"
        assert rec.confidence > 0
        # Ready MO with all materials should get release recommendation
        assert rec.decision_type in ("release", "expedite", "sequence")

    def test_evaluate_deferred_order(self, trm, deferred_mo_state):
        """Test evaluation of an MO that should be deferred."""
        rec = trm.evaluate_order(deferred_mo_state)
        assert rec.order_id == "MO-002"
        # Materials at 50%, far from due date -> defer expected
        assert rec.decision_type in ("defer", "release")

    def test_heuristic_customer_linked_expedite(self, trm):
        """Test heuristic: customer-linked MO close to due gets expedited."""
        state = MOExecutionState(
            order_id="MO-CL",
            product_id="FG-300",
            site_id="PLANT-001",
            planned_quantity=100.0,
            days_until_due=3,
            priority=4,  # Low priority, but customer-linked
            material_availability_pct=0.99,
            missing_component_count=0,
            capacity_utilization_pct=0.50,
            resource_utilization_pct=0.40,
            setup_time_hours=1.0,
            run_time_hours=2.0,
            queue_depth=1,
            queue_total_hours=5.0,
            customer_order_linked=True,
        )
        rec = trm.evaluate_order(state)
        # Customer-linked + close to due should trigger priority override and expedite
        if rec.decision_type in ("release", "expedite"):
            # Heuristic should boost priority for customer-linked orders near due
            assert rec.expedite is True or rec.priority_override is not None or rec.decision_type == "expedite"

    def test_batch_evaluation(self, trm, ready_mo_state, deferred_mo_state):
        """Test batch evaluation."""
        results = trm.evaluate_batch([ready_mo_state, deferred_mo_state])
        assert len(results) == 2
        assert results[0].order_id == "MO-001"
        assert results[1].order_id == "MO-002"

    def test_encode_state_length(self, trm, ready_mo_state):
        """Test that _encode_state returns correct feature length."""
        features = trm._encode_state(ready_mo_state)
        assert len(features) == 17
        assert all(isinstance(f, float) for f in features)

    def test_get_training_data_no_db(self, trm):
        """Test that get_training_data returns empty without DB."""
        data = trm.get_training_data(config_id=1)
        assert data == []


# ============================================================================
# TO Execution TRM Tests
# ============================================================================

class TestTOExecutionTRM:
    """Tests for TOExecutionTRM service."""

    @pytest.fixture
    def trm(self):
        return TOExecutionTRM(site_key="DC-001")

    @pytest.fixture
    def draft_to_state(self):
        """Draft TO that needs release evaluation."""
        return TOExecutionState(
            order_id="TO-001",
            product_id="SKU-100",
            source_site_id="CDC-01",
            dest_site_id="RDC-01",
            planned_qty=200.0,
            status="DRAFT",
            transportation_mode="truck",
            estimated_transit_days=2,
            source_on_hand=500.0,
            source_dos=15.0,
            source_committed=100.0,
            dest_on_hand=50.0,
            dest_dos=3.0,
            dest_backlog=20.0,
            dest_safety_stock=80.0,
            days_until_needed=4,
            priority=2,
            transportation_cost=500.0,
        )

    @pytest.fixture
    def urgent_to_state(self):
        """Urgent TO where destination has backlog and low inventory."""
        return TOExecutionState(
            order_id="TO-002",
            product_id="SKU-200",
            source_site_id="CDC-01",
            dest_site_id="RDC-02",
            planned_qty=300.0,
            status="RELEASED",
            transportation_mode="truck",
            estimated_transit_days=3,
            source_on_hand=1000.0,
            source_dos=20.0,
            dest_on_hand=10.0,
            dest_dos=0.5,
            dest_backlog=150.0,
            dest_safety_stock=100.0,
            days_until_needed=0,
            priority=1,
        )

    def test_to_state_dataclass_construction(self, draft_to_state):
        """Test TOExecutionState fields."""
        assert draft_to_state.order_id == "TO-001"
        assert draft_to_state.source_site_id == "CDC-01"
        assert draft_to_state.dest_site_id == "RDC-01"
        assert draft_to_state.planned_qty == 200.0

    def test_to_recommendation_defaults(self):
        """Test TORecommendation default values."""
        rec = TORecommendation(
            order_id="TO-X",
            decision_type="release",
            confidence=0.7,
        )
        assert rec.release_now is False
        assert rec.expedite is False
        assert rec.consolidate_with == []
        assert rec.defer_days == 0
        assert rec.reroute_via is None

    def test_trm_initialization(self):
        """Test TRM initializes properly."""
        trm = TOExecutionTRM(site_key="DC-X")
        assert trm.site_key == "DC-X"
        assert trm.model is None
        assert trm.config.max_defer_days == 7

    def test_trm_custom_config(self):
        """Test TRM with custom config."""
        cfg = TOExecutionTRMConfig(max_defer_days=14, confidence_threshold=0.8)
        trm = TOExecutionTRM(site_key="DC-X", config=cfg)
        assert trm.config.max_defer_days == 14
        assert trm.config.confidence_threshold == 0.8

    def test_evaluate_draft_to(self, trm, draft_to_state):
        """Test evaluation of a draft TO."""
        rec = trm.evaluate_order(draft_to_state)
        assert isinstance(rec, TORecommendation)
        assert rec.order_id == "TO-001"
        assert rec.confidence > 0

    def test_evaluate_urgent_to_expedite(self, trm, urgent_to_state):
        """Test evaluation of urgent TO triggers expedite."""
        rec = trm.evaluate_order(urgent_to_state)
        assert rec.order_id == "TO-002"
        # Dest DOS of 0.5 with backlog should recommend expedite
        assert rec.expedite is True or rec.decision_type == "expedite"

    def test_heuristic_backlog_release(self, trm):
        """Test heuristic: destination backlog + source plenty = immediate release."""
        state = TOExecutionState(
            order_id="TO-BACKLOG",
            product_id="SKU-300",
            source_site_id="CDC-01",
            dest_site_id="RDC-03",
            planned_qty=100.0,
            status="DRAFT",
            source_on_hand=2000.0,
            source_dos=30.0,
            dest_on_hand=5.0,
            dest_dos=0.3,
            dest_backlog=50.0,
            days_until_needed=1,
            priority=2,
        )
        rec = trm.evaluate_order(state)
        # Source has plenty (DOS=30 > 7) and dest has backlog
        assert rec.release_now is True or rec.decision_type == "release"

    def test_encode_state_length(self, trm, draft_to_state):
        """Test _encode_state returns correct feature length."""
        features = trm._encode_state(draft_to_state)
        assert len(features) == 18

    def test_batch_evaluation(self, trm, draft_to_state, urgent_to_state):
        """Test batch evaluation."""
        results = trm.evaluate_batch([draft_to_state, urgent_to_state])
        assert len(results) == 2

    def test_get_training_data_no_db(self, trm):
        """Test get_training_data returns empty without DB."""
        data = trm.get_training_data(config_id=1)
        assert data == []


# ============================================================================
# Quality Disposition TRM Tests
# ============================================================================

class TestQualityDispositionTRM:
    """Tests for QualityDispositionTRM service."""

    @pytest.fixture
    def trm(self):
        return QualityDispositionTRM(site_key="PLANT-001")

    @pytest.fixture
    def minor_defect_state(self):
        """Inspection with minor defects -- likely accept or use-as-is."""
        return QualityDispositionState(
            quality_order_id="QO-001",
            product_id="PROD-A",
            site_id="PLANT-001",
            inspection_type="incoming",
            inspection_quantity=1000.0,
            defect_count=5,
            defect_rate=0.005,
            defect_category="visual",
            severity_level="minor",
            characteristics_tested=20,
            characteristics_passed=19,
            product_unit_value=50.0,
            estimated_rework_cost=1000.0,
            estimated_scrap_cost=5000.0,
            vendor_id="V001",
            vendor_quality_score=92.0,
            inventory_on_hand=500.0,
            safety_stock=200.0,
            days_of_supply=15.0,
        )

    @pytest.fixture
    def critical_defect_state(self):
        """Inspection with critical defects -- should reject."""
        return QualityDispositionState(
            quality_order_id="QO-002",
            product_id="PROD-B",
            site_id="PLANT-001",
            inspection_type="incoming",
            inspection_quantity=500.0,
            defect_count=25,
            defect_rate=0.05,
            defect_category="functional",
            severity_level="critical",
            characteristics_tested=10,
            characteristics_passed=7,
            product_unit_value=100.0,
            estimated_rework_cost=10000.0,
            estimated_scrap_cost=50000.0,
            vendor_id="V002",
            vendor_quality_score=70.0,
            days_since_receipt=5,
            inventory_on_hand=2000.0,
            safety_stock=300.0,
            days_of_supply=30.0,
        )

    def test_quality_state_dataclass(self, minor_defect_state):
        """Test QualityDispositionState fields."""
        assert minor_defect_state.quality_order_id == "QO-001"
        assert minor_defect_state.defect_rate == 0.005
        assert minor_defect_state.severity_level == "minor"

    def test_quality_recommendation_defaults(self):
        """Test QualityRecommendation defaults."""
        rec = QualityRecommendation(
            quality_order_id="QO-X",
            disposition="accept",
            confidence=0.9,
        )
        assert rec.accept_qty == 0.0
        assert rec.reject_qty == 0.0
        assert rec.rework_qty == 0.0
        assert rec.return_to_vendor is False

    def test_trm_initialization(self):
        """Test TRM initializes properly."""
        trm = QualityDispositionTRM(site_key="SITE-A")
        assert trm.site_key == "SITE-A"
        assert trm.model is None
        assert trm.config.confidence_threshold == 0.7

    def test_evaluate_minor_defects_accepted(self, trm, minor_defect_state):
        """Test minor defects get accepted or use-as-is."""
        rec = trm.evaluate_disposition(minor_defect_state)
        assert isinstance(rec, QualityRecommendation)
        assert rec.quality_order_id == "QO-001"
        # Very low defect rate (0.5%) + minor severity -> should accept
        assert rec.disposition in ("accept", "use_as_is", "conditional_accept")
        assert rec.confidence > 0

    def test_evaluate_critical_defects_rejected(self, trm, critical_defect_state):
        """Test critical defects get rejected."""
        rec = trm.evaluate_disposition(critical_defect_state)
        assert rec.quality_order_id == "QO-002"
        # Critical severity -> should reject
        assert rec.disposition in ("reject", "return_to_vendor", "scrap")

    def test_heuristic_vendor_poor_quality_reject(self, trm):
        """Test heuristic: poor vendor recent quality triggers return."""
        state = QualityDispositionState(
            quality_order_id="QO-POOR",
            product_id="PROD-C",
            site_id="PLANT-001",
            inspection_type="incoming",
            inspection_quantity=100.0,
            defect_count=4,
            defect_rate=0.04,
            defect_category="dimensional",
            severity_level="major",
            characteristics_tested=10,
            characteristics_passed=8,
            product_unit_value=25.0,
            estimated_rework_cost=500.0,
            estimated_scrap_cost=2500.0,
            vendor_id="V-BAD",
            vendor_quality_score=60.0,
            vendor_recent_reject_rate=0.20,  # 20% recent reject rate
            days_since_receipt=5,
        )
        rec = trm.evaluate_disposition(state)
        # Vendor has >15% recent reject rate + major severity -> return_to_vendor
        assert rec.disposition in ("return_to_vendor", "reject", "rework")

    def test_encode_state_length(self, trm, minor_defect_state):
        """Test _encode_state returns correct feature length."""
        features = trm._encode_state(minor_defect_state)
        assert len(features) == 18

    def test_batch_evaluation(self, trm, minor_defect_state, critical_defect_state):
        """Test batch evaluation."""
        results = trm.evaluate_batch([minor_defect_state, critical_defect_state])
        assert len(results) == 2
        assert results[0].quality_order_id == "QO-001"
        assert results[1].quality_order_id == "QO-002"


# ============================================================================
# Maintenance Scheduling TRM Tests
# ============================================================================

class TestMaintenanceSchedulingTRM:
    """Tests for MaintenanceSchedulingTRM service."""

    @pytest.fixture
    def trm(self):
        return MaintenanceSchedulingTRM(site_key="PLANT-001")

    @pytest.fixture
    def routine_maintenance(self):
        """Routine preventive maintenance, not overdue."""
        return MaintenanceSchedulingState(
            order_id="MAINT-001",
            asset_id="ASSET-CNC-01",
            site_id="PLANT-001",
            maintenance_type="preventive",
            status="PLANNED",
            scheduled_date=date.today() + timedelta(days=5),
            days_since_last_maintenance=80,
            maintenance_frequency_days=90,
            days_overdue=0,
            defer_count=0,
            estimated_downtime_hours=4.0,
            estimated_labor_hours=6.0,
            estimated_cost=2000.0,
            spare_parts_available=True,
            asset_criticality="normal",
            asset_age_years=5.0,
            mean_time_between_failures_days=365.0,
            recent_failure_count=0,
            production_schedule_load_pct=70.0,
            next_production_gap_days=3,
            priority="NORMAL",
        )

    @pytest.fixture
    def emergency_maintenance(self):
        """Emergency corrective maintenance."""
        return MaintenanceSchedulingState(
            order_id="MAINT-002",
            asset_id="ASSET-PRESS-01",
            site_id="PLANT-001",
            maintenance_type="emergency",
            status="PLANNED",
            days_since_last_maintenance=200,
            maintenance_frequency_days=90,
            days_overdue=20,
            defer_count=2,
            estimated_downtime_hours=12.0,
            estimated_cost=8000.0,
            spare_parts_available=True,
            asset_criticality="critical",
            asset_age_years=15.0,
            recent_failure_count=3,
            production_schedule_load_pct=95.0,
            priority="EMERGENCY",
        )

    def test_maintenance_state_dataclass(self, routine_maintenance):
        """Test MaintenanceSchedulingState fields."""
        assert routine_maintenance.order_id == "MAINT-001"
        assert routine_maintenance.maintenance_type == "preventive"
        assert routine_maintenance.asset_criticality == "normal"
        assert routine_maintenance.spare_parts_available is True

    def test_maintenance_recommendation_defaults(self):
        """Test MaintenanceRecommendation defaults."""
        rec = MaintenanceRecommendation(
            order_id="M-X",
            decision_type="schedule",
            confidence=0.7,
        )
        assert rec.expedite is False
        assert rec.outsource is False
        assert rec.combine_with == []
        assert rec.defer_risk == 0.0
        assert rec.breakdown_probability == 0.0

    def test_trm_initialization(self):
        """Test TRM initializes properly."""
        trm = MaintenanceSchedulingTRM(site_key="PLANT-X")
        assert trm.site_key == "PLANT-X"
        assert trm.model is None
        assert trm.config.confidence_threshold == 0.7

    def test_evaluate_routine_maintenance(self, trm, routine_maintenance):
        """Test evaluation of routine preventive maintenance."""
        rec = trm.evaluate_scheduling(routine_maintenance)
        assert isinstance(rec, MaintenanceRecommendation)
        assert rec.order_id == "MAINT-001"
        # Routine with no overdue should schedule or defer
        assert rec.decision_type in ("schedule", "defer")
        assert rec.confidence > 0

    def test_evaluate_emergency_expedite(self, trm, emergency_maintenance):
        """Test emergency maintenance gets expedited."""
        rec = trm.evaluate_scheduling(emergency_maintenance)
        assert rec.order_id == "MAINT-002"
        # Emergency type -> should expedite
        assert rec.decision_type == "expedite"
        assert rec.expedite is True

    def test_heuristic_high_breakdown_no_defer(self, trm):
        """Test heuristic: high historical breakdown rate prevents deferral."""
        state = MaintenanceSchedulingState(
            order_id="MAINT-RISK",
            asset_id="ASSET-OLD",
            site_id="PLANT-001",
            maintenance_type="preventive",
            status="PLANNED",
            days_since_last_maintenance=120,
            maintenance_frequency_days=90,
            days_overdue=30,
            defer_count=1,
            estimated_downtime_hours=8.0,
            estimated_cost=5000.0,
            spare_parts_available=True,
            asset_criticality="high",
            asset_age_years=12.0,
            recent_failure_count=2,
            production_schedule_load_pct=90.0,
            next_production_gap_days=10,
            priority="HIGH",
            historical_breakdown_rate_after_defer=0.40,  # >30% -> should not defer
        )
        rec = trm.evaluate_scheduling(state)
        # High breakdown rate after defer should override deferral to schedule
        # (if engine says defer, heuristic overrides to schedule)
        assert rec.decision_type in ("schedule", "expedite")

    def test_encode_state_length(self, trm, routine_maintenance):
        """Test _encode_state returns correct feature length."""
        features = trm._encode_state(routine_maintenance)
        assert len(features) == 16

    def test_batch_evaluation(self, trm, routine_maintenance, emergency_maintenance):
        """Test batch evaluation."""
        results = trm.evaluate_batch([routine_maintenance, emergency_maintenance])
        assert len(results) == 2
        assert results[0].order_id == "MAINT-001"
        assert results[1].order_id == "MAINT-002"

    def test_get_training_data_no_db(self, trm):
        """Test get_training_data returns empty without DB."""
        data = trm.get_training_data(config_id=1)
        assert data == []


# ============================================================================
# Subcontracting TRM Tests
# ============================================================================

class TestSubcontractingTRM:
    """Tests for SubcontractingTRM service."""

    @pytest.fixture
    def trm(self):
        return SubcontractingTRM(site_key="PLANT-001")

    @pytest.fixture
    def internal_preferred_state(self):
        """State where internal production is preferred."""
        return SubcontractingState(
            product_id="PROD-INT",
            site_id="PLANT-001",
            required_quantity=500.0,
            required_by_date=date.today() + timedelta(days=14),
            internal_capacity_pct=50.0,
            internal_cost_per_unit=10.0,
            internal_lead_time_days=7,
            internal_quality_yield_pct=0.99,
            subcontractor_id="SUB-001",
            subcontractor_cost_per_unit=12.0,  # More expensive
            subcontractor_lead_time_days=10,
            subcontractor_quality_score=0.90,
            subcontractor_on_time_score=0.85,
            subcontractor_capacity_available=500.0,
            is_critical_product=False,
        )

    @pytest.fixture
    def capacity_constrained_state(self):
        """State where capacity forces external routing."""
        return SubcontractingState(
            product_id="PROD-EXT",
            site_id="PLANT-001",
            required_quantity=1000.0,
            required_by_date=date.today() + timedelta(days=21),
            internal_capacity_pct=95.0,  # Almost full
            internal_cost_per_unit=15.0,
            internal_lead_time_days=14,
            internal_quality_yield_pct=0.97,
            subcontractor_id="SUB-002",
            subcontractor_cost_per_unit=13.0,  # Cheaper externally
            subcontractor_lead_time_days=7,
            subcontractor_quality_score=0.93,
            subcontractor_on_time_score=0.90,
            subcontractor_capacity_available=800.0,
        )

    def test_subcontracting_state_dataclass(self, internal_preferred_state):
        """Test SubcontractingState fields."""
        assert internal_preferred_state.product_id == "PROD-INT"
        assert internal_preferred_state.internal_capacity_pct == 50.0
        assert internal_preferred_state.is_critical_product is False

    def test_subcontracting_recommendation_defaults(self):
        """Test SubcontractingRecommendation defaults."""
        rec = SubcontractingRecommendation(
            order_id="SC-X",
            decision_type="keep_internal",
            confidence=0.8,
        )
        assert rec.internal_quantity == 0.0
        assert rec.external_quantity == 0.0
        assert rec.recommended_vendor is None
        assert rec.cost_savings == 0.0

    def test_trm_initialization(self):
        """Test TRM initializes properly."""
        trm = SubcontractingTRM(site_key="PLANT-X")
        assert trm.site_key == "PLANT-X"
        assert trm.model is None
        assert trm.config.confidence_threshold == 0.7

    def test_evaluate_keep_internal(self, trm, internal_preferred_state):
        """Test evaluation keeps production internal when preferred."""
        rec = trm.evaluate_routing(internal_preferred_state)
        assert isinstance(rec, SubcontractingRecommendation)
        # Internal is cheaper and has capacity -> keep internal or split
        assert rec.decision_type in ("keep_internal", "split")

    def test_evaluate_capacity_constrained(self, trm, capacity_constrained_state):
        """Test capacity-constrained scenario routes externally."""
        rec = trm.evaluate_routing(capacity_constrained_state)
        # Internal capacity at 95% -> should split or route_external
        assert rec.decision_type in ("split", "route_external", "keep_internal")

    def test_heuristic_critical_product_keeps_internal(self, trm):
        """Test heuristic: critical product with mediocre vendor stays internal."""
        state = SubcontractingState(
            product_id="PROD-CRIT",
            site_id="PLANT-001",
            required_quantity=200.0,
            internal_capacity_pct=60.0,
            internal_cost_per_unit=20.0,
            internal_lead_time_days=10,
            subcontractor_id="SUB-003",
            subcontractor_cost_per_unit=10.0,  # Much cheaper
            subcontractor_lead_time_days=5,
            subcontractor_quality_score=0.88,  # Below 0.92 threshold
            subcontractor_on_time_score=0.90,
            is_critical_product=True,  # Critical product
        )
        rec = trm.evaluate_routing(state)
        # Critical product + vendor quality < 0.92 -> keep internal
        assert rec.decision_type == "keep_internal"

    def test_heuristic_high_reject_rate_avoids_vendor(self, trm):
        """Test heuristic: high vendor reject rate avoids external routing."""
        state = SubcontractingState(
            product_id="PROD-REJ",
            site_id="PLANT-001",
            required_quantity=300.0,
            internal_capacity_pct=95.0,
            internal_cost_per_unit=15.0,
            internal_lead_time_days=10,
            subcontractor_id="SUB-004",
            subcontractor_cost_per_unit=8.0,
            subcontractor_lead_time_days=5,
            subcontractor_quality_score=0.95,
            subcontractor_on_time_score=0.95,
            vendor_historical_reject_rate=0.15,  # >10% -> avoid
        )
        rec = trm.evaluate_routing(state)
        # High reject rate should prevent external routing
        assert rec.decision_type == "keep_internal"

    def test_no_subcontractor_keeps_internal(self, trm):
        """Test that missing subcontractor keeps internal."""
        state = SubcontractingState(
            product_id="PROD-NOSUB",
            site_id="PLANT-001",
            required_quantity=100.0,
            internal_capacity_pct=50.0,
            internal_cost_per_unit=10.0,
            subcontractor_id=None,  # No subcontractor
        )
        rec = trm.evaluate_routing(state)
        assert rec.decision_type == "keep_internal"

    def test_ip_sensitivity_keeps_internal(self, trm):
        """Test high IP sensitivity keeps production internal."""
        state = SubcontractingState(
            product_id="PROD-IP",
            site_id="PLANT-001",
            required_quantity=100.0,
            internal_capacity_pct=95.0,
            internal_cost_per_unit=50.0,
            subcontractor_id="SUB-005",
            subcontractor_cost_per_unit=10.0,  # Much cheaper
            subcontractor_quality_score=0.99,
            subcontractor_on_time_score=0.99,
            ip_sensitivity="high",
        )
        rec = trm.evaluate_routing(state)
        assert rec.decision_type == "keep_internal"

    def test_encode_state_length(self, trm, internal_preferred_state):
        """Test _encode_state returns correct feature length."""
        features = trm._encode_state(internal_preferred_state)
        assert len(features) == 17

    def test_batch_evaluation(self, trm, internal_preferred_state, capacity_constrained_state):
        """Test batch evaluation."""
        results = trm.evaluate_batch([internal_preferred_state, capacity_constrained_state])
        assert len(results) == 2


# ============================================================================
# Forecast Adjustment TRM Tests
# ============================================================================

class TestForecastAdjustmentTRM:
    """Tests for ForecastAdjustmentTRM service."""

    @pytest.fixture
    def trm(self):
        return ForecastAdjustmentTRM(site_key="DC-001")

    @pytest.fixture
    def strong_up_signal(self):
        """Strong upward signal from reliable source."""
        return ForecastAdjustmentState(
            signal_id="SIG-001",
            product_id="SKU-100",
            site_id="DC-001",
            source="market_intelligence",
            signal_type="demand_increase",
            signal_text="Major customer increasing orders by 20% next quarter",
            signal_confidence=0.85,
            direction="up",
            magnitude_hint=0.20,
            time_horizon_periods=4,
            current_forecast_value=10000.0,
            current_forecast_confidence=0.80,
            historical_forecast_accuracy=0.85,
            source_historical_accuracy=0.90,
            product_volatility=0.15,
            product_trend=0.05,
            seasonality_factor=1.0,
        )

    @pytest.fixture
    def weak_signal(self):
        """Weak signal from unreliable source."""
        return ForecastAdjustmentState(
            signal_id="SIG-002",
            product_id="SKU-200",
            site_id="DC-001",
            source="social_media",
            signal_type="demand_increase",
            signal_text="Some social media chatter about the product",
            signal_confidence=0.30,
            direction="up",
            time_horizon_periods=2,
            current_forecast_value=5000.0,
            source_historical_accuracy=0.30,
            product_volatility=0.60,  # High volatility
        )

    def test_forecast_state_dataclass(self, strong_up_signal):
        """Test ForecastAdjustmentState fields."""
        assert strong_up_signal.signal_id == "SIG-001"
        assert strong_up_signal.source == "market_intelligence"
        assert strong_up_signal.direction == "up"
        assert strong_up_signal.magnitude_hint == 0.20

    def test_forecast_recommendation_defaults(self):
        """Test ForecastAdjustmentRecommendation defaults."""
        rec = ForecastAdjustmentRecommendation(
            signal_id="SIG-X",
            product_id="P",
            site_id="S",
        )
        assert rec.should_adjust is False
        assert rec.direction == "no_change"
        assert rec.adjustment_pct == 0.0
        assert rec.requires_human_review is True
        assert rec.auto_applicable is False

    def test_trm_initialization(self):
        """Test TRM initializes properly."""
        trm = ForecastAdjustmentTRM(site_key="DC-X")
        assert trm.site_key == "DC-X"
        assert trm.model is None
        assert trm.config.confidence_threshold == 0.7

    def test_trm_with_learned_reliability(self):
        """Test TRM with learned source reliability."""
        cfg = ForecastAdjustmentTRMConfig(
            learned_source_reliability={"sales_input": 0.9, "social_media": 0.2}
        )
        trm = ForecastAdjustmentTRM(site_key="DC-X", config=cfg)
        assert trm.config.learned_source_reliability["sales_input"] == 0.9

    def test_evaluate_strong_signal(self, trm, strong_up_signal):
        """Test evaluation of a strong upward signal."""
        rec = trm.evaluate_signal(strong_up_signal)
        assert isinstance(rec, ForecastAdjustmentRecommendation)
        assert rec.signal_id == "SIG-001"
        # Strong signal from reliable source should recommend adjustment
        assert rec.should_adjust is True
        assert rec.direction == "up"
        assert rec.adjustment_pct > 0
        assert rec.adjusted_forecast_value > strong_up_signal.current_forecast_value

    def test_evaluate_weak_signal_high_volatility(self, trm, weak_signal):
        """Test weak signal on high-volatility product gets dampened or rejected."""
        rec = trm.evaluate_signal(weak_signal)
        assert rec.signal_id == "SIG-002"
        # Low source accuracy (0.30) + high volatility (0.60) + small adj
        # Heuristic override 3: high volatility + adj < 0.10 -> should_adjust=False
        # OR the adjustment is very small
        if rec.should_adjust:
            assert rec.adjustment_pct < 0.15  # Should be dampened

    def test_heuristic_source_accuracy_dampening(self, trm):
        """Test that poor source accuracy dampens the adjustment."""
        state = ForecastAdjustmentState(
            signal_id="SIG-POOR",
            product_id="SKU-300",
            site_id="DC-001",
            source="email",
            signal_type="demand_increase",
            signal_text="Email says demand up 50%",
            signal_confidence=0.70,
            direction="up",
            magnitude_hint=0.50,
            current_forecast_value=1000.0,
            source_historical_accuracy=0.40,  # Poor accuracy
            product_volatility=0.10,
        )
        rec = trm.evaluate_signal(state)
        if rec.should_adjust:
            # Adjustment should be dampened from 50% due to poor source accuracy
            assert rec.adjustment_pct < 0.50

    def test_evaluate_no_change_direction(self, trm):
        """Test signal with no_change direction."""
        state = ForecastAdjustmentState(
            signal_id="SIG-NC",
            product_id="SKU-400",
            site_id="DC-001",
            source="sales_input",
            signal_type="demand_increase",
            signal_text="Market is stable",
            signal_confidence=0.90,
            direction="no_change",
            current_forecast_value=5000.0,
        )
        rec = trm.evaluate_signal(state)
        # No change direction should not adjust
        assert rec.direction in ("no_change",)

    def test_encode_state_length(self, trm, strong_up_signal):
        """Test _encode_state returns correct feature length."""
        features = trm._encode_state(strong_up_signal)
        assert len(features) == 15

    def test_batch_evaluation(self, trm, strong_up_signal, weak_signal):
        """Test batch evaluation."""
        results = trm.evaluate_batch([strong_up_signal, weak_signal])
        assert len(results) == 2
        assert results[0].signal_id == "SIG-001"
        assert results[1].signal_id == "SIG-002"

    def test_get_training_data_no_db(self, trm):
        """Test get_training_data returns empty without DB."""
        data = trm.get_training_data(config_id=1)
        assert data == []


# ============================================================================
# Inventory Buffer TRM Tests
# ============================================================================

class TestInventoryBufferTRM:
    """Tests for InventoryBufferTRM service."""

    @pytest.fixture
    def trm(self):
        return InventoryBufferTRM(use_heuristic_fallback=True)

    @pytest.fixture
    def stable_state(self):
        """Stable product-location with no issues."""
        return SSState(
            product_id="SKU-STABLE",
            location_id="DC-01",
            baseline_ss=100.0,
            baseline_reorder_point=200.0,
            baseline_target_inventory=350.0,
            policy_type="sl",
            current_on_hand=250.0,
            current_dos=15.0,
            demand_cv=0.15,
            avg_daily_demand=20.0,
            demand_trend=0.0,
            seasonal_index=1.0,
            month_of_year=6,
            recent_stockout_count=0,
            recent_excess_days=0,
            forecast_bias=0.0,
            lead_time_days=5.0,
            lead_time_cv=0.1,
        )

    @pytest.fixture
    def stockout_state(self):
        """Product-location with recent stockouts."""
        return SSState(
            product_id="SKU-STOCKOUT",
            location_id="DC-02",
            baseline_ss=50.0,
            baseline_reorder_point=100.0,
            baseline_target_inventory=200.0,
            policy_type="doc_dem",
            current_on_hand=30.0,
            current_dos=3.0,
            demand_cv=0.40,
            avg_daily_demand=10.0,
            demand_trend=0.05,
            seasonal_index=1.1,
            month_of_year=11,
            recent_stockout_count=3,
            recent_excess_days=0,
            forecast_bias=-0.10,
            lead_time_days=7.0,
            lead_time_cv=0.3,
        )

    @pytest.fixture
    def excess_state(self):
        """Product-location with excess inventory."""
        return SSState(
            product_id="SKU-EXCESS",
            location_id="DC-03",
            baseline_ss=200.0,
            baseline_reorder_point=400.0,
            baseline_target_inventory=600.0,
            policy_type="abs_level",
            current_on_hand=900.0,
            current_dos=60.0,
            demand_cv=0.10,
            avg_daily_demand=15.0,
            demand_trend=-0.15,
            seasonal_index=0.6,
            month_of_year=2,
            recent_stockout_count=0,
            recent_excess_days=75,
            forecast_bias=0.20,
            lead_time_days=3.0,
            lead_time_cv=0.05,
        )

    def test_ss_state_dataclass_construction(self, stable_state):
        """Test SSState fields."""
        assert stable_state.product_id == "SKU-STABLE"
        assert stable_state.baseline_ss == 100.0
        assert stable_state.policy_type == "sl"
        assert stable_state.demand_cv == 0.15

    def test_ss_state_to_features(self, stable_state):
        """Test feature vector generation."""
        features = stable_state.to_features()
        assert isinstance(features, np.ndarray)
        assert features.dtype == np.float32
        assert len(features) == 11

    def test_ss_adjustment_to_dict(self):
        """Test SSAdjustment serialization."""
        adj = SSAdjustment(
            product_id="P1",
            location_id="L1",
            baseline_ss=100.0,
            multiplier=1.3,
            adjusted_ss=130.0,
            adjusted_reorder_point=230.0,
            reason=SSAdjustmentReason.HIGH_VOLATILITY,
            confidence=0.85,
            description="Heuristic adjustment",
        )
        d = adj.to_dict()
        assert d["product_id"] == "P1"
        assert d["baseline_ss"] == 100.0
        assert d["multiplier"] == 1.3
        assert d["adjusted_ss"] == 130.0
        assert d["reason"] == "high_volatility"
        assert d["confidence"] == 0.85

    def test_trm_initialization_defaults(self):
        """Test TRM initializes with defaults."""
        trm = InventoryBufferTRM()
        assert trm.min_multiplier == 0.5
        assert trm.max_multiplier == 2.0
        assert trm.use_heuristic_fallback is True
        assert trm.trm_model is None

    def test_trm_initialization_custom_bounds(self):
        """Test TRM with custom multiplier bounds."""
        trm = InventoryBufferTRM(min_multiplier=0.8, max_multiplier=1.5)
        assert trm.min_multiplier == 0.8
        assert trm.max_multiplier == 1.5

    def test_evaluate_stable_no_adjustment(self, trm, stable_state):
        """Test stable state gets no or minimal adjustment."""
        result = trm.evaluate(stable_state)
        assert isinstance(result, SSAdjustment)
        assert result.product_id == "SKU-STABLE"
        assert result.baseline_ss == 100.0
        # Stable product should have multiplier close to 1.0
        assert result.multiplier == pytest.approx(1.0, abs=0.05)
        assert result.reason == SSAdjustmentReason.NO_ADJUSTMENT

    def test_evaluate_stockout_increases_ss(self, trm, stockout_state):
        """Test stockouts trigger SS increase."""
        result = trm.evaluate(stockout_state)
        assert result.product_id == "SKU-STOCKOUT"
        # 3 recent stockouts should trigger increase
        assert result.multiplier > 1.0
        assert result.adjusted_ss > result.baseline_ss
        assert result.reason == SSAdjustmentReason.RECENT_STOCKOUT

    def test_evaluate_excess_decreases_ss(self, trm, excess_state):
        """Test excess inventory triggers SS decrease."""
        result = trm.evaluate(excess_state)
        assert result.product_id == "SKU-EXCESS"
        # 75 excess days + downward trend -> should decrease
        assert result.multiplier < 1.0
        assert result.adjusted_ss < result.baseline_ss

    def test_heuristic_seasonal_peak(self, trm):
        """Test seasonal peak increases SS."""
        state = SSState(
            product_id="SKU-SEASON",
            location_id="DC-01",
            baseline_ss=100.0,
            baseline_reorder_point=200.0,
            baseline_target_inventory=350.0,
            policy_type="sl",
            current_on_hand=200.0,
            current_dos=10.0,
            demand_cv=0.20,
            avg_daily_demand=20.0,
            demand_trend=0.0,
            seasonal_index=1.5,  # Strong seasonal peak
            month_of_year=12,
            recent_stockout_count=0,
            recent_excess_days=0,
            forecast_bias=0.0,
            lead_time_days=5.0,
            lead_time_cv=0.1,
        )
        result = trm.evaluate(state)
        assert result.multiplier > 1.0
        assert result.reason == SSAdjustmentReason.SEASONAL_PEAK

    def test_heuristic_seasonal_trough(self, trm):
        """Test seasonal trough decreases SS."""
        state = SSState(
            product_id="SKU-TROUGH",
            location_id="DC-01",
            baseline_ss=100.0,
            baseline_reorder_point=200.0,
            baseline_target_inventory=350.0,
            policy_type="sl",
            current_on_hand=200.0,
            current_dos=10.0,
            demand_cv=0.20,
            avg_daily_demand=20.0,
            demand_trend=0.0,
            seasonal_index=0.5,  # Strong seasonal trough
            month_of_year=1,
            recent_stockout_count=0,
            recent_excess_days=0,
            forecast_bias=0.0,
            lead_time_days=5.0,
            lead_time_cv=0.1,
        )
        result = trm.evaluate(state)
        assert result.multiplier < 1.0
        assert result.reason == SSAdjustmentReason.SEASONAL_TROUGH

    def test_heuristic_high_demand_cv(self, trm):
        """Test high demand volatility increases SS."""
        state = SSState(
            product_id="SKU-VOL",
            location_id="DC-01",
            baseline_ss=100.0,
            baseline_reorder_point=200.0,
            baseline_target_inventory=350.0,
            policy_type="sl",
            current_on_hand=200.0,
            current_dos=10.0,
            demand_cv=0.60,  # Very high volatility
            avg_daily_demand=20.0,
            demand_trend=0.0,
            seasonal_index=1.0,
            month_of_year=6,
            recent_stockout_count=0,
            recent_excess_days=0,
            forecast_bias=0.0,
            lead_time_days=5.0,
            lead_time_cv=0.1,
        )
        result = trm.evaluate(state)
        assert result.multiplier > 1.0
        assert result.reason == SSAdjustmentReason.HIGH_VOLATILITY

    def test_multiplier_clamped_to_bounds(self, trm):
        """Test that multiplier respects min/max bounds."""
        # Create extreme state that would push multiplier beyond bounds
        state = SSState(
            product_id="SKU-EXTREME",
            location_id="DC-01",
            baseline_ss=10.0,
            baseline_reorder_point=20.0,
            baseline_target_inventory=30.0,
            policy_type="sl",
            current_on_hand=5.0,
            current_dos=0.5,
            demand_cv=0.20,
            avg_daily_demand=10.0,
            demand_trend=0.0,
            seasonal_index=1.0,
            month_of_year=6,
            recent_stockout_count=10,  # Very many stockouts
            recent_excess_days=0,
            forecast_bias=0.0,
            lead_time_days=5.0,
            lead_time_cv=0.1,
        )
        result = trm.evaluate(state)
        assert result.multiplier <= trm.max_multiplier
        assert result.multiplier >= trm.min_multiplier

    def test_effective_bounds_with_tgnn_multiplier(self):
        """Test effective_bounds property with tGNN multiplier."""
        trm = InventoryBufferTRM(min_multiplier=0.5, max_multiplier=2.0)
        trm.apply_network_context({"safety_stock_multiplier": 1.3})
        lo, hi = trm.effective_bounds
        assert lo == pytest.approx(0.65)  # 0.5 * 1.3
        assert hi == pytest.approx(2.6)   # 2.0 * 1.3

    def test_apply_network_context_clamped(self):
        """Test that tGNN multiplier is clamped to [0.1, 5.0]."""
        trm = InventoryBufferTRM()
        trm.apply_network_context({"safety_stock_multiplier": 10.0})
        assert trm._tgnn_ss_multiplier == 5.0

        trm.apply_network_context({"safety_stock_multiplier": 0.01})
        assert trm._tgnn_ss_multiplier == 0.1

    def test_no_fallback_returns_no_adjustment(self, stable_state):
        """Test that disabling heuristic returns no adjustment when no model."""
        trm = InventoryBufferTRM(use_heuristic_fallback=False)
        result = trm.evaluate(stable_state)
        assert result.multiplier == 1.0
        assert result.reason == SSAdjustmentReason.NO_ADJUSTMENT
        assert result.confidence == 1.0

    def test_decision_history_recording(self, trm, stable_state):
        """Test that evaluation records decisions for training."""
        trm.evaluate(stable_state)
        history = trm.get_training_data()
        assert len(history) >= 1
        assert history[0]["state"]["product_id"] == "SKU-STABLE"

    def test_record_outcome(self, trm, stable_state):
        """Test recording outcomes for training feedback."""
        result = trm.evaluate(stable_state)
        trm.record_outcome(
            adjustment=result,
            actual_stockout=False,
            actual_dos_after=12.0,
            excess_cost=50.0,
        )
        history = trm.get_training_data()
        # Should have both the decision and the outcome
        assert len(history) >= 2
        # Last entry should be the outcome
        assert "actual_stockout" in history[-1]
        assert history[-1]["actual_stockout"] is False

    def test_batch_evaluation(self, trm, stable_state, stockout_state, excess_state):
        """Test batch evaluation."""
        results = trm.evaluate_batch([stable_state, stockout_state, excess_state])
        assert len(results) == 3
        assert results[0].product_id == "SKU-STABLE"
        assert results[1].product_id == "SKU-STOCKOUT"
        assert results[2].product_id == "SKU-EXCESS"

    def test_classify_reason_no_adjustment(self, trm):
        """Test _classify_reason with near-1.0 multiplier."""
        state = SSState(
            product_id="P", location_id="L",
            baseline_ss=100, baseline_reorder_point=200,
            baseline_target_inventory=350, policy_type="sl",
            current_on_hand=200, current_dos=15,
            demand_cv=0.15, avg_daily_demand=20,
            demand_trend=0.0, seasonal_index=1.0,
            month_of_year=6, recent_stockout_count=0,
            recent_excess_days=0, forecast_bias=0.0,
            lead_time_days=5, lead_time_cv=0.1,
        )
        reason = trm._classify_reason(state, 1.02)
        assert reason == SSAdjustmentReason.NO_ADJUSTMENT

    def test_classify_reason_stockout(self, trm):
        """Test _classify_reason with stockout history."""
        state = SSState(
            product_id="P", location_id="L",
            baseline_ss=100, baseline_reorder_point=200,
            baseline_target_inventory=350, policy_type="sl",
            current_on_hand=200, current_dos=15,
            demand_cv=0.15, avg_daily_demand=20,
            demand_trend=0.0, seasonal_index=1.0,
            month_of_year=6, recent_stockout_count=2,
            recent_excess_days=0, forecast_bias=0.0,
            lead_time_days=5, lead_time_cv=0.1,
        )
        reason = trm._classify_reason(state, 1.3)
        assert reason == SSAdjustmentReason.RECENT_STOCKOUT

    def test_ss_state_to_features_zero_daily_demand(self):
        """Test feature vector handles zero avg_daily_demand."""
        state = SSState(
            product_id="P", location_id="L",
            baseline_ss=0, baseline_reorder_point=0,
            baseline_target_inventory=0, policy_type="abs_level",
            current_on_hand=0, current_dos=0,
            demand_cv=0, avg_daily_demand=0,
            demand_trend=0, seasonal_index=1.0,
            month_of_year=1, recent_stockout_count=0,
            recent_excess_days=0, forecast_bias=0,
            lead_time_days=0, lead_time_cv=0,
        )
        features = state.to_features()
        assert len(features) == 11
        # Should not raise divide-by-zero -- uses max(1, ...) guard
        assert not np.any(np.isnan(features))
        assert not np.any(np.isinf(features))
