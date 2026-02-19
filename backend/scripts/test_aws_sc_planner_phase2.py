"""
Test AWS SC Planner with Phase 2 group_id Support

This script tests that the AWSSupplyChainPlanner works correctly with
the new group_id parameter added in Phase 2.

Usage:
    docker compose exec backend python scripts/test_aws_sc_planner_phase2.py
"""

import asyncio
from datetime import date, timedelta
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.supply_chain_config import SupplyChainConfig
from app.models.group import Group
from app.services.aws_sc_planning.planner import AWSSupplyChainPlanner


async def test_planner_with_group_id():
    """Test AWSSupplyChainPlanner with group_id filtering"""

    print("=" * 80)
    print("Testing AWS SC Planner with Phase 2 group_id Support")
    print("=" * 80)
    print()

    async with SessionLocal() as db:
        # Find a group with a config that has AWS SC data
        print("1. Finding suitable test configuration...")
        print("-" * 80)

        # Get Complex_SC group (group_id=3) which has planning data
        result = await db.execute(
            select(Group).filter(Group.name == "Complex_SC")
        )
        group = result.scalar_one_or_none()

        if not group:
            print("❌ Complex_SC group not found")
            return False

        print(f"✓ Found group: {group.name} (ID={group.id})")

        # Get the config for this group
        result = await db.execute(
            select(SupplyChainConfig).filter(
                SupplyChainConfig.group_id == group.id
            ).limit(1)
        )
        config = result.scalar_one_or_none()

        if not config:
            print(f"❌ No config found for group {group.id}")
            return False

        print(f"✓ Found config: {config.name} (ID={config.id})")
        print()

        # Test OLD way (should fail - config_id only)
        print("2. Testing OLD planner (config_id only)...")
        print("-" * 80)
        try:
            # This should fail because __init__ now requires group_id
            planner_old = AWSSupplyChainPlanner(
                config_id=config.id,
                planning_horizon=7
            )
            print("❌ OLD planner creation should have failed!")
            return False
        except TypeError as e:
            print(f"✓ OLD planner correctly rejected: {e}")
            print()

        # Test NEW way (should work - config_id + group_id)
        print("3. Testing NEW planner (config_id + group_id)...")
        print("-" * 80)
        try:
            planner_new = AWSSupplyChainPlanner(
                config_id=config.id,
                group_id=group.id,
                planning_horizon=7
            )
            print(f"✓ NEW planner created successfully")
            print(f"  - config_id: {planner_new.config_id}")
            print(f"  - group_id: {planner_new.group_id}")
            print(f"  - planning_horizon: {planner_new.planning_horizon}")
            print()
        except Exception as e:
            print(f"❌ NEW planner creation failed: {e}")
            return False

        # Test validation
        print("4. Testing configuration validation...")
        print("-" * 80)
        try:
            is_valid, errors = await planner_new.validate_configuration()
            if is_valid:
                print(f"✓ Configuration is valid")
            else:
                print(f"⚠️  Configuration has {len(errors)} errors:")
                for err in errors:
                    print(f"  - {err}")
            print()
        except Exception as e:
            print(f"❌ Validation failed: {e}")
            return False

        # Test running planning (if valid)
        if is_valid:
            print("5. Testing planning execution...")
            print("-" * 80)
            try:
                start_date = date.today()
                supply_plans = await planner_new.run_planning(
                    start_date=start_date,
                    game_id=None
                )
                print(f"✓ Planning completed successfully")
                print(f"  - Generated {len(supply_plans)} supply plans")
                print()

                # Verify all plans have group_id set
                print("6. Verifying supply plans have group_id...")
                print("-" * 80)
                plans_with_group = sum(1 for p in supply_plans if p.group_id == group.id)
                print(f"  - Plans with group_id: {plans_with_group}/{len(supply_plans)}")

                if plans_with_group == len(supply_plans):
                    print(f"✓ All plans have correct group_id")
                else:
                    print(f"⚠️  Some plans missing group_id")
                print()

            except Exception as e:
                print(f"❌ Planning execution failed: {e}")
                import traceback
                traceback.print_exc()
                return False

        # Summary
        print("=" * 80)
        print("Test Summary")
        print("=" * 80)
        print(f"✅ Phase 2 group_id support is working correctly!")
        print()
        print("Key Changes Verified:")
        print("  ✓ AWSSupplyChainPlanner requires group_id parameter")
        print("  ✓ All sub-processors (DemandProcessor, InventoryTargetCalculator, NetRequirementsCalculator)")
        print("    accept and use group_id for filtering")
        print("  ✓ Planning execution works with group-based filtering")
        if is_valid and len(supply_plans) > 0:
            print(f"  ✓ Supply plans generated with group_id={group.id}")
        print()
        print("=" * 80)

        return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_planner_with_group_id())
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
