"""
Unit tests for DirectiveBroadcastService — the Layer 3 orchestration
that generates inter-hive signals and broadcasts directives to SiteAgents.

Tests:
  - Service initialization and site registration
  - Site state collection
  - Inter-hive signal generation from tGNN outputs
  - Directive construction with from_gnn_output()
  - Broadcasting to registered SiteAgents
  - Feedback collection from hives
  - Full run_cycle() orchestration
  - Edge cases: missing sites, empty topology, failed applies
"""

import pytest
from typing import Dict, Any, Optional

from app.services.powell.directive_broadcast_service import DirectiveBroadcastService
from app.services.powell.site_agent import SiteAgent, SiteAgentConfig
from app.services.powell.hive_signal import (
    HiveSignal, HiveSignalBus, HiveSignalType,
)
from app.services.powell.inter_hive_signal import (
    InterHiveSignal, InterHiveSignalType, tGNNSiteDirective,
)


# ---- Fixtures ----

class FakeTRM:
    """Minimal TRM stand-in."""
    def __init__(self, name: str):
        self.name = name
        self.signal_bus: Optional[HiveSignalBus] = None
        self.executed = False
        self.last_network_context = None

    def __call__(self):
        self.executed = True
        if self.signal_bus:
            self.signal_bus.emit(HiveSignal(
                source_trm=self.name,
                signal_type=HiveSignalType.BUFFER_INCREASED,
                urgency=0.5,
                direction="relief",
                magnitude=50.0,
            ))

    def apply_network_context(self, params):
        self.last_network_context = params


def make_site(key: str, trm_names=None) -> SiteAgent:
    """Create a SiteAgent with optional TRMs registered."""
    agent = SiteAgent(SiteAgentConfig(
        site_key=key, use_trm_adjustments=False, enable_hive_signals=True,
    ))
    if trm_names:
        trms = {n: FakeTRM(n) for n in trm_names}
        agent.connect_trms(**trms)
    return agent


@pytest.fixture
def broadcast_service():
    """Service with 3 registered sites."""
    svc = DirectiveBroadcastService()
    for key in ["plant_a", "dc_b", "dc_c"]:
        svc.register_site(key, make_site(key, ["atp_executor", "inventory_buffer"]))
    return svc


@pytest.fixture
def gnn_outputs():
    return {
        "plant_a": {
            "criticality_score": 0.9,
            "bottleneck_risk": 0.8,
            "resilience_score": 0.3,
            "safety_stock_multiplier": 1.5,
            "demand_forecast": 1000.0,
            "exception_probability": 0.75,
        },
        "dc_b": {
            "criticality_score": 0.5,
            "bottleneck_risk": 0.2,
            "resilience_score": 0.8,
            "safety_stock_multiplier": 1.0,
            "demand_forecast": 500.0,
            "exception_probability": 0.1,
        },
        "dc_c": {
            "criticality_score": 0.6,
            "bottleneck_risk": 0.3,
            "resilience_score": 0.7,
            "safety_stock_multiplier": 1.1,
            "demand_forecast": 600.0,
            "exception_probability": 0.2,
        },
    }


@pytest.fixture
def topology():
    return {
        "plant_a": ["dc_b", "dc_c"],
        "dc_b": ["plant_a"],
        "dc_c": ["plant_a"],
    }


# ============================================================
# Service Lifecycle Tests
# ============================================================

class TestServiceInit:
    def test_empty_init(self):
        svc = DirectiveBroadcastService()
        assert svc.registered_sites == []
        assert svc._last_broadcast is None

    def test_register_sites(self, broadcast_service):
        assert len(broadcast_service.registered_sites) == 3
        assert "plant_a" in broadcast_service.registered_sites

    def test_status(self, broadcast_service):
        status = broadcast_service.get_status()
        assert status["broadcast_count"] == 0
        assert status["last_broadcast"] is None
        assert len(status["registered_sites"]) == 3


# ============================================================
# State Collection Tests
# ============================================================

class TestCollectState:
    def test_collect_empty_sites(self, broadcast_service):
        state = broadcast_service.collect_site_state()
        assert len(state) == 3
        for key in ["plant_a", "dc_b", "dc_c"]:
            assert key in state
            assert "urgency_vector" in state[key]
            assert "signal_summary" in state[key]

    def test_collect_with_signals(self, broadcast_service):
        agent = broadcast_service._site_agents["plant_a"]
        agent.signal_bus.emit(HiveSignal(
            source_trm="atp_executor",
            signal_type=HiveSignalType.ATP_SHORTAGE,
            urgency=0.8,
            direction="shortage",
            magnitude=100.0,
        ))
        state = broadcast_service.collect_site_state()
        assert state["plant_a"]["bus_stats"]["alive"] >= 1


# ============================================================
# Inter-Hive Signal Generation Tests
# ============================================================

class TestSignalGeneration:
    def test_shortage_signals_generated(self, broadcast_service, gnn_outputs, topology):
        directives = broadcast_service.generate_directives_from_gnn(gnn_outputs, topology)
        # plant_a has exception_probability=0.75 > 0.6, bottleneck_risk=0.8 > 0.7
        # Should generate signals to dc_b and dc_c
        dc_b_dir = directives["dc_b"]
        dc_c_dir = directives["dc_c"]
        assert len(dc_b_dir.inter_hive_signals) >= 1
        assert len(dc_c_dir.inter_hive_signals) >= 1

    def test_no_signals_for_low_risk(self, broadcast_service, gnn_outputs, topology):
        directives = broadcast_service.generate_directives_from_gnn(gnn_outputs, topology)
        # dc_b has exception_probability=0.1, bottleneck_risk=0.2 — below thresholds
        # plant_a should NOT receive signals FROM dc_b
        plant_dir = directives["plant_a"]
        # Only receives from dc_b and dc_c as neighbors, both low risk
        from_dc = [s for s in plant_dir.inter_hive_signals
                    if s.source_site in ("dc_b", "dc_c")]
        assert len(from_dc) == 0  # Neither dc_b nor dc_c triggers shortage

    def test_no_topology_no_signals(self, broadcast_service, gnn_outputs):
        directives = broadcast_service.generate_directives_from_gnn(gnn_outputs, {})
        for d in directives.values():
            assert len(d.inter_hive_signals) == 0

    def test_directive_has_sop_params(self, broadcast_service, gnn_outputs, topology):
        directives = broadcast_service.generate_directives_from_gnn(gnn_outputs, topology)
        d = directives["plant_a"]
        assert d.safety_stock_multiplier == 1.5
        assert d.criticality_score == 0.9
        assert d.bottleneck_risk == 0.8


# ============================================================
# Broadcast Tests
# ============================================================

class TestBroadcast:
    def test_broadcast_delivers_to_all(self, broadcast_service, gnn_outputs, topology):
        directives = broadcast_service.generate_directives_from_gnn(gnn_outputs, topology)
        results = broadcast_service.broadcast(directives)
        assert len(results) == 3
        for key in ["plant_a", "dc_b", "dc_c"]:
            assert key in results
            assert "signals_injected" in results[key]

    def test_broadcast_updates_status(self, broadcast_service, gnn_outputs, topology):
        directives = broadcast_service.generate_directives_from_gnn(gnn_outputs, topology)
        broadcast_service.broadcast(directives)
        status = broadcast_service.get_status()
        assert status["broadcast_count"] == 1
        assert status["last_broadcast"] is not None

    def test_broadcast_skips_unregistered(self, broadcast_service):
        directive = tGNNSiteDirective.from_gnn_output(
            site_key="unknown_site",
            gnn_embeddings={"criticality_score": 0.5, "bottleneck_risk": 0.1},
        )
        results = broadcast_service.broadcast({"unknown_site": directive})
        assert "unknown_site" not in results or "error" not in results.get("unknown_site", {})

    def test_trm_receives_network_context(self, broadcast_service, gnn_outputs, topology):
        directives = broadcast_service.generate_directives_from_gnn(gnn_outputs, topology)
        broadcast_service.broadcast(directives)
        # Check that TRMs in plant_a got network context
        agent = broadcast_service._site_agents["plant_a"]
        ss_trm = agent.get_registered_trm("inventory_buffer")
        assert ss_trm is not None
        assert ss_trm.last_network_context is not None
        assert ss_trm.last_network_context["safety_stock_multiplier"] == 1.5


# ============================================================
# Feedback Collection Tests
# ============================================================

class TestFeedback:
    def test_feedback_from_all_sites(self, broadcast_service):
        feedback = broadcast_service.collect_feedback()
        assert len(feedback) == 3
        for key in ["plant_a", "dc_b", "dc_c"]:
            assert "net_urgency_avg" in feedback[key]
            assert "shortage_signal_density" in feedback[key]

    def test_feedback_reflects_signals(self, broadcast_service):
        agent = broadcast_service._site_agents["plant_a"]
        for _ in range(3):
            agent.signal_bus.emit(HiveSignal(
                source_trm="atp_executor",
                signal_type=HiveSignalType.ATP_SHORTAGE,
                urgency=0.8,
                direction="shortage",
                magnitude=100.0,
            ))
        feedback = broadcast_service.collect_feedback()
        assert feedback["plant_a"]["total_active_signals"] >= 3


# ============================================================
# Full Cycle Tests
# ============================================================

class TestRunCycle:
    def test_full_cycle(self, broadcast_service, gnn_outputs, topology):
        result = broadcast_service.run_cycle(gnn_outputs, topology)
        assert result["directives_generated"] == 3
        assert "broadcast_results" in result
        assert "feedback" in result
        assert result["total_inter_hive_signals"] >= 2  # plant_a generates signals

    def test_multiple_cycles(self, broadcast_service, gnn_outputs, topology):
        broadcast_service.run_cycle(gnn_outputs, topology)
        broadcast_service.run_cycle(gnn_outputs, topology)
        status = broadcast_service.get_status()
        assert status["broadcast_count"] == 2


# ============================================================
# InterHiveSignal Tests
# ============================================================

class TestInterHiveSignal:
    def test_creation(self):
        sig = InterHiveSignal(
            signal_type=InterHiveSignalType.NETWORK_SHORTAGE,
            source_site="a", target_site="b",
            urgency=0.9, direction="shortage", magnitude=500.0,
        )
        assert sig.source_site == "a"
        assert sig.half_life_hours == 12.0

    def test_serialization(self):
        sig = InterHiveSignal(
            signal_type=InterHiveSignalType.BOTTLENECK_RISK,
            source_site="x", target_site="y",
            urgency=0.7, direction="risk", magnitude=100.0,
        )
        d = sig.to_dict()
        assert d["signal_type"] == "bottleneck_risk"
        assert d["source_site"] == "x"

    def test_unique_ids(self):
        s1 = InterHiveSignal(
            signal_type=InterHiveSignalType.NETWORK_SURPLUS,
            source_site="a", target_site="b",
            urgency=0.5, direction="surplus", magnitude=100.0,
        )
        s2 = InterHiveSignal(
            signal_type=InterHiveSignalType.NETWORK_SURPLUS,
            source_site="a", target_site="b",
            urgency=0.5, direction="surplus", magnitude=100.0,
        )
        assert s1.signal_id != s2.signal_id


class TestTGNNSiteDirective:
    def test_from_gnn_output(self):
        d = tGNNSiteDirective.from_gnn_output(
            site_key="test",
            gnn_embeddings={
                "criticality_score": 0.8,
                "safety_stock_multiplier": 1.3,
            },
        )
        assert d.site_key == "test"
        assert d.criticality_score == 0.8
        assert d.safety_stock_multiplier == 1.3

    def test_with_signals(self):
        sig = InterHiveSignal(
            signal_type=InterHiveSignalType.DEMAND_PROPAGATION,
            source_site="a", target_site="test",
            urgency=0.6, direction="shortage", magnitude=200.0,
        )
        d = tGNNSiteDirective.from_gnn_output(
            site_key="test",
            gnn_embeddings={},
            inter_hive_signals=[sig],
        )
        assert len(d.inter_hive_signals) == 1
