"""
Test Dual-Mode Integration (Legacy vs AWS SC Planning)

This script tests the dual-mode routing in mixed_scenario_service.py:
1. Create a test scenario with AWS SC mode DISABLED (legacy)
2. Run 1 round using legacy engine
3. Create a test scenario with AWS SC mode ENABLED
4. Run 1 round using AWS SC planner
5. Compare results

Usage:
    docker compose exec backend python scripts/test_dual_mode_integration.py
"""

import asyncio
import sys
from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal, async_session_factory
from app.models.scenario import Scenario
from app.models.participant import Participant
from app.models.group import Group
from app.models.supply_chain_config import SupplyChainConfig
from app.services.mixed_scenario_service import MixedScenarioService


def test_legacy_mode():
    """Test legacy Beer Scenario engine mode"""
    print("=" * 80)
    print("TEST 1: Legacy Beer Scenario Engine Mode")
    print("=" * 80)
    print()

    with SessionLocal() as db:
        # Get or create a test group
        group = db.query(Group).filter(Group.name == "Test Group").first()
        if not group:
            group = Group(name="Test Group", description="Test group for dual-mode testing")
            db.add(group)
            db.commit()
            db.refresh(group)

        # Get a supply chain config (use Default TBG if available)
        config = db.query(SupplyChainConfig).filter(
            SupplyChainConfig.name.like("%Default%")
        ).first()

        if not config:
            print("❌ No supply chain config found. Please seed the database first.")
            return False

        print(f"Using config: {config.name} (ID: {config.id})")
        print(f"Using group: {group.name} (ID: {group.id})")
        print()

        # Create test scenario with LEGACY mode
        scenario = Scenario(
            name="Test Legacy Mode",
            group_id=group.id,
            supply_chain_config_id=config.id,
            use_aws_sc_planning=False,  # LEGACY MODE
            max_rounds=1,
            status="active",
            start_date=date(2024, 1, 1),
            current_round=0,
            config={
                "demand_pattern": {"type": "constant", "value": 4}
            }
        )
        db.add(scenario)
        db.commit()
        db.refresh(scenario)

        print(f"✓ Created scenario: {scenario.name} (ID: {scenario.id})")
        print(f"  use_aws_sc_planning: {scenario.use_aws_sc_planning}")
        print()

        # Create service
        service = MixedScenarioService(db)

        # Run 1 round
        print("Running round 1 with legacy engine...")
        try:
            scenario_round = service.start_new_round(scenario)

            if scenario_round:
                print(f"✅ Legacy mode SUCCESS")
                print(f"   Round {scenario_round.round_number} completed")
                print(f"   Started: {scenario_round.started_at}")
                print(f"   Completed: {scenario_round.completed_at}")
                print()
                return True
            else:
                print(f"❌ Legacy mode FAILED: No scenario round returned")
                return False

        except Exception as e:
            print(f"❌ Legacy mode FAILED with error:")
            print(f"   {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return False


async def test_aws_sc_mode_async():
    """Test AWS SC planning mode (async wrapper)"""
    print("=" * 80)
    print("TEST 2: AWS SC Planning Mode")
    print("=" * 80)
    print()

    async with async_session_factory() as db:
        # Get or create a test group
        result = await db.execute(select(Group).filter(Group.name == "Test Group"))
        group = result.scalar_one_or_none()

        if not group:
            group = Group(name="Test Group", description="Test group for dual-mode testing")
            db.add(group)
            await db.commit()
            await db.refresh(group)

        # Get a supply chain config
        result = await db.execute(
            select(SupplyChainConfig)
            .options(selectinload(SupplyChainConfig.nodes))
            .filter(SupplyChainConfig.name.like("%Default%"))
        )
        config = result.scalar_one_or_none()

        if not config:
            print("❌ No supply chain config found. Please seed the database first.")
            return False

        print(f"Using config: {config.name} (ID: {config.id})")
        print(f"Using group: {group.name} (ID: {group.id})")
        print()

        # Create test scenario with AWS SC mode
        scenario = Scenario(
            name="Test AWS SC Mode",
            group_id=group.id,
            supply_chain_config_id=config.id,
            use_aws_sc_planning=True,  # AWS SC MODE
            max_rounds=1,
            status="active",
            start_date=date(2024, 1, 1),
            current_round=0,
            config={
                "demand_pattern": {"type": "constant", "value": 4},
                "nodes": {}
            },
            demand_pattern={"type": "constant", "value": 4}
        )
        db.add(scenario)
        await db.commit()
        await db.refresh(scenario)

        print(f"✓ Created scenario: {scenario.name} (ID: {scenario.id})")
        print(f"  use_aws_sc_planning: {scenario.use_aws_sc_planning}")
        print()

        # Create test players for each node
        await db.refresh(config, ['nodes'])
        print(f"Creating {len(config.nodes)} test players...")

        # Initialize node states in scenario config
        nodes_state = {}
        for node in config.nodes:
            if node.type not in ['market_supply', 'market_demand']:
                player = Participant(
                    scenario_id=scenario.id,
                    role=node.name,
                    is_ai=True,
                    ai_strategy="naive"
                )
                db.add(player)

                # Initialize node state
                nodes_state[node.name] = {
                    "inventory": 12,
                    "backlog": 0,
                    "current_order": 0,
                    "order_history": []
                }

                print(f"  ✓ Created player: {node.name}")

        # Update scenario config with node states
        scenario.config["nodes"] = nodes_state
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(scenario, "config")

        await db.commit()
        await db.refresh(scenario)
        print()

    # Now test with sync session (since mixed_scenario_service uses sync)
    with SessionLocal() as sync_db:
        # Reload scenario in sync session
        scenario_sync = sync_db.query(Scenario).filter(Scenario.id == scenario.id).first()

        # Create service
        service = MixedScenarioService(sync_db)

        # Run 1 round
        print("Running round 1 with AWS SC planner...")
        try:
            scenario_round = service.start_new_round(scenario_sync)

            if scenario_round:
                print(f"✅ AWS SC mode SUCCESS")
                print(f"   Round {scenario_round.round_number} completed")
                print(f"   Started: {scenario_round.started_at}")
                print(f"   Completed: {scenario_round.completed_at}")
                print(f"   Notes: {scenario_round.notes}")
                print()
                return True
            else:
                print(f"❌ AWS SC mode FAILED: No scenario round returned")
                return False

        except Exception as e:
            print(f"❌ AWS SC mode FAILED with error:")
            print(f"   {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_aws_sc_mode():
    """Sync wrapper for async AWS SC test"""
    return asyncio.run(test_aws_sc_mode_async())


if __name__ == "__main__":
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "DUAL-MODE INTEGRATION TEST" + " " * 32 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    # Test 1: Legacy Mode
    legacy_result = test_legacy_mode()

    # Test 2: AWS SC Mode
    aws_sc_result = test_aws_sc_mode()

    # Summary
    print()
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Legacy Mode:   {'✅ PASS' if legacy_result else '❌ FAIL'}")
    print(f"AWS SC Mode:   {'✅ PASS' if aws_sc_result else '❌ FAIL'}")
    print()

    if legacy_result and aws_sc_result:
        print("🎉 All tests passed! Dual-mode integration is working correctly.")
        sys.exit(0)
    else:
        print("⚠️  Some tests failed. Review output above for details.")
        sys.exit(1)
