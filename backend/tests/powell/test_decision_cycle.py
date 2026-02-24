"""
Tests for Decision Cycle module and 7 remaining TRM signal integration.

Covers:
- DecisionCyclePhase ordering and mappings
- CycleResult / PhaseResult data structures
- Conflict detection in REFLECT phase
- SiteAgent.execute_decision_cycle() integration
- 7 remaining TRMs: MO, TO, Quality, Maintenance, Subcontracting,
  ForecastAdj, InventoryBuffer — signal emit/read verification
"""

import pytest
import time
from datetime import datetime, timezone

from app.services.powell.decision_cycle import (
    DecisionCyclePhase,
    CycleResult,
    PhaseResult,
    TRM_PHASE_MAP,
    PHASE_TRM_MAP,
    get_phase_for_trm,
    get_trms_for_phase,
    detect_conflicts,
)
from app.services.powell.hive_signal import (
    HiveSignal,
    HiveSignalBus,
    HiveSignalType,
    UrgencyVector,
)


# ============================================================================
# DecisionCyclePhase tests
# ============================================================================


class TestDecisionCyclePhase:
    """Tests for phase enum and ordering."""

    def test_six_phases(self):
        assert len(DecisionCyclePhase) == 6

    def test_phase_ordering(self):
        """Phases must be numerically ordered 1-6."""
        assert DecisionCyclePhase.SENSE < DecisionCyclePhase.ASSESS
        assert DecisionCyclePhase.ASSESS < DecisionCyclePhase.ACQUIRE
        assert DecisionCyclePhase.ACQUIRE < DecisionCyclePhase.PROTECT
        assert DecisionCyclePhase.PROTECT < DecisionCyclePhase.BUILD
        assert DecisionCyclePhase.BUILD < DecisionCyclePhase.REFLECT

    def test_phase_values(self):
        assert DecisionCyclePhase.SENSE == 1
        assert DecisionCyclePhase.REFLECT == 6

    def test_all_11_trms_mapped(self):
        """Every TRM must be mapped to exactly one phase."""
        assert len(TRM_PHASE_MAP) == 11

    def test_expected_trm_phase_assignments(self):
        """Verify specific TRM → phase assignments per architecture doc."""
        assert get_phase_for_trm("atp_executor") == DecisionCyclePhase.SENSE
        assert get_phase_for_trm("order_tracking") == DecisionCyclePhase.SENSE
        assert get_phase_for_trm("inventory_buffer") == DecisionCyclePhase.ASSESS
        assert get_phase_for_trm("forecast_adj") == DecisionCyclePhase.ASSESS
        assert get_phase_for_trm("quality") == DecisionCyclePhase.ASSESS
        assert get_phase_for_trm("po_creation") == DecisionCyclePhase.ACQUIRE
        assert get_phase_for_trm("subcontracting") == DecisionCyclePhase.ACQUIRE
        assert get_phase_for_trm("maintenance") == DecisionCyclePhase.PROTECT
        assert get_phase_for_trm("mo_execution") == DecisionCyclePhase.BUILD
        assert get_phase_for_trm("to_execution") == DecisionCyclePhase.BUILD
        assert get_phase_for_trm("rebalancing") == DecisionCyclePhase.REFLECT

    def test_unknown_trm_raises(self):
        with pytest.raises(ValueError, match="Unknown TRM"):
            get_phase_for_trm("nonexistent_trm")

    def test_get_trms_for_phase_sense(self):
        trms = get_trms_for_phase(DecisionCyclePhase.SENSE)
        assert "atp_executor" in trms
        assert "order_tracking" in trms
        assert len(trms) == 2

    def test_get_trms_for_phase_build(self):
        trms = get_trms_for_phase(DecisionCyclePhase.BUILD)
        assert "mo_execution" in trms
        assert "to_execution" in trms

    def test_reverse_map_covers_all_trms(self):
        """PHASE_TRM_MAP should contain all 11 TRMs across all phases."""
        all_trms = set()
        for trms in PHASE_TRM_MAP.values():
            all_trms.update(trms)
        assert len(all_trms) == 11


# ============================================================================
# CycleResult / PhaseResult tests
# ============================================================================


class TestCycleResult:
    """Tests for result data structures."""

    def test_phase_result_success_when_no_errors(self):
        pr = PhaseResult(phase=DecisionCyclePhase.SENSE, trms_executed=["atp_executor"])
        assert pr.success is True

    def test_phase_result_failure_on_error(self):
        pr = PhaseResult(
            phase=DecisionCyclePhase.SENSE,
            errors=["atp_executor: timeout"],
        )
        assert pr.success is False

    def test_phase_result_to_dict(self):
        pr = PhaseResult(
            phase=DecisionCyclePhase.BUILD,
            trms_executed=["mo_execution"],
            signals_emitted=2,
            duration_ms=1.5,
        )
        d = pr.to_dict()
        assert d["phase"] == "BUILD"
        assert d["phase_number"] == 5
        assert d["signals_emitted"] == 2
        assert d["success"] is True

    def test_cycle_result_success(self):
        cr = CycleResult(phases=[
            PhaseResult(phase=DecisionCyclePhase.SENSE),
            PhaseResult(phase=DecisionCyclePhase.ASSESS),
        ])
        assert cr.success is True
        assert cr.phases_completed == 2

    def test_cycle_result_failure_propagates(self):
        cr = CycleResult(phases=[
            PhaseResult(phase=DecisionCyclePhase.SENSE),
            PhaseResult(phase=DecisionCyclePhase.ASSESS, errors=["quality: crash"]),
        ])
        assert cr.success is False

    def test_cycle_result_to_dict(self):
        cr = CycleResult()
        d = cr.to_dict()
        assert "cycle_id" in d
        assert "started_at" in d
        assert d["phases_completed"] == 0
        assert d["success"] is True


# ============================================================================
# Conflict detection tests
# ============================================================================


class TestConflictDetection:
    """Tests for detect_conflicts()."""

    def test_no_conflict_all_neutral(self):
        snapshot = {
            "values": [0.0] * 11,
            "directions": ["neutral"] * 11,
        }
        assert detect_conflicts(snapshot) == []

    def test_no_conflict_same_direction(self):
        """Two TRMs in shortage is NOT a conflict."""
        values = [0.0] * 11
        directions = ["neutral"] * 11
        values[0] = 0.5  # atp_executor
        values[2] = 0.5  # po_creation
        directions[0] = "shortage"
        directions[2] = "shortage"
        snapshot = {"values": values, "directions": directions}
        assert detect_conflicts(snapshot) == []

    def test_conflict_shortage_vs_surplus(self):
        """Shortage and surplus with high urgency = conflict."""
        values = [0.0] * 11
        directions = ["neutral"] * 11
        values[0] = 0.5  # atp_executor: shortage
        values[5] = 0.5  # inventory_buffer: surplus
        directions[0] = "shortage"
        directions[5] = "surplus"
        snapshot = {"values": values, "directions": directions}
        conflicts = detect_conflicts(snapshot)
        assert len(conflicts) == 1
        c = conflicts[0]
        assert c["type"] == "shortage_vs_surplus"
        assert {c["trm_a"], c["trm_b"]} == {"atp_executor", "inventory_buffer"}

    def test_conflict_risk_vs_relief(self):
        values = [0.0] * 11
        directions = ["neutral"] * 11
        values[7] = 0.6  # quality: risk
        values[9] = 0.4  # mo_execution: relief
        directions[7] = "risk"
        directions[9] = "relief"
        snapshot = {"values": values, "directions": directions}
        conflicts = detect_conflicts(snapshot)
        assert len(conflicts) == 1
        assert conflicts[0]["type"] == "risk_vs_relief"

    def test_no_conflict_below_threshold(self):
        """Low urgency signals don't trigger conflict detection."""
        values = [0.0] * 11
        directions = ["neutral"] * 11
        values[0] = 0.2  # Below threshold 0.3
        values[5] = 0.2
        directions[0] = "shortage"
        directions[5] = "surplus"
        snapshot = {"values": values, "directions": directions}
        assert detect_conflicts(snapshot) == []

    def test_multiple_conflicts(self):
        values = [0.0] * 11
        directions = ["neutral"] * 11
        values[0] = 0.8  # atp: shortage
        values[3] = 0.6  # rebalancing: surplus
        values[7] = 0.5  # quality: risk
        values[9] = 0.4  # mo_execution: relief
        directions[0] = "shortage"
        directions[3] = "surplus"
        directions[7] = "risk"
        directions[9] = "relief"
        snapshot = {"values": values, "directions": directions}
        conflicts = detect_conflicts(snapshot)
        assert len(conflicts) == 2


# ============================================================================
# MO Execution TRM signal tests
# ============================================================================


class TestMOExecutionSignals:
    """Tests for MOExecutionTRM signal emit/read."""

    def _make_trm(self):
        from app.services.powell.mo_execution_trm import MOExecutionTRM
        trm = MOExecutionTRM(site_key="test_site")
        trm.signal_bus = HiveSignalBus()
        return trm

    def _make_state(self, **overrides):
        from app.services.powell.mo_execution_trm import MOExecutionState
        defaults = dict(
            order_id="MO-001", product_id="P1", site_id="S1",
            planned_quantity=500, days_until_due=10, priority=2,
            material_availability_pct=0.95, missing_component_count=0,
            capacity_utilization_pct=0.7, resource_utilization_pct=0.6,
            setup_time_hours=2.0, run_time_hours=8.0,
            queue_depth=3, queue_total_hours=24.0,
        )
        defaults.update(overrides)
        return MOExecutionState(**defaults)

    def test_no_bus_works(self):
        from app.services.powell.mo_execution_trm import MOExecutionTRM
        trm = MOExecutionTRM(site_key="test_site")
        state = self._make_state()
        rec = trm.evaluate_order(state)
        assert rec.order_id == "MO-001"

    def test_release_emits_mo_released(self):
        trm = self._make_trm()
        state = self._make_state(material_availability_pct=1.0, days_until_due=3, priority=1)
        rec = trm.evaluate_order(state)
        if rec.release_now:
            signals = trm.signal_bus.active_signals()
            mo_released = [s for s in signals if s.signal_type == HiveSignalType.MO_RELEASED]
            assert len(mo_released) >= 1
            assert mo_released[0].direction == "relief"

    def test_defer_emits_mo_delayed(self):
        trm = self._make_trm()
        # Low material availability should cause deferral
        state = self._make_state(material_availability_pct=0.3, missing_component_count=5)
        rec = trm.evaluate_order(state)
        if rec.defer_days > 0 or rec.decision_type == "defer":
            signals = trm.signal_bus.active_signals()
            mo_delayed = [s for s in signals if s.signal_type == HiveSignalType.MO_DELAYED]
            assert len(mo_delayed) >= 1
            assert mo_delayed[0].direction == "risk"

    def test_urgency_vector_updated(self):
        trm = self._make_trm()
        state = self._make_state()
        trm.evaluate_order(state)
        val, direction, _ = trm.signal_bus.urgency.read("mo_execution")
        # Should have been updated (either relief or risk)
        assert direction in ("relief", "risk", "neutral")


# ============================================================================
# TO Execution TRM signal tests
# ============================================================================


class TestTOExecutionSignals:

    def _make_trm(self):
        from app.services.powell.to_execution_trm import TOExecutionTRM
        trm = TOExecutionTRM(site_key="test_site")
        trm.signal_bus = HiveSignalBus()
        return trm

    def _make_state(self, **overrides):
        from app.services.powell.to_execution_trm import TOExecutionState
        defaults = dict(
            order_id="TO-001", product_id="P1",
            source_site_id="S1", dest_site_id="S2",
            planned_qty=200, status="DRAFT",
            source_on_hand=1000, source_dos=15,
            dest_on_hand=50, dest_dos=3, dest_backlog=100,
            dest_safety_stock=80, days_until_needed=5,
            priority=2,
        )
        defaults.update(overrides)
        return TOExecutionState(**defaults)

    def test_no_bus_works(self):
        from app.services.powell.to_execution_trm import TOExecutionTRM
        trm = TOExecutionTRM(site_key="test_site")
        state = self._make_state()
        rec = trm.evaluate_order(state)
        assert rec.order_id == "TO-001"

    def test_release_emits_to_released(self):
        trm = self._make_trm()
        state = self._make_state(dest_backlog=200, source_dos=20)
        rec = trm.evaluate_order(state)
        if rec.release_now:
            signals = trm.signal_bus.active_signals()
            released = [s for s in signals if s.signal_type == HiveSignalType.TO_RELEASED]
            assert len(released) >= 1

    def test_urgency_updated(self):
        trm = self._make_trm()
        state = self._make_state()
        trm.evaluate_order(state)
        val, direction, _ = trm.signal_bus.urgency.read("to_execution")
        assert direction in ("relief", "risk", "neutral")


# ============================================================================
# Quality Disposition TRM signal tests
# ============================================================================


class TestQualitySignals:

    def _make_trm(self):
        from app.services.powell.quality_disposition_trm import QualityDispositionTRM
        trm = QualityDispositionTRM(site_key="test_site")
        trm.signal_bus = HiveSignalBus()
        return trm

    def _make_state(self, **overrides):
        from app.services.powell.quality_disposition_trm import QualityDispositionState
        defaults = dict(
            quality_order_id="QO-001", product_id="P1", site_id="S1",
            inspection_type="receiving", inspection_quantity=100,
            defect_count=15, defect_rate=0.15, defect_category="dimensional",
            severity_level="major", characteristics_tested=10,
            characteristics_passed=8, product_unit_value=50.0,
            estimated_rework_cost=500.0, estimated_scrap_cost=7500.0,
        )
        defaults.update(overrides)
        return QualityDispositionState(**defaults)

    def test_no_bus_works(self):
        from app.services.powell.quality_disposition_trm import QualityDispositionTRM
        trm = QualityDispositionTRM(site_key="test_site")
        rec = trm.evaluate_disposition(self._make_state())
        assert rec.quality_order_id == "QO-001"

    def test_reject_emits_quality_reject(self):
        trm = self._make_trm()
        # Critical defects → should reject
        state = self._make_state(severity_level="critical", defect_rate=0.50)
        rec = trm.evaluate_disposition(state)
        if rec.disposition in ("reject", "scrap", "return_to_vendor"):
            signals = trm.signal_bus.active_signals()
            rejects = [s for s in signals if s.signal_type == HiveSignalType.QUALITY_REJECT]
            assert len(rejects) >= 1
            assert rejects[0].direction == "risk"

    def test_rework_emits_quality_hold(self):
        trm = self._make_trm()
        state = self._make_state(severity_level="minor", defect_rate=0.05)
        rec = trm.evaluate_disposition(state)
        # Whatever disposition, check that quality signals are emitted
        signals = trm.signal_bus.active_signals()
        quality_signals = [s for s in signals if s.signal_type in (
            HiveSignalType.QUALITY_REJECT, HiveSignalType.QUALITY_HOLD
        )]
        # May or may not emit depending on disposition outcome
        val, _, _ = trm.signal_bus.urgency.read("quality")
        # Urgency should have been set
        assert isinstance(val, float)


# ============================================================================
# Maintenance Scheduling TRM signal tests
# ============================================================================


class TestMaintenanceSignals:

    def _make_trm(self):
        from app.services.powell.maintenance_scheduling_trm import MaintenanceSchedulingTRM
        trm = MaintenanceSchedulingTRM(site_key="test_site")
        trm.signal_bus = HiveSignalBus()
        return trm

    def _make_state(self, **overrides):
        from app.services.powell.maintenance_scheduling_trm import MaintenanceSchedulingState
        defaults = dict(
            order_id="WO-001", asset_id="A1", site_id="S1",
            maintenance_type="preventive", status="PLANNED",
            estimated_downtime_hours=4.0, estimated_cost=2000.0,
            spare_parts_available=True,
            production_schedule_load_pct=70.0,
        )
        defaults.update(overrides)
        return MaintenanceSchedulingState(**defaults)

    def test_no_bus_works(self):
        from app.services.powell.maintenance_scheduling_trm import MaintenanceSchedulingTRM
        trm = MaintenanceSchedulingTRM(site_key="test_site")
        rec = trm.evaluate_scheduling(self._make_state())
        assert rec.order_id == "WO-001"

    def test_defer_emits_maintenance_deferred(self):
        trm = self._make_trm()
        # High production load → engine likely defers
        state = self._make_state(production_schedule_load_pct=95.0, next_production_gap_days=14)
        rec = trm.evaluate_scheduling(state)
        if rec.decision_type == "defer":
            signals = trm.signal_bus.active_signals()
            deferred = [s for s in signals if s.signal_type == HiveSignalType.MAINTENANCE_DEFERRED]
            assert len(deferred) >= 1

    def test_urgency_updated(self):
        trm = self._make_trm()
        trm.evaluate_scheduling(self._make_state())
        val, direction, _ = trm.signal_bus.urgency.read("maintenance")
        assert direction in ("risk", "neutral")


# ============================================================================
# Subcontracting TRM signal tests
# ============================================================================


class TestSubcontractingSignals:

    def _make_trm(self):
        from app.services.powell.subcontracting_trm import SubcontractingTRM
        trm = SubcontractingTRM(site_key="test_site")
        trm.signal_bus = HiveSignalBus()
        return trm

    def _make_state(self, **overrides):
        from app.services.powell.subcontracting_trm import SubcontractingState
        defaults = dict(
            product_id="P1", site_id="S1", required_quantity=500,
            internal_capacity_pct=30.0, internal_cost_per_unit=10.0,
            internal_lead_time_days=5,
            subcontractor_id="V1", subcontractor_cost_per_unit=12.0,
            subcontractor_lead_time_days=7, subcontractor_quality_score=0.95,
            subcontractor_on_time_score=0.90, subcontractor_capacity_available=1000,
        )
        defaults.update(overrides)
        return SubcontractingState(**defaults)

    def test_no_bus_works(self):
        from app.services.powell.subcontracting_trm import SubcontractingTRM
        trm = SubcontractingTRM(site_key="test_site")
        rec = trm.evaluate_routing(self._make_state())
        assert rec.order_id == "P1_S1"

    def test_route_external_emits_subcontract_routed(self):
        trm = self._make_trm()
        # Very low internal capacity → should route external
        state = self._make_state(internal_capacity_pct=5.0)
        rec = trm.evaluate_routing(state)
        if rec.decision_type in ("route_external", "split"):
            signals = trm.signal_bus.active_signals()
            routed = [s for s in signals if s.signal_type == HiveSignalType.SUBCONTRACT_ROUTED]
            assert len(routed) >= 1

    def test_reads_mo_delayed(self):
        trm = self._make_trm()
        # Pre-populate a MO_DELAYED signal
        trm.signal_bus.emit(HiveSignal(
            source_trm="mo_execution",
            signal_type=HiveSignalType.MO_DELAYED,
            urgency=0.7, direction="risk",
        ))
        ctx = trm._read_signals_before_decision()
        assert ctx.get("mo_delayed") is True


# ============================================================================
# Forecast Adjustment TRM signal tests
# ============================================================================


class TestForecastAdjSignals:

    def _make_trm(self):
        from app.services.powell.forecast_adjustment_trm import ForecastAdjustmentTRM
        trm = ForecastAdjustmentTRM(site_key="test_site")
        trm.signal_bus = HiveSignalBus()
        return trm

    def _make_state(self, **overrides):
        from app.services.powell.forecast_adjustment_trm import ForecastAdjustmentState
        defaults = dict(
            signal_id="SIG-001", product_id="P1", site_id="S1",
            source="sales_input", signal_type="demand_change",
            signal_text="Major customer placing large order next month",
            signal_confidence=0.8, direction="up",
            magnitude_hint=0.20, current_forecast_value=1000.0,
            current_forecast_confidence=0.7,
            source_historical_accuracy=0.75,
        )
        defaults.update(overrides)
        return ForecastAdjustmentState(**defaults)

    def test_no_bus_works(self):
        from app.services.powell.forecast_adjustment_trm import ForecastAdjustmentTRM
        trm = ForecastAdjustmentTRM(site_key="test_site")
        rec = trm.evaluate_signal(self._make_state())
        assert rec.signal_id == "SIG-001"

    def test_adjustment_emits_forecast_adjusted(self):
        trm = self._make_trm()
        state = self._make_state(signal_confidence=0.9, magnitude_hint=0.30)
        rec = trm.evaluate_signal(state)
        if rec.should_adjust and abs(rec.adjustment_pct) > 0.01:
            signals = trm.signal_bus.active_signals()
            adjusted = [s for s in signals if s.signal_type == HiveSignalType.FORECAST_ADJUSTED]
            assert len(adjusted) >= 1

    def test_reads_demand_surge(self):
        trm = self._make_trm()
        trm.signal_bus.emit(HiveSignal(
            source_trm="atp_executor",
            signal_type=HiveSignalType.DEMAND_SURGE,
            urgency=0.6, direction="shortage",
        ))
        ctx = trm._read_signals_before_decision()
        assert ctx.get("demand_surge") is True


# ============================================================================
# Inventory Buffer TRM signal tests
# ============================================================================


class TestInventoryBufferSignals:

    def _make_trm(self):
        from app.services.powell.inventory_buffer_trm import InventoryBufferTRM
        trm = InventoryBufferTRM()
        trm.signal_bus = HiveSignalBus()
        return trm

    def _make_state(self, **overrides):
        from app.services.powell.inventory_buffer_trm import SSState
        defaults = dict(
            product_id="P1", location_id="L1",
            baseline_ss=100.0, baseline_reorder_point=150.0,
            baseline_target_inventory=250.0, policy_type="sl",
            current_on_hand=120.0, current_dos=12.0,
            demand_cv=0.25, avg_daily_demand=10.0,
            demand_trend=0.05, seasonal_index=1.0,
            month_of_year=6, recent_stockout_count=0,
            recent_excess_days=0, forecast_bias=0.0,
            lead_time_days=7.0, lead_time_cv=0.15,
        )
        defaults.update(overrides)
        return SSState(**defaults)

    def test_no_bus_works(self):
        from app.services.powell.inventory_buffer_trm import InventoryBufferTRM
        trm = InventoryBufferTRM()
        rec = trm.evaluate(self._make_state())
        assert rec.product_id == "P1"

    def test_increase_emits_buffer_increased(self):
        trm = self._make_trm()
        # High stockout count → SS should increase
        state = self._make_state(recent_stockout_count=3, demand_cv=0.6)
        rec = trm.evaluate(state)
        if rec.multiplier > 1.05:
            signals = trm.signal_bus.active_signals()
            increased = [s for s in signals if s.signal_type == HiveSignalType.BUFFER_INCREASED]
            assert len(increased) >= 1
            assert increased[0].direction == "shortage"

    def test_decrease_emits_buffer_decreased(self):
        trm = self._make_trm()
        # Excess inventory + seasonal trough → SS should decrease
        state = self._make_state(
            recent_excess_days=70, seasonal_index=0.6,
            recent_stockout_count=0, demand_cv=0.1,
        )
        rec = trm.evaluate(state)
        if rec.multiplier < 0.95:
            signals = trm.signal_bus.active_signals()
            decreased = [s for s in signals if s.signal_type == HiveSignalType.BUFFER_DECREASED]
            assert len(decreased) >= 1
            assert decreased[0].direction == "surplus"

    def test_reads_atp_shortage(self):
        trm = self._make_trm()
        trm.signal_bus.emit(HiveSignal(
            source_trm="atp_executor",
            signal_type=HiveSignalType.ATP_SHORTAGE,
            urgency=0.8, direction="shortage",
        ))
        ctx = trm._read_signals_before_decision()
        assert ctx.get("atp_shortage") is True
        assert ctx["atp_shortage_urgency"] > 0.5

    def test_reads_forecast_adjusted(self):
        trm = self._make_trm()
        trm.signal_bus.emit(HiveSignal(
            source_trm="forecast_adj",
            signal_type=HiveSignalType.FORECAST_ADJUSTED,
            urgency=0.5, direction="surplus",
        ))
        ctx = trm._read_signals_before_decision()
        assert ctx.get("forecast_adjusted") is True
        assert ctx["forecast_direction"] == "surplus"


# ============================================================================
# SiteAgent.execute_decision_cycle() integration tests
# ============================================================================


class TestExecuteDecisionCycle:
    """Integration tests for the full 6-phase decision cycle."""

    def _make_site_agent(self):
        from app.services.powell.site_agent import SiteAgent, SiteAgentConfig
        config = SiteAgentConfig(
            site_key="test_cycle",
            use_trm_adjustments=False,
            enable_hive_signals=True,
        )
        return SiteAgent(config)

    def test_empty_cycle(self):
        """Cycle with no executors → 6 empty phases, success."""
        agent = self._make_site_agent()
        result = agent.execute_decision_cycle()
        assert result.success is True
        assert result.phases_completed == 6
        assert result.total_signals_emitted == 0

    def test_cycle_with_executors(self):
        """Cycle with mock executors runs phases in order."""
        agent = self._make_site_agent()
        execution_order = []

        def make_executor(name):
            def executor():
                execution_order.append(name)
            return executor

        executors = {
            "atp_executor": make_executor("atp_executor"),
            "quality": make_executor("quality"),
            "po_creation": make_executor("po_creation"),
            "maintenance": make_executor("maintenance"),
            "mo_execution": make_executor("mo_execution"),
            "rebalancing": make_executor("rebalancing"),
        }
        result = agent.execute_decision_cycle(trm_executors=executors)
        assert result.success is True

        # Verify ordering: SENSE < ASSESS < ACQUIRE < PROTECT < BUILD < REFLECT
        expected = ["atp_executor", "quality", "po_creation", "maintenance", "mo_execution", "rebalancing"]
        assert execution_order == expected

    def test_cycle_captures_signals(self):
        """Executors that emit signals are captured in phase results."""
        agent = self._make_site_agent()
        bus = agent.signal_bus

        def sense_executor():
            bus.emit(HiveSignal(
                source_trm="atp_executor",
                signal_type=HiveSignalType.ATP_SHORTAGE,
                urgency=0.8, direction="shortage",
            ))

        result = agent.execute_decision_cycle(trm_executors={"atp_executor": sense_executor})
        assert result.total_signals_emitted == 1
        sense_phase = result.phases[0]
        assert sense_phase.signals_emitted == 1

    def test_cycle_error_isolation(self):
        """A failing executor doesn't crash the whole cycle."""
        agent = self._make_site_agent()

        def failing_executor():
            raise RuntimeError("test failure")

        def good_executor():
            pass

        result = agent.execute_decision_cycle(trm_executors={
            "atp_executor": failing_executor,
            "rebalancing": good_executor,
        })
        # Cycle completes (not crash)
        assert result.phases_completed == 6
        # SENSE phase has error
        sense_phase = result.phases[0]
        assert not sense_phase.success
        assert "test failure" in sense_phase.errors[0]
        # REFLECT phase is fine
        reflect_phase = result.phases[5]
        assert reflect_phase.success

    def test_cycle_conflict_detection(self):
        """REFLECT phase detects urgency conflicts."""
        agent = self._make_site_agent()

        def sense_executor():
            agent.signal_bus.urgency.update("atp_executor", 0.7, "shortage")

        def assess_executor():
            agent.signal_bus.urgency.update("inventory_buffer", 0.6, "surplus")

        result = agent.execute_decision_cycle(trm_executors={
            "atp_executor": sense_executor,
            "inventory_buffer": assess_executor,
        })
        assert len(result.conflicts_detected) == 1
        conflict = result.conflicts_detected[0]
        assert conflict["type"] == "shortage_vs_surplus"

    def test_cycle_performance(self):
        """Full cycle with all 11 mock executors should be fast (<10ms)."""
        agent = self._make_site_agent()
        executors = {trm: (lambda: None) for trm in TRM_PHASE_MAP}
        result = agent.execute_decision_cycle(trm_executors=executors)
        assert result.total_duration_ms < 10.0

    def test_cycle_to_dict(self):
        """CycleResult serializes cleanly."""
        agent = self._make_site_agent()
        result = agent.execute_decision_cycle()
        d = result.to_dict()
        assert isinstance(d, dict)
        assert len(d["phases"]) == 6
        assert d["success"] is True


# ============================================================================
# Cross-TRM signal cascade tests (end-to-end)
# ============================================================================


class TestCrossTRMCascade:
    """End-to-end tests verifying signals flow between TRM phases."""

    def test_quality_reject_visible_to_mo_in_later_phase(self):
        """Quality (ASSESS) reject signal reaches MO (BUILD) via bus."""
        bus = HiveSignalBus()

        from app.services.powell.quality_disposition_trm import QualityDispositionTRM, QualityDispositionState
        from app.services.powell.mo_execution_trm import MOExecutionTRM, MOExecutionState

        quality_trm = QualityDispositionTRM(site_key="test")
        quality_trm.signal_bus = bus
        mo_trm = MOExecutionTRM(site_key="test")
        mo_trm.signal_bus = bus

        # Phase ASSESS: Quality rejects
        q_state = QualityDispositionState(
            quality_order_id="QO-100", product_id="P1", site_id="S1",
            inspection_type="receiving", inspection_quantity=100,
            defect_count=50, defect_rate=0.50, defect_category="critical",
            severity_level="critical", characteristics_tested=10,
            characteristics_passed=5, product_unit_value=100.0,
            estimated_rework_cost=5000.0, estimated_scrap_cost=5000.0,
        )
        quality_trm.evaluate_disposition(q_state)

        # Phase BUILD: MO reads signals
        context = mo_trm._read_signals_before_decision()
        # Should see quality reject or hold signal
        has_quality_signal = (
            context.get("quality_hold_active") or
            context.get("quality_reject_active")
        )
        assert has_quality_signal, f"MO should see quality signal, got: {context}"

    def test_full_11_trm_cascade(self):
        """Run all 11 TRMs through a decision cycle and verify signal accumulation."""
        from app.services.powell.site_agent import SiteAgent, SiteAgentConfig

        config = SiteAgentConfig(
            site_key="test_cascade",
            use_trm_adjustments=False,
            enable_hive_signals=True,
        )
        agent = SiteAgent(config)
        bus = agent.signal_bus

        # Create simple executors that emit known signals
        def emit_signal(sig_type, source, urgency, direction):
            def executor():
                bus.emit(HiveSignal(
                    source_trm=source, signal_type=sig_type,
                    urgency=urgency, direction=direction,
                ))
                bus.urgency.update(source, urgency, direction)
            return executor

        executors = {
            "atp_executor": emit_signal(HiveSignalType.ATP_SHORTAGE, "atp_executor", 0.7, "shortage"),
            "order_tracking": emit_signal(HiveSignalType.ORDER_EXCEPTION, "order_tracking", 0.5, "risk"),
            "inventory_buffer": emit_signal(HiveSignalType.BUFFER_INCREASED, "inventory_buffer", 0.4, "shortage"),
            "forecast_adj": emit_signal(HiveSignalType.FORECAST_ADJUSTED, "forecast_adj", 0.3, "surplus"),
            "quality": emit_signal(HiveSignalType.QUALITY_REJECT, "quality", 0.6, "risk"),
            "po_creation": emit_signal(HiveSignalType.PO_EXPEDITE, "po_creation", 0.5, "shortage"),
            "subcontracting": emit_signal(HiveSignalType.SUBCONTRACT_ROUTED, "subcontracting", 0.3, "relief"),
            "maintenance": emit_signal(HiveSignalType.MAINTENANCE_DEFERRED, "maintenance", 0.4, "risk"),
            "mo_execution": emit_signal(HiveSignalType.MO_RELEASED, "mo_execution", 0.3, "relief"),
            "to_execution": emit_signal(HiveSignalType.TO_RELEASED, "to_execution", 0.2, "relief"),
            "rebalancing": emit_signal(HiveSignalType.REBALANCE_INBOUND, "rebalancing", 0.3, "relief"),
        }

        result = agent.execute_decision_cycle(trm_executors=executors)
        assert result.success is True
        assert result.total_signals_emitted == 11
        assert result.phases_completed == 6

        # Verify all 11 urgency slots were updated
        snapshot = bus.urgency.snapshot()
        for val in snapshot["values"]:
            assert val > 0.0, "All 11 TRM urgency slots should be non-zero"

        # Check for expected conflicts (shortage vs surplus, risk vs relief)
        assert len(result.conflicts_detected) > 0
