"""
simulation to SC Execution Adapter

This adapter translates simulation execution to SC Work Order Management,
treating simulation as an EXECUTION scenario, not a planning scenario.

Key Architectural Change (Phase 2 Refactor):
- OLD: simulation used SC Planning (demand processing → supply plans)
- NEW: simulation uses SC Execution (work orders → order fulfillment)

Concept Mapping for EXECUTION:
- ScenarioUser places order       → InboundOrderLine (quantity_submitted)
- Order in transit          → InboundOrderLine (status='open', expected_delivery_date)
- Shipment arrives          → InboundOrderLine (quantity_received, order_receive_date)
- Customer demand hits      → OutboundOrderLine (quantity_delivered)
- Inventory snapshot        → InvLevel (on_hand_qty)

Work Order Types:
- TO (Transfer Order):      Between internal sites (Distributor → Wholesaler)
- MO (Manufacturing Order): Production at factory
- PO (Purchase Order):      From external market (if market_supply node exists)

Planning vs Execution Separation:
- Planning: Happens BEFORE the game starts (forecast, inv policies, sourcing rules)
- Execution: Happens DURING the game rounds (work orders, fulfillment, inventory updates)

References:
- SC Work Orders: https://docs.[removed]
- Inbound Order Line: https://docs.[removed]
- Outbound Order Line: https://docs.[removed]
"""

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scenario import Scenario
from app.models.scenario_user import ScenarioUser

# Aliases for backwards compatibility
Game = Scenario
ScenarioUser = ScenarioUser
from app.models.supply_chain_config import SupplyChainConfig, Node, TransportationLane
from app.models.sc_entities import Product
from app.models.sc_entities import (
    InvLevel,
    OutboundOrderLine,
    SourcingRules
)
from app.models.sc_planning import (
    InboundOrderLine,
    AggregatedOrder,
    OrderAggregationPolicy
)
from app.services.sc_planning.execution_cache import ExecutionCache
from app.services.sc_planning.stochastic_sampler import StochasticSampler


class SimulationExecutionAdapter:
    """
    Adapter to translate simulation execution to/from SC work order entities

    This class manages the execution lifecycle:
    1. Sync current game state (inventory, backlog) → inv_level
    2. Record customer demand → outbound_order_line
    3. Create scenario_user orders → inbound_order_line (work orders)
    4. Process order deliveries → update quantity_received, inventory
    5. Extract orders from work orders → scenario_user orders for game engine
    """

    def __init__(self, game: Game, db: AsyncSession, use_cache: bool = True):
        """
        Initialize execution adapter

        Args:
            game: The simulation instance
            db: Database session
            use_cache: Enable execution cache for performance (default: True)
        """
        self.game = game
        self.db = db
        self.config = game.supply_chain_config
        self.tenant_id = game.tenant_id
        self.config_id = game.supply_chain_config_id

        if not self.tenant_id:
            raise ValueError(f"Game {game.id} has no tenant_id - cannot use SC execution")

        if not self.config_id:
            raise ValueError(f"Game {game.id} has no config_id - cannot use SC execution")

        # Phase 3: Execution cache for performance
        self.cache: Optional[ExecutionCache] = None
        if use_cache:
            self.cache = ExecutionCache(db, self.config_id, self.tenant_id)

        # Phase 5: Stochastic sampler for distribution sampling
        self.stochastic_sampler = StochasticSampler(scenario_id=game.id, use_cache=use_cache)

    # ============================================================================
    # STATE SYNCHRONIZATION (Game → SC)
    # ============================================================================

    async def sync_inventory_levels(self, round_number: int) -> int:
        """
        Sync current game inventory to inv_level table (execution snapshot)

        Reads scenario_user inventory from game state and writes to inv_level
        so SC can track on-hand quantities during execution.

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

        # Delete old snapshots for this game round
        await self.db.execute(
            delete(InvLevel).filter(
                InvLevel.customer_id == self.tenant_id,
                InvLevel.config_id == self.config_id
            )
        )

        records_created = 0
        snapshot_date = self.game.start_date + timedelta(days=round_number * 7)

        # For each scenario_user, create inv_level record
        for scenario_user in scenario_users:
            # Get scenario_user's node
            node = next((n for n in self.config.nodes if n.name == scenario_user.role), None)
            if not node:
                print(f"    ⚠️  No node found for scenario_user role {scenario_user.role}")
                continue

            # Get item (simulation typically has 1 item: "Cases")
            if not self.config.items:
                print(f"    ⚠️  No items defined in config")
                continue

            item = self.config.items[0]

            # Get scenario_user's current inventory and backlog from game state
            inventory_qty, backlog_qty = self._get_scenario_user_inventory_and_backlog(
                scenario_user, round_number
            )

            # Calculate in-transit quantity from open inbound orders
            in_transit_qty = await self._calculate_in_transit(item.id, node.id)

            # Create InvLevel record
            inv_level = InvLevel(
                product_id=item.id,
                site_id=node.id,
                on_hand_qty=inventory_qty,
                available_qty=max(0, inventory_qty - backlog_qty),
                reserved_qty=0,
                in_transit_qty=in_transit_qty,
                backorder_qty=backlog_qty,
                safety_stock_qty=0,
                reorder_point_qty=0,
                snapshot_date=snapshot_date,
                tenant_id=self.tenant_id,
                config_id=self.config_id
            )

            self.db.add(inv_level)
            records_created += 1

            print(f"    ✓ {scenario_user.role}: on_hand={inventory_qty}, backlog={backlog_qty}, "
                  f"in_transit={in_transit_qty}")

        await self.db.commit()
        print(f"  ✓ Created {records_created} inv_level records")

        return records_created

    async def _calculate_in_transit(self, product_id: int, site_id: int) -> float:
        """
        Calculate in-transit quantity from open inbound orders

        Args:
            product_id: Product ID
            site_id: Destination site ID

        Returns:
            Total quantity in transit
        """
        result = await self.db.execute(
            select(InboundOrderLine).filter(
                and_(
                    InboundOrderLine.product_id == product_id,
                    InboundOrderLine.to_site_id == site_id,
                    InboundOrderLine.customer_id == self.tenant_id,
                    InboundOrderLine.config_id == self.config_id,
                    InboundOrderLine.scenario_id == self.game.id,
                    InboundOrderLine.status.in_(['open', 'confirmed']),
                    InboundOrderLine.quantity_received == None
                )
            )
        )
        orders = result.scalars().all()

        in_transit = sum(order.quantity_submitted for order in orders)
        return float(in_transit)

    def _get_scenario_user_inventory_and_backlog(
        self,
        scenario_user: ScenarioUser,
        round_number: int
    ) -> Tuple[float, float]:
        """
        Extract scenario_user's current inventory and backlog from game state

        Args:
            scenario_user: ScenarioUser instance
            round_number: Current round

        Returns:
            Tuple of (inventory, backlog)
        """
        game_config = self.game.config or {}
        nodes_state = game_config.get('nodes', {})
        scenario_user_state = nodes_state.get(scenario_user.role, {})

        inventory = scenario_user_state.get('inventory', 12)
        backlog = scenario_user_state.get('backlog', 0)

        return float(inventory), float(backlog)

    # ============================================================================
    # CUSTOMER DEMAND (Outbound Orders)
    # ============================================================================

    async def record_customer_demand(
        self,
        role: str,
        demand_qty: float,
        round_number: int
    ) -> None:
        """
        Record actual customer demand in outbound_order_line table

        Creates an outbound order representing customer demand hitting the retailer.
        This is execution data, not planning data.

        Args:
            role: ScenarioUser role (typically Retailer)
            demand_qty: Actual demand quantity
            round_number: Current game round
        """
        print(f"    Recording customer demand: {role} = {demand_qty}")

        # Get node and item
        await self.db.refresh(self.config, ['nodes', 'items'])
        node = next((n for n in self.config.nodes if n.name == role), None)
        item = self.config.items[0] if self.config.items else None

        if not node or not item:
            print(f"    ⚠️  Cannot record demand: node or item not found")
            return

        order_date = self.game.start_date + timedelta(days=round_number * 7)

        # Create outbound order line (execution record)
        order_line = OutboundOrderLine(
            order_id=f"GAME_{self.game.id}_R{round_number}",
            line_number=1,
            product_id=item.id,
            site_id=node.id,
            ship_from_site_id=node.id,
            # Execution quantities
            init_quantity_requested=demand_qty,
            final_quantity_requested=demand_qty,
            quantity_promised=demand_qty,
            quantity_delivered=demand_qty,  # Immediate fulfillment attempt
            # Dates
            order_date=order_date,
            requested_delivery_date=order_date,
            promised_delivery_date=order_date,
            actual_delivery_date=order_date,
            # Status
            status='delivered',
            # Multi-tenancy
            tenant_id=self.tenant_id,
            config_id=self.config_id,
            scenario_id=self.game.id,
            round_number=round_number
        )

        self.db.add(order_line)
        await self.db.commit()

        print(f"    ✓ Recorded customer demand: {role} = {demand_qty}")

    # ============================================================================
    # PLAYER ORDERS (Inbound Work Orders)
    # ============================================================================

    async def create_work_orders(
        self,
        scenario_user_orders: Dict[str, float],
        round_number: int
    ) -> int:
        """
        Create inbound work orders (TO/MO/PO) from scenario_user order decisions

        This is the PRIMARY execution method: scenario_user orders become work orders.

        Args:
            scenario_user_orders: Dict mapping role → order quantity
            round_number: Current game round

        Returns:
            Number of work orders created
        """
        print(f"  Creating work orders for round {round_number}...")

        await self.db.refresh(self.config, ['nodes', 'items', 'lanes'])
        item = self.config.items[0] if self.config.items else None

        if not item:
            print(f"    ⚠️  No item found")
            return 0

        order_date = self.game.start_date + timedelta(days=round_number * 7)
        orders_created = 0

        for role, order_qty in scenario_user_orders.items():
            if order_qty <= 0:
                continue

            # Get node for this scenario_user
            node = next((n for n in self.config.nodes if n.name == role), None)
            if not node:
                print(f"    ⚠️  No node found for role {role}")
                continue

            # Find upstream source (from lane)
            upstream_lane = next(
                (lane for lane in self.config.lanes if lane.to_site_id == node.id),
                None
            )

            if not upstream_lane:
                print(f"    ⚠️  No upstream lane found for {role}")
                continue

            upstream_node = next(
                (n for n in self.config.nodes if n.id == upstream_lane.from_site_id),
                None
            )

            if not upstream_node:
                print(f"    ⚠️  No upstream node found for {role}")
                continue

            # Determine order type and lead time
            order_type, lead_time_days = self._determine_order_type_and_lead_time(
                upstream_node, upstream_lane
            )

            expected_delivery = order_date + timedelta(days=lead_time_days)

            # Create inbound order line (work order)
            inbound_order = InboundOrderLine(
                order_id=f"GAME_{self.game.id}_R{round_number}_{role}",
                line_number=1,
                product_id=item.id,
                to_site_id=node.id,
                from_site_id=upstream_node.id if order_type in ['TO', 'MO'] else None,
                tpartner_id=None,  # simulation doesn't use external vendors
                # Order type
                order_type=order_type,
                # Quantities
                quantity_submitted=order_qty,
                quantity_confirmed=order_qty,  # Auto-confirm in simulation
                quantity_received=None,  # Will be set when shipment arrives
                quantity_uom='CASES',
                # Dates
                submitted_date=order_date,
                expected_delivery_date=expected_delivery,
                earliest_delivery_date=expected_delivery,
                latest_delivery_date=expected_delivery,
                confirmation_date=order_date,  # Auto-confirm
                order_receive_date=None,  # Will be set on delivery
                # Status
                status='open',  # Will become 'received' when delivered
                vendor_status='confirmed',
                # Lead time
                lead_time_days=lead_time_days,
                # Multi-tenancy
                tenant_id=self.tenant_id,
                config_id=self.config_id,
                scenario_id=self.game.id,
                round_number=round_number
            )

            self.db.add(inbound_order)
            orders_created += 1

            print(f"    ✓ {role}: {order_type} order {order_qty} to {upstream_node.name} "
                  f"(delivery: {expected_delivery})")

        await self.db.commit()
        print(f"  ✓ Created {orders_created} work orders")

        return orders_created

    async def create_work_orders_batch(
        self,
        scenario_user_orders: Dict[str, float],
        round_number: int
    ) -> int:
        """
        Create inbound work orders using batch insert (PHASE 3 - Performance optimization)

        This method is 10-20x faster than create_work_orders() for multi-scenario_user games
        because it uses a single batch insert instead of individual inserts.

        Args:
            scenario_user_orders: Dict mapping role → order quantity
            round_number: Current game round

        Returns:
            Number of work orders created
        """
        print(f"  Creating work orders (BATCH) for round {round_number}...")

        # Ensure cache is loaded
        if self.cache and not self.cache.is_loaded():
            await self.cache.load()

        # Get item (simulation has one item: "Case")
        item = self.cache.get_first_item() if self.cache else None
        if not item:
            await self.db.refresh(self.config, ['items'])
            item = self.config.items[0] if self.config.items else None

        if not item:
            print(f"    ⚠️  No item found")
            return 0

        order_date = self.game.start_date + timedelta(days=round_number * 7)

        # Build all work orders in memory first
        work_orders = []

        for role, order_qty in scenario_user_orders.items():
            if order_qty <= 0:
                continue

            # Get node (use cache if available)
            node = self.cache.get_node_by_name(role) if self.cache else None
            if not node:
                await self.db.refresh(self.config, ['nodes', 'lanes'])
                node = next((n for n in self.config.nodes if n.name == role), None)

            if not node:
                print(f"    ⚠️  No node found for role {role}")
                continue

            # Find upstream source using cache
            upstream_node = None
            lead_time_days = 14
            order_type = 'TO'

            if self.cache:
                # Fast path: use cached sourcing rules
                upstream_node = self.cache.get_upstream_site(item.id, node.id)
                if upstream_node:
                    lead_time_days = self.cache.get_lead_time(
                        item.id, upstream_node.id, node.id
                    )
                    order_type = self._determine_order_type_from_master_type(
                        upstream_node.master_type
                    )
            else:
                # Slow path: query lanes
                upstream_lane = next(
                    (lane for lane in self.config.lanes if lane.to_site_id == node.id),
                    None
                )
                if upstream_lane:
                    upstream_node = next(
                        (n for n in self.config.nodes if n.id == upstream_lane.from_site_id),
                        None
                    )
                    if upstream_node:
                        order_type, lead_time_days = self._determine_order_type_and_lead_time(
                            upstream_node, upstream_lane
                        )

            if not upstream_node:
                print(f"    ⚠️  No upstream node found for {role}")
                continue

            expected_delivery = order_date + timedelta(days=lead_time_days)

            # Create work order object (don't add to session yet)
            work_order = InboundOrderLine(
                order_id=f"GAME_{self.game.id}_R{round_number}_{role}",
                line_number=1,
                product_id=item.id,
                to_site_id=node.id,
                from_site_id=upstream_node.id if order_type in ['TO', 'MO'] else None,
                tpartner_id=None,
                order_type=order_type,
                quantity_submitted=order_qty,
                quantity_confirmed=order_qty,
                quantity_received=None,
                quantity_uom='CASES',
                submitted_date=order_date,
                expected_delivery_date=expected_delivery,
                earliest_delivery_date=expected_delivery,
                latest_delivery_date=expected_delivery,
                confirmation_date=order_date,
                order_receive_date=None,
                status='open',
                vendor_status='confirmed',
                lead_time_days=lead_time_days,
                tenant_id=self.tenant_id,
                config_id=self.config_id,
                scenario_id=self.game.id,
                round_number=round_number
            )

            work_orders.append(work_order)

            print(f"    ✓ {role}: {order_type} order {order_qty} to {upstream_node.name} "
                  f"(delivery: {expected_delivery})")

        # Batch insert all work orders in single transaction
        if work_orders:
            self.db.add_all(work_orders)
            await self.db.commit()

        print(f"  ✓ Created {len(work_orders)} work orders (BATCH)")

        return len(work_orders)

    def _determine_order_type_from_master_type(self, master_type: str) -> str:
        """
        Determine order type from node master type

        Args:
            master_type: Node master type (manufacturer, market_supply, inventory)

        Returns:
            Order type (TO/MO/PO)
        """
        if master_type == 'manufacturer':
            return 'MO'  # Manufacturing Order
        elif master_type == 'market_supply':
            return 'PO'  # Purchase Order
        else:
            return 'TO'  # Transfer Order

    def _determine_order_type_and_lead_time(
        self,
        upstream_node: Node,
        lane: TransportationLane
    ) -> Tuple[str, int]:
        """
        Determine work order type (TO/MO/PO) and lead time

        Args:
            upstream_node: Upstream source node
            lane: Transportation lane connecting sites

        Returns:
            Tuple of (order_type, lead_time_days)
        """
        # Determine order type based on upstream node master_type
        if upstream_node.master_type == 'manufacturer':
            order_type = 'MO'  # Manufacturing Order
        elif upstream_node.master_type == 'market_supply':
            order_type = 'PO'  # Purchase Order (external)
        else:
            order_type = 'TO'  # Transfer Order (internal)

        # Get lead time from lane (weeks → days)
        lead_time_days = 14  # Default: 2 weeks

        # Try various lead time fields
        if hasattr(lane, 'lead_time_days') and lane.lead_time_days and isinstance(lane.lead_time_days, (int, float)):
            lead_time_days = int(lane.lead_time_days)
        elif hasattr(lane, 'supply_lead_time') and lane.supply_lead_time and isinstance(lane.supply_lead_time, (int, float)):
            lead_time_days = int(lane.supply_lead_time)
        elif hasattr(lane, 'lead_time') and lane.lead_time and isinstance(lane.lead_time, (int, float)):
            # Old format: weeks
            lead_time_days = int(lane.lead_time * 7)

        return order_type, lead_time_days

    async def process_deliveries(self, round_number: int) -> Dict[str, float]:
        """
        Process work order deliveries that arrive this round

        Finds all inbound orders with expected_delivery_date <= current date
        and marks them as received.

        Args:
            round_number: Current game round

        Returns:
            Dict mapping role → total received quantity
        """
        print(f"  Processing deliveries for round {round_number}...")

        current_date = self.game.start_date + timedelta(days=round_number * 7)

        # Find all open orders due for delivery
        result = await self.db.execute(
            select(InboundOrderLine).filter(
                and_(
                    InboundOrderLine.customer_id == self.tenant_id,
                    InboundOrderLine.config_id == self.config_id,
                    InboundOrderLine.scenario_id == self.game.id,
                    InboundOrderLine.status == 'open',
                    InboundOrderLine.expected_delivery_date <= current_date
                )
            )
        )
        orders = result.scalars().all()

        deliveries = {}
        await self.db.refresh(self.config, ['nodes'])
        node_id_to_name = {n.id: n.name for n in self.config.nodes}

        for order in orders:
            # Mark as received
            order.quantity_received = order.quantity_confirmed or order.quantity_submitted
            order.order_receive_date = current_date
            order.status = 'received'

            # Track delivery by role
            role = node_id_to_name.get(order.to_site_id)
            if role:
                if role not in deliveries:
                    deliveries[role] = 0
                deliveries[role] += order.quantity_received

                print(f"    ✓ {role}: received {order.quantity_received} "
                      f"(order {order.order_id})")

        await self.db.commit()
        print(f"  ✓ Processed {len(orders)} deliveries")

        return deliveries

    # ============================================================================
    # HELPER METHODS
    # ============================================================================

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
                ScenarioUser.role == role
            )
        )
        scenario_user = result.scalar_one_or_none()

        if not scenario_user:
            return 0.0

        inventory, _ = self._get_scenario_user_inventory_and_backlog(
            scenario_user, self.game.current_round
        )
        return inventory

    # ============================================================================
    # CAPACITY CONSTRAINTS (Phase 3 - Sprint 2)
    # ============================================================================

    async def create_work_orders_with_capacity(
        self,
        scenario_user_orders: Dict[str, float],
        round_number: int
    ) -> Dict[str, any]:
        """
        Create work orders with capacity constraints (Phase 3 - Sprint 2)

        Enforces capacity limits at upstream sites. If capacity is exceeded,
        orders are either queued for next period or rejected.

        Args:
            scenario_user_orders: Dict mapping role → order quantity
            round_number: Current game round

        Returns:
            {
                'created': List[InboundOrderLine],  # Orders that fit in capacity
                'queued': List[Dict],  # Orders waiting for capacity
                'rejected': List[Dict],  # Orders that can't be fulfilled
                'capacity_used': Dict[str, float]  # Capacity consumed per site
            }
        """
        print(f"  Creating work orders with CAPACITY constraints for round {round_number}...")

        # Ensure cache is loaded
        if self.cache and not self.cache.is_loaded():
            await self.cache.load()

        # Get item
        item = self.cache.get_first_item() if self.cache else None
        if not item:
            await self.db.refresh(self.config, ['items'])
            item = self.config.items[0] if self.config.items else None

        if not item:
            print(f"    ⚠️  No item found")
            return {'created': [], 'queued': [], 'rejected': [], 'capacity_used': {}}

        order_date = self.game.start_date + timedelta(days=round_number * 7)

        created = []
        queued = []
        rejected = []
        capacity_used = {}

        for role, order_qty in scenario_user_orders.items():
            if order_qty <= 0:
                continue

            # Get node
            node = self.cache.get_node_by_name(role) if self.cache else None
            if not node:
                print(f"    ⚠️  No node found for role {role}")
                continue

            # Get upstream node
            upstream_node = None
            lead_time_days = 14
            order_type = 'TO'

            if self.cache:
                upstream_node = self.cache.get_upstream_site(item.id, node.id)
                if upstream_node:
                    lead_time_days = self.cache.get_lead_time(item.id, upstream_node.id, node.id)
                    order_type = self._determine_order_type_from_master_type(upstream_node.master_type)

            # Fallback: Try to find upstream via lanes if sourcing rules don't exist
            if not upstream_node:
                for lane in self.config.lanes:
                    if lane.to_site_id == node.id:
                        upstream_node = self.cache.get_node(lane.from_site_id) if self.cache else None
                        if upstream_node:
                            # Determine lead time from lane (with robust type checking)
                            if hasattr(lane, 'lead_time_days') and lane.lead_time_days:
                                if isinstance(lane.lead_time_days, (int, float)):
                                    lead_time_days = int(lane.lead_time_days)
                            elif hasattr(lane, 'supply_lead_time') and lane.supply_lead_time:
                                if isinstance(lane.supply_lead_time, (int, float)):
                                    lead_time_days = int(lane.supply_lead_time)
                            order_type = self._determine_order_type_from_master_type(upstream_node.master_type)
                            break

            if not upstream_node:
                print(f"    ⚠️  No upstream node found for {role}")
                continue

            # Check capacity at upstream site
            capacity = self.cache.get_production_capacity(upstream_node.id, item.id) if self.cache else None

            if not capacity:
                # No capacity constraint - create order normally
                work_order = self._build_work_order(
                    role, order_qty, item, node, upstream_node,
                    order_type, lead_time_days, order_date, round_number
                )
                created.append(work_order)
                print(f"    ✓ {role}: {order_type} order {order_qty} (no capacity limit)")
                continue

            # Calculate available capacity
            available = capacity.max_capacity_per_period - capacity.current_capacity_used

            if order_qty <= available:
                # Fits within capacity
                work_order = self._build_work_order(
                    role, order_qty, item, node, upstream_node,
                    order_type, lead_time_days, order_date, round_number
                )
                capacity.current_capacity_used += order_qty
                capacity_used[upstream_node.name] = capacity.current_capacity_used
                created.append(work_order)
                print(f"    ✓ {role}: {order_type} order {order_qty} "
                      f"(capacity: {capacity.current_capacity_used}/{capacity.max_capacity_per_period})")

            elif capacity.allow_overflow:
                # Overflow allowed - create order with cost multiplier
                work_order = self._build_work_order(
                    role, order_qty, item, node, upstream_node,
                    order_type, lead_time_days, order_date, round_number
                )
                # Apply overflow cost
                work_order.cost = (work_order.cost or 0) * capacity.overflow_cost_multiplier
                capacity.current_capacity_used += order_qty
                capacity_used[upstream_node.name] = capacity.current_capacity_used
                created.append(work_order)
                print(f"    ⚠️  {role}: {order_type} order {order_qty} (OVERFLOW - "
                      f"capacity: {capacity.current_capacity_used}/{capacity.max_capacity_per_period})")

            else:
                # Capacity exceeded - partial fulfillment or queue
                if available > 0:
                    # Partial fulfillment
                    work_order = self._build_work_order(
                        role, available, item, node, upstream_node,
                        order_type, lead_time_days, order_date, round_number
                    )
                    capacity.current_capacity_used = capacity.max_capacity_per_period
                    capacity_used[upstream_node.name] = capacity.current_capacity_used
                    created.append(work_order)

                    # Queue remainder
                    remainder = order_qty - available
                    queued.append({
                        'role': role,
                        'quantity': remainder,
                        'round': round_number + 1,
                        'reason': 'capacity_exceeded'
                    })
                    print(f"    ⚠️  {role}: {order_type} order {available} (partial), "
                          f"{remainder} queued (capacity full)")
                else:
                    # No capacity available - queue entire order
                    queued.append({
                        'role': role,
                        'quantity': order_qty,
                        'round': round_number + 1,
                        'reason': 'no_capacity'
                    })
                    print(f"    ⚠️  {role}: {order_type} order {order_qty} QUEUED "
                          f"(no capacity available)")

        # Batch insert all created work orders
        if created:
            self.db.add_all(created)
            await self.db.commit()

        print(f"  ✓ Created {len(created)} work orders, "
              f"{len(queued)} queued, {len(rejected)} rejected")

        return {
            'created': created,
            'queued': queued,
            'rejected': rejected,
            'capacity_used': capacity_used
        }

    def _build_work_order(
        self,
        role: str,
        quantity: float,
        item,
        node,
        upstream_node,
        order_type: str,
        lead_time_days: int,
        order_date: date,
        round_number: int
    ) -> 'InboundOrderLine':
        """
        Build a single work order object (helper method)

        Args:
            role: ScenarioUser role
            quantity: Order quantity
            item: Item object
            node: Destination node
            upstream_node: Source node
            order_type: TO/MO/PO
            lead_time_days: Lead time in days
            order_date: Order date
            round_number: Game round

        Returns:
            InboundOrderLine object (not yet added to session)
        """
        expected_delivery = order_date + timedelta(days=lead_time_days)

        return InboundOrderLine(
            order_id=f"GAME_{self.game.id}_R{round_number}_{role}",
            line_number=1,
            product_id=item.id,
            to_site_id=node.id,
            from_site_id=upstream_node.id if order_type in ['TO', 'MO'] else None,
            tpartner_id=None,
            order_type=order_type,
            quantity_submitted=quantity,
            quantity_confirmed=quantity,
            quantity_received=None,
            quantity_uom='CASES',
            submitted_date=order_date,
            expected_delivery_date=expected_delivery,
            earliest_delivery_date=expected_delivery,
            latest_delivery_date=expected_delivery,
            confirmation_date=order_date,
            order_receive_date=None,
            status='open',
            vendor_status='confirmed',
            lead_time_days=lead_time_days,
            tenant_id=self.tenant_id,
            config_id=self.config_id,
            scenario_id=self.game.id,
            round_number=round_number
        )

    async def reset_period_capacity(self) -> int:
        """
        Reset capacity counters at start of new period (Phase 3 - Sprint 2)

        Called at the beginning of each round to reset current_capacity_used to 0.

        Returns:
            Number of capacity records reset
        """
        from sqlalchemy import update
        from app.models.sc_entities import ProductionCapacity

        result = await self.db.execute(
            update(ProductionCapacity)
            .filter(
                ProductionCapacity.tenant_id == self.tenant_id,
                ProductionCapacity.config_id == self.config_id
            )
            .values(current_capacity_used=0)
        )
        await self.db.commit()

        count = result.rowcount
        print(f"  ✓ Reset {count} capacity records for new period")

        return count

    async def create_work_orders_with_aggregation(
        self,
        scenario_user_orders: Dict[str, float],
        round_number: int,
        use_capacity: bool = False
    ) -> Dict[str, any]:
        """
        Create work orders with order aggregation and scheduling (Phase 3 - Sprint 3)

        Aggregates multiple orders to same upstream site, applies quantity constraints,
        and optionally enforces capacity limits.

        Args:
            scenario_user_orders: Dict mapping role → order quantity
            round_number: Current game round
            use_capacity: Enforce capacity constraints (default: False)

        Returns:
            {
                'created': List[InboundOrderLine],  # Orders that were created
                'aggregated': List[AggregatedOrder],  # Aggregation tracking records
                'queued': List[Dict],  # Orders waiting for next period
                'capacity_used': Dict[str, float],  # Capacity consumed per site
                'cost_savings': float  # Total fixed cost savings from aggregation
            }
        """
        print(f"  Creating work orders with AGGREGATION for round {round_number}...")

        # Ensure cache is loaded
        if self.cache and not self.cache.is_loaded():
            await self.cache.load()

        # Get item
        item = self.cache.get_first_item() if self.cache else None
        if not item:
            await self.db.refresh(self.config, ['items'])
            item = self.config.items[0] if self.config.items else None

        if not item:
            print(f"    ⚠️  No item found")
            return {
                'created': [], 'aggregated': [], 'queued': [],
                'capacity_used': {}, 'cost_savings': 0.0
            }

        order_date = self.game.start_date + timedelta(days=round_number * 7)

        # Step 1: Group orders by upstream site
        upstream_groups = {}  # {(upstream_site_id, product_id): [(role, qty, node, upstream, lead_time, order_type), ...]}

        for role, order_qty in scenario_user_orders.items():
            if order_qty <= 0:
                continue

            # Get node
            node = self.cache.get_node_by_name(role) if self.cache else None
            if not node:
                print(f"    ⚠️  No node found for role {role}")
                continue

            # Get upstream node
            upstream_node = None
            lead_time_days = 14
            order_type = 'TO'

            if self.cache:
                upstream_node = self.cache.get_upstream_site(item.id, node.id)
                if upstream_node:
                    lead_time_days = self.cache.get_lead_time(item.id, upstream_node.id, node.id)
                    order_type = self._determine_order_type_from_master_type(upstream_node.master_type)

            # Fallback: Try to find upstream via lanes if sourcing rules don't exist
            if not upstream_node:
                for lane in self.config.lanes:
                    if lane.to_site_id == node.id:
                        upstream_node = self.cache.get_node(lane.from_site_id) if self.cache else None
                        if upstream_node:
                            if hasattr(lane, 'lead_time_days') and lane.lead_time_days:
                                if isinstance(lane.lead_time_days, (int, float)):
                                    lead_time_days = int(lane.lead_time_days)
                            elif hasattr(lane, 'supply_lead_time') and lane.supply_lead_time:
                                if isinstance(lane.supply_lead_time, (int, float)):
                                    lead_time_days = int(lane.supply_lead_time)
                            order_type = self._determine_order_type_from_master_type(upstream_node.master_type)
                            break

            if not upstream_node:
                print(f"    ⚠️  No upstream node found for {role}")
                continue

            # Group by upstream site and product
            key = (upstream_node.id, item.id)
            if key not in upstream_groups:
                upstream_groups[key] = []
            upstream_groups[key].append((role, order_qty, node, upstream_node, lead_time_days, order_type))

        # Step 2: Process each upstream group
        created = []
        aggregated_records = []
        queued = []
        capacity_used = {}
        total_cost_savings = 0.0

        for (upstream_site_id, product_id), orders in upstream_groups.items():
            # Check if aggregation policy exists for any of these orders
            policy = None
            for (role, order_qty, node, upstream_node, lead_time_days, order_type) in orders:
                policy = self.cache.get_aggregation_policy(
                    from_site_id=node.id,
                    to_site_id=upstream_site_id,
                    product_id=product_id
                ) if self.cache else None
                if policy:
                    break

            if not policy:
                # No aggregation policy - create individual orders
                for (role, order_qty, node, upstream_node, lead_time_days, order_type) in orders:
                    if use_capacity:
                        # Check capacity
                        capacity = self.cache.get_production_capacity(upstream_node.id, item.id) if self.cache else None
                        if capacity:
                            available = capacity.max_capacity_per_period - capacity.current_capacity_used
                            if order_qty <= available:
                                work_order = self._build_work_order(
                                    role, order_qty, item, node, upstream_node,
                                    order_type, lead_time_days, order_date, round_number
                                )
                                capacity.current_capacity_used += order_qty
                                capacity_used[upstream_node.name] = capacity.current_capacity_used
                                created.append(work_order)
                                print(f"    ✓ {role}: {order_type} order {order_qty} "
                                      f"(no aggregation, capacity: {capacity.current_capacity_used}/{capacity.max_capacity_per_period})")
                            else:
                                # Queue entire order if capacity exceeded
                                queued.append({
                                    'role': role,
                                    'quantity': order_qty,
                                    'round': round_number + 1,
                                    'reason': 'capacity_exceeded'
                                })
                                print(f"    ⚠️  {role}: {order_type} order {order_qty} QUEUED (capacity full)")
                            continue

                    # No capacity constraint - create normally
                    work_order = self._build_work_order(
                        role, order_qty, item, node, upstream_node,
                        order_type, lead_time_days, order_date, round_number
                    )
                    created.append(work_order)
                    print(f"    ✓ {role}: {order_type} order {order_qty} (no aggregation)")
                continue

            # Step 3: Apply aggregation policy
            print(f"    🔀 Aggregating {len(orders)} orders to {upstream_node.name}")

            # Sum total quantity
            total_qty = sum(order_qty for (role, order_qty, _, _, _, _) in orders)
            print(f"      Total quantity before constraints: {total_qty}")

            # Step 4: Apply quantity constraints
            adjusted_qty = total_qty

            if policy.min_order_quantity and adjusted_qty < policy.min_order_quantity:
                adjusted_qty = policy.min_order_quantity
                print(f"      Adjusted to min quantity: {adjusted_qty}")

            if policy.max_order_quantity and adjusted_qty > policy.max_order_quantity:
                adjusted_qty = policy.max_order_quantity
                print(f"      Adjusted to max quantity: {adjusted_qty}")

            if policy.order_multiple and policy.order_multiple > 1.0:
                # Round to nearest multiple
                import math
                adjusted_qty = math.ceil(adjusted_qty / policy.order_multiple) * policy.order_multiple
                print(f"      Adjusted to multiple of {policy.order_multiple}: {adjusted_qty}")

            # Step 5: Check capacity if required
            if use_capacity:
                capacity = self.cache.get_production_capacity(upstream_node.id, item.id) if self.cache else None
                if capacity:
                    available = capacity.max_capacity_per_period - capacity.current_capacity_used
                    if adjusted_qty > available:
                        # Queue entire aggregated order if capacity exceeded
                        for (role, order_qty, node, _, _, _) in orders:
                            queued.append({
                                'role': role,
                                'quantity': order_qty,
                                'round': round_number + 1,
                                'reason': 'capacity_exceeded'
                            })
                        print(f"      ⚠️  Aggregated order {adjusted_qty} QUEUED (capacity: {available}/{capacity.max_capacity_per_period})")
                        continue

                    # Update capacity
                    capacity.current_capacity_used += adjusted_qty
                    capacity_used[upstream_node.name] = capacity.current_capacity_used

            # Step 6: Calculate cost savings
            num_orders = len(orders)
            fixed_cost_savings = 0.0
            if policy.fixed_order_cost and num_orders > 1:
                fixed_cost_savings = (num_orders - 1) * policy.fixed_order_cost
                total_cost_savings += fixed_cost_savings
                print(f"      💰 Fixed cost savings: ${fixed_cost_savings:.2f} ({num_orders - 1} orders saved)")

            # Step 7: Create single aggregated work order
            # Use first order's info for the aggregated order
            first_role, _, first_node, upstream_node, lead_time_days, order_type = orders[0]

            work_order = self._build_work_order(
                first_role, adjusted_qty, item, first_node, upstream_node,
                order_type, lead_time_days, order_date, round_number
            )
            work_order.order_id = f"GAME_{self.game.id}_R{round_number}_AGG_{upstream_node.name}"
            created.append(work_order)

            # Step 8: Create aggregation tracking record
            source_order_ids = ','.join([f"{role}" for (role, _, _, _, _, _) in orders])
            agg_record = AggregatedOrder(
                policy_id=policy.id,
                scenario_id=self.game.id,
                round_number=round_number,
                from_site_id=first_node.id,
                to_site_id=upstream_node.id,
                product_id=item.id,
                total_quantity=total_qty,
                adjusted_quantity=adjusted_qty,
                num_orders_aggregated=num_orders,
                source_order_ids=source_order_ids,
                aggregation_date=order_date,
                scheduled_order_date=order_date,
                fixed_cost_saved=fixed_cost_savings,
                total_order_cost=(adjusted_qty * (policy.variable_cost_per_unit or 0) + (policy.fixed_order_cost or 0)),
                status='placed',
                tenant_id=self.tenant_id,
                config_id=self.config_id
            )
            aggregated_records.append(agg_record)

            capacity_str = f" (capacity: {capacity_used.get(upstream_node.name, 0)})" if use_capacity else ""
            print(f"      ✓ Created aggregated {order_type} order: {adjusted_qty} units{capacity_str}")

        # Batch insert all created work orders and aggregation records
        if created:
            self.db.add_all(created)
        if aggregated_records:
            self.db.add_all(aggregated_records)
        if created or aggregated_records:
            await self.db.commit()

        print(f"  ✓ Created {len(created)} work orders ({len(aggregated_records)} aggregated), "
              f"{len(queued)} queued, ${total_cost_savings:.2f} saved")

        return {
            'created': created,
            'aggregated': aggregated_records,
            'queued': queued,
            'capacity_used': capacity_used,
            'cost_savings': total_cost_savings
        }
