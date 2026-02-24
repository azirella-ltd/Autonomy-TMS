"""
Tests for Sprint 6: Inter-Hive Signals + Feedback Features

Validates that:
1. InterHiveSignalType enum has expected values
2. InterHiveSignal dataclass creates and serializes correctly
3. tGNNSiteDirective constructs from GNN output and serializes
4. HiveFeedbackFeatures computes from urgency/traces/signal_bus
5. InventoryBufferTRM respects tgnn_ss_multiplier bound modulation
6. SiteAgent.apply_directive() injects typed signals into local bus
"""

import pytest
import numpy as np

from app.services.powell.inter_hive_signal import (
    InterHiveSignalType,
    InterHiveSignal,
    tGNNSiteDirective,
)
from app.services.powell.hive_feedback import (
    HiveFeedbackFeatures,
    compute_feedback_features,
)
from app.services.powell.hive_signal import (
    HiveSignalBus,
    HiveSignal,
    HiveSignalType,
)
from app.services.powell.inventory_buffer_trm import (
    InventoryBufferTRM,
    SSState,
    SSAdjustment,
    SSAdjustmentReason,
)


# ---------------------------------------------------------------------------
# 1. InterHiveSignalType
# ---------------------------------------------------------------------------

class TestInterHiveSignalType:
    """Test the 10 inter-hive signal types."""

    def test_all_10_types_exist(self):
        expected = {
            "network_shortage", "network_surplus", "demand_propagation",
            "bottleneck_risk", "concentration_risk", "resilience_alert",
            "allocation_refresh", "priority_shift", "forecast_revision",
            "policy_param_update",
        }
        actual = {t.value for t in InterHiveSignalType}
        assert expected == actual

    def test_is_string_enum(self):
        assert isinstance(InterHiveSignalType.NETWORK_SHORTAGE, str)
        assert InterHiveSignalType.NETWORK_SHORTAGE == "network_shortage"


# ---------------------------------------------------------------------------
# 2. InterHiveSignal
# ---------------------------------------------------------------------------

class TestInterHiveSignal:
    """Test InterHiveSignal dataclass."""

    def test_default_creation(self):
        sig = InterHiveSignal()
        assert sig.signal_type == InterHiveSignalType.NETWORK_SHORTAGE
        assert sig.urgency == 0.5
        assert sig.half_life_hours == 12.0
        assert sig.propagation_depth == 0

    def test_custom_creation(self):
        sig = InterHiveSignal(
            signal_type=InterHiveSignalType.BOTTLENECK_RISK,
            source_site="SITE_A",
            target_site="SITE_B",
            urgency=0.8,
            direction="risk",
            magnitude=0.6,
            confidence=0.9,
            propagation_depth=2,
        )
        assert sig.source_site == "SITE_A"
        assert sig.target_site == "SITE_B"
        assert sig.urgency == 0.8
        assert sig.propagation_depth == 2

    def test_to_dict(self):
        sig = InterHiveSignal(
            source_site="A", target_site="B",
            urgency=0.7, direction="shortage",
        )
        d = sig.to_dict()
        assert d["source_site"] == "A"
        assert d["target_site"] == "B"
        assert d["urgency"] == 0.7
        assert d["direction"] == "shortage"
        assert "signal_id" in d
        assert "timestamp" in d

    def test_unique_signal_ids(self):
        s1 = InterHiveSignal()
        s2 = InterHiveSignal()
        assert s1.signal_id != s2.signal_id


# ---------------------------------------------------------------------------
# 3. tGNNSiteDirective
# ---------------------------------------------------------------------------

class TestTGNNSiteDirective:
    """Test tGNNSiteDirective construction and serialization."""

    def test_default_creation(self):
        d = tGNNSiteDirective(site_key="SITE_1")
        assert d.site_key == "SITE_1"
        assert d.safety_stock_multiplier == 1.0
        assert d.criticality_score == 0.5
        assert d.bottleneck_risk == 0.0
        assert d.inter_hive_signals == []

    def test_with_signals(self):
        signals = [
            InterHiveSignal(
                signal_type=InterHiveSignalType.NETWORK_SHORTAGE,
                source_site="UPSTREAM",
                target_site="SITE_1",
                urgency=0.9,
                direction="shortage",
            ),
            InterHiveSignal(
                signal_type=InterHiveSignalType.ALLOCATION_REFRESH,
                source_site="TGNN",
                target_site="SITE_1",
                urgency=0.3,
                direction="neutral",
            ),
        ]
        d = tGNNSiteDirective(
            site_key="SITE_1",
            inter_hive_signals=signals,
            safety_stock_multiplier=1.3,
        )
        assert len(d.inter_hive_signals) == 2
        assert d.safety_stock_multiplier == 1.3

    def test_to_dict(self):
        d = tGNNSiteDirective(site_key="SITE_X", bottleneck_risk=0.7)
        out = d.to_dict()
        assert out["site_key"] == "SITE_X"
        assert out["bottleneck_risk"] == 0.7
        assert "directive_id" in out
        assert "inter_hive_signals_count" in out

    def test_from_gnn_output(self):
        embeddings = {
            "safety_stock_multiplier": 1.5,
            "criticality_score": 0.8,
            "bottleneck_risk": 0.3,
            "resilience_score": 0.9,
            "demand_forecast": 150.0,
            "exception_probability": 0.1,
        }
        signals = [
            InterHiveSignal(
                signal_type=InterHiveSignalType.FORECAST_REVISION,
                urgency=0.4,
            )
        ]
        d = tGNNSiteDirective.from_gnn_output(
            site_key="FACTORY_1",
            gnn_embeddings=embeddings,
            inter_hive_signals=signals,
        )
        assert d.site_key == "FACTORY_1"
        assert d.safety_stock_multiplier == 1.5
        assert d.criticality_score == 0.8
        assert d.demand_forecast == 150.0
        assert len(d.inter_hive_signals) == 1

    def test_from_gnn_output_defaults(self):
        d = tGNNSiteDirective.from_gnn_output(
            site_key="S1", gnn_embeddings={}
        )
        assert d.safety_stock_multiplier == 1.0
        assert d.criticality_score == 0.5
        assert d.bottleneck_risk == 0.0
        assert d.demand_forecast is None
        assert d.inter_hive_signals == []


# ---------------------------------------------------------------------------
# 4. HiveFeedbackFeatures
# ---------------------------------------------------------------------------

class TestHiveFeedbackFeatures:
    """Test HiveFeedbackFeatures dataclass and computation."""

    def test_default_values(self):
        f = HiveFeedbackFeatures()
        assert f.avg_urgency == 0.0
        assert f.urgency_spread == 0.0
        assert f.dominant_caste == 0

    def test_to_tensor_shape(self):
        f = HiveFeedbackFeatures(avg_urgency=0.5, signal_rate=3.0)
        t = f.to_tensor()
        assert isinstance(t, np.ndarray)
        assert t.shape == (8,)
        assert t.dtype == np.float32

    def test_to_tensor_values(self):
        f = HiveFeedbackFeatures(
            avg_urgency=0.5,
            urgency_spread=0.1,
            signal_rate=2.0,
            conflict_rate=0.5,
            cross_head_reward=1.2,
            dominant_caste=3,
            ss_adjustment_dir=1.0,
            exception_rate=0.25,
        )
        t = f.to_tensor()
        assert t[0] == pytest.approx(0.5)     # avg_urgency
        assert t[1] == pytest.approx(0.1)     # urgency_spread
        assert t[2] == pytest.approx(2.0)     # signal_rate
        assert t[5] == pytest.approx(0.75)    # dominant_caste/4
        assert t[6] == pytest.approx(1.0)     # ss_adjustment_dir
        assert t[7] == pytest.approx(0.25)    # exception_rate

    def test_to_dict(self):
        f = HiveFeedbackFeatures(avg_urgency=0.3, conflict_rate=0.1)
        d = f.to_dict()
        assert d["avg_urgency"] == 0.3
        assert d["conflict_rate"] == 0.1
        assert "dominant_caste" in d


class TestComputeFeedbackFeatures:
    """Test compute_feedback_features function."""

    def test_all_none_returns_defaults(self):
        f = compute_feedback_features()
        assert f.avg_urgency == 0.0
        assert f.urgency_spread == 0.0
        assert f.signal_rate == 0.0

    def test_urgency_from_snapshot(self):
        snapshot = {"values": [0.2, 0.4, 0.6, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}
        f = compute_feedback_features(urgency_snapshot=snapshot)
        assert f.avg_urgency == pytest.approx(np.mean(snapshot["values"]), abs=1e-4)

    def test_urgency_spread_from_active(self):
        snapshot = {"values": [0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}
        f = compute_feedback_features(urgency_snapshot=snapshot)
        # Active values are [0.5, 0.5] → std = 0.0
        assert f.urgency_spread == pytest.approx(0.0, abs=1e-4)

    def test_empty_values_no_crash(self):
        f = compute_feedback_features(urgency_snapshot={"values": []})
        assert f.avg_urgency == 0.0

    def test_dominant_caste_from_bus(self):
        bus = HiveSignalBus()
        # Emit 3 Scout signals and 1 Builder
        for _ in range(3):
            bus.emit(HiveSignal(
                source_trm="test", signal_type=HiveSignalType.ATP_SHORTAGE,
                urgency=0.5,
            ))
        bus.emit(HiveSignal(
            source_trm="test", signal_type=HiveSignalType.MO_RELEASED,
            urgency=0.3,
        ))
        f = compute_feedback_features(signal_bus=bus)
        assert f.dominant_caste == 0  # Scout is dominant

    def test_no_bus_dominant_caste_zero(self):
        f = compute_feedback_features(signal_bus=None)
        assert f.dominant_caste == 0


# ---------------------------------------------------------------------------
# 5. InventoryBufferTRM tgnn_ss_multiplier
# ---------------------------------------------------------------------------

class TestInventoryBufferTRMBoundModulation:
    """Test that tGNN SS multiplier modulates effective bounds."""

    def _make_state(self, **overrides) -> SSState:
        defaults = dict(
            product_id="P1", location_id="L1",
            baseline_ss=100.0, baseline_reorder_point=150.0,
            baseline_target_inventory=200.0, policy_type="sl",
            current_on_hand=120.0, current_dos=10.0,
            demand_cv=0.2, avg_daily_demand=10.0, demand_trend=0.0,
            seasonal_index=1.0, month_of_year=6,
            recent_stockout_count=0, recent_excess_days=0,
            forecast_bias=0.0,
            lead_time_days=7.0, lead_time_cv=0.1,
        )
        defaults.update(overrides)
        return SSState(**defaults)

    def test_default_effective_bounds(self):
        trm = InventoryBufferTRM()
        lo, hi = trm.effective_bounds
        assert lo == pytest.approx(0.5)
        assert hi == pytest.approx(2.0)

    def test_apply_network_context_updates_multiplier(self):
        trm = InventoryBufferTRM()
        trm.apply_network_context({"safety_stock_multiplier": 1.5})
        assert trm._tgnn_ss_multiplier == pytest.approx(1.5)
        lo, hi = trm.effective_bounds
        assert lo == pytest.approx(0.75)   # 0.5 * 1.5
        assert hi == pytest.approx(3.0)    # 2.0 * 1.5

    def test_apply_network_context_clamps_extreme(self):
        trm = InventoryBufferTRM()
        trm.apply_network_context({"safety_stock_multiplier": 100.0})
        assert trm._tgnn_ss_multiplier == pytest.approx(5.0)  # clamped

    def test_apply_network_context_ignores_missing(self):
        trm = InventoryBufferTRM()
        trm.apply_network_context({"criticality_score": 0.8})
        assert trm._tgnn_ss_multiplier == pytest.approx(1.0)  # unchanged

    def test_heuristic_respects_tgnn_bounds(self):
        trm = InventoryBufferTRM(min_multiplier=0.5, max_multiplier=2.0)
        trm.apply_network_context({"safety_stock_multiplier": 1.5})

        # Trigger seasonal trough heuristic: multiplier=0.8
        state = self._make_state(seasonal_index=0.5)
        result = trm.evaluate(state)
        # 0.8 * 1.0 = 0.8, but lo = 0.75, so it should be >= 0.75
        assert result.multiplier >= 0.75

    def test_heuristic_clamps_to_upper_bound(self):
        trm = InventoryBufferTRM(min_multiplier=0.5, max_multiplier=2.0)
        trm.apply_network_context({"safety_stock_multiplier": 0.5})
        # Effective max = 1.0

        # Trigger high-stockout heuristic: multiplier=1.4
        state = self._make_state(recent_stockout_count=5)
        result = trm.evaluate(state)
        # 1.4 clamped to 1.0 (effective max)
        assert result.multiplier == pytest.approx(1.0)

    def test_evaluate_returns_adjustment(self):
        trm = InventoryBufferTRM()
        state = self._make_state()
        result = trm.evaluate(state)
        assert isinstance(result, SSAdjustment)
        assert result.product_id == "P1"
        assert result.baseline_ss == 100.0


# ---------------------------------------------------------------------------
# 6. SiteAgent.apply_directive integration
# ---------------------------------------------------------------------------

class TestSiteAgentApplyDirective:
    """Test that SiteAgent correctly applies typed tGNNSiteDirective."""

    def _make_site_agent(self):
        """Create a minimal SiteAgent for testing."""
        from app.services.powell.site_agent import SiteAgent, SiteAgentConfig
        config = SiteAgentConfig(site_key="TEST_SITE")
        agent = SiteAgent(config)
        return agent

    def test_apply_directive_injects_signals(self):
        agent = self._make_site_agent()
        signals = [
            InterHiveSignal(
                signal_type=InterHiveSignalType.NETWORK_SHORTAGE,
                source_site="UPSTREAM",
                target_site="TEST_SITE",
                urgency=0.8,
                direction="shortage",
            ),
            InterHiveSignal(
                signal_type=InterHiveSignalType.ALLOCATION_REFRESH,
                source_site="TGNN",
                target_site="TEST_SITE",
                urgency=0.3,
                direction="neutral",
            ),
        ]
        directive = tGNNSiteDirective(
            site_key="TEST_SITE",
            inter_hive_signals=signals,
            safety_stock_multiplier=1.2,
        )
        summary = agent.apply_directive(directive)
        assert summary["signals_injected"] == 2
        assert summary["params_applied"]["safety_stock_multiplier"] == 1.2

    def test_apply_directive_empty_signals(self):
        agent = self._make_site_agent()
        directive = tGNNSiteDirective(
            site_key="TEST_SITE",
            bottleneck_risk=0.9,
        )
        summary = agent.apply_directive(directive)
        assert summary["signals_injected"] == 0
        assert summary["params_applied"]["bottleneck_risk"] == 0.9

    def test_apply_directive_stores_directive(self):
        agent = self._make_site_agent()
        directive = tGNNSiteDirective(site_key="TEST_SITE")
        agent.apply_directive(directive)
        stored = agent.get_current_directive()
        assert stored is directive

    def test_apply_directive_signals_appear_in_bus(self):
        agent = self._make_site_agent()
        signals = [
            InterHiveSignal(
                signal_type=InterHiveSignalType.NETWORK_SHORTAGE,
                source_site="UP",
                target_site="TEST_SITE",
                urgency=0.7,
                direction="shortage",
                half_life_hours=6.0,
            ),
        ]
        directive = tGNNSiteDirective(
            site_key="TEST_SITE",
            inter_hive_signals=signals,
        )
        agent.apply_directive(directive)
        # Check local bus received the signal
        if agent.signal_bus is not None:
            active = agent.signal_bus.active_signals()
            tgnn_signals = [s for s in active if s.source_trm == "tgnn_network"]
            assert len(tgnn_signals) >= 1
            assert tgnn_signals[0].signal_type == HiveSignalType.NETWORK_SHORTAGE
            # Half life should be 6h * 60 = 360 minutes
            assert tgnn_signals[0].half_life_minutes == pytest.approx(360.0)

    def test_apply_directive_pushes_to_registered_trm(self):
        agent = self._make_site_agent()
        # Register a mock TRM with apply_network_context
        class MockTRM:
            def __init__(self):
                self.received_params = None
            def apply_network_context(self, params):
                self.received_params = params

        mock = MockTRM()
        agent._registered_trms["inventory_buffer"] = mock

        directive = tGNNSiteDirective(
            site_key="TEST_SITE",
            safety_stock_multiplier=1.4,
            criticality_score=0.9,
        )
        agent.apply_directive(directive)
        assert mock.received_params is not None
        assert mock.received_params["safety_stock_multiplier"] == 1.4
        assert mock.received_params["criticality_score"] == 0.9

    def test_from_gnn_output_roundtrip(self):
        """Test that from_gnn_output → apply_directive works end-to-end."""
        agent = self._make_site_agent()

        embeddings = {
            "safety_stock_multiplier": 1.3,
            "criticality_score": 0.7,
            "bottleneck_risk": 0.2,
        }
        ihs = InterHiveSignal(
            signal_type=InterHiveSignalType.NETWORK_SURPLUS,
            source_site="NEIGHBOR",
            target_site="TEST_SITE",
            urgency=0.4,
            direction="surplus",
        )
        directive = tGNNSiteDirective.from_gnn_output(
            site_key="TEST_SITE",
            gnn_embeddings=embeddings,
            inter_hive_signals=[ihs],
        )
        summary = agent.apply_directive(directive)
        assert summary["signals_injected"] == 1
        assert summary["params_applied"]["safety_stock_multiplier"] == 1.3

    def test_signal_type_mapping(self):
        """Verify all InterHiveSignalType values map correctly."""
        from app.services.powell.site_agent import SiteAgent
        mapping = SiteAgent._INTER_TO_LOCAL
        for iht in InterHiveSignalType:
            assert iht in mapping, f"{iht} missing from _INTER_TO_LOCAL mapping"
            assert isinstance(mapping[iht], HiveSignalType)
