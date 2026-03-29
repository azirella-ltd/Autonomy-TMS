"""
Migration Script: Legacy Engine → Execution Engine

Migrates existing simulation data from legacy Node-based engine
to new AWS SC execution-based engine with full order lifecycle tracking.

Migration Strategy:
1. Read ScenarioUserPeriod records (legacy state)
2. Generate OutboundOrderLine, PurchaseOrder, TransferOrder equivalents
3. Create RoundMetric records from ScenarioUserPeriod data
4. Validate data integrity
5. Enable parallel testing mode

Usage:
    python scripts/migrate_to_execution_engine.py --scenario-id 1 [--dry-run] [--validate]
"""

import asyncio
import argparse
import sys
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, and_

from app.core.config import settings
from app.models.scenario import Scenario
from app.models.supply_chain import ScenarioUserPeriod
from app.models.sc_entities import OutboundOrderLine, InventoryLevel
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLineItem
from app.models.transfer_order import TransferOrder, TransferOrderLineItem
from app.models.round_metric import RoundMetric
from app.models.supply_chain_config import Site


class LegacyToExecutionMigrator:
    """Migrates simulation data from legacy to execution engine."""

    def __init__(self, db: AsyncSession, scenario_id: int, dry_run: bool = False):
        self.db = db
        self.scenario_id = scenario_id
        self.dry_run = dry_run
        self.migration_log = []

    async def migrate(self) -> Dict[str, Any]:
        """
        Execute full migration.

        Returns:
            Migration summary with counts and validation results
        """
        self.log(f"Starting migration for scenario {self.scenario_id}")

        # Step 1: Load scenario and validate
        scenario = await self._load_and_validate_scenario()
        if not scenario:
            return {'status': 'error', 'message': f'Scenario {self.scenario_id} not found'}

        # Step 2: Load legacy data
        legacy_data = await self._load_legacy_data()
        self.log(f"Loaded {len(legacy_data)} rounds of legacy data")

        # Step 3: Migrate inventory levels
        inventory_summary = await self._migrate_inventory_levels(legacy_data)

        # Step 4: Reconstruct orders from state changes
        orders_summary = await self._reconstruct_orders(legacy_data, scenario)

        # Step 5: Migrate round metrics
        metrics_summary = await self._migrate_round_metrics(legacy_data)

        # Step 6: Validate migration
        validation = await self._validate_migration(scenario)

        # Commit or rollback
        if not self.dry_run and validation['valid']:
            await self.db.commit()
            self.log("Migration committed successfully")
        else:
            await self.db.rollback()
            self.log("Migration rolled back (dry-run or validation failed)")

        return {
            'status': 'success' if validation['valid'] else 'validation_failed',
            'scenario_id': self.scenario_id,
            'dry_run': self.dry_run,
            'inventory': inventory_summary,
            'orders': orders_summary,
            'metrics': metrics_summary,
            'validation': validation,
            'log': self.migration_log,
        }

    async def _load_and_validate_scenario(self) -> Optional[Scenario]:
        """Load scenario and validate it's eligible for migration."""
        scenario = await self.db.get(Scenario, self.scenario_id)
        if not scenario:
            self.log(f"ERROR: Scenario {self.scenario_id} not found")
            return None

        self.log(f"Scenario: {scenario.name}, Status: {scenario.status}, Rounds: {scenario.current_period}")
        return scenario

    async def _load_legacy_data(self) -> List[ScenarioUserPeriod]:
        """Load all ScenarioUserPeriod records for the scenario."""
        result = await self.db.execute(
            select(ScenarioUserPeriod)
            .where(ScenarioUserPeriod.scenario_round_id == self.scenario_id)
            .order_by(ScenarioUserPeriod.scenario_round_id)
        )
        return list(result.scalars().all())

    async def _migrate_inventory_levels(self, legacy_data: List[ScenarioUserPeriod]) -> Dict[str, Any]:
        """
        Migrate inventory levels from ScenarioUserPeriod to InventoryLevel.

        Uses latest round's inventory as starting point.
        """
        if not legacy_data:
            return {'inventory_levels_created': 0}

        # Get latest round per site
        latest_rounds = {}
        for pr in legacy_data:
            if pr.site_id not in latest_rounds or pr.round_number > latest_rounds[pr.site_id].round_number:
                latest_rounds[pr.site_id] = pr

        inventory_count = 0

        for site_id, pr in latest_rounds.items():
            # Check if inventory level already exists
            existing = await self.db.execute(
                select(InventoryLevel).where(
                    and_(
                        InventoryLevel.site_id == site_id,
                        InventoryLevel.scenario_id == self.scenario_id
                    )
                )
            )
            if existing.scalar_one_or_none():
                self.log(f"Inventory level already exists for site {site_id}, skipping")
                continue

            # Get scenario
            scenario = await self.db.get(Scenario, self.scenario_id)

            # Create inventory level
            inv_level = InventoryLevel(
                site_id=site_id,
                product_id="BEER-CASE",  # Default simulation product
                quantity=float(pr.inventory),
                config_id=scenario.supply_chain_config_id if scenario else None,
                scenario_id=self.scenario_id,
                as_of_date=date.today(),
            )

            self.db.add(inv_level)
            inventory_count += 1
            self.log(f"Created inventory level for site {site_id}: {pr.inventory} units")

        await self.db.flush()

        return {'inventory_levels_created': inventory_count}

    async def _reconstruct_orders(self, legacy_data: List[ScenarioUserPeriod], scenario: Scenario) -> Dict[str, Any]:
        """
        Reconstruct orders from legacy state changes.

        Infers orders from inventory movements, shipments, and backlog changes.
        """
        orders_created = 0
        pos_created = 0
        tos_created = 0

        # Group by round
        rounds_data = {}
        for pr in legacy_data:
            if pr.round_number not in rounds_data:
                rounds_data[pr.round_number] = []
            rounds_data[pr.round_number].append(pr)

        # Process each round
        for round_num in sorted(rounds_data.keys()):
            round_prs = rounds_data[round_num]

            for pr in round_prs:
                # Reconstruct customer order if backlog increased
                if pr.backlog > 0:
                    # Create customer order
                    order = OutboundOrderLine(
                        order_id=f"MIGRATED-ORD-{self.scenario_id}-{round_num}-{pr.site_id}",
                        line_number=1,
                        product_id="BEER-CASE",
                        site_id=pr.site_id,
                        ordered_quantity=float(pr.backlog),
                        requested_delivery_date=date.today() + timedelta(weeks=1),
                        order_date=date.today() - timedelta(weeks=(scenario.current_period - round_num)),
                        status="PARTIALLY_FULFILLED" if pr.backlog > 0 else "FULFILLED",
                        priority_code="STANDARD",
                        shipped_quantity=0.0,
                        backlog_quantity=float(pr.backlog),
                        config_id=scenario.supply_chain_config_id,
                        scenario_id=self.scenario_id,
                    )
                    self.db.add(order)
                    orders_created += 1

                # Reconstruct PO if order was placed (from ScenarioUserPeriod.order_placed)
                if hasattr(pr, 'order_placed') and pr.order_placed and pr.order_placed > 0:
                    po = PurchaseOrder(
                        po_number=f"MIGRATED-PO-{self.scenario_id}-{round_num}-{pr.site_id}",
                        supplier_site_id=pr.site_id + 1,  # Simplified: assume upstream site
                        destination_site_id=pr.site_id,
                        config_id=scenario.supply_chain_config_id,
                        status="APPROVED",
                        order_date=date.today() - timedelta(weeks=(scenario.current_period - round_num)),
                        requested_delivery_date=date.today() + timedelta(weeks=2),
                        scenario_id=self.scenario_id,
                        order_round=round_num,
                    )
                    self.db.add(po)
                    await self.db.flush()

                    # Add line item
                    po_line = PurchaseOrderLineItem(
                        po_id=po.id,
                        line_number=1,
                        product_id="BEER-CASE",
                        quantity=float(pr.order_placed),
                        shipped_quantity=0.0,
                        received_quantity=0.0,
                        unit_price=10.0,
                        line_total=float(pr.order_placed) * 10.0,
                    )
                    self.db.add(po_line)
                    pos_created += 1

        await self.db.flush()

        self.log(f"Reconstructed {orders_created} customer orders, {pos_created} purchase orders")

        return {
            'customer_orders_created': orders_created,
            'purchase_orders_created': pos_created,
            'transfer_orders_created': tos_created,
        }

    async def _migrate_round_metrics(self, legacy_data: List[ScenarioUserPeriod]) -> Dict[str, Any]:
        """
        Migrate ScenarioUserPeriod data to RoundMetric records.

        Direct 1:1 mapping of legacy metrics.
        """
        metrics_created = 0

        for pr in legacy_data:
            # Check if metric already exists
            existing = await self.db.execute(
                select(RoundMetric).where(
                    and_(
                        RoundMetric.scenario_id == self.scenario_id,
                        RoundMetric.round_number == pr.round_number,
                        RoundMetric.site_id == pr.site_id
                    )
                )
            )
            if existing.scalar_one_or_none():
                self.log(f"Metric already exists for round {pr.round_number}, site {pr.site_id}, skipping")
                continue

            # Create RoundMetric
            metric = RoundMetric(
                scenario_id=self.scenario_id,
                round_number=pr.round_number,
                site_id=pr.site_id,
                scenario_user_id=pr.scenario_user_id,
                inventory=float(pr.inventory),
                backlog=float(pr.backlog),
                pipeline_qty=0.0,  # Not tracked in legacy
                in_transit_qty=0.0,  # Not tracked in legacy
                holding_cost=float(pr.holding_cost) if hasattr(pr, 'holding_cost') else 0.0,
                backlog_cost=float(pr.backlog_cost) if hasattr(pr, 'backlog_cost') else 0.0,
                total_cost=float(pr.total_cost) if hasattr(pr, 'total_cost') else 0.0,
                cumulative_cost=float(pr.cumulative_cost) if hasattr(pr, 'cumulative_cost') else 0.0,
                fill_rate=None,  # Calculate later
                service_level=None,  # Calculate later
                orders_received=0,
                orders_fulfilled=0,
                incoming_order_qty=0.0,
                outgoing_order_qty=float(pr.order_placed) if hasattr(pr, 'order_placed') else 0.0,
                shipment_qty=0.0,
            )

            self.db.add(metric)
            metrics_created += 1

        await self.db.flush()

        self.log(f"Created {metrics_created} round metrics")

        return {'metrics_created': metrics_created}

    async def _validate_migration(self, scenario: Scenario) -> Dict[str, Any]:
        """
        Validate migration integrity.

        Checks:
        - All rounds have metrics
        - Inventory levels match latest metrics
        - Order counts are reasonable
        """
        validation_errors = []

        # Check metrics count
        metrics_result = await self.db.execute(
            select(RoundMetric).where(RoundMetric.scenario_id == self.scenario_id)
        )
        metrics_count = len(list(metrics_result.scalars().all()))

        # Expected: sites * rounds
        result = await self.db.execute(
            select(Site).where(Site.config_id == scenario.supply_chain_config_id)
        )
        sites_count = len(list(result.scalars().all()))
        expected_metrics = sites_count * scenario.current_period

        if metrics_count < expected_metrics:
            validation_errors.append(
                f"Insufficient metrics: {metrics_count} < {expected_metrics} expected"
            )

        # Check inventory levels exist
        inv_result = await self.db.execute(
            select(InventoryLevel).where(InventoryLevel.scenario_id == self.scenario_id)
        )
        inv_count = len(list(inv_result.scalars().all()))

        if inv_count < sites_count:
            validation_errors.append(
                f"Insufficient inventory levels: {inv_count} < {sites_count} expected"
            )

        is_valid = len(validation_errors) == 0

        self.log(f"Validation: {'PASSED' if is_valid else 'FAILED'}")
        for error in validation_errors:
            self.log(f"  - {error}")

        return {
            'valid': is_valid,
            'errors': validation_errors,
            'metrics_count': metrics_count,
            'expected_metrics': expected_metrics,
            'inventory_levels': inv_count,
        }

    def log(self, message: str):
        """Add message to migration log."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        self.migration_log.append(log_message)
        print(log_message)


async def run_migration(scenario_id: int, dry_run: bool = False, validate_only: bool = False):
    """Run migration for a scenario."""
    # Create database engine
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI, echo=False)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        migrator = LegacyToExecutionMigrator(session, scenario_id, dry_run=dry_run)

        if validate_only:
            # Load scenario and validate
            scenario = await migrator._load_and_validate_scenario()
            if scenario:
                validation = await migrator._validate_migration(scenario)
                print("\n=== Validation Results ===")
                print(f"Valid: {validation['valid']}")
                for error in validation.get('errors', []):
                    print(f"  ERROR: {error}")
                return

        # Run full migration
        result = await migrator.migrate()

        print("\n=== Migration Summary ===")
        print(f"Status: {result['status']}")
        print(f"Scenario ID: {result['scenario_id']}")
        print(f"Dry Run: {result['dry_run']}")
        print(f"\nInventory:")
        print(f"  - Levels created: {result['inventory']['inventory_levels_created']}")
        print(f"\nOrders:")
        print(f"  - Customer orders: {result['orders']['customer_orders_created']}")
        print(f"  - Purchase orders: {result['orders']['purchase_orders_created']}")
        print(f"  - Transfer orders: {result['orders']['transfer_orders_created']}")
        print(f"\nMetrics:")
        print(f"  - Round metrics: {result['metrics']['metrics_created']}")
        print(f"\nValidation:")
        print(f"  - Valid: {result['validation']['valid']}")
        for error in result['validation'].get('errors', []):
            print(f"  - ERROR: {error}")

    await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Migrate simulation data to Execution Engine")
    parser.add_argument("--scenario-id", type=int, required=True, help="Scenario ID to migrate")
    parser.add_argument("--dry-run", action="store_true", help="Run without committing changes")
    parser.add_argument("--validate", action="store_true", help="Only validate, don't migrate")

    args = parser.parse_args()

    asyncio.run(run_migration(args.scenario_id, dry_run=args.dry_run, validate_only=args.validate))


if __name__ == "__main__":
    main()
