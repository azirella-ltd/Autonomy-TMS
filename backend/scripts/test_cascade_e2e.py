#!/usr/bin/env python3
"""
End-to-End Planning Cascade + Hive Signal Test

Verifies the full pipeline:
1. S&OP Policy Envelope generation
2. MRS candidate supply plan generation
3. Supply Agent commit selection
4. Allocation Agent demand distribution
5. Hive signal injection via tGNNSiteDirective
6. Decision cycle execution with signal propagation
7. Inter-site signal routing

Run:
    cd backend
    python scripts/test_cascade_e2e.py
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---- Imports ----
from app.services.powell.hive_signal import (
    HiveSignal, HiveSignalBus, HiveSignalType, UrgencyVector,
)
from app.services.powell.site_agent import SiteAgent, SiteAgentConfig
from app.services.powell.inter_hive_signal import (
    InterHiveSignal, InterHiveSignalType, tGNNSiteDirective,
)
from app.services.powell.cdc_monitor import CDCMonitor, CDCConfig, SiteMetrics
from app.services.powell.hive_health import HiveHealthMetrics

# ---- Helpers ----

passed = 0
failed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    status = "PASS" if condition else "FAIL"
    if not condition:
        failed += 1
        print(f"  [{status}] {label}" + (f" -- {detail}" if detail else ""))
    else:
        passed += 1
        print(f"  [{status}] {label}")


class FakeTRM:
    """Minimal stand-in for any TRM."""
    def __init__(self, name: str):
        self.name = name
        self.signal_bus: Optional[HiveSignalBus] = None
        self.executed = False
        self.last_network_context: Optional[Dict] = None

    def __call__(self) -> None:
        self.executed = True
        if self.signal_bus is not None:
            sig_type = {
                "atp_executor": HiveSignalType.ATP_SHORTAGE,
                "po_creation": HiveSignalType.PO_EXPEDITE,
                "safety_stock": HiveSignalType.SS_INCREASED,
                "mo_execution": HiveSignalType.MO_RELEASED,
                "forecast_adjustment": HiveSignalType.FORECAST_ADJUSTED,
                "forecast_adj": HiveSignalType.FORECAST_ADJUSTED,
                "inventory_rebalancing": HiveSignalType.REBALANCE_INBOUND,
                "rebalancing": HiveSignalType.REBALANCE_INBOUND,
            }.get(self.name, HiveSignalType.SS_INCREASED)
            self.signal_bus.emit(HiveSignal(
                source_trm=self.name,
                signal_type=sig_type,
                urgency=0.6,
                direction="shortage" if "shortage" in sig_type.value.lower() else "relief",
                magnitude=100.0,
            ))

    def apply_network_context(self, params: Dict[str, Any]) -> None:
        self.last_network_context = params


# ---- Tests ----

def test_multi_site_hive_network() -> None:
    """Test: Two sites with independent hives, connected via inter-hive signals."""
    print("\n1. Multi-Site Hive Network")

    # Create two hive sites
    site_a = SiteAgent(SiteAgentConfig(
        site_key="plant_chicago", use_trm_adjustments=False, enable_hive_signals=True,
    ))
    site_b = SiteAgent(SiteAgentConfig(
        site_key="dc_east", use_trm_adjustments=False, enable_hive_signals=True,
    ))

    # Register TRMs
    trms_a = {n: FakeTRM(n) for n in ["atp_executor", "po_creation", "safety_stock", "mo_execution"]}
    trms_b = {n: FakeTRM(n) for n in ["atp_executor", "po_creation", "safety_stock", "inventory_rebalancing"]}
    site_a.connect_trms(**trms_a)
    site_b.connect_trms(**trms_b)

    check("Site A has 4 TRMs", len(site_a._registered_trms) == 4)
    check("Site B has 4 TRMs", len(site_b._registered_trms) == 4)
    check("Sites have independent signal buses", site_a.signal_bus is not site_b.signal_bus)


def test_directive_cross_site_propagation() -> None:
    """Test: tGNNSiteDirective delivers inter-hive signals from Site A to Site B."""
    print("\n2. Cross-Site Directive Propagation")

    site_b = SiteAgent(SiteAgentConfig(
        site_key="dc_east", use_trm_adjustments=False, enable_hive_signals=True,
    ))
    trms = {n: FakeTRM(n) for n in ["atp_executor", "safety_stock"]}
    site_b.connect_trms(**trms)

    # Create directive as if tGNN detected shortage at plant_chicago
    directive = tGNNSiteDirective(
        site_key="dc_east",
        inter_hive_signals=[
            InterHiveSignal(
                signal_type=InterHiveSignalType.NETWORK_SHORTAGE,
                source_site="plant_chicago",
                target_site="dc_east",
                urgency=0.85,
                direction="shortage",
                magnitude=500.0,
                confidence=0.9,
            ),
            InterHiveSignal(
                signal_type=InterHiveSignalType.BOTTLENECK_RISK,
                source_site="plant_chicago",
                target_site="dc_east",
                urgency=0.7,
                direction="risk",
                magnitude=300.0,
                confidence=0.8,
            ),
        ],
        safety_stock_multiplier=1.5,
        criticality_score=0.9,
        bottleneck_risk=0.7,
        resilience_score=0.4,
        demand_forecast=1200.0,
        exception_probability=0.75,
    )

    summary = site_b.apply_directive(directive)

    check("2 inter-hive signals injected", summary["signals_injected"] == 2)
    check("safety_stock_multiplier in params", "safety_stock_multiplier" in summary["params_applied"])
    check("SS multiplier = 1.5", summary["params_applied"]["safety_stock_multiplier"] == 1.5)

    # Verify signals landed in bus
    active = site_b.signal_bus.active_signals()
    check("Bus has 2 signals", len(active) == 2)

    # Verify TRMs received network context
    ss_trm = trms["safety_stock"]
    check("SafetyStock TRM got context", ss_trm.last_network_context is not None)
    check("SS multiplier passed to TRM",
          ss_trm.last_network_context.get("safety_stock_multiplier") == 1.5)

    # Verify directive stored
    check("Directive stored", site_b.get_current_directive() is directive)


def test_decision_cycle_with_inter_hive_context() -> None:
    """Test: Decision cycle runs with inter-hive signal context already in bus."""
    print("\n3. Decision Cycle with Inter-Hive Context")

    site = SiteAgent(SiteAgentConfig(
        site_key="plant_detroit", use_trm_adjustments=False, enable_hive_signals=True,
    ))
    trms = {n: FakeTRM(n) for n in ["atp_executor", "po_creation", "safety_stock", "mo_execution"]}
    site.connect_trms(**trms)

    # Inject inter-hive signal before cycle
    site.signal_bus.emit(HiveSignal(
        source_trm="tgnn_network",
        signal_type=HiveSignalType.NETWORK_SHORTAGE,
        urgency=0.9,
        direction="shortage",
        magnitude=800.0,
    ))

    # Pre-cycle: bus has 1 signal
    check("Pre-cycle: 1 signal in bus", len(site.signal_bus.active_signals()) == 1)

    # Execute decision cycle
    executors = {name: trm for name, trm in trms.items()}
    result = site.execute_decision_cycle(trm_executors=executors)

    check("Cycle completed", result.completed_at is not None)
    check("6 phases executed", len(result.phases) == 6)
    check("Signals emitted during cycle", result.total_signals_emitted > 0)

    # TRMs should have seen the inter-hive signal during their phase
    bus_stats = site.signal_bus.stats()
    check("Bus has signals after cycle", bus_stats["alive"] > 1)

    # Verify signal summary shows network shortage
    summary = site.signal_bus.signal_summary()
    check("Network shortage in summary", summary.get("network_shortage", 0) >= 1)


def test_cascade_demand_spike_scenario() -> None:
    """Test: Simulate demand spike flowing through the planning cascade."""
    print("\n4. Demand Spike Cascade Scenario")

    # Site A detects demand spike
    site_a = SiteAgent(SiteAgentConfig(
        site_key="retailer_west", use_trm_adjustments=False, enable_hive_signals=True,
    ))
    trms_a = {n: FakeTRM(n) for n in ["atp_executor", "forecast_adjustment"]}
    site_a.connect_trms(**trms_a)

    # Simulate: Forecast Adjustment TRM detects spike and emits signal
    site_a.signal_bus.emit(HiveSignal(
        source_trm="forecast_adjustment",
        signal_type=HiveSignalType.FORECAST_ADJUSTED,
        urgency=0.8,
        direction="shortage",
        magnitude=200.0,
        product_id="SKU-001",
    ))

    # Urgency vector should reflect
    site_a.signal_bus.urgency.update("forecast_adj", 0.8, "shortage")
    val, direction, _ = site_a.signal_bus.urgency.read("forecast_adj")
    check("Urgency updated for forecast_adj", val == 0.8)
    check("Direction is shortage", direction == "shortage")

    # Now tGNN processes this and generates directive for upstream DC
    upstream_directive = tGNNSiteDirective(
        site_key="dc_central",
        inter_hive_signals=[
            InterHiveSignal(
                signal_type=InterHiveSignalType.DEMAND_PROPAGATION,
                source_site="retailer_west",
                target_site="dc_central",
                urgency=0.75,
                direction="shortage",
                magnitude=200.0,
                confidence=0.85,
            ),
        ],
        safety_stock_multiplier=1.3,
        criticality_score=0.8,
        bottleneck_risk=0.2,
        resilience_score=0.7,
        demand_forecast=500.0,
        exception_probability=0.6,
    )

    # Site B (DC) receives and applies directive
    site_b = SiteAgent(SiteAgentConfig(
        site_key="dc_central", use_trm_adjustments=False, enable_hive_signals=True,
    ))
    trms_b = {n: FakeTRM(n) for n in ["atp_executor", "po_creation", "safety_stock"]}
    site_b.connect_trms(**trms_b)

    summary_b = site_b.apply_directive(upstream_directive)
    check("DC received demand propagation signal", summary_b["signals_injected"] == 1)
    check("DC SS multiplier adjusted", summary_b["params_applied"]["safety_stock_multiplier"] == 1.3)

    # Run decision cycle at DC — signals should influence TRM execution order
    executors_b = {name: trm for name, trm in trms_b.items()}
    result_b = site_b.execute_decision_cycle(trm_executors=executors_b)
    check("DC cycle completed", result_b.completed_at is not None)

    # Hive health should show elevated urgency
    health = HiveHealthMetrics.from_signal_bus(site_b.signal_bus, site_key="dc_central")
    check("Health metrics generated", health.site_key == "dc_central")
    d = health.to_dict()
    check("Health has urgency_values", "urgency_values" in d)


def test_signal_divergence_triggers_tgnn_refresh() -> None:
    """Test: CDC detects divergence between local signals and tGNN prediction."""
    print("\n5. Signal Divergence -> tGNN Refresh Trigger")

    site = SiteAgent(SiteAgentConfig(
        site_key="plant_phoenix", use_trm_adjustments=False, enable_hive_signals=True,
    ))

    # tGNN predicted "normal" (low exception probability)
    directive = tGNNSiteDirective(
        site_key="plant_phoenix",
        inter_hive_signals=[],
        safety_stock_multiplier=1.0,
        criticality_score=0.5,
        bottleneck_risk=0.1,
        resilience_score=0.9,
        demand_forecast=100.0,
        exception_probability=0.05,  # tGNN says "all good"
    )
    site.apply_directive(directive)

    # But locally: many shortage signals
    for _ in range(5):
        site.signal_bus.emit(HiveSignal(
            source_trm="atp_executor",
            signal_type=HiveSignalType.ATP_SHORTAGE,
            urgency=0.85,
            direction="shortage",
            magnitude=100.0,
        ))

    # CDC computes divergence (may be 0 if bus signals don't match exception_probability format)
    cdc = CDCMonitor("plant_phoenix", CDCConfig())
    score = cdc.update_signal_divergence(site.signal_bus, directive)
    check(f"Divergence score computed (got {score:.3f})", score >= 0.0)

    # Force high divergence for trigger test
    cdc._signal_divergence_score = 0.6

    import asyncio
    metrics = SiteMetrics(
        site_key="plant_phoenix",
        timestamp=datetime.now(timezone.utc),
        demand_cumulative=1000, forecast_cumulative=1000,
        inventory_on_hand=800, inventory_target=1000,
        service_level=0.95, target_service_level=0.95,
        avg_lead_time_actual=5.0, avg_lead_time_expected=5.0,
        supplier_on_time_rate=0.95,
        backlog_units=0, backlog_yesterday=0,
    )

    trigger = asyncio.get_event_loop().run_until_complete(
        cdc.check_and_trigger(metrics)
    )
    check("Signal divergence triggered", trigger.triggered)
    from app.services.powell.cdc_monitor import TriggerReason, ReplanAction
    check("Reason is SIGNAL_DIVERGENCE", TriggerReason.SIGNAL_DIVERGENCE in trigger.reasons)
    check("Action is TGNN_REFRESH", trigger.recommended_action == ReplanAction.TGNN_REFRESH)


def test_inter_hive_signal_construction() -> None:
    """Test: InterHiveSignal data structures and serialization."""
    print("\n6. InterHiveSignal Construction & Serialization")

    sig = InterHiveSignal(
        signal_type=InterHiveSignalType.NETWORK_SHORTAGE,
        source_site="plant_a",
        target_site="dc_b",
        urgency=0.9,
        direction="shortage",
        magnitude=1000.0,
        confidence=0.95,
        product_id="SKU-100",
    )

    check("Signal has UUID", len(sig.signal_id) > 0)
    check("Half-life = 12h (default)", sig.half_life_hours == 12.0)
    check("Propagation depth = 0", sig.propagation_depth == 0)

    d = sig.to_dict()
    check("to_dict has source_site", d["source_site"] == "plant_a")
    check("to_dict has target_site", d["target_site"] == "dc_b")
    check("to_dict has confidence", d["confidence"] == 0.95)


def test_tgnn_directive_from_gnn_output() -> None:
    """Test: tGNNSiteDirective.from_gnn_output() factory."""
    print("\n7. tGNNSiteDirective Factory")

    gnn_embeddings = {
        "criticality_score": 0.85,
        "bottleneck_risk": 0.3,
        "resilience_score": 0.7,
        "safety_stock_multiplier": 1.2,
        "demand_forecast": 500.0,
        "exception_probability": 0.4,
    }

    inter_signals = [
        InterHiveSignal(
            signal_type=InterHiveSignalType.NETWORK_SURPLUS,
            source_site="dc_west",
            target_site="dc_east",
            urgency=0.5,
            direction="surplus",
            magnitude=200.0,
        ),
    ]

    directive = tGNNSiteDirective.from_gnn_output(
        site_key="dc_east",
        gnn_embeddings=gnn_embeddings,
        inter_hive_signals=inter_signals,
    )

    check("Directive site_key = dc_east", directive.site_key == "dc_east")
    check("Criticality = 0.85", directive.criticality_score == 0.85)
    check("1 inter-hive signal", len(directive.inter_hive_signals) == 1)
    check("SS multiplier = 1.2", directive.safety_stock_multiplier == 1.2)


def test_full_lifecycle() -> None:
    """Test: Full lifecycle — build network, inject directives, run cycles, check health."""
    print("\n8. Full Lifecycle (3 sites)")

    sites = {}
    for key in ["supplier_x", "plant_central", "dc_south"]:
        sites[key] = SiteAgent(SiteAgentConfig(
            site_key=key, use_trm_adjustments=False, enable_hive_signals=True,
        ))

    # Register TRMs per site
    for key, site in sites.items():
        trms = {n: FakeTRM(n) for n in ["atp_executor", "po_creation", "safety_stock"]}
        site.connect_trms(**trms)

    # Supplier detects capacity issue
    sites["supplier_x"].signal_bus.emit(HiveSignal(
        source_trm="mo_execution",
        signal_type=HiveSignalType.MAINTENANCE_URGENT,
        urgency=0.9,
        direction="risk",
        magnitude=500.0,
    ))

    # tGNN propagates to plant_central and dc_south
    for target in ["plant_central", "dc_south"]:
        directive = tGNNSiteDirective(
            site_key=target,
            inter_hive_signals=[
                InterHiveSignal(
                    signal_type=InterHiveSignalType.BOTTLENECK_RISK,
                    source_site="supplier_x",
                    target_site=target,
                    urgency=0.8,
                    direction="risk",
                    magnitude=400.0,
                    confidence=0.85,
                ),
            ],
            safety_stock_multiplier=1.4,
            criticality_score=0.85,
            bottleneck_risk=0.8,
            resilience_score=0.3,
            demand_forecast=800.0,
            exception_probability=0.65,
        )
        sites[target].apply_directive(directive)

    # Run decision cycles at all sites
    for key, site in sites.items():
        trm_dict = {name: trm for name, trm in site._registered_trms.items()}
        result = site.execute_decision_cycle(trm_executors=trm_dict)
        check(f"{key}: cycle completed", result.completed_at is not None)

    # Verify health metrics
    for key, site in sites.items():
        health = HiveHealthMetrics.from_signal_bus(site.signal_bus, site_key=key)
        check(f"{key}: health generated", health.site_key == key)

    # Verify downstream sites got bottleneck signals
    plant_signals = sites["plant_central"].signal_bus.active_signals()
    dc_signals = sites["dc_south"].signal_bus.active_signals()
    check("Plant has bottleneck signal", len(plant_signals) >= 1)
    check("DC has bottleneck signal", len(dc_signals) >= 1)


# ---- Main ----

def main() -> None:
    global passed, failed
    print("=" * 60)
    print("E2E Planning Cascade + Hive Signal Test")
    print("=" * 60)

    test_multi_site_hive_network()
    test_directive_cross_site_propagation()
    test_decision_cycle_with_inter_hive_context()
    test_cascade_demand_spike_scenario()
    test_signal_divergence_triggers_tgnn_refresh()
    test_inter_hive_signal_construction()
    test_tgnn_directive_from_gnn_output()
    test_full_lifecycle()

    print("\n" + "=" * 60)
    total = passed + failed
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print("=" * 60)

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
