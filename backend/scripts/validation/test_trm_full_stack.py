#!/usr/bin/env python3
"""C12: TRM Full Stack Validation

Verifies all 11 TRM types can be imported, have correct engine associations,
output schemas match powell_*_decisions table columns, and risk_bound /
decision_reasoning fields are present.
"""

import os
import sys
import inspect

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

passed = 0
failed = 0


def check(label, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS: {label}")
        passed += 1
    else:
        print(f"  FAIL: {label} {detail}")
        failed += 1


# ---------------------------------------------------------------------------
# TRM class → module path, expected engine import, decision table class
# ---------------------------------------------------------------------------
TRM_SPECS = {
    "atp_executor": {
        "module": "app.services.powell.atp_executor",
        "class": "ATPExecutorTRM",
        "engine_module": "app.services.powell.engines.aatp_engine",
        "engine_class": "AATPEngine",
        "decision_model": "PowellATPDecision",
        "table": "powell_atp_decisions",
    },
    "inventory_rebalancing": {
        "module": "app.services.powell.inventory_rebalancing_trm",
        "class": "InventoryRebalancingTRM",
        "engine_module": "app.services.powell.engines.rebalancing_engine",
        "engine_class": "RebalancingEngine",
        "decision_model": "PowellRebalanceDecision",
        "table": "powell_rebalance_decisions",
    },
    # po_creation entry removed: POCreationTRM replaced by TMS's
    # FreightProcurementTRM (ACQUIRE phase). See .claude/rules/trm-mapping.md.
    "order_tracking": {
        "module": "app.services.powell.order_tracking_trm",
        "class": "OrderTrackingTRM",
        "engine_module": "app.services.powell.engines.order_tracking_engine",
        "engine_class": "OrderTrackingEngine",
        "decision_model": "PowellOrderException",
        "table": "powell_order_exceptions",
    },
    "mo_execution": {
        "module": "app.services.powell.mo_execution_trm",
        "class": "MOExecutionTRM",
        "engine_module": "app.services.powell.engines.mo_execution_engine",
        "engine_class": "MOExecutionEngine",
        "decision_model": "PowellMODecision",
        "table": "powell_mo_decisions",
    },
    "to_execution": {
        "module": "app.services.powell.to_execution_trm",
        "class": "TOExecutionTRM",
        "engine_module": "app.services.powell.engines.to_execution_engine",
        "engine_class": "TOExecutionEngine",
        "decision_model": "PowellTODecision",
        "table": "powell_to_decisions",
    },
    "quality_disposition": {
        "module": "app.services.powell.quality_disposition_trm",
        "class": "QualityDispositionTRM",
        "engine_module": "app.services.powell.engines.quality_engine",
        "engine_class": "QualityEngine",
        "decision_model": "PowellQualityDecision",
        "table": "powell_quality_decisions",
    },
    "maintenance_scheduling": {
        "module": "app.services.powell.maintenance_scheduling_trm",
        "class": "MaintenanceSchedulingTRM",
        "engine_module": "app.services.powell.engines.maintenance_engine",
        "engine_class": "MaintenanceEngine",
        "decision_model": "PowellMaintenanceDecision",
        "table": "powell_maintenance_decisions",
    },
    "subcontracting": {
        "module": "app.services.powell.subcontracting_trm",
        "class": "SubcontractingTRM",
        "engine_module": "app.services.powell.engines.subcontracting_engine",
        "engine_class": "SubcontractingEngine",
        "decision_model": "PowellSubcontractingDecision",
        "table": "powell_subcontracting_decisions",
    },
    "forecast_adjustment": {
        "module": "app.services.powell.forecast_adjustment_trm",
        "class": "ForecastAdjustmentTRM",
        "engine_module": "app.services.powell.engines.forecast_adjustment_engine",
        "engine_class": "ForecastAdjustmentEngine",
        "decision_model": "PowellForecastAdjustmentDecision",
        "table": "powell_forecast_adjustment_decisions",
    },
    "inventory_buffer": {
        "module": "app.services.powell.inventory_buffer_trm",
        "class": "InventoryBufferTRM",
        "engine_module": None,  # Uses BufferCalculator directly, no separate engine
        "engine_class": None,
        "decision_model": "PowellBufferDecision",
        "table": "powell_buffer_decisions",
    },
}

print("=" * 60)
print("C12: TRM Full Stack Validation")
print("=" * 60)

# ---------------------------------------------------------------------------
# 1. Import all 11 TRM classes
# ---------------------------------------------------------------------------
print("\n-- 1. TRM class imports --")
trm_classes = {}
for trm_name, spec in TRM_SPECS.items():
    try:
        mod = __import__(spec["module"], fromlist=[spec["class"]])
        cls = getattr(mod, spec["class"])
        trm_classes[trm_name] = cls
        check(f"{trm_name}: import {spec['class']}", True)
    except Exception as e:
        trm_classes[trm_name] = None
        check(f"{trm_name}: import {spec['class']}", False, str(e))

# ---------------------------------------------------------------------------
# 2. Engine type association — verify each TRM module imports its engine
# ---------------------------------------------------------------------------
print("\n-- 2. Engine type associations --")
for trm_name, spec in TRM_SPECS.items():
    if spec["engine_module"] is None:
        # inventory_buffer uses no separate engine module
        check(f"{trm_name}: no dedicated engine (uses BufferCalculator)", True)
        continue
    try:
        mod = __import__(spec["engine_module"], fromlist=[spec["engine_class"]])
        engine_cls = getattr(mod, spec["engine_class"])
        check(f"{trm_name}: engine {spec['engine_class']}", engine_cls is not None)
    except Exception as e:
        check(f"{trm_name}: engine {spec['engine_class']}", False, str(e))

# ---------------------------------------------------------------------------
# 3. Decision table column matching — verify decision model exists and has
#    columns expected by the TRM output (confidence, created_at, config_id)
# ---------------------------------------------------------------------------
print("\n-- 3. Decision table schema --")
try:
    import app.models.powell_decisions as pdm
    DECISION_MODELS_AVAILABLE = True
except ImportError as e:
    DECISION_MODELS_AVAILABLE = False
    check("import powell_decisions models", False, str(e))

if DECISION_MODELS_AVAILABLE:
    for trm_name, spec in TRM_SPECS.items():
        model_name = spec["decision_model"]
        model_cls = getattr(pdm, model_name, None)
        check(f"{trm_name}: model {model_name} exists", model_cls is not None)
        if model_cls is None:
            continue

        # Verify __tablename__
        check(
            f"{trm_name}: table = {spec['table']}",
            getattr(model_cls, "__tablename__", None) == spec["table"],
            f"got {getattr(model_cls, '__tablename__', 'MISSING')}",
        )

        # Every decision table must have these base columns
        required_cols = ["id", "config_id", "confidence", "created_at"]
        table_cols = set()
        if hasattr(model_cls, "__table__"):
            table_cols = {c.name for c in model_cls.__table__.columns}
        for col in required_cols:
            check(
                f"{trm_name}: column '{col}'",
                col in table_cols,
                f"missing from {spec['table']}",
            )

# ---------------------------------------------------------------------------
# 4. HiveSignalMixin fields — risk_bound (via CDT) is on the response
#    dataclass, decision_reasoning is on the DB model (HiveSignalMixin)
# ---------------------------------------------------------------------------
print("\n-- 4. risk_bound and decision_reasoning --")
if DECISION_MODELS_AVAILABLE:
    for trm_name, spec in TRM_SPECS.items():
        model_cls = getattr(pdm, spec["decision_model"], None)
        if model_cls is None:
            check(f"{trm_name}: decision_reasoning column", False, "model missing")
            continue
        table_cols = set()
        if hasattr(model_cls, "__table__"):
            table_cols = {c.name for c in model_cls.__table__.columns}
        check(
            f"{trm_name}: decision_reasoning column",
            "decision_reasoning" in table_cols,
        )

    # risk_bound lives on ATPResponse / recommendation dataclasses, not the DB
    # Verify the mixin has signal_context (part of HiveSignalMixin alongside
    # decision_reasoning)
    mixin = getattr(pdm, "HiveSignalMixin", None)
    check("HiveSignalMixin exists", mixin is not None)
    if mixin:
        check(
            "HiveSignalMixin has decision_reasoning",
            hasattr(mixin, "decision_reasoning"),
        )
        check(
            "HiveSignalMixin has signal_context",
            hasattr(mixin, "signal_context"),
        )

    # risk_bound on ATP response dataclass
    try:
        from app.services.powell.atp_executor import ATPResponse as ATPResp
        fields = {f for f in dir(ATPResp) if not f.startswith("_")}
        check("ATPResponse has risk_bound", "risk_bound" in fields)
        check("ATPResponse has risk_assessment", "risk_assessment" in fields)
    except Exception as e:
        check("ATPResponse risk_bound import", False, str(e))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
total = passed + failed
print(f"C12 Result: {passed}/{total} passed, {failed} failed")
if failed == 0:
    print("PASS")
    sys.exit(0)
else:
    print("FAIL")
    sys.exit(1)
