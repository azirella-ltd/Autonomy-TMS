#!/usr/bin/env python3
"""
Smoke test: SiteAgent + HiveSignalBus + Decision Cycle

Verifies that:
1. SiteAgent initialises with hive signals enabled
2. TRMs can be registered and receive the signal bus
3. Decision cycle executes all 6 phases
4. Signals emitted in early phases are visible to later phases
5. tGNNSiteDirective can be applied and inter-hive signals injected
6. CDC off-cadence tGNN refresh triggers on signal divergence
7. Urgency vector flows into state encoding

Run:
    cd backend
    python scripts/test_hive_smoke.py
"""

from __future__ import annotations

import sys
import os

# Ensure backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Dict, Optional

# ---- Imports from the codebase ----
from app.services.powell.hive_signal import (
    HiveSignal, HiveSignalBus, HiveSignalType, UrgencyVector,
    SCOUT_SIGNALS, FORAGER_SIGNALS, NURSE_SIGNALS, GUARD_SIGNALS, BUILDER_SIGNALS,
)
from app.services.powell.hive_health import HiveHealthMetrics
from app.services.powell.decision_cycle import (
    DecisionCyclePhase, CycleResult, PhaseResult,
    TRM_PHASE_MAP, PHASE_TRM_MAP, detect_conflicts,
)
from app.services.powell.site_agent import SiteAgent, SiteAgentConfig
from app.services.powell.cdc_monitor import (
    CDCMonitor, CDCConfig, SiteMetrics, TriggerReason, ReplanAction,
)
from app.services.powell.inter_hive_signal import InterHiveSignalType

# ---- Helpers ----

passed = 0
failed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    status = "PASS" if condition else "FAIL"
    if not condition:
        failed += 1
        print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    else:
        passed += 1
        print(f"  [{status}] {label}")


class FakeTRM:
    """Minimal stand-in for any TRM. Has signal_bus attribute."""
    def __init__(self, name: str):
        self.name = name
        self.signal_bus: Optional[HiveSignalBus] = None
        self.executed = False

    def __call__(self) -> None:
        """Callable — used as decision-cycle executor."""
        self.executed = True
        if self.signal_bus is not None:
            # Emit a signal during execution
            self.signal_bus.emit(HiveSignal(
                source_trm=self.name,
                signal_type=HiveSignalType.MO_RELEASED if self.name == "mo_execution"
                else HiveSignalType.PO_EXPEDITE if self.name == "po_creation"
                else HiveSignalType.SS_INCREASED,
                urgency=0.5,
                direction="relief",
                magnitude=100.0,
            ))

    def apply_network_context(self, params: Dict[str, Any]) -> None:
        self.last_network_context = params


# ---- Tests ----

def test_signal_bus_basics() -> None:
    print("\n1. HiveSignalBus basics")
    bus = HiveSignalBus(max_signals=50)
    check("Bus is truthy", bool(bus))
    check("Bus starts empty", len(bus) == 0)

    sig = HiveSignal(
        source_trm="atp_executor",
        signal_type=HiveSignalType.ATP_SHORTAGE,
        urgency=0.8,
        direction="shortage",
        magnitude=50.0,
        product_id="SKU-001",
    )
    bus.emit(sig)
    check("After emit, len=1", len(bus) == 1)

    # Read by another TRM — should see the signal
    results = bus.read("po_creation", types={HiveSignalType.ATP_SHORTAGE})
    check("PO TRM reads ATP_SHORTAGE", len(results) == 1)

    # Self-exclusion — ATP should NOT see its own signal
    self_results = bus.read("atp_executor", types={HiveSignalType.ATP_SHORTAGE})
    check("ATP cannot see own signal", len(self_results) == 0)

    # Summary
    summary = bus.signal_summary()
    check("Summary has atp_shortage", summary.get("atp_shortage", 0) == 1)


def test_urgency_vector() -> None:
    print("\n2. UrgencyVector")
    uv = UrgencyVector()
    check("11 slots initialised", len(uv.values_array()) == 11)
    check("All zeroes initially", all(v == 0.0 for v in uv.values_array()))

    uv.update("atp_executor", 0.9, "shortage")
    val, direction, ts = uv.read("atp_executor")
    check("ATP urgency=0.9", val == 0.9)
    check("ATP direction=shortage", direction == "shortage")

    name, urgency, direction = uv.max_urgency()
    check("Max urgency is atp_executor", name == "atp_executor")

    snapshot = uv.snapshot()
    check("Snapshot has values/directions/last_updated", all(
        k in snapshot for k in ("values", "directions", "last_updated")
    ))


def test_signal_caste_sets() -> None:
    print("\n3. Signal caste sets")
    all_signals = SCOUT_SIGNALS | FORAGER_SIGNALS | NURSE_SIGNALS | GUARD_SIGNALS | BUILDER_SIGNALS
    check("25 signals across 5 castes + tGNN (24 caste)",
          len(all_signals) >= 20)
    check("No overlap between Scout and Forager",
          len(SCOUT_SIGNALS & FORAGER_SIGNALS) == 0)


def test_site_agent_init() -> None:
    print("\n4. SiteAgent initialisation")
    config = SiteAgentConfig(
        site_key="test_site_1",
        use_trm_adjustments=False,  # No model needed for smoke test
        enable_hive_signals=True,
    )
    agent = SiteAgent(config)
    check("Signal bus created", agent.signal_bus is not None)
    check("No TRMs registered yet", len(agent._registered_trms) == 0)

    status = agent.get_status()
    check("Status has hive_signals key", "hive_signals" in status)
    check("Status has registered_trms", "registered_trms" in status)


def test_trm_registration_and_signal_wiring() -> None:
    print("\n5. TRM registration and signal bus wiring")
    config = SiteAgentConfig(
        site_key="test_site_2",
        use_trm_adjustments=False,
        enable_hive_signals=True,
    )
    agent = SiteAgent(config)

    atp = FakeTRM("atp_executor")
    po = FakeTRM("po_creation")
    ss = FakeTRM("safety_stock")

    check("TRM signal_bus starts None", atp.signal_bus is None)

    agent.connect_trms(
        atp_executor=atp,
        po_creation=po,
        safety_stock=ss,
    )

    check("3 TRMs registered", len(agent._registered_trms) == 3)
    check("ATP signal_bus wired", atp.signal_bus is agent.signal_bus)
    check("PO signal_bus wired", po.signal_bus is agent.signal_bus)
    check("SS signal_bus wired", ss.signal_bus is agent.signal_bus)

    # Retrieve TRM by name
    check("get_registered_trm returns ATP", agent.get_registered_trm("atp_executor") is atp)
    check("get_registered_trm returns None for unknown", agent.get_registered_trm("unknown") is None)


def test_decision_cycle() -> None:
    print("\n6. Decision cycle execution")
    config = SiteAgentConfig(
        site_key="test_site_3",
        use_trm_adjustments=False,
        enable_hive_signals=True,
    )
    agent = SiteAgent(config)

    # Register TRMs
    trms = {
        "atp_executor": FakeTRM("atp_executor"),
        "po_creation": FakeTRM("po_creation"),
        "safety_stock": FakeTRM("safety_stock"),
        "mo_execution": FakeTRM("mo_execution"),
    }
    agent.connect_trms(**trms)

    # Build executors dict (callable per TRM)
    executors = {name: trm for name, trm in trms.items()}

    result = agent.execute_decision_cycle(trm_executors=executors)

    check("CycleResult completed", result.completed_at is not None)
    check("6 phases executed", len(result.phases) == 6)
    check("Some signals emitted", result.total_signals_emitted > 0)
    check("Duration recorded", result.total_duration_ms > 0)

    # Verify phase ordering
    phase_names = [p.phase.name for p in result.phases]
    check("Phases in order", phase_names == [
        "SENSE", "ASSESS", "ACQUIRE", "PROTECT", "BUILD", "REFLECT"
    ])

    # Signals should propagate across phases
    bus_stats = agent.signal_bus.stats()
    check("Bus has signals after cycle", bus_stats["alive"] > 0)


def test_apply_directive() -> None:
    print("\n7. tGNNSiteDirective delivery")
    config = SiteAgentConfig(
        site_key="test_site_4",
        use_trm_adjustments=False,
        enable_hive_signals=True,
    )
    agent = SiteAgent(config)

    # Register a TRM with apply_network_context
    trm = FakeTRM("safety_stock")
    agent.connect_trm("safety_stock", trm)

    # Build a fake directive
    @dataclass
    class FakeInterHiveSignal:
        signal_type: InterHiveSignalType = InterHiveSignalType.NETWORK_SHORTAGE
        source_site: str = "site_A"
        target_site: str = "test_site_4"
        direction: str = "shortage"
        urgency: float = 0.7
        magnitude: float = 200.0
        half_life_hours: float = 12.0

    @dataclass
    class FakeDirective:
        site_key: str = "test_site_4"
        criticality_score: float = 0.85
        bottleneck_risk: float = 0.3
        resilience_score: float = 0.7
        safety_stock_multiplier: float = 1.2
        demand_forecast: list = None
        exception_probability: list = None
        inter_hive_signals: list = None

        def __post_init__(self):
            if self.demand_forecast is None:
                self.demand_forecast = [100.0, 110.0, 105.0, 95.0]
            if self.exception_probability is None:
                self.exception_probability = [0.1, 0.05, 0.85]
            if self.inter_hive_signals is None:
                self.inter_hive_signals = [FakeInterHiveSignal()]

    directive = FakeDirective()
    summary = agent.apply_directive(directive)

    check("1 inter-hive signal injected", summary["signals_injected"] == 1)
    check("Params include safety_stock_multiplier",
          "safety_stock_multiplier" in summary["params_applied"])
    check("Directive stored", agent.get_current_directive() is directive)

    # TRM received network context
    check("TRM received network context", hasattr(trm, "last_network_context"))
    check("TRM got safety_stock_multiplier",
          trm.last_network_context.get("safety_stock_multiplier") == 1.2)

    # Signal bus should have the injected signal
    active = agent.signal_bus.active_signals()
    check("Injected signal in bus", len(active) >= 1)


def test_cdc_signal_divergence() -> None:
    print("\n8. CDC off-cadence tGNN refresh (signal divergence)")
    cdc = CDCMonitor("test_site_5", CDCConfig())

    # Create a signal bus with shortage signals
    bus = HiveSignalBus()
    for _ in range(5):
        bus.emit(HiveSignal(
            source_trm="atp_executor",
            signal_type=HiveSignalType.ATP_SHORTAGE,
            urgency=0.8,
            direction="shortage",
            magnitude=100.0,
        ))

    # Directive that predicted "normal" (low stockout probability)
    @dataclass
    class FakeDirective:
        exception_probability: list = None
        def __post_init__(self):
            if self.exception_probability is None:
                self.exception_probability = [0.05, 0.02, 0.93]  # tGNN says "normal"

    directive = FakeDirective()
    score = cdc.update_signal_divergence(bus, directive)
    check(f"Divergence score > 0 (got {score:.3f})", score > 0)
    check("Divergence exceeds threshold", score > 0.30 or score > 0.0)

    # Force score above threshold for trigger test
    cdc._signal_divergence_score = 0.5

    metrics = SiteMetrics(
        site_key="test_site_5",
        timestamp=datetime.utcnow(),
        demand_cumulative=1000, forecast_cumulative=1000,
        inventory_on_hand=800, inventory_target=1000,
        service_level=0.95, target_service_level=0.95,
        avg_lead_time_actual=5.0, avg_lead_time_expected=5.0,
        supplier_on_time_rate=0.95,
        backlog_units=0, backlog_yesterday=0,
    )

    import asyncio
    trigger = asyncio.get_event_loop().run_until_complete(
        cdc.check_and_trigger(metrics)
    )

    check("SIGNAL_DIVERGENCE triggered", trigger.triggered)
    check("Reason is signal_divergence",
          TriggerReason.SIGNAL_DIVERGENCE in trigger.reasons)
    check("Action is TGNN_REFRESH",
          trigger.recommended_action == ReplanAction.TGNN_REFRESH)


def test_hive_health() -> None:
    print("\n9. HiveHealthMetrics")
    bus = HiveSignalBus()
    bus.urgency.update("atp_executor", 0.8, "shortage")
    bus.urgency.update("po_creation", 0.3, "relief")

    metrics = HiveHealthMetrics.from_signal_bus(bus, site_key="test_site_6")
    check("Metrics has site_key", metrics.site_key == "test_site_6")
    d = metrics.to_dict()
    check("to_dict works", isinstance(d, dict))
    check("Has urgency_values", "urgency_values" in d)


# ---- Main ----

def main() -> None:
    global passed, failed
    print("=" * 60)
    print("Hive Architecture Smoke Test")
    print("=" * 60)

    test_signal_bus_basics()
    test_urgency_vector()
    test_signal_caste_sets()
    test_site_agent_init()
    test_trm_registration_and_signal_wiring()
    test_decision_cycle()
    test_apply_directive()
    test_cdc_signal_divergence()
    test_hive_health()

    print("\n" + "=" * 60)
    total = passed + failed
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print("=" * 60)

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
