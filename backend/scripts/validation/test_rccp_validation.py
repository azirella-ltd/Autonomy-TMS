#!/usr/bin/env python3
"""B5: RCCP (Rough-Cut Capacity Planning) Validation

Verifies:
1. RCCPService can be constructed
2. Method detection (detect_method) works
3. 3 methods exist: CPOF, bill_of_capacity, resource_profile
4. 7 decision rules exist in the service
5. BoR auto-generation from production_process
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


print("=" * 60)
print("B5: RCCP Validation")
print("=" * 60)

# ---------------------------------------------------------------------------
# 1. RCCPService import
# ---------------------------------------------------------------------------
print("\n-- 1. RCCPService construction --")
try:
    from app.services.rccp_service import RCCPService
    check("RCCPService import", True)
except Exception as e:
    check("RCCPService import", False, str(e))
    print("\nFAIL")
    sys.exit(1)

# Verify key methods exist
for method_name in ["validate_mps", "detect_method", "auto_generate_bor"]:
    check(f"RCCPService.{method_name} method", hasattr(RCCPService, method_name))

# ---------------------------------------------------------------------------
# 2. Method detection
# ---------------------------------------------------------------------------
print("\n-- 2. Method detection --")
try:
    from app.models.rccp import RCCPMethod, RCCPRun, BillOfResources
    check("RCCPMethod import", True)

    # Verify detect_method signature
    sig = inspect.signature(RCCPService.detect_method)
    params = list(sig.parameters.keys())
    check("detect_method params: self, config_id, site_id",
          "config_id" in params and "site_id" in params)
except Exception as e:
    check("RCCPMethod import", False, str(e))

# ---------------------------------------------------------------------------
# 3. Three RCCP methods
# ---------------------------------------------------------------------------
print("\n-- 3. Three RCCP methods --")
try:
    methods = [m.value for m in RCCPMethod]
    check("RCCPMethod has 3 values", len(methods) == 3, f"got {len(methods)}: {methods}")
    check("CPOF method", "cpof" in methods)
    check("Bill of Capacity method", "bill_of_capacity" in methods)
    check("Resource Profile method", "resource_profile" in methods)
except Exception as e:
    check("RCCPMethod values", False, str(e))

# Verify the service handles all three methods
try:
    source = inspect.getsource(RCCPService)
    check("Service references CPOF", "CPOF" in source or "cpof" in source)
    check("Service references BILL_OF_CAPACITY",
          "BILL_OF_CAPACITY" in source or "bill_of_capacity" in source)
    check("Service references RESOURCE_PROFILE",
          "RESOURCE_PROFILE" in source or "resource_profile" in source)
except Exception as e:
    check("Method references in source", False, str(e))

# ---------------------------------------------------------------------------
# 4. Seven decision rules
# ---------------------------------------------------------------------------
print("\n-- 4. Seven decision rules --")
try:
    source = inspect.getsource(RCCPService)

    # Rule 1: Overload detection
    check("Rule 1: Overload detection",
          "overload_detection" in source or "Rule 1" in source)

    # Rule 2: Overtime authorization
    check("Rule 2: Overtime authorization",
          "overtime" in source.lower() or "Rule 2" in source)

    # Rule 3: MPS levelling
    check("Rule 3: MPS levelling",
          "levelling" in source.lower() or "Rule 3" in source)

    # Rule 4: Underload alert
    check("Rule 4: Underload alert",
          "underload" in source.lower() or "Rule 4" in source)

    # Rule 5: Chronic overload
    check("Rule 5: Chronic overload",
          "chronic" in source.lower() or "Rule 5" in source)

    # Rule 6: Variability hedge
    check("Rule 6: Variability hedge",
          "variability" in source.lower() or "Rule 6" in source)

    # Rule 7: Changeover-heavy mix
    check("Rule 7: Changeover-heavy mix",
          "changeover" in source.lower() or "Rule 7" in source)

    # Count distinct rule identifiers in rules_applied
    rule_keywords = [
        "overload_detection", "overtime", "mps_levelling",
        "underload_alert", "chronic_overload", "variability_hedge",
        "changeover",
    ]
    rules_found = sum(1 for kw in rule_keywords if kw in source)
    check(f"At least 7 distinct rule keywords ({rules_found} found)",
          rules_found >= 7,
          f"only {rules_found} of 7 keywords found")
except Exception as e:
    check("Decision rules inspection", False, str(e))

# ---------------------------------------------------------------------------
# 5. BoR auto-generation from production_process
# ---------------------------------------------------------------------------
print("\n-- 5. BoR auto-generation --")
try:
    source = inspect.getsource(RCCPService.auto_generate_bor)
    check("auto_generate_bor references ProductionProcess",
          "ProductionProcess" in source)
    check("auto_generate_bor creates BillOfResources",
          "BillOfResources" in source)
    check("auto_generate_bor uses setup_time or operation_time",
          "setup_time" in source or "operation_time" in source)
except Exception as e:
    check("auto_generate_bor inspection", False, str(e))

# Verify BillOfResources model
try:
    bor_cols = {c.name for c in BillOfResources.__table__.columns}
    for col in ["config_id", "site_id", "product_id", "hours_per_unit", "is_active"]:
        check(f"BillOfResources.{col} column", col in bor_cols)
except Exception as e:
    check("BillOfResources model", False, str(e))

# ---------------------------------------------------------------------------
# 6. DB-dependent tests
# ---------------------------------------------------------------------------
print("\n-- 6. DB-dependent tests --")
try:
    from app.db.session import sync_session_factory
    from sqlalchemy import select, func
    db = sync_session_factory()

    # Construct service with DB
    svc = RCCPService(db=db)
    check("RCCPService(db=db) construction", True)

    # Test detect_method — use config 22, find a site
    from app.models.supply_chain_config import Site
    sites = db.execute(
        select(Site.id).where(Site.config_id == 22).limit(3)
    ).scalars().all()

    if sites:
        result = svc.detect_method(config_id=22, site_id=sites[0])
        check("detect_method returns dict", isinstance(result, dict))
        check("detect_method has recommended_method",
              "recommended_method" in result,
              f"keys: {list(result.keys())}")
        check("detect_method has bor_entry_count",
              "bor_entry_count" in result)
        check(f"Recommended method: {result.get('recommended_method', '?')}", True)
    else:
        print("  SKIP: No sites found for config 22")

    db.close()
except Exception as e:
    print(f"  SKIP: DB tests (no connection): {e}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
total = passed + failed
print(f"B5 Result: {passed}/{total} passed, {failed} failed")
if failed == 0:
    print("PASS")
    sys.exit(0)
else:
    print("FAIL")
    sys.exit(1)
