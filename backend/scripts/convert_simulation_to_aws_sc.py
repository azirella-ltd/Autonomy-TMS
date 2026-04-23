"""
Convert Supply Chain Config to AWS SC Format

This script converts an existing SupplyChainConfig to AWS SC entities:
- InvPolicy (inventory policies for each node)
- SourcingRules (sourcing relationships between nodes)
- ProductionProcess (manufacturing processes for factory nodes)
- Forecast (demand forecast for 52 weeks)

Usage:
    docker compose exec backend python scripts/convert_simulation_to_aws_sc.py

Options:
    --config-name "Default Beer Scenario"  (default: "Default Beer Scenario")
    --tenant-name "Default Tenant" (default: "Default Tenant")
    --horizon 52                 (default: 52 weeks)
"""

import asyncio
import sys
from datetime import date, timedelta
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal, async_session_factory
from app.models.supply_chain_config import SupplyChainConfig, Site, Lane, Item
from app.models.tenant import Tenant
from app.models.aws_sc_planning import (
    InvPolicy,
    SourcingRules,
    ProductionProcess,
    Forecast
)


async def convert_config_to_aws_sc(
    config_name: str = "Default Beer Scenario",
    tenant_name: str = "Default Tenant",
    horizon: int = 52
):
    """
    Convert a supply chain config to AWS SC format

    Args:
        config_name: Name of the SupplyChainConfig to convert
        tenant_name: Name of the Tenant to use
        horizon: Number of weeks to forecast
    """
    print("=" * 80)
    print("Supply Chain Config → AWS SC Conversion")
    print("=" * 80)
    print()

    async with async_session_factory() as db:
        # ================================================================
        # 1. Load Configuration and Tenant
        # ================================================================
        print(f"1. Loading configuration: {config_name}")

        result = await db.execute(
            select(SupplyChainConfig)
            .options(
                selectinload(SupplyChainConfig.nodes),
                selectinload(SupplyChainConfig.lanes),
                selectinload(SupplyChainConfig.items)
            )
            .filter(SupplyChainConfig.name == config_name)
        )
        config = result.scalar_one_or_none()

        if not config:
            print(f"❌ Config '{config_name}' not found")
            return False

        print(f"   ✓ Config ID: {config.id}")
        print(f"   ✓ Nodes: {len(config.nodes)}")
        print(f"   ✓ Lanes: {len(config.lanes)}")
        print(f"   ✓ Items: {len(config.items)}")
        print()

        # Load tenant
        result = await db.execute(select(Tenant).filter(Tenant.name == tenant_name))
        tenant = result.scalar_one_or_none()

        if not tenant:
            print(f"❌ Tenant '{tenant_name}' not found")
            return False

        print(f"   ✓ Tenant ID: {tenant.id}")
        print()

        # ================================================================
        # 2. Create InvPolicy Records
        # ================================================================
        print("2. Creating InvPolicy records (inventory policies)...")

        inv_policies_created = 0

        # Get the primary item (simulation configs typically have one item: "Cases")
        if not config.items:
            print("   ❌ No items defined in config")
            return False

        item = config.items[0]
        print(f"   Using item: {item.name} (ID: {item.id})")
        print()

        for node in config.nodes:
            # Skip market nodes (they don't have inventory policies)
            if node.type in ['vendor', 'customer', 'Vendor', 'Customer']:
                print(f"   ⊗ Skipping {node.name} (market node)")
                continue

            # Get target inventory from node attributes or default to 12
            attributes = node.attributes or {}
            target_qty = attributes.get('initial_inventory', 12)
            safety_stock = attributes.get('safety_stock', 0)
            reorder_point = attributes.get('reorder_point', 0)

            inv_policy = InvPolicy(
                customer_id=tenant.id,
                config_id=config.id,
                product_id=item.id,
                site_id=node.id,
                policy_type='abs_level',  # Absolute level policy (target inventory)
                target_qty=float(target_qty),
                safety_stock_qty=float(safety_stock),
                reorder_point_qty=float(reorder_point),
                min_qty=0.0,
                max_qty=9999.0,  # Unlimited for simulation
                review_period_days=7,  # Weekly review
                is_active='true'
            )

            db.add(inv_policy)
            inv_policies_created += 1

            print(f"   ✓ {node.name}: target={target_qty}, safety_stock={safety_stock}")

        await db.flush()
        print()
        print(f"   ✅ Created {inv_policies_created} InvPolicy records")
        print()

        # ================================================================
        # 3. Create SourcingRules Records
        # ================================================================
        print("3. Creating SourcingRules records (sourcing relationships)...")

        sourcing_rules_created = 0

        for lane in config.lanes:
            # Get from and to nodes
            from_node = next((n for n in config.nodes if n.id == lane.from_node_id), None)
            to_node = next((n for n in config.nodes if n.id == lane.to_node_id), None)

            if not from_node or not to_node:
                print(f"   ⚠️  Lane missing nodes: from={lane.from_node_id}, to={lane.to_node_id}")
                continue

            # Determine sourcing type based on from_node master_type
            if from_node.master_type == 'manufacturer':
                sourcing_type = 'manufacture'
            elif from_node.master_type == 'vendor':
                sourcing_type = 'purchase'
            else:
                sourcing_type = 'transfer'

            # Get lead time (simulation uses weeks, AWS SC uses days)
            lead_time_weeks = lane.lead_time or 2
            lead_time_days = lead_time_weeks * 7

            sourcing_rule = SourcingRules(
                customer_id=tenant.id,
                config_id=config.id,
                product_id=item.id,
                site_id=to_node.id,  # Destination
                supplier_site_id=from_node.id,  # Source
                sourcing_type=sourcing_type,
                allocation_percentage=100.0,  # Single sourcing for simulation
                lead_time_days=lead_time_days,
                transit_time_days=lead_time_days,
                min_order_qty=0.0,
                max_order_qty=9999.0,  # Unlimited
                is_active='true',
                priority=1
            )

            db.add(sourcing_rule)
            sourcing_rules_created += 1

            print(f"   ✓ {from_node.name} → {to_node.name}: {sourcing_type}, lead_time={lead_time_weeks}w")

        await db.flush()
        print()
        print(f"   ✅ Created {sourcing_rules_created} SourcingRules records")
        print()

        # ================================================================
        # 4. Create ProductionProcess Records
        # ================================================================
        print("4. Creating ProductionProcess records (manufacturing processes)...")

        production_processes_created = 0

        for node in config.nodes:
            # Only for manufacturer nodes
            if node.master_type != 'manufacturer':
                continue

            attributes = node.attributes or {}

            # Get manufacturing lead time
            mfg_leadtime = attributes.get('manufacturing_leadtime', 2)
            if isinstance(mfg_leadtime, dict):
                # Handle case where it's per-product
                mfg_leadtime = mfg_leadtime.get(item.name, 2)

            # Get capacity (simulation configs typically have unlimited capacity)
            capacity_hours = attributes.get('capacity_hours', 9999)

            production_process = ProductionProcess(
                customer_id=tenant.id,
                config_id=config.id,
                product_id=item.id,
                site_id=node.id,
                manufacturing_leadtime=int(mfg_leadtime),
                capacity_hours=int(capacity_hours),
                capacity_utilization_pct=100.0,
                yield_pct=100.0,
                setup_time_hours=0,
                is_active='true'
            )

            db.add(production_process)
            production_processes_created += 1

            print(f"   ✓ {node.name}: leadtime={mfg_leadtime}w, capacity={capacity_hours}h")

        await db.flush()
        print()
        print(f"   ✅ Created {production_processes_created} ProductionProcess records")
        print()

        # ================================================================
        # 5. Create Forecast Records
        # ================================================================
        print(f"5. Creating Forecast records ({horizon} weeks)...")

        # Find the retailer node (where demand hits)
        retailer_node = next(
            (n for n in config.nodes if n.type in ['retailer', 'Retailer']),
            None
        )

        if not retailer_node:
            print("   ⚠️  No retailer node found, skipping forecast")
        else:
            print(f"   Using node: {retailer_node.name} (ID: {retailer_node.id})")

            # Get demand pattern from config
            demand_pattern = config.demand_pattern or {"type": "constant", "value": 4}
            print(f"   Demand pattern: {demand_pattern}")
            print()

            forecasts_created = 0
            start_date = date.today()

            for week in range(horizon):
                forecast_date = start_date + timedelta(weeks=week)

                # Calculate demand for this week
                demand_qty = _get_demand_for_week(demand_pattern, week)

                forecast = Forecast(
                    customer_id=tenant.id,
                    config_id=config.id,
                    product_id=item.id,
                    site_id=retailer_node.id,
                    forecast_date=forecast_date,
                    forecast_quantity=demand_qty,
                    forecast_p50=demand_qty,  # Median
                    forecast_p10=demand_qty * 0.8,  # Pessimistic
                    forecast_p90=demand_qty * 1.2,  # Optimistic
                    user_override_quantity=None,
                    is_active='true'
                )

                db.add(forecast)
                forecasts_created += 1

                if week < 5 or week >= horizon - 2:
                    print(f"   Week {week:2d}: {demand_qty:5.1f} units (date: {forecast_date})")
                elif week == 5:
                    print(f"   ... ({horizon - 7} more weeks)")

            await db.flush()
            print()
            print(f"   ✅ Created {forecasts_created} Forecast records")
            print()

        # ================================================================
        # 6. Commit All Changes
        # ================================================================
        print("6. Committing changes to database...")
        await db.commit()
        print("   ✅ All changes committed")
        print()

        # ================================================================
        # Summary
        # ================================================================
        print("=" * 80)
        print("Conversion Summary")
        print("=" * 80)
        print(f"Config:              {config.name} (ID: {config.id})")
        print(f"Tenant:              {tenant.name} (ID: {tenant.id})")
        print(f"InvPolicy:           {inv_policies_created} records")
        print(f"SourcingRules:       {sourcing_rules_created} records")
        print(f"ProductionProcess:   {production_processes_created} records")
        print(f"Forecast:            {forecasts_created} records")
        print()
        print("✅ Conversion complete! Config is now ready for AWS SC planning.")
        print()
        print("Next steps:")
        print("1. Create a scenario with use_aws_sc_planning=True")
        print("2. Set scenario.supply_chain_config_id = {config.id}")
        print("3. Set scenario.customer_id = {tenant.id}")
        print("4. Start the scenario and observe AWS SC planning in action!")
        print("=" * 80)

        return True


def _get_demand_for_week(demand_pattern: dict, week: int) -> float:
    """
    Calculate demand for a specific week based on demand pattern

    Args:
        demand_pattern: Demand pattern dict
        week: Week number (0-indexed)

    Returns:
        Demand quantity for this week
    """
    pattern_type = demand_pattern.get('type', 'constant')

    if pattern_type == 'step':
        initial = demand_pattern.get('initial', 4)
        step_week = demand_pattern.get('step_week', 5)
        step_value = demand_pattern.get('step_value', 8)

        if week < step_week:
            return float(initial)
        else:
            return float(step_value)

    elif pattern_type == 'constant':
        return float(demand_pattern.get('value', 4))

    elif 'weeks' in demand_pattern:
        weeks = demand_pattern['weeks']
        if week < len(weeks):
            return float(weeks[week])
        else:
            # Repeat last value
            return float(weeks[-1]) if weeks else 4.0

    else:
        # Default to standard demand
        return 4.0


async def verify_conversion(config_name: str, tenant_name: str):
    """
    Verify that the conversion was successful

    Args:
        config_name: Name of the config
        tenant_name: Name of the tenant
    """
    print()
    print("=" * 80)
    print("Verification")
    print("=" * 80)
    print()

    async with async_session_factory() as db:
        # Get config and tenant
        result = await db.execute(
            select(SupplyChainConfig).filter(SupplyChainConfig.name == config_name)
        )
        config = result.scalar_one_or_none()

        result = await db.execute(select(Tenant).filter(Tenant.name == tenant_name))
        tenant = result.scalar_one_or_none()

        if not config or not tenant:
            print("❌ Config or tenant not found")
            return False

        # Count records
        inv_policy_count = await db.execute(
            select(InvPolicy).filter(
                InvPolicy.customer_id == tenant.id,
                InvPolicy.config_id == config.id
            )
        )
        inv_policy_count = len(inv_policy_count.scalars().all())

        sourcing_rules_count = await db.execute(
            select(SourcingRules).filter(
                SourcingRules.customer_id == tenant.id,
                SourcingRules.config_id == config.id
            )
        )
        sourcing_rules_count = len(sourcing_rules_count.scalars().all())

        production_process_count = await db.execute(
            select(ProductionProcess).filter(
                ProductionProcess.customer_id == tenant.id,
                ProductionProcess.config_id == config.id
            )
        )
        production_process_count = len(production_process_count.scalars().all())

        forecast_count = await db.execute(
            select(Forecast).filter(
                Forecast.customer_id == tenant.id,
                Forecast.config_id == config.id
            )
        )
        forecast_count = len(forecast_count.scalars().all())

        print(f"Config: {config.name} (ID: {config.id})")
        print(f"Tenant:    {tenant.name} (ID: {tenant.id})")
        print()
        print(f"InvPolicy:         {inv_policy_count:3d} records")
        print(f"SourcingRules:     {sourcing_rules_count:3d} records")
        print(f"ProductionProcess: {production_process_count:3d} records")
        print(f"Forecast:          {forecast_count:3d} records")
        print()

        all_present = all([
            inv_policy_count > 0,
            sourcing_rules_count > 0,
            forecast_count > 0
        ])

        if all_present:
            print("✅ All required AWS SC entities are present")
            print("✅ Config is ready for AWS SC planning mode")
        else:
            print("⚠️  Some entities are missing")
            if inv_policy_count == 0:
                print("   ❌ No InvPolicy records")
            if sourcing_rules_count == 0:
                print("   ❌ No SourcingRules records")
            if forecast_count == 0:
                print("   ❌ No Forecast records")

        print("=" * 80)
        print()

        return all_present


async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert supply chain config to AWS SC format"
    )
    parser.add_argument(
        '--config-name',
        default='Default Beer Scenario',
        help='Name of the SupplyChainConfig to convert'
    )
    parser.add_argument(
        '--tenant-name',
        default='Default Tenant',
        help='Name of the Tenant to use'
    )
    parser.add_argument(
        '--horizon',
        type=int,
        default=52,
        help='Number of weeks to forecast'
    )
    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Only verify existing conversion'
    )

    args = parser.parse_args()

    if args.verify_only:
        success = await verify_conversion(args.config_name, args.tenant_name)
    else:
        success = await convert_config_to_aws_sc(
            config_name=args.config_name,
            tenant_name=args.tenant_name,
            horizon=args.horizon
        )

        if success:
            await verify_conversion(args.config_name, args.tenant_name)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
