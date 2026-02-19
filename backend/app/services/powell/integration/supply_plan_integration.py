"""
Supply Plan Integration

Connects SiteAgent's MRP engine to the supply plan generation service.
Provides deterministic net requirements calculation with optional TRM adjustments.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import date, timedelta
from dataclasses import dataclass, asdict

from sqlalchemy.orm import Session

from app.models.supply_chain_config import SupplyChainConfig, Node, TransportationLane
from app.models.sc_entities import Product
from app.services.powell.site_agent import SiteAgent, SiteAgentConfig
from app.services.powell.engines import (
    MRPEngine,
    MRPConfig,
    GrossRequirement,
    PlannedOrder,
    SafetyStockCalculator,
    SSPolicy,
    PolicyType,
    DemandStats,
)

logger = logging.getLogger(__name__)


@dataclass
class PlanningContext:
    """Context for supply planning request"""
    config_id: int
    planning_horizon_days: int
    service_level: float
    use_trm_adjustments: bool
    safety_stock_policy: str  # abs_level, doc_dem, doc_fcst, sl


@dataclass
class PlannedOrderResult:
    """Planned order with optional TRM adjustment"""
    item_id: str
    quantity: int
    order_date: date
    receipt_date: date
    order_type: str  # purchase, manufacture, transfer
    source_node: Optional[str]
    destination_node: str
    trm_adjusted: bool
    adjustment_reason: Optional[str]
    confidence: float


class SiteAgentSupplyPlanAdapter:
    """
    Adapter that connects SiteAgent's MRP engine to supply plan generation.

    Provides:
    - Deterministic net requirements calculation via MRPEngine
    - Optional TRM adjustments for PO timing/quantity
    - Integration with existing supply plan service
    """

    def __init__(
        self,
        db: Session,
        config: SupplyChainConfig,
        use_trm: bool = True
    ):
        """
        Initialize supply plan adapter.

        Args:
            db: Database session
            config: Supply chain configuration
            use_trm: Enable TRM adjustments
        """
        self.db = db
        self.config = config
        self._site_agents: Dict[str, SiteAgent] = {}
        self.use_trm = use_trm

    def get_site_agent(self, site_key: str) -> SiteAgent:
        """Get or create SiteAgent for a site."""
        if site_key not in self._site_agents:
            agent_config = SiteAgentConfig(
                site_key=site_key,
                use_trm_adjustments=self.use_trm,
                agent_mode="copilot",
            )
            self._site_agents[site_key] = SiteAgent(agent_config)
        return self._site_agents[site_key]

    def generate_supply_plan(
        self,
        context: PlanningContext,
        demand_forecasts: Dict[Tuple[str, str], float],
        on_hand_inventory: Dict[Tuple[str, str], int],
        scheduled_receipts: Dict[str, List[Tuple[date, int]]],
    ) -> List[PlannedOrderResult]:
        """
        Generate supply plan using SiteAgent's MRP engine.

        This is the main integration point that connects SiteAgent deterministic
        engines with the broader supply planning workflow.

        Args:
            context: Planning context
            demand_forecasts: {(item_id, node_id): daily_demand}
            on_hand_inventory: {(item_id, node_id): quantity}
            scheduled_receipts: {item_id: [(arrival_date, quantity)]}

        Returns:
            List of planned orders with optional TRM adjustments
        """
        all_orders: List[PlannedOrderResult] = []

        # Get all inventory nodes
        nodes = self.db.query(Node).filter(
            Node.config_id == context.config_id,
            Node.master_type == "INVENTORY"
        ).all()

        for node in nodes:
            site_key = node.node_key
            site_agent = self.get_site_agent(site_key)

            # Build gross requirements for this node
            gross_reqs = self._build_gross_requirements(
                node,
                demand_forecasts,
                context.planning_horizon_days
            )

            # Build on-hand and scheduled receipts
            node_on_hand = self._extract_node_inventory(node, on_hand_inventory)
            node_receipts = self._extract_node_receipts(node, scheduled_receipts)

            # Get BOM structure
            bom = self._extract_bom(node)

            # Get lead times
            lead_times = self._extract_lead_times(node)

            # Calculate safety stock
            safety_stocks = self._calculate_safety_stocks(
                node,
                demand_forecasts,
                context.service_level,
                context.safety_stock_policy,
                site_agent
            )

            # Run MRP explosion
            net_reqs, planned_orders = site_agent.mrp_engine.compute_net_requirements(
                gross_requirements=gross_reqs,
                on_hand_inventory=node_on_hand,
                scheduled_receipts=node_receipts,
                bom=bom,
                lead_times=lead_times,
                safety_stocks=safety_stocks,
            )

            # Apply TRM adjustments if enabled
            for po in planned_orders:
                order_result = self._apply_trm_adjustments(
                    site_agent,
                    po,
                    node,
                    context.use_trm_adjustments
                )
                all_orders.append(order_result)

        logger.info(f"Generated {len(all_orders)} planned orders for config {context.config_id}")
        return all_orders

    def _build_gross_requirements(
        self,
        node: Node,
        demand_forecasts: Dict[Tuple[str, str], float],
        horizon_days: int
    ) -> List[GrossRequirement]:
        """Build gross requirements from demand forecasts."""
        requirements = []
        today = date.today()

        # Get products associated with this node
        products = self.db.query(Product).filter(
            Product.config_id == node.config_id
        ).all()

        for product in products:
            key = (product.id, node.node_key)
            daily_demand = demand_forecasts.get(key, 0)

            if daily_demand > 0:
                # Aggregate daily demand into weekly buckets
                for week in range(horizon_days // 7):
                    required_date = today + timedelta(days=(week + 1) * 7)
                    weekly_qty = int(daily_demand * 7)

                    requirements.append(GrossRequirement(
                        item_id=product.id,
                        required_date=required_date,
                        quantity=weekly_qty,
                        source="forecast"
                    ))

        return requirements

    def _extract_node_inventory(
        self,
        node: Node,
        on_hand_inventory: Dict[Tuple[str, str], int]
    ) -> Dict[str, int]:
        """Extract on-hand inventory for a node."""
        result = {}
        for (item_id, node_key), qty in on_hand_inventory.items():
            if node_key == node.node_key:
                result[item_id] = qty
        return result

    def _extract_node_receipts(
        self,
        node: Node,
        scheduled_receipts: Dict[str, List[Tuple[date, int]]]
    ) -> Dict[str, List[Tuple[date, int]]]:
        """Extract scheduled receipts for a node."""
        # In full implementation, filter by destination node
        # For now, return all receipts
        return scheduled_receipts

    def _extract_bom(self, node: Node) -> Dict[str, List[Tuple[str, float]]]:
        """Extract BOM structure for manufacturer nodes."""
        # Only manufacturers have BOMs
        if node.master_type != "MANUFACTURER":
            return {}

        # Query BOM from database
        # This is a simplified implementation - extend for multi-level BOM
        bom = {}
        # TODO: Load from product_bom table
        return bom

    def _extract_lead_times(self, node: Node) -> Dict[str, int]:
        """Extract lead times for items at this node."""
        lead_times = {}

        # Get transportation lanes feeding into this site
        lanes = self.db.query(TransportationLane).filter(
            TransportationLane.to_site_id == node.id
        ).all()

        # Default lead time if no lane found
        products = self.db.query(Product).filter(
            Product.config_id == node.config_id
        ).all()

        for product in products:
            # Find lane-specific lead time or use default
            default_lt = 7  # 1 week default
            for lane in lanes:
                if hasattr(lane, 'supply_lead_time') and lane.supply_lead_time:
                    if isinstance(lane.supply_lead_time, dict):
                        default_lt = lane.supply_lead_time.get('min', 7)
                    break
            lead_times[product.id] = default_lt

        return lead_times

    def _calculate_safety_stocks(
        self,
        node: Node,
        demand_forecasts: Dict[Tuple[str, str], float],
        service_level: float,
        policy_type_str: str,
        site_agent: SiteAgent
    ) -> Dict[str, int]:
        """Calculate safety stocks for all items at this node."""
        safety_stocks = {}

        # Map string to PolicyType
        policy_map = {
            "abs_level": PolicyType.ABS_LEVEL,
            "doc_dem": PolicyType.DOC_DEM,
            "doc_fcst": PolicyType.DOC_FCST,
            "sl": PolicyType.SL,
        }
        policy_type = policy_map.get(policy_type_str, PolicyType.SL)

        products = self.db.query(Product).filter(
            Product.config_id == node.config_id
        ).all()

        for product in products:
            key = (product.id, node.node_key)
            daily_demand = demand_forecasts.get(key, 0)

            if daily_demand <= 0:
                safety_stocks[product.id] = 0
                continue

            # Build demand stats
            demand_stats = DemandStats(
                avg_daily_demand=daily_demand,
                std_daily_demand=daily_demand * 0.2,  # Assume 20% CV
                avg_daily_forecast=daily_demand,
                lead_time_days=7,  # Default
            )

            # Build policy based on type
            if policy_type == PolicyType.ABS_LEVEL:
                policy = SSPolicy(
                    policy_type=PolicyType.ABS_LEVEL,
                    fixed_quantity=int(daily_demand * 7),  # 1 week
                )
            elif policy_type == PolicyType.DOC_DEM:
                policy = SSPolicy(
                    policy_type=PolicyType.DOC_DEM,
                    days_of_coverage=14,  # 2 weeks
                )
            elif policy_type == PolicyType.DOC_FCST:
                policy = SSPolicy(
                    policy_type=PolicyType.DOC_FCST,
                    days_of_coverage=14,
                )
            else:  # SL
                policy = SSPolicy(
                    policy_type=PolicyType.SL,
                    target_service_level=service_level,
                )

            # Calculate using engine
            result = site_agent.ss_calculator.compute_safety_stock(
                product_id=product.id,
                location_id=node.node_key,
                policy=policy,
                demand_stats=demand_stats
            )

            # Apply TRM adjustment if available
            if self.use_trm and site_agent.model:
                try:
                    import asyncio
                    loop = asyncio.get_event_loop()
                    adjustments = loop.run_until_complete(
                        site_agent.get_inventory_adjustments()
                    )
                    ss_multiplier = adjustments.get('ss_multiplier', 1.0)
                    adjusted_ss = int(result.safety_stock * ss_multiplier)
                    safety_stocks[product.id] = adjusted_ss
                except Exception as e:
                    logger.warning(f"TRM adjustment failed: {e}")
                    safety_stocks[product.id] = result.safety_stock
            else:
                safety_stocks[product.id] = result.safety_stock

        return safety_stocks

    async def _apply_trm_adjustments(
        self,
        site_agent: SiteAgent,
        planned_order: PlannedOrder,
        node: Node,
        use_trm: bool
    ) -> PlannedOrderResult:
        """Apply TRM adjustments to a planned order."""

        # Base result from deterministic engine
        result = PlannedOrderResult(
            item_id=planned_order.item_id,
            quantity=planned_order.quantity,
            order_date=planned_order.order_date,
            receipt_date=planned_order.receipt_date,
            order_type=planned_order.order_type,
            source_node=None,  # Determined by sourcing rules
            destination_node=node.node_key,
            trm_adjusted=False,
            adjustment_reason=None,
            confidence=1.0,
        )

        if not use_trm or not site_agent.model:
            return result

        # Get PO timing recommendation from TRM
        try:
            po_recommendation = await site_agent.get_po_recommendation(
                product_id=planned_order.item_id,
                location_id=node.node_key,
                current_inventory=0,  # Would need actual inventory
                pipeline_qty=0,
                forecast_demand=planned_order.quantity,
            )

            # Apply timing adjustment
            if po_recommendation.days_offset != 0:
                adjusted_order_date = planned_order.order_date + timedelta(
                    days=po_recommendation.days_offset
                )
                result.order_date = adjusted_order_date
                result.trm_adjusted = True
                result.adjustment_reason = f"TRM timing: {po_recommendation.days_offset:+d} days"
                result.confidence = po_recommendation.confidence

            # Apply quantity adjustment if expedite recommended
            if po_recommendation.expedite_prob > 0.7:
                # Increase quantity by 10% for expedite scenarios
                result.quantity = int(planned_order.quantity * 1.1)
                result.trm_adjusted = True
                result.adjustment_reason = (result.adjustment_reason or "") + ", expedite recommended"

        except Exception as e:
            logger.warning(f"TRM PO adjustment failed: {e}")

        return result

    def convert_to_supply_plan_orders(
        self,
        planned_orders: List[PlannedOrderResult]
    ) -> List[Dict[str, Any]]:
        """
        Convert SiteAgent planned orders to supply plan service format.

        This enables seamless integration with the existing SupplyPlanService.
        """
        orders = []
        for po in planned_orders:
            order_dict = {
                "order_type": po.order_type,
                "item_id": po.item_id,
                "source_node_id": po.source_node,
                "destination_node_id": po.destination_node,
                "quantity": float(po.quantity),
                "planned_week": (po.order_date - date.today()).days // 7,
                "delivery_week": (po.receipt_date - date.today()).days // 7,
                "cost": 0.0,  # Would be calculated based on sourcing rules
                "trm_adjusted": po.trm_adjusted,
                "adjustment_reason": po.adjustment_reason,
                "confidence": po.confidence,
            }
            orders.append(order_dict)
        return orders
