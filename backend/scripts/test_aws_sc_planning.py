"""
Test AWS SC Planning Logic

This script tests the 3-step AWS SC planning process against a configuration.
"""

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.aws_sc_planning import AWSSupplyChainPlanner
from app.db.session import SessionLocal
from app.models.supply_chain_config import SupplyChainConfig
from sqlalchemy import select


async def test_planning(config_name: str = "Complex_SC"):
    """Test planning against a configuration"""

    print("=" * 80)
    print("AWS Supply Chain Planning Test")
    print("=" * 80)
    print()

    # Get config ID
    async with SessionLocal() as db:
        result = await db.execute(
            select(SupplyChainConfig).filter(
                SupplyChainConfig.name == config_name
            )
        )
        config = result.scalar_one_or_none()

        if not config:
            print(f"❌ Configuration '{config_name}' not found")
            return

        config_id = config.id
        print(f"✓ Found configuration: {config.name} (ID: {config_id})")
        print()

    # Create planner
    planning_horizon = 52  # 52 days ahead
    planner = AWSSupplyChainPlanner(config_id=config_id, planning_horizon=planning_horizon)

    # Validate configuration
    print("Validating configuration...")
    is_valid, errors = await planner.validate_configuration()

    if not is_valid:
        print(f"❌ Configuration validation failed:")
        for error in errors:
            print(f"  • {error}")
        print()
        print("Note: Some validation errors are expected since we haven't populated")
        print("forecast data yet. Continuing with planning test...")
        print()
    else:
        print("✓ Configuration is valid")
        print()

    # Run planning
    start_date = date.today()
    print(f"Running planning process...")
    print(f"  Start date: {start_date}")
    print(f"  Horizon: {planning_horizon} days")
    print()

    try:
        supply_plans = await planner.run_planning(start_date)

        print()
        print("=" * 80)
        print("✅ Planning completed successfully!")
        print("=" * 80)
        print()
        print(f"Generated {len(supply_plans)} supply plan recommendations")

        if supply_plans:
            print()
            print("Sample supply plans:")
            for i, plan in enumerate(supply_plans[:5]):
                print(f"  {i+1}. {plan.plan_type}: Product {plan.product_id} at Site {plan.destination_site_id}")
                print(f"     Order: {plan.planned_order_quantity} units on {plan.planned_order_date}")
                print(f"     Receipt: {plan.planned_receipt_date} (lead time: {plan.lead_time_days} days)")
                if plan.unit_cost:
                    print(f"     Cost: ${plan.unit_cost:.2f}/unit")
                print()

    except Exception as e:
        print()
        print("=" * 80)
        print(f"❌ Planning failed with error:")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test AWS SC Planning")
    parser.add_argument(
        "--config",
        default="Complex_SC",
        help="Supply chain configuration name (default: Complex_SC)"
    )

    args = parser.parse_args()

    asyncio.run(test_planning(args.config))
