#!/usr/bin/env python3
"""C13: Site Agent Decision Cycle Validation

Verifies:
1. SiteAgent class can be imported and constructed with SiteAgentConfig
2. The 6 decision cycle phases are defined (SENSE..REFLECT)
3. All 11 TRMs map to one of the 6 phases
4. SiteAgentConfig has required fields
5. site_capabilities maps master_types to TRM sets correctly
"""

import os
import sys

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


print("=" * 60)
print("C13: Site Agent Decision Cycle Validation")
print("=" * 60)

# ---------------------------------------------------------------------------
# 1. Import SiteAgent and SiteAgentConfig
# ---------------------------------------------------------------------------
print("\n-- 1. SiteAgent import and construction --")
try:
    from app.services.powell.site_agent import SiteAgent, SiteAgentConfig
    check("SiteAgent import", True)
    check("SiteAgentConfig import", True)
except Exception as e:
    check("SiteAgent / SiteAgentConfig import", False, str(e))
    print("\nFAIL (cannot proceed without imports)")
    sys.exit(1)

# Construct with minimal config
try:
    cfg = SiteAgentConfig(site_key="TEST_SITE_001")
    check("SiteAgentConfig construction", True)
except Exception as e:
    check("SiteAgentConfig construction", False, str(e))

try:
    agent = SiteAgent(config=SiteAgentConfig(site_key="TEST_SITE_001"))
    check("SiteAgent construction", True)
except Exception as e:
    check("SiteAgent construction", False, str(e))

# ---------------------------------------------------------------------------
# 2. Six decision cycle phases
# ---------------------------------------------------------------------------
print("\n-- 2. Decision cycle phases --")
try:
    from app.services.powell.decision_cycle import (
        DecisionCyclePhase, TRM_PHASE_MAP, PHASE_TRM_MAP,
        CycleResult, PhaseResult, detect_conflicts,
    )
    check("DecisionCyclePhase import", True)
except Exception as e:
    check("DecisionCyclePhase import", False, str(e))
    print("\nFAIL (cannot proceed without decision_cycle)")
    sys.exit(1)

expected_phases = ["SENSE", "ASSESS", "ACQUIRE", "PROTECT", "BUILD", "REFLECT"]
actual_phases = [p.name for p in DecisionCyclePhase]
check("6 phases defined", len(actual_phases) == 6, f"got {len(actual_phases)}: {actual_phases}")
for phase_name in expected_phases:
    check(f"Phase {phase_name} exists", phase_name in actual_phases)

# Phase ordering: SENSE=1 .. REFLECT=6
check("SENSE < REFLECT", DecisionCyclePhase.SENSE < DecisionCyclePhase.REFLECT)
check("Phase values 1-6", [int(p) for p in DecisionCyclePhase] == [1, 2, 3, 4, 5, 6])

# ---------------------------------------------------------------------------
# 3. All 11 TRMs map to a phase
# ---------------------------------------------------------------------------
print("\n-- 3. TRM-to-phase mapping --")
CANONICAL_TRMS = {
    "atp_executor", "order_tracking",
    "inventory_buffer", "forecast_adjustment", "quality_disposition",
    "po_creation", "subcontracting",
    "maintenance_scheduling",
    "mo_execution", "to_execution",
    "rebalancing",
}

# Every canonical TRM must appear in TRM_PHASE_MAP
for trm in sorted(CANONICAL_TRMS):
    check(f"{trm} has phase mapping", trm in TRM_PHASE_MAP,
          f"missing from TRM_PHASE_MAP")

# Every phase must have at least one TRM
for phase in DecisionCyclePhase:
    trms_in_phase = PHASE_TRM_MAP.get(phase, [])
    check(f"Phase {phase.name} has TRMs", len(trms_in_phase) > 0,
          f"empty phase")

# Verify expected phase assignments
expected_assignments = {
    "atp_executor": "SENSE",
    "order_tracking": "SENSE",
    "inventory_buffer": "ASSESS",
    "forecast_adjustment": "ASSESS",
    "quality_disposition": "ASSESS",
    "po_creation": "ACQUIRE",
    "subcontracting": "ACQUIRE",
    "maintenance_scheduling": "PROTECT",
    "mo_execution": "BUILD",
    "to_execution": "BUILD",
    "rebalancing": "REFLECT",
}
for trm, expected_phase in expected_assignments.items():
    actual = TRM_PHASE_MAP.get(trm)
    if actual is not None:
        check(f"{trm} -> {expected_phase}",
              actual.name == expected_phase,
              f"got {actual.name}")
    else:
        check(f"{trm} -> {expected_phase}", False, "not in map")

# ---------------------------------------------------------------------------
# 4. SiteAgentConfig required fields
# ---------------------------------------------------------------------------
print("\n-- 4. SiteAgentConfig fields --")
required_fields = [
    "site_key", "config_id" if hasattr(SiteAgentConfig, "config_id") else None,
    "tenant_id", "use_trm_adjustments", "agent_mode",
    "enable_hive_signals", "enable_authorization",
    "use_claude_skills", "skill_escalation_threshold",
    "enable_vertical_escalation", "enable_site_tgnn",
    "master_type", "sc_site_type",
]
# Filter None (config_id check)
required_fields = [f for f in required_fields if f is not None]

import dataclasses
if dataclasses.is_dataclass(SiteAgentConfig):
    field_names = {f.name for f in dataclasses.fields(SiteAgentConfig)}
else:
    field_names = set(dir(SiteAgentConfig))

for fname in required_fields:
    check(f"SiteAgentConfig.{fname}", fname in field_names)

# site_key is required (no default)
try:
    bad_cfg = SiteAgentConfig()  # Should fail — site_key has no default
    check("site_key is required (no default)", False, "constructed without site_key")
except TypeError:
    check("site_key is required (no default)", True)

# ---------------------------------------------------------------------------
# 5. site_capabilities master_type mapping
# ---------------------------------------------------------------------------
print("\n-- 5. site_capabilities module --")
try:
    from app.services.powell.site_capabilities import (
        get_active_trms, ALL_TRM_NAMES, is_trm_active,
    )
    check("site_capabilities import", True)
except Exception as e:
    check("site_capabilities import", False, str(e))
    print(f"\n{'PASS' if failed == 0 else 'FAIL'}")
    sys.exit(0 if failed == 0 else 1)

check("ALL_TRM_NAMES has 11 entries", len(ALL_TRM_NAMES) == 11,
      f"got {len(ALL_TRM_NAMES)}")

# Manufacturer gets all 11
mfg_trms = get_active_trms("manufacturer")
check("manufacturer: 11 TRMs", len(mfg_trms) == 11, f"got {len(mfg_trms)}")
check("manufacturer: all TRMs == ALL_TRM_NAMES", mfg_trms == ALL_TRM_NAMES)

# Inventory (DC) gets subset — no MO, Quality, Maintenance, Subcontracting
inv_trms = get_active_trms("inventory")
check("inventory: 7 TRMs", len(inv_trms) == 7, f"got {len(inv_trms)}: {sorted(inv_trms)}")
for excluded in ["mo_execution", "quality_disposition", "maintenance_scheduling", "subcontracting"]:
    check(f"inventory: no {excluded}", excluded not in inv_trms)

# Retailer override — 6 TRMs (no PO)
ret_trms = get_active_trms("inventory", sc_site_type="RETAILER")
check("RETAILER: 6 TRMs", len(ret_trms) == 6, f"got {len(ret_trms)}: {sorted(ret_trms)}")
check("RETAILER: no po_creation", "po_creation" not in ret_trms)

# Vendor/customer — external, no TRMs
vendor_trms = get_active_trms("vendor")
check("vendor: 0 TRMs", len(vendor_trms) == 0, f"got {len(vendor_trms)}")

customer_trms = get_active_trms("customer")
check("customer: 0 TRMs", len(customer_trms) == 0, f"got {len(customer_trms)}")

# Legacy compatibility
legacy_vendor = get_active_trms("market_supply")
check("market_supply (legacy) maps to vendor", legacy_vendor == vendor_trms)

legacy_customer = get_active_trms("market_demand")
check("market_demand (legacy) maps to customer", legacy_customer == customer_trms)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
total = passed + failed
print(f"C13 Result: {passed}/{total} passed, {failed} failed")
if failed == 0:
    print("PASS")
    sys.exit(0)
else:
    print("FAIL")
    sys.exit(1)
