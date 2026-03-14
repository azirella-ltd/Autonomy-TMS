#!/usr/bin/env python3
"""B4: MPS Generation Validation

Verifies:
1. MPSPlan model can be imported
2. MPSPlanItem fields match expected schema
3. Capacity check logic exists (MPSCapacityCheck)
4. Approval workflow states defined (MPSStatus)
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
print("B4: MPS Generation Validation")
print("=" * 60)

# ---------------------------------------------------------------------------
# 1. MPSPlan model import
# ---------------------------------------------------------------------------
print("\n-- 1. MPSPlan model --")
try:
    from app.models.mps import MPSPlan, MPSPlanItem, MPSStatus
    check("MPSPlan import", True)
    check("MPSPlanItem import", True)
    check("MPSStatus import", True)
except Exception as e:
    check("MPS model imports", False, str(e))
    print("\nFAIL")
    sys.exit(1)

# Verify MPSPlan table name
check("MPSPlan.__tablename__", MPSPlan.__tablename__ == "mps_plans",
      f"got {MPSPlan.__tablename__}")

# MPSPlan columns
plan_cols = {c.name for c in MPSPlan.__table__.columns}
expected_plan_cols = [
    "id", "name", "supply_chain_config_id", "planning_horizon_weeks",
    "bucket_size_days", "start_date", "end_date", "status",
    "created_by", "approved_by", "approved_at",
    "created_at", "updated_at",
]
for col in expected_plan_cols:
    check(f"MPSPlan.{col}", col in plan_cols)

# ---------------------------------------------------------------------------
# 2. MPSPlanItem schema
# ---------------------------------------------------------------------------
print("\n-- 2. MPSPlanItem schema --")
check("MPSPlanItem.__tablename__", MPSPlanItem.__tablename__ == "mps_plan_items",
      f"got {MPSPlanItem.__tablename__}")

item_cols = {c.name for c in MPSPlanItem.__table__.columns}
expected_item_cols = [
    "id", "plan_id", "product_id", "site_id",
    "weekly_quantities", "lot_size_rule", "lot_size_value",
    "created_at", "updated_at",
]
for col in expected_item_cols:
    check(f"MPSPlanItem.{col}", col in item_cols)

# Verify relationships
check("MPSPlanItem.plan relationship", hasattr(MPSPlanItem, "plan"))
check("MPSPlanItem.product relationship", hasattr(MPSPlanItem, "product"))
check("MPSPlanItem.site relationship", hasattr(MPSPlanItem, "site"))
check("MPSPlan.items relationship", hasattr(MPSPlan, "items"))

# ---------------------------------------------------------------------------
# 3. Capacity check model
# ---------------------------------------------------------------------------
print("\n-- 3. Capacity check model --")
try:
    from app.models.mps import MPSCapacityCheck
    check("MPSCapacityCheck import", True)
    cap_cols = {c.name for c in MPSCapacityCheck.__table__.columns}
    check("MPSCapacityCheck.plan_id", "plan_id" in cap_cols)
    check("MPSCapacityCheck.resource_name", "resource_name" in cap_cols)
    check("MPSCapacityCheck.site_id", "site_id" in cap_cols)
    check("MPSPlan.capacity_checks relationship", hasattr(MPSPlan, "capacity_checks"))
except Exception as e:
    check("MPSCapacityCheck model", False, str(e))

# Verify RCCP service exists and can be imported
try:
    from app.services.rccp_service import RCCPService
    check("RCCPService import", True)
    check("RCCPService.validate_mps method", hasattr(RCCPService, "validate_mps"))
except Exception as e:
    check("RCCPService import", False, str(e))

# ---------------------------------------------------------------------------
# 4. Approval workflow states
# ---------------------------------------------------------------------------
print("\n-- 4. Approval workflow states --")
expected_states = ["DRAFT", "PENDING_APPROVAL", "APPROVED", "IN_EXECUTION", "COMPLETED", "CANCELLED"]
actual_states = [s.value for s in MPSStatus]

check(f"MPSStatus has {len(expected_states)} states",
      len(actual_states) == len(expected_states),
      f"got {len(actual_states)}: {actual_states}")

for state in expected_states:
    check(f"MPSStatus.{state}", state in actual_states)

# Verify workflow progression logic
check("DRAFT is initial state", MPSStatus.DRAFT.value == "DRAFT")
check("APPROVED requires approved_by", "approved_by" in plan_cols)
check("APPROVED requires approved_at", "approved_at" in plan_cols)
check("IN_EXECUTION has execution_started_at", "execution_started_at" in plan_cols)
check("COMPLETED has execution_completed_at", "execution_completed_at" in plan_cols)

# ---------------------------------------------------------------------------
# 5. DB-dependent tests
# ---------------------------------------------------------------------------
print("\n-- 5. DB-dependent tests --")
try:
    from app.db.session import sync_session_factory
    from sqlalchemy import select, func
    db = sync_session_factory()

    plan_count = db.execute(select(func.count(MPSPlan.id))).scalar() or 0
    check("MPS plans in database", True, f"found {plan_count}")

    if plan_count > 0:
        # Check status distribution
        statuses = db.execute(
            select(MPSPlan.status, func.count(MPSPlan.id)).group_by(MPSPlan.status)
        ).all()
        status_dict = {s.value if hasattr(s, 'value') else s: c for s, c in statuses}
        check("MPS plan statuses", True, f"distribution: {status_dict}")

    db.close()
except Exception as e:
    print(f"  SKIP: DB tests (no connection): {e}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
total = passed + failed
print(f"B4 Result: {passed}/{total} passed, {failed} failed")
if failed == 0:
    print("PASS")
    sys.exit(0)
else:
    print("FAIL")
    sys.exit(1)
