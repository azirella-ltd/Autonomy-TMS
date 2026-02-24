"""
simulation to SC Adapter

This adapter translates between simulation concepts and SC Data Model concepts
enabling The simulation to use SC planning logic as a special case.

Concept Mapping:
- simulation Node     → SC Site (product_id, site_id)
- ScenarioUser Inventory   → SC InvLevel (on_hand_qty)
- ScenarioUser Order       → SC Supply Plan (PO/TO request)
- Round              → SC Planning Period
- Demand Pattern     → SC Forecast

Phase 2 Architecture: This adapter enables dual-mode operation where games can
optionally use SC 3-step planning instead of legacy engine.py logic.
"""

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scenario import Scenario
from app.models.scenario_user import ScenarioUser

# Aliases for backwards compatibility
Game = Scenario
ScenarioUser = ScenarioUser
from app.models.supply_chain_config import SupplyChainConfig, Node
from app.models.sc_entities import Product
from app.models.sc_entities import (
    InvLevel,
    Forecast,
    SupplyPlan,
    OutboundOrderLine,
)


class SimulationToSCAdapter:
    """
    Adapter to translate simulation state to/from SC planning entities

    This class bridges the gap between simulation's in-memory simulation
    and SC's database-driven planning system.
    """

    def __init__(self, game: Game, db: AsyncSession):
        """
        Initialize adapter

        Args:
            game: The simulation instance
            db: Database session
        """
        self.game = game
        self.db = db
        self.config = game.supply_chain_config
        self.group_id = game.group_id
        self.config_id = game.supply_chain_config_id

        if not self.group_id:
            raise ValueError(f"Game {game.id} has no group_id - cannot use SC planning")

    async def sync_inventory_levels(self, round_number: int) -> int:
        """
        Sync current game inventory to inv_level table

        Reads scenario_user inventory from game state and writes to inv_level
        so SC planner can see current on-hand quantities.

        Args:
            round_number: Current game round

        Returns:
            Number of inv_level records created/updated
        """
        print(f"  Syncing inventory levels for round {round_number}...")

        # Get all scenario_users in this game
        result = await self.db.execute(
            select(ScenarioUser).filter(ScenarioUser.scenario_id == self.game.id)
        )
        scenario_users = result.scalars().all()

        # Get config data
        await self.db.refresh(self.config, ['nodes', 'items'])

        # Delete old snapshots for this game (if any)
        await self.db.execute(
            delete(InvLevel).filter(
                InvLevel.group_id == self.group_id,
                InvLevel.config_id == self.config_id,
            )
        )

        records_created = 0
        snapshot_date = self.game.start_date + timedelta(days=round_number * 7)

        # For each scenario_user, create inv_level record
        for scenario_user in scenario_users:
            # Get scenario_user's node
            node = next((n for n in self.config.nodes if n.name == scenario_user.role), None)
            if not node:
                print(f"    Warning: No node found for scenario_user role {scenario_user.role}")
                continue

            # Get item (simulation typically has 1 item: "Cases" or similar)
            if not self.config.items:
                print(f"    Warning: No items defined in config")
                continue

            item = self.config.items[0]  # Use first item

            # Get scenario_user's current inventory from game state
            # This depends on how game state is stored - check game.config
            inventory_qty = self._get_player_inventory(scenario_user, round_number)

            # Create InvLevel record
            inv_level = InvLevel(
                product_id=item.id,
                site_id=node.id,
                on_hand_qty=inventory_qty,
                available_qty=max(0, inventory_qty),  # Available = on-hand minus reserved
                reserved_qty=0,  # simulation doesn't track reservations
                in_transit_qty=0,  # TODO: Calculate from pipeline
                backorder_qty=max(0, -inventory_qty),  # Negative inventory = backlog
                safety_stock_qty=0,  # TODO: Get from node policy
                reorder_point_qty=0,
                snapshot_date=snapshot_date,
                group_id=self.group_id,
                config_id=self.config_id,
            )

            self.db.add(inv_level)
            records_created += 1

            print(f"    OK {scenario_user.role}: on_hand={inventory_qty}")

        await self.db.commit()
        print(f"  OK Created {records_created} inv_level records")

        return records_created

    def _get_player_inventory(self, scenario_user: ScenarioUser, round_number: int) -> float:
        """
        Extract scenario_user's current inventory from game state

        Args:
            scenario_user: ScenarioUser instance
            round_number: Current round

        Returns:
            Current inventory quantity (can be negative for backlog)
        """
        # Game state is stored in game.config JSON
        # Structure: game.config['nodes'][role]['inventory']
        game_config = self.game.config or {}
        nodes_state = game_config.get('nodes', {})
        player_state = nodes_state.get(scenario_user.role, {})

        # Get inventory (default to 12 for simulation initial state)
        inventory = player_state.get('inventory', 12)

        return float(inventory)

    async def sync_demand_forecast(
        self,
        round_number: int,
        horizon: int = 52,
    ) -> int:
        """
        Sync market demand pattern to forecast table

        Creates forecast records for future rounds based on demand_pattern.

        Args:
            round_number: Current game round
            horizon: Number of periods ahead to forecast

        Returns:
            Number of forecast records created
        """
        print(f"  Syncing demand forecast for {horizon} periods ahead...")

        # Get demand pattern from game
        demand_pattern = self.game.demand_pattern or self.game.config.get('demand_pattern', {})

        if not demand_pattern:
            print(f"    Warning: No demand pattern defined")
            return 0

        # Get retailer node (where market demand hits)
        await self.db.refresh(self.config, ['nodes', 'items'])
        retailer_node = next(
            (n for n in self.config.nodes if n.type in ['retailer', 'Retailer']),
            None,
        )

        if not retailer_node:
            print(f"    Warning: No retailer node found")
            return 0

        item = self.config.items[0] if self.config.items else None
        if not item:
            print(f"    Warning: No item found")
            return 0

        # Delete old forecasts for this game
        await self.db.execute(
            delete(Forecast).filter(
                Forecast.group_id == self.group_id,
                Forecast.config_id == self.config_id,
                Forecast.scenario_id == self.game.id,
            )
        )

        records_created = 0

        # Create forecast records for each period
        for period_offset in range(horizon):
            forecast_round = round_number + period_offset
            forecast_date = self.game.start_date + timedelta(days=forecast_round * 7)

            # Get demand for this period from pattern
            demand_qty = self._get_demand_for_period(demand_pattern, forecast_round)

            forecast = Forecast(
                product_id=item.id,
                site_id=retailer_node.id,
                forecast_date=forecast_date,
                forecast_quantity=demand_qty,
                forecast_p50=demand_qty,  # Median = mean for deterministic
                forecast_p10=demand_qty * 0.8,  # Pessimistic
                forecast_p90=demand_qty * 1.2,  # Optimistic
                user_override_quantity=None,
                is_active='true',
                group_id=self.group_id,
                config_id=self.config_id,
                scenario_id=self.game.id,
            )

            self.db.add(forecast)
            records_created += 1

        await self.db.commit()
        print(f"  OK Created {records_created} forecast records")

        return records_created

    def _get_demand_for_period(
        self,
        demand_pattern: dict,
        period: int,
    ) -> float:
        """
        Get demand quantity for a specific period from demand pattern

        Args:
            demand_pattern: Demand pattern dict
            period: Period number (0-indexed)

        Returns:
            Demand quantity for this period
        """
        # simulation demand patterns have format:
        # {"type": "step", "initial": 4, "step_week": 5, "step_value": 8}
        # or
        # {"weeks": [4, 4, 4, 4, 8, 8, ...]}

        pattern_type = demand_pattern.get('type', 'constant')

        if pattern_type == 'step':
            initial = demand_pattern.get('initial', 4)
            step_week = demand_pattern.get('step_week', 5)
            step_value = demand_pattern.get('step_value', 8)

            if period < step_week:
                return float(initial)
            else:
                return float(step_value)

        elif pattern_type == 'constant':
            return float(demand_pattern.get('value', 4))

        elif 'weeks' in demand_pattern:
            weeks = demand_pattern['weeks']
            if period < len(weeks):
                return float(weeks[period])
            else:
                # Repeat last value
                return float(weeks[-1]) if weeks else 4.0

        else:
            # Default to steady state
            return 4.0

    async def convert_supply_plans_to_orders(
        self,
        supply_plans: List[SupplyPlan],
    ) -> Dict[str, float]:
        """
        Convert SC supply plans to simulation scenario_user orders

        Maps:
        - po_request (Purchase Order) -> ScenarioUser order to upstream supplier
        - to_request (Transfer Order) -> ScenarioUser order to upstream DC
        - mo_request (Manufacturing Order) -> Production order at factory

        Args:
            supply_plans: List of SupplyPlan recommendations from SC planner

        Returns:
            Dict mapping scenario_user role -> order quantity for this round
        """
        print(f"  Converting {len(supply_plans)} supply plans to scenario_user orders...")

        player_orders = {}

        # Get node mapping
        await self.db.refresh(self.config, ['nodes'])
        node_id_to_name = {n.id: n.name for n in self.config.nodes}

        # Group supply plans by destination site (scenario_user)
        for plan in supply_plans:
            # Get the scenario_user role for this destination site
            role = node_id_to_name.get(plan.destination_site_id)

            if not role:
                print(f"    Warning: No role found for site_id {plan.destination_site_id}")
                continue

            # Aggregate orders for this scenario_user
            if role not in player_orders:
                player_orders[role] = 0

            player_orders[role] += plan.planned_order_quantity

            print(f"    OK {role}: order {plan.planned_order_quantity} "
                  f"(type={plan.plan_type}, from site={plan.source_site_id})")

        print(f"  OK Converted to {len(player_orders)} scenario_user orders")

        return player_orders

    async def get_current_inventory(self, role: str) -> float:
        """
        Get current inventory for a scenario_user/node

        Args:
            role: ScenarioUser role (node name)

        Returns:
            Current inventory quantity
        """
        result = await self.db.execute(
            select(ScenarioUser).filter(
                ScenarioUser.scenario_id == self.game.id,
                ScenarioUser.role == role,
            )
        )
        scenario_user = result.scalar_one_or_none()

        if not scenario_user:
            return 0.0

        return self._get_player_inventory(scenario_user, self.game.current_round)

    async def record_actual_demand(
        self,
        role: str,
        demand_qty: float,
        period_date: date,
    ) -> None:
        """
        Record actual customer demand in outbound_order_line table

        This allows SC to track forecast accuracy and consume forecasts
        with actuals in the demand processing step.

        Args:
            role: ScenarioUser role (typically Retailer)
            demand_qty: Actual demand quantity
            period_date: Date of the demand
        """
        # Get node and item
        await self.db.refresh(self.config, ['nodes', 'items'])
        node = next((n for n in self.config.nodes if n.name == role), None)
        item = self.config.items[0] if self.config.items else None

        if not node or not item:
            return

        # Create outbound order line
        order_line = OutboundOrderLine(
            order_id=f"GAME_{self.game.id}_R{self.game.current_round}",
            line_number=1,
            product_id=item.id,
            site_id=node.id,
            ordered_quantity=demand_qty,
            requested_delivery_date=period_date,
            order_date=period_date,
            config_id=self.config_id,
            scenario_id=self.game.id,
        )

        self.db.add(order_line)
        await self.db.commit()

        print(f"    OK Recorded actual demand: {role} = {demand_qty}")
