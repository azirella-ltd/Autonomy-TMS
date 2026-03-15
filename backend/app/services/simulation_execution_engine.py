"""
simulation Execution Engine

Orchestrates simulation round execution using AWS SC execution capabilities:
- OrderManagementService for order CRUD
- FulfillmentService for FIFO fulfillment
- ATPCalculationService for order promising

Replaces simplified Node-based engine with full order lifecycle tracking,
backlog management, and ATP-based fulfillment.

Execution Flow per Round:
1. Receive shipments (TransferOrders arriving)
2. Generate customer orders (Market Demand sites)
3. Fulfill customer orders (Retailer → customers)
4. Evaluate replenishment needs
5. Issue POs to upstream sites
6. Fulfill POs as sales orders (upstream sites)
7. Calculate costs and metrics
8. Save RoundMetric records
"""

from typing import List, Optional, Dict, Any, Tuple
from datetime import date, datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload

from app.models.scenario import Scenario

# Aliases for backwards compatibility
Game = Scenario
from app.models.sc_entities import OutboundOrderLine, InvLevel, InvPolicy, Product
from app.models.purchase_order import PurchaseOrder
from app.models.transfer_order import TransferOrder
from app.models.supply_chain_config import Site, SupplyChainConfig, TransportationLane
from app.models.compatibility import Item
from app.models.round_metric import RoundMetric
from app.services.order_management_service import OrderManagementService
from app.services.fulfillment_service import FulfillmentService
from app.services.atp_calculation_service import ATPCalculationService


class SimulationExecutionEngine:
    """
    simulation execution engine using AWS SC order management.

    Orchestrates complete order lifecycle for multi-echelon simulation:
    - Market Demand → Retailer → Wholesaler → Distributor → Manufacturer → Market Supply
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.order_mgmt = OrderManagementService(db_session)
        self.fulfillment = FulfillmentService(db_session)
        self.atp_service = ATPCalculationService(db_session)

    # ========================================================================
    # Main Execution Method
    # ========================================================================

    async def execute_round(
        self,
        scenario_id: int,
        current_round: int,
        agent_decisions: Optional[Dict[int, float]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a complete simulation round.

        Args:
            scenario_id: simulation ID
            current_round: Current round number
            agent_decisions: Optional dict of {site_id: order_quantity} for agent decisions

        Returns:
            Round execution summary with metrics
        """
        # Get game and config
        game = await self.db.get(Game, scenario_id)
        if not game:
            raise ValueError(f"Game {scenario_id} not found")

        config = await self.db.get(SupplyChainConfig, game.config_id)
        if not config:
            raise ValueError(f"Config {game.config_id} not found")

        # Get all sites in topology order (downstream to upstream)
        sites = await self._get_sites_in_topology_order(config.id)

        product_id = await self._get_primary_product(config.id)

        # Step 1: Receive shipments (TransferOrders arriving this round)
        receipt_summary = await self._receive_shipments(
            scenario_id=scenario_id,
            current_round=current_round,
            config_id=config.id,
        )

        # Step 2: Generate customer orders (Market Demand → Retailer)
        customer_order_summary = await self._generate_customer_orders(
            scenario_id=scenario_id,
            config_id=config.id,
            current_round=current_round,
            product_id=product_id,
        )

        # Step 3: Fulfill customer orders and POs at all sites (downstream to upstream)
        fulfillment_summary = await self._fulfill_orders_all_sites(
            sites=sites,
            scenario_id=scenario_id,
            config_id=config.id,
            current_round=current_round,
            product_id=product_id,
        )

        # Step 4: Evaluate replenishment needs and issue POs
        replenishment_summary = await self._evaluate_replenishment(
            sites=sites,
            scenario_id=scenario_id,
            config_id=config.id,
            current_round=current_round,
            product_id=product_id,
            agent_decisions=agent_decisions,
        )

        # Step 5: Calculate costs and save metrics
        metrics_summary = await self._calculate_and_save_metrics(
            sites=sites,
            scenario_id=scenario_id,
            config_id=config.id,
            current_round=current_round,
            product_id=product_id,
        )

        # Commit all changes
        await self.db.commit()

        return {
            'scenario_id': scenario_id,
            'round': current_round,
            'receipts': receipt_summary,
            'customer_orders': customer_order_summary,
            'fulfillment': fulfillment_summary,
            'replenishment': replenishment_summary,
            'metrics': metrics_summary,
        }

    # ========================================================================
    # Step 1: Receive Shipments
    # ========================================================================

    async def _receive_shipments(
        self,
        scenario_id: int,
        current_round: int,
        config_id: int,
    ) -> Dict[str, Any]:
        """Process all arriving TransferOrders for current round."""
        return await self.fulfillment.receive_shipments(
            scenario_id=scenario_id,
            arrival_round=current_round,
            config_id=config_id,
        )

    # ========================================================================
    # Step 2: Generate Customer Orders
    # ========================================================================

    async def _generate_customer_orders(
        self,
        scenario_id: int,
        config_id: int,
        current_round: int,
        product_id: str,
    ) -> Dict[str, Any]:
        """
        Generate customer orders from Market Demand sites.

        Each Market Demand site places 1 order with 1 line per round.
        """
        # Get Market Demand sites
        market_demand_sites = await self._get_sites_by_master_type(
            config_id=config_id,
            master_type="MARKET_DEMAND",
        )

        # Get downstream sites (Retailers) connected to Market Demand
        retailer_sites = await self._get_downstream_sites(
            config_id=config_id,
            upstream_master_type="INVENTORY",
            sc_node_type="Retailer",
        )

        orders_created = []

        for market_site in market_demand_sites:
            # Get demand quantity for this round (from game settings or default)
            demand_qty = await self._get_market_demand(
                scenario_id=scenario_id,
                market_site_id=market_site.id,
                round_number=current_round,
            )

            if demand_qty <= 0:
                continue

            # Find Retailer to fulfill this demand
            # In simulation, typically 1:1 mapping
            retailer = retailer_sites[0] if retailer_sites else None
            if not retailer:
                continue

            # Create customer order
            order = await self.order_mgmt.create_customer_order(
                order_id=f"ORD-{scenario_id}-{current_round}-{market_site.id}",
                line_number=1,
                product_id=product_id,
                site_id=retailer.id,
                ordered_quantity=demand_qty,
                requested_delivery_date=date.today() + timedelta(weeks=1),
                market_demand_site_id=market_site.id,
                priority_code="STANDARD",
                config_id=config_id,
                scenario_id=scenario_id,
            )

            # Mark as CONFIRMED with backlog
            order.status = "CONFIRMED"
            order.backlog_quantity = demand_qty

            orders_created.append(order)

        await self.db.flush()

        return {
            'orders_created': len(orders_created),
            'total_demand': sum(o.ordered_quantity for o in orders_created),
        }

    # ========================================================================
    # Step 3: Fulfill Orders at All Sites
    # ========================================================================

    async def _fulfill_orders_all_sites(
        self,
        sites: List[Site],
        scenario_id: int,
        config_id: int,
        current_round: int,
        product_id: str,
    ) -> Dict[str, Any]:
        """
        Fulfill customer orders and POs at all sites (downstream to upstream).

        Processing order:
        1. Retailer: Fulfill customer orders
        2. Wholesaler: Fulfill POs from Retailer (as sales orders)
        3. Distributor: Fulfill POs from Wholesaler
        4. Manufacturer: Fulfill POs from Distributor
        """
        fulfillment_by_site = {}

        for site in sites:
            if site.master_type == "MARKET_DEMAND" or site.master_type == "MARKET_SUPPLY":
                continue

            # Fulfill customer orders (for Retailer)
            customer_fulfillment = await self.fulfillment.fulfill_customer_orders_fifo(
                site_id=site.id,
                product_id=product_id,
                scenario_id=scenario_id,
                config_id=config_id,
                current_round=current_round,
            )

            # Fulfill POs (for Wholesaler, Distributor, Manufacturer)
            po_fulfillment = await self.fulfillment.fulfill_purchase_orders(
                supplier_site_id=site.id,
                product_id=product_id,
                scenario_id=scenario_id,
                config_id=config_id,
                current_round=current_round,
            )

            fulfillment_by_site[site.id] = {
                'site_name': site.name,
                'customer_orders': customer_fulfillment,
                'purchase_orders': po_fulfillment,
            }

        return fulfillment_by_site

    # ========================================================================
    # Step 4: Evaluate Replenishment
    # ========================================================================

    async def _evaluate_replenishment(
        self,
        sites: List[Site],
        scenario_id: int,
        config_id: int,
        current_round: int,
        product_id: str,
        agent_decisions: Optional[Dict[int, float]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate replenishment needs and issue POs to upstream sites.

        Agent decisions override default replenishment logic.
        """
        replenishment_by_site = {}
        agent_decisions = agent_decisions or {}

        for site in sites:
            if site.master_type == "MARKET_DEMAND" or site.master_type == "MARKET_SUPPLY":
                continue

            # Get upstream supplier
            upstream_site = await self._get_upstream_supplier(
                site_id=site.id,
                config_id=config_id,
            )

            if not upstream_site:
                continue

            # Determine order quantity
            if site.id in agent_decisions:
                # Agent decision provided
                order_qty = agent_decisions[site.id]
            else:
                # Default replenishment logic
                order_qty = await self._calculate_default_replenishment(
                    site_id=site.id,
                    product_id=product_id,
                    scenario_id=scenario_id,
                    config_id=config_id,
                )

            if order_qty <= 0:
                replenishment_by_site[site.id] = {
                    'site_name': site.name,
                    'order_quantity': 0.0,
                    'po_created': False,
                }
                continue

            # Create PO to upstream site
            po = await self.order_mgmt.create_purchase_order(
                po_number=f"PO-{scenario_id}-{current_round}-{site.id}-{upstream_site.id}",
                supplier_site_id=upstream_site.id,
                destination_site_id=site.id,
                product_id=product_id,
                quantity=order_qty,
                requested_delivery_date=date.today() + timedelta(weeks=2),
                config_id=config_id,
                customer_id=None,
                scenario_id=scenario_id,
                order_round=current_round,
            )

            replenishment_by_site[site.id] = {
                'site_name': site.name,
                'upstream_site': upstream_site.name,
                'order_quantity': order_qty,
                'po_created': True,
                'po_id': po.id,
            }

        return replenishment_by_site

    async def _calculate_default_replenishment(
        self,
        site_id: int,
        product_id: str,
        scenario_id: int,
        config_id: int,
    ) -> float:
        """
        Calculate default replenishment quantity.

        Simple simulation logic:
        - Order quantity = Backlog + (Target inventory - Current inventory)
        - Target inventory = 2 weeks of average demand
        """
        # Get current inventory
        inv = await self.fulfillment.get_inventory_level(
            site_id=site_id,
            product_id=product_id,
            config_id=config_id,
            scenario_id=scenario_id,
        )

        # Get backlog
        backlog = await self.order_mgmt.get_backlog_for_site(
            site_id=site_id,
            product_id=product_id,
            scenario_id=scenario_id,
        )

        # Simple heuristic: target inventory = 12 units (classic simulation)
        target_inventory = 12.0

        # Order quantity = backlog + (target - current)
        order_qty = backlog + max(0, target_inventory - inv)

        return max(0.0, order_qty)

    # ========================================================================
    # Step 5: Calculate Costs and Save Metrics
    # ========================================================================

    async def _calculate_and_save_metrics(
        self,
        sites: List[Site],
        scenario_id: int,
        config_id: int,
        current_round: int,
        product_id: str,
    ) -> Dict[str, Any]:
        """
        Calculate per-site costs and KPIs, save to RoundMetric table.

        Cost rates are loaded from InvPolicy for the config's product.
        Fallback: unit_cost * 0.25 / 52 (holding), * 4 (backlog) from Product.unit_cost.
        """
        holding_cost_rate, backlog_cost_rate = await self._get_cost_rates(config_id, product_id)

        metrics_by_site = {}

        for site in sites:
            if site.master_type == "MARKET_DEMAND" or site.master_type == "MARKET_SUPPLY":
                continue

            # Get current state
            inventory = await self.fulfillment.get_inventory_level(
                site_id=site.id,
                product_id=product_id,
                config_id=config_id,
                scenario_id=scenario_id,
            )

            backlog = await self.order_mgmt.get_backlog_for_site(
                site_id=site.id,
                product_id=product_id,
                scenario_id=scenario_id,
            )

            pipeline_qty = await self._get_pipeline_quantity(
                site_id=site.id,
                product_id=product_id,
                scenario_id=scenario_id,
            )

            in_transit_qty = await self.atp_service._get_in_transit_quantity(
                site_id=site.id,
                product_id=product_id,
                scenario_id=scenario_id,
            )

            # Calculate costs
            holding_cost = inventory * holding_cost_rate
            backlog_cost = backlog * backlog_cost_rate
            total_cost = holding_cost + backlog_cost

            # Get cumulative cost from previous round
            prev_cumulative = await self._get_previous_cumulative_cost(
                scenario_id=scenario_id,
                site_id=site.id,
                round_number=current_round - 1,
            )
            cumulative_cost = prev_cumulative + total_cost

            # Get order flow metrics
            incoming_order_qty = await self._get_incoming_order_quantity(
                site_id=site.id,
                product_id=product_id,
                scenario_id=scenario_id,
                current_round=current_round,
            )

            outgoing_order_qty = await self._get_outgoing_order_quantity(
                site_id=site.id,
                product_id=product_id,
                scenario_id=scenario_id,
                current_round=current_round,
            )

            shipment_qty = await self._get_shipment_quantity(
                site_id=site.id,
                product_id=product_id,
                scenario_id=scenario_id,
                current_round=current_round,
            )

            # Calculate KPIs
            orders_received, orders_fulfilled = await self._get_order_counts(
                site_id=site.id,
                product_id=product_id,
                scenario_id=scenario_id,
                current_round=current_round,
            )

            fill_rate = (orders_fulfilled / orders_received) if orders_received > 0 else 1.0
            service_level = fill_rate  # Simplified for simulation

            # Look up scenario_user assigned to this site
            scenario_user_id = await self._get_participant_for_site(scenario_id, site.id)

            # Create RoundMetric
            metric = RoundMetric(
                scenario_id=scenario_id,
                round_number=current_round,
                site_id=site.id,
                scenario_user_id=scenario_user_id,
                inventory=inventory,
                backlog=backlog,
                pipeline_qty=pipeline_qty,
                in_transit_qty=in_transit_qty,
                holding_cost=holding_cost,
                backlog_cost=backlog_cost,
                total_cost=total_cost,
                cumulative_cost=cumulative_cost,
                fill_rate=fill_rate,
                service_level=service_level,
                orders_received=orders_received,
                orders_fulfilled=orders_fulfilled,
                incoming_order_qty=incoming_order_qty,
                outgoing_order_qty=outgoing_order_qty,
                shipment_qty=shipment_qty,
            )

            self.db.add(metric)

            metrics_by_site[site.id] = {
                'site_name': site.name,
                'inventory': inventory,
                'backlog': backlog,
                'holding_cost': holding_cost,
                'backlog_cost': backlog_cost,
                'total_cost': total_cost,
                'cumulative_cost': cumulative_cost,
                'fill_rate': fill_rate,
            }

        await self.db.flush()

        return metrics_by_site

    # ========================================================================
    # Helper Methods
    # ========================================================================

    async def _get_sites_in_topology_order(self, config_id: int) -> List[Site]:
        """
        Get sites in topology order (downstream to upstream).

        Order: Retailer → Wholesaler → Distributor → Manufacturer
        """
        result = await self.db.execute(
            select(Site)
            .where(Site.config_id == config_id)
            .order_by(Site.id)  # Simplified: assume ID order matches topology
        )
        return list(result.scalars().all())

    async def _get_primary_product(self, config_id: int) -> str:
        """Get primary product for scenario (typically 'CASES')."""
        result = await self.db.execute(
            select(Item)
            .where(Item.config_id == config_id)
            .limit(1)
        )
        product = result.scalar_one_or_none()
        return product.product_id if product else "CASES"

    async def _get_sites_by_master_type(self, config_id: int, master_type: str) -> List[Site]:
        """Get sites by master type."""
        result = await self.db.execute(
            select(Site)
            .where(and_(
                Site.config_id == config_id,
                Site.master_type == master_type
            ))
        )
        return list(result.scalars().all())

    async def _get_downstream_sites(
        self,
        config_id: int,
        upstream_master_type: str,
        sc_node_type: Optional[str] = None
    ) -> List[Site]:
        """Get downstream sites of a specific type."""
        query = select(Site).where(and_(
            Site.config_id == config_id,
            Site.master_type == upstream_master_type
        ))

        if sc_node_type:
            query = query.where(Site.sc_node_type == sc_node_type)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _get_market_demand(
        self,
        scenario_id: int,
        market_site_id: int,
        round_number: int,
    ) -> float:
        """
        Get market demand quantity for a round from config demand patterns.

        Queries MarketDemand for the scenario's config. Falls back to classic
        classic pattern (4 units for rounds 1-4, then 8) if no config exists.
        """
        try:
            from app.models.supply_chain_config import MarketDemand

            # Get scenario to find config_id
            scenario = await self.db.get(Scenario, scenario_id)
            if scenario and scenario.config_id:
                result = await self.db.execute(
                    select(MarketDemand).where(
                        MarketDemand.config_id == scenario.config_id
                    ).limit(1)
                )
                md = result.scalar_one_or_none()
                if md and md.demand_pattern:
                    params = md.demand_pattern.get("parameters") or md.demand_pattern.get("params", {})
                    initial = params.get("initial_demand", 4)
                    change_week = params.get("change_week", 15)
                    final = params.get("final_demand", 8)
                    return float(initial) if round_number <= change_week else float(final)
        except Exception:
            pass  # Fall back to classic pattern

        return 4.0 if round_number <= 4 else 8.0

    async def _get_participant_for_site(self, scenario_id: int, site_id: int) -> Optional[int]:
        """Look up the scenario_user assigned to a site in this scenario."""
        try:
            from app.models.scenario_user import ScenarioUser
            result = await self.db.execute(
                select(ScenarioUser.id).where(and_(
                    ScenarioUser.scenario_id == scenario_id,
                    ScenarioUser.node_id == site_id,
                )).limit(1)
            )
            row = result.scalar_one_or_none()
            return row
        except Exception:
            return None

    async def _get_upstream_supplier(self, site_id: int, config_id: int) -> Optional[Site]:
        """Get upstream supplier site via TransportationLane."""
        result = await self.db.execute(
            select(TransportationLane)
            .where(and_(
                TransportationLane.destination_node_id == site_id,
                TransportationLane.config_id == config_id
            ))
            .limit(1)
        )
        lane = result.scalar_one_or_none()

        if not lane:
            return None

        return await self.db.get(Site, lane.source_node_id)

    async def _get_pipeline_quantity(
        self,
        site_id: int,
        product_id: str,
        scenario_id: int,
    ) -> float:
        """Get pipeline quantity (POs issued but not yet shipped)."""
        result = await self.db.execute(
            select(func.sum(PurchaseOrderLineItem.quantity))
            .select_from(PurchaseOrder)
            .join(PurchaseOrderLineItem, PurchaseOrderLineItem.po_id == PurchaseOrder.id)
            .where(and_(
                PurchaseOrder.destination_site_id == site_id,
                PurchaseOrder.scenario_id == scenario_id,
                PurchaseOrder.status.in_(['APPROVED', 'ACKNOWLEDGED']),
                PurchaseOrderLineItem.product_id == product_id
            ))
        )
        pipeline = result.scalar()
        return float(pipeline) if pipeline else 0.0

    async def _get_previous_cumulative_cost(
        self,
        scenario_id: int,
        site_id: int,
        round_number: int,
    ) -> float:
        """Get cumulative cost from previous round."""
        if round_number < 1:
            return 0.0

        result = await self.db.execute(
            select(RoundMetric.cumulative_cost)
            .where(and_(
                RoundMetric.scenario_id == scenario_id,
                RoundMetric.site_id == site_id,
                RoundMetric.round_number == round_number
            ))
        )
        prev_cost = result.scalar_one_or_none()
        return float(prev_cost) if prev_cost else 0.0

    async def _get_incoming_order_quantity(
        self,
        site_id: int,
        product_id: str,
        scenario_id: int,
        current_round: int,
    ) -> float:
        """Get incoming order quantity (customer orders + POs received this round)."""
        # Customer orders
        customer_result = await self.db.execute(
            select(func.sum(OutboundOrderLine.ordered_quantity))
            .where(and_(
                OutboundOrderLine.site_id == site_id,
                OutboundOrderLine.product_id == product_id,
                OutboundOrderLine.scenario_id == scenario_id,
                func.extract('week', OutboundOrderLine.order_date) == current_round
            ))
        )
        customer_qty = customer_result.scalar() or 0.0

        # POs received (as supplier)
        po_result = await self.db.execute(
            select(func.sum(PurchaseOrderLineItem.quantity))
            .select_from(PurchaseOrder)
            .join(PurchaseOrderLineItem)
            .where(and_(
                PurchaseOrder.supplier_site_id == site_id,
                PurchaseOrder.scenario_id == scenario_id,
                PurchaseOrder.order_round == current_round,
                PurchaseOrderLineItem.product_id == product_id
            ))
        )
        po_qty = po_result.scalar() or 0.0

        return float(customer_qty + po_qty)

    async def _get_outgoing_order_quantity(
        self,
        site_id: int,
        product_id: str,
        scenario_id: int,
        current_round: int,
    ) -> float:
        """Get outgoing order quantity (POs issued this round)."""
        result = await self.db.execute(
            select(func.sum(PurchaseOrderLineItem.quantity))
            .select_from(PurchaseOrder)
            .join(PurchaseOrderLineItem)
            .where(and_(
                PurchaseOrder.destination_site_id == site_id,
                PurchaseOrder.scenario_id == scenario_id,
                PurchaseOrder.order_round == current_round,
                PurchaseOrderLineItem.product_id == product_id
            ))
        )
        qty = result.scalar()
        return float(qty) if qty else 0.0

    async def _get_shipment_quantity(
        self,
        site_id: int,
        product_id: str,
        scenario_id: int,
        current_round: int,
    ) -> float:
        """Get shipment quantity (TOs created this round)."""
        result = await self.db.execute(
            select(func.sum(TransferOrderLineItem.quantity))
            .select_from(TransferOrder)
            .join(TransferOrderLineItem)
            .where(and_(
                TransferOrder.source_site_id == site_id,
                TransferOrder.scenario_id == scenario_id,
                TransferOrder.order_round == current_round,
                TransferOrderLineItem.product_id == product_id
            ))
        )
        qty = result.scalar()
        return float(qty) if qty else 0.0

    async def _get_order_counts(
        self,
        site_id: int,
        product_id: str,
        scenario_id: int,
        current_round: int,
    ) -> Tuple[int, int]:
        """Get orders received and fulfilled counts."""
        # Orders received (customer orders this round)
        received_result = await self.db.execute(
            select(func.count(OutboundOrderLine.id))
            .where(and_(
                OutboundOrderLine.site_id == site_id,
                OutboundOrderLine.product_id == product_id,
                OutboundOrderLine.scenario_id == scenario_id,
                func.extract('week', OutboundOrderLine.order_date) == current_round
            ))
        )
        orders_received = received_result.scalar() or 0

        # Orders fulfilled (status = FULFILLED this round)
        fulfilled_result = await self.db.execute(
            select(func.count(OutboundOrderLine.id))
            .where(and_(
                OutboundOrderLine.site_id == site_id,
                OutboundOrderLine.product_id == product_id,
                OutboundOrderLine.scenario_id == scenario_id,
                OutboundOrderLine.status == "FULFILLED",
                func.extract('week', OutboundOrderLine.last_ship_date) == current_round
            ))
        )
        orders_fulfilled = fulfilled_result.scalar() or 0

        return int(orders_received), int(orders_fulfilled)

    async def _get_cost_rates(self, config_id: int, product_id: str) -> tuple:
        """Load holding and backlog cost rates from InvPolicy for the given config/product.

        Uses InvPolicy.holding_cost_range['min'] and backlog_cost_range['min'].
        Falls back to Product.unit_cost * 0.25/52 (holding) and * 4 (backlog).

        Raises:
            ValueError: If product_id is not found in the database for this config.
        """
        product_result = await self.db.execute(
            select(Product).where(Product.id == product_id)
        )
        product = product_result.scalars().first()
        if not product:
            raise ValueError(
                f"Product '{product_id}' not found in database for config {config_id}. "
                f"Cannot compute cost rates. Ensure the Product table is seeded for this config."
            )

        unit_cost = float(product.unit_cost or 0.0)
        default_holding = unit_cost * 0.25 / 52
        default_backlog = default_holding * 4.0

        inv_policy_result = await self.db.execute(
            select(InvPolicy).where(InvPolicy.product_id == product_id).limit(1)
        )
        inv_policy = inv_policy_result.scalars().first()

        if inv_policy:
            hcr = inv_policy.holding_cost_range or {}
            bcr = inv_policy.backlog_cost_range or {}
            holding_cost_rate = hcr.get("min", default_holding)
            backlog_cost_rate = bcr.get("min", default_backlog)
        else:
            holding_cost_rate = default_holding
            backlog_cost_rate = default_backlog

        return holding_cost_rate, backlog_cost_rate
