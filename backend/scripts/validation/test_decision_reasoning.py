#!/usr/bin/env python3
"""G4: Decision Reasoning Generators Validation"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Direct module load to avoid powell/__init__.py (which triggers DB config)
_POWELL_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "app", "services", "powell"
)


def _load_module(name, filepath):
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_dr = _load_module(
    "decision_reasoning", os.path.join(_POWELL_DIR, "decision_reasoning.py")
)

atp_reasoning = _dr.atp_reasoning
po_reasoning = _dr.po_reasoning
rebalancing_reasoning = _dr.rebalancing_reasoning
order_tracking_reasoning = _dr.order_tracking_reasoning
mo_execution_reasoning = _dr.mo_execution_reasoning
to_execution_reasoning = _dr.to_execution_reasoning
quality_reasoning = _dr.quality_reasoning
maintenance_reasoning = _dr.maintenance_reasoning
subcontracting_reasoning = _dr.subcontracting_reasoning
forecast_adjustment_reasoning = _dr.forecast_adjustment_reasoning
inventory_buffer_reasoning = _dr.inventory_buffer_reasoning
sop_graphsage_reasoning = _dr.sop_graphsage_reasoning
execution_tgnn_reasoning = _dr.execution_tgnn_reasoning
site_tgnn_reasoning = _dr.site_tgnn_reasoning
capture_hive_context = _dr.capture_hive_context

passed = 0
failed = 0
errors = []


def test(name, condition, detail=""):
    global passed, failed, errors
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  FAIL: {name} -- {detail}")


if __name__ == "__main__":
    print(f"\n{'='*60}")
    print("G4: Decision Reasoning Generators Validation")
    print(f"{'='*60}")

    # ── Test 1: All 11 TRM reasoning generators exist and are callable ──
    print("\n[Test 1] All 11 TRM reasoning generators exist and callable")
    trm_generators = {
        "atp_executor": atp_reasoning,
        "po_creation": po_reasoning,
        "rebalancing": rebalancing_reasoning,
        "order_tracking": order_tracking_reasoning,
        "mo_execution": mo_execution_reasoning,
        "to_execution": to_execution_reasoning,
        "quality_disposition": quality_reasoning,
        "maintenance_scheduling": maintenance_reasoning,
        "subcontracting": subcontracting_reasoning,
        "forecast_adjustment": forecast_adjustment_reasoning,
        "inventory_buffer": inventory_buffer_reasoning,
    }
    for name_key, func in trm_generators.items():
        test(
            f"{name_key} reasoning generator exists",
            callable(func),
            f"Not callable: {type(func)}",
        )

    # ── Test 2: Each generator produces non-empty string output ───────
    print("\n[Test 2] Each generator produces non-empty string output")

    # ATP (partial fulfillment path)
    atp_result = atp_reasoning(
        product_id="SKU_001",
        location_id="DC_WEST",
        requested_qty=100,
        promised_qty=80,
        can_fulfill=False,
        order_priority=2,
        confidence=0.85,
        decision_method="trm",
    )
    test(
        "atp_reasoning returns non-empty string",
        isinstance(atp_result, str) and len(atp_result) > 20,
        f"Got: {repr(atp_result[:50])}",
    )

    # ATP (full fulfillment path)
    atp_full = atp_reasoning(
        product_id="SKU_002",
        location_id="DC_EAST",
        requested_qty=50,
        promised_qty=50,
        can_fulfill=True,
        order_priority=1,
        confidence=0.95,
        decision_method="heuristic",
        unit_price=12.50,
    )
    test(
        "atp_reasoning full fulfillment path works",
        isinstance(atp_full, str) and "SKU_002" in atp_full,
        f"Got: {repr(atp_full[:50])}",
    )

    # PO
    po_result = po_reasoning(
        product_id="MAT_100",
        location_id="PLANT_01",
        supplier_id="VENDOR_A",
        recommended_qty=500,
        trigger_reason="below_reorder_point",
        urgency="high",
        confidence=0.92,
        inventory_position=120.0,
        expected_cost=5000.0,
        unit_cost=10.0,
    )
    test(
        "po_reasoning returns non-empty string",
        isinstance(po_result, str) and len(po_result) > 20,
        f"Got: {repr(po_result[:50])}",
    )

    # Rebalancing
    reb_result = rebalancing_reasoning(
        product_id="FG_200",
        from_site="DC_EAST",
        to_site="DC_WEST",
        recommended_qty=150,
        confidence=0.78,
        from_inventory=800.0,
        to_inventory=50.0,
    )
    test(
        "rebalancing_reasoning returns non-empty string",
        isinstance(reb_result, str) and len(reb_result) > 20,
        f"Got: {repr(reb_result[:50])}",
    )

    # Order Tracking
    ot_result = order_tracking_reasoning(
        order_id="PO_12345",
        exception_type="LATE_DELIVERY",
        severity="high",
        recommended_action="expedite",
        confidence=0.70,
        reason="Supplier delayed shipment by 3 days",
        estimated_impact_cost=15000.0,
    )
    test(
        "order_tracking_reasoning returns non-empty string",
        isinstance(ot_result, str) and len(ot_result) > 20,
        f"Got: {repr(ot_result[:50])}",
    )

    # MO Execution
    mo_result = mo_execution_reasoning(
        product_id="FG_500",
        location_id="PLANT_01",
        decision_type="release",
        confidence=0.88,
        mo_id="MO_001",
        unit_cost=25.0,
        quantity=200.0,
    )
    test(
        "mo_execution_reasoning returns non-empty string",
        isinstance(mo_result, str) and len(mo_result) > 20,
        f"Got: {repr(mo_result[:50])}",
    )

    # TO Execution
    to_result = to_execution_reasoning(
        product_id="FG_300",
        source_site_id="DC_EAST",
        dest_site_id="DC_WEST",
        decision_type="release",
        confidence=0.85,
        to_id="TO_001",
        unit_cost=15.0,
        quantity=300.0,
        transfer_cost=450.0,
    )
    test(
        "to_execution_reasoning returns non-empty string",
        isinstance(to_result, str) and len(to_result) > 20,
        f"Got: {repr(to_result[:50])}",
    )

    # Quality
    qual_result = quality_reasoning(
        product_id="RAW_100",
        location_id="PLANT_01",
        disposition="accept",
        confidence=0.90,
        lot_id="LOT_2026_001",
        unit_cost=8.0,
        quantity=500.0,
    )
    test(
        "quality_reasoning returns non-empty string",
        isinstance(qual_result, str) and len(qual_result) > 20,
        f"Got: {repr(qual_result[:50])}",
    )

    # Maintenance
    maint_result = maintenance_reasoning(
        asset_id="MACHINE_A",
        location_id="PLANT_01",
        decision_type="schedule",
        confidence=0.80,
        reason="Preventive maintenance interval reached",
        estimated_maintenance_cost=2500.0,
        estimated_downtime_hours=4.0,
        hourly_production_value=1200.0,
    )
    test(
        "maintenance_reasoning returns non-empty string",
        isinstance(maint_result, str) and len(maint_result) > 20,
        f"Got: {repr(maint_result[:50])}",
    )

    # Subcontracting
    sub_result = subcontracting_reasoning(
        product_id="COMP_100",
        routing_decision="external",
        confidence=0.75,
        external_supplier="EXT_MFG_01",
        reason="Internal capacity fully committed",
        quantity=1000.0,
        internal_cost_per_unit=12.0,
        external_cost_per_unit=15.0,
    )
    test(
        "subcontracting_reasoning returns non-empty string",
        isinstance(sub_result, str) and len(sub_result) > 20,
        f"Got: {repr(sub_result[:50])}",
    )

    # Forecast Adjustment
    fa_result = forecast_adjustment_reasoning(
        product_id="FG_100",
        adjustment_direction="up",
        adjustment_pct=15.0,
        confidence=0.82,
        signal_type="demand_increase",
        current_value=1000.0,
        adjusted_value=1150.0,
        unit_cost=10.0,
        unit_price=18.0,
    )
    test(
        "forecast_adjustment_reasoning returns non-empty string",
        isinstance(fa_result, str) and len(fa_result) > 20,
        f"Got: {repr(fa_result[:50])}",
    )

    # Inventory Buffer
    ib_result = inventory_buffer_reasoning(
        product_id="SKU_050",
        location_id="DC_CENTRAL",
        baseline_ss=200.0,
        adjusted_ss=280.0,
        multiplier=1.4,
        confidence=0.88,
        reason="demand_variability_increase",
        unit_cost=20.0,
        unit_price=35.0,
    )
    test(
        "inventory_buffer_reasoning returns non-empty string",
        isinstance(ib_result, str) and len(ib_result) > 20,
        f"Got: {repr(ib_result[:50])}",
    )

    # ── Test 3: GNN reasoning generators exist and work ───────────────
    print(
        "\n[Test 3] GNN reasoning generators"
        " (sop_graphsage, execution_tgnn, site_tgnn)"
    )

    test(
        "sop_graphsage_reasoning is callable",
        callable(sop_graphsage_reasoning),
        f"Not callable: {type(sop_graphsage_reasoning)}",
    )
    test(
        "execution_tgnn_reasoning is callable",
        callable(execution_tgnn_reasoning),
        f"Not callable: {type(execution_tgnn_reasoning)}",
    )
    test(
        "site_tgnn_reasoning is callable",
        callable(site_tgnn_reasoning),
        f"Not callable: {type(site_tgnn_reasoning)}",
    )

    sop_result = sop_graphsage_reasoning(
        site_key="PLANT_01",
        criticality=0.85,
        bottleneck_risk=0.3,
        concentration_risk=0.6,
        resilience=0.7,
        safety_stock_multiplier=1.2,
    )
    test(
        "sop_graphsage_reasoning returns non-empty string",
        isinstance(sop_result, str) and len(sop_result) > 20,
        f"Got: {repr(sop_result[:50])}",
    )
    test(
        "sop_graphsage_reasoning mentions site_key",
        "PLANT_01" in sop_result,
        "Site key not found in reasoning",
    )

    exec_result = execution_tgnn_reasoning(
        site_key="DC_WEST",
        demand_forecast_next=1500.0,
        exception_probability=0.15,
        order_recommendation=1200.0,
        confidence=0.88,
    )
    test(
        "execution_tgnn_reasoning returns non-empty string",
        isinstance(exec_result, str) and len(exec_result) > 20,
        f"Got: {repr(exec_result[:50])}",
    )
    test(
        "execution_tgnn_reasoning mentions site_key",
        "DC_WEST" in exec_result,
        "Site key not found in reasoning",
    )

    site_result = site_tgnn_reasoning(
        site_key="PLANT_01",
        urgency_adjustments={"atp_executor": 0.1, "po_creation": -0.05},
        confidence_modifiers={"atp_executor": 0.02},
        coordination_signals={"atp_executor": 0.8},
    )
    test(
        "site_tgnn_reasoning returns non-empty string",
        isinstance(site_result, str) and len(site_result) > 20,
        f"Got: {repr(site_result[:50])}",
    )
    test(
        "site_tgnn_reasoning mentions site_key",
        "PLANT_01" in site_result,
        "Site key not found in reasoning",
    )

    # ── Test 4: Reasoning text includes relevant context ──────────────
    print("\n[Test 4] Reasoning text includes relevant context")

    test(
        "ATP reasoning includes product_id",
        "SKU_001" in atp_result,
        "Product ID not found",
    )
    test(
        "ATP reasoning includes location_id",
        "DC_WEST" in atp_result,
        "Location not found",
    )
    test(
        "PO reasoning includes product_id",
        "MAT_100" in po_result,
        "Product not found",
    )
    test(
        "PO reasoning includes supplier_id",
        "VENDOR_A" in po_result,
        "Supplier not found",
    )
    test(
        "Rebalancing reasoning includes both sites",
        "DC_EAST" in reb_result and "DC_WEST" in reb_result,
        "Sites not found",
    )
    test(
        "Rebalancing reasoning includes quantity",
        "150" in reb_result,
        "Quantity not found",
    )
    test(
        "Order tracking reasoning includes order_id",
        "PO_12345" in ot_result,
        "Order ID not found",
    )
    test(
        "MO reasoning includes mo_id and location",
        "MO_001" in mo_result and "PLANT_01" in mo_result,
        "MO ID/location not found",
    )
    test(
        "TO reasoning includes source and dest sites",
        "DC_EAST" in to_result and "DC_WEST" in to_result,
        "Sites not found",
    )
    test(
        "Quality reasoning includes lot_id",
        "LOT_2026_001" in qual_result,
        "Lot ID not found",
    )
    test(
        "Maintenance reasoning includes asset_id",
        "MACHINE_A" in maint_result,
        "Asset ID not found",
    )
    test(
        "Subcontracting reasoning includes product_id",
        "COMP_100" in sub_result,
        "Product not found",
    )
    test(
        "Subcontracting reasoning includes external supplier",
        "EXT_MFG_01" in sub_result,
        "External supplier not found",
    )
    test(
        "Forecast adjustment reasoning includes product_id",
        "FG_100" in fa_result,
        "Product not found",
    )
    test(
        "Forecast adjustment reasoning includes direction",
        "up" in fa_result.lower(),
        "Direction not found",
    )
    test(
        "Inventory buffer reasoning includes product and location",
        "SKU_050" in ib_result and "DC_CENTRAL" in ib_result,
        "Product/location not found",
    )
    test(
        "ATP partial references shortfall",
        "shortfall" in atp_result.lower() or "partial" in atp_result.lower(),
        "No mention of shortfall or partial fulfillment",
    )
    test(
        "PO reasoning references urgency",
        "high" in po_result.lower(),
        "Urgency not found",
    )
    test(
        "Quality reasoning references disposition type",
        "accept" in qual_result.lower(),
        "Disposition type not found",
    )
    test(
        "Maintenance reasoning references decision type",
        "schedule" in maint_result.lower(),
        "Decision type not found",
    )
    test(
        "Inventory buffer reasoning references direction",
        "increased" in ib_result.lower() or "decreased" in ib_result.lower(),
        "Buffer direction not found",
    )

    # ── Test 5: capture_hive_context helper ────────────────────────────
    print("\n[Test 5] capture_hive_context helper")
    test(
        "capture_hive_context is callable",
        callable(capture_hive_context),
        f"Not callable: {type(capture_hive_context)}",
    )

    hive_ctx = capture_hive_context(signal_bus=None, trm_name="atp_executor")
    test(
        "capture_hive_context returns dict with expected keys",
        isinstance(hive_ctx, dict)
        and "signal_context" in hive_ctx
        and "urgency_at_time" in hive_ctx
        and "triggered_by" in hive_ctx
        and "cycle_phase" in hive_ctx
        and "cycle_id" in hive_ctx,
        f"Got keys: {list(hive_ctx.keys()) if isinstance(hive_ctx, dict) else type(hive_ctx)}",
    )
    test(
        "capture_hive_context with None bus returns None values",
        hive_ctx.get("signal_context") is None
        and hive_ctx.get("urgency_at_time") is None,
        "Expected None values for signal_context and urgency_at_time",
    )

    hive_ctx2 = capture_hive_context(
        signal_bus=None,
        trm_name="po_creation",
        cycle_id="abc-123",
        cycle_phase="BUILD",
    )
    test(
        "capture_hive_context preserves cycle metadata",
        hive_ctx2.get("cycle_id") == "abc-123"
        and hive_ctx2.get("cycle_phase") == "BUILD",
        f"cycle_id={hive_ctx2.get('cycle_id')},"
        f" cycle_phase={hive_ctx2.get('cycle_phase')}",
    )

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if errors:
        print("Failures:")
        for e in errors:
            print(f"  - {e}")
    print(f"{'='*60}")
    sys.exit(0 if failed == 0 else 1)
