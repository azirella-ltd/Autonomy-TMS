"""
Seed Planning Data for Complex_SC Configuration

This script populates the planning tables with test data for Complex_SC:
- Forecasts: Demand forecasts for finished goods at demand sites
- BOMs: Bill of materials for manufacturing sites
- Sourcing Rules: Transfer/buy/manufacture rules
"""

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.models.supply_chain_config import SupplyChainConfig, Node, Item, Lane
from app.models.aws_sc_planning import (
    Forecast, ProductBom, SourcingRules, ProductionProcess
)
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload


async def seed_planning_data():
    """Seed planning data for Complex_SC"""

    print("=" * 80)
    print("Seeding Planning Data for Complex_SC")
    print("=" * 80)
    print()

    async with SessionLocal() as db:
        # Get Complex_SC configuration with eager loading
        result = await db.execute(
            select(SupplyChainConfig)
            .options(selectinload(SupplyChainConfig.lanes))
            .filter(SupplyChainConfig.name == "Complex_SC")
        )
        config = result.scalar_one_or_none()

        if not config:
            print("❌ Complex_SC configuration not found")
            return

        config_id = config.id
        print(f"✓ Found Complex_SC (ID: {config_id})")
        print()

        # Get all nodes and items
        nodes_result = await db.execute(
            select(Node).filter(Node.config_id == config_id)
        )
        nodes = {n.id: n for n in nodes_result.scalars().all()}

        items_result = await db.execute(
            select(Item).filter(Item.config_id == config_id)
        )
        items = {i.id: i for i in items_result.scalars().all()}

        lanes_result = await db.execute(
            select(Lane).filter(Lane.config_id == config_id)
        )
        lanes = list(lanes_result.scalars().all())

        print(f"✓ Loaded {len(nodes)} nodes, {len(items)} items, {len(lanes)} lanes")
        print()

        # ====================================================================
        # 1. Clear existing planning data
        # ====================================================================
        print("Clearing existing planning data...")
        await db.execute(delete(Forecast).filter(Forecast.config_id == config_id))
        await db.execute(delete(ProductBom).filter(ProductBom.config_id == config_id))
        await db.execute(delete(ProductionProcess).filter(ProductionProcess.config_id == config_id))
        await db.execute(delete(SourcingRules))  # No config_id filter available
        await db.commit()
        print("✓ Cleared existing data")
        print()

        # ====================================================================
        # 2. Create Forecasts for finished goods at demand sites
        # ====================================================================
        print("Creating forecasts...")

        # Find finished goods (FG-01, FG-02) and demand markets
        finished_goods = [i for i in items.values() if i.name.startswith('FG-')]
        demand_nodes = [n for n in nodes.values() if n.master_type == 'market_demand']

        forecast_count = 0
        start_date = date.today()

        for fg in finished_goods:
            for demand_node in demand_nodes:
                # Create 8 weeks of daily forecasts
                for day in range(56):
                    forecast_date = start_date + timedelta(days=day)

                    # Varying demand pattern (50-150 units/day with weekly cycle)
                    base_demand = 100
                    weekly_variation = 30 * (day % 7) / 7  # 0-30 variation
                    daily_demand = base_demand + weekly_variation

                    forecast = Forecast(
                        product_id=fg.id,
                        site_id=demand_node.id,
                        forecast_date=forecast_date,
                        forecast_quantity=daily_demand,
                        forecast_p50=daily_demand,
                        forecast_p10=daily_demand * 0.8,
                        forecast_p90=daily_demand * 1.2,
                        is_active='true',
                        config_id=config_id
                    )
                    db.add(forecast)
                    forecast_count += 1

        await db.commit()
        print(f"✓ Created {forecast_count} forecast entries")
        print()

        # ====================================================================
        # 3. Create Production Processes for manufacturers
        # ====================================================================
        print("Creating production processes...")

        manufacturers = [n for n in nodes.values() if n.master_type == 'manufacturer']

        prod_process_count = 0
        for mfg in manufacturers:
            process = ProductionProcess(
                id=f"PROC-{mfg.name.replace(' ', '_')}",
                description=f"Production process for {mfg.name}",
                site_id=mfg.id,
                manufacturing_leadtime=2,  # 2 days lead time
                cycle_time=1,
                yield_percentage=98.0,
                capacity_units=1000.0,
                capacity_period='day',
                config_id=config_id
            )
            db.add(process)
            prod_process_count += 1

        await db.commit()
        print(f"✓ Created {prod_process_count} production processes")
        print()

        # ====================================================================
        # 4. Create BOMs from Node.attributes
        # ====================================================================
        print("Creating BOMs from node attributes...")

        bom_count = 0
        for mfg in manufacturers:
            # Get BOM from attributes
            bom_data = (mfg.attributes or {}).get('bill_of_materials', {})

            if not bom_data:
                print(f"  ⚠️  {mfg.name} has no BOM in attributes")
                continue

            process_id = f"PROC-{mfg.name.replace(' ', '_')}"

            # BOM structure: {product_id_str: {component_id: quantity}}
            for product_id_str, components in bom_data.items():
                product_id = int(product_id_str)

                for component_id, quantity in components.items():
                    bom = ProductBom(
                        product_id=product_id,
                        component_product_id=int(component_id),
                        component_quantity=quantity,
                        production_process_id=process_id,
                        alternate_group=0,
                        priority=1,
                        scrap_percentage=2.0,  # 2% scrap
                        config_id=config_id
                    )
                    db.add(bom)
                    bom_count += 1

        await db.commit()
        print(f"✓ Created {bom_count} BOM entries")
        print()

        # ====================================================================
        # 5. Create Sourcing Rules
        # ====================================================================
        print("Creating sourcing rules...")

        # Strategy: Create sourcing rules based on lanes
        # - If lane goes to manufacturer: manufacture rule
        # - If lane from market_supply: buy rule
        # - Otherwise: transfer rule

        sourcing_count = 0

        # Get all items that need sourcing rules (all products)
        for item in items.values():
            # For each node that could need this item
            for node in nodes.values():
                if node.master_type in ['manufacturer', 'inventory', 'market_demand']:
                    # Find upstream nodes (potential sources)
                    upstream_nodes = [n for n in nodes.values()
                                     if any(l.from_site_id == n.id and l.to_site_id == node.id
                                           for l in lanes)]

                    for upstream in upstream_nodes:
                        # Determine rule type
                        if node.master_type == 'manufacturer':
                            rule_type = 'manufacture'
                        elif upstream.master_type == 'market_supply':
                            rule_type = 'buy'
                        else:
                            rule_type = 'transfer'

                        sourcing = SourcingRules(
                            product_id=item.id,
                            site_id=node.id,
                            supplier_site_id=upstream.id,
                            priority=1,
                            sourcing_rule_type=rule_type,
                            allocation_percent=100.0,
                            lead_time=2,
                            unit_cost=10.0,
                            eff_start_date='1900-01-01 00:00:00',
                            eff_end_date='9999-12-31 23:59:59'
                        )
                        db.add(sourcing)
                        sourcing_count += 1

        await db.commit()
        print(f"✓ Created {sourcing_count} sourcing rules")
        print()

        # ====================================================================
        # Summary
        # ====================================================================
        print("=" * 80)
        print("✅ Seeding Complete")
        print("=" * 80)
        print()
        print("Summary:")
        print(f"  • Forecasts: {forecast_count}")
        print(f"  • Production Processes: {prod_process_count}")
        print(f"  • BOMs: {bom_count}")
        print(f"  • Sourcing Rules: {sourcing_count}")
        print()


if __name__ == "__main__":
    asyncio.run(seed_planning_data())
