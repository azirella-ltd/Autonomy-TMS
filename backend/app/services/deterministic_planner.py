"""
Deterministic Supply Planning Module

Generates strategic supply plans using classical planning policies:
- Safety stock calculations
- Reorder point (ROP) policy
- Economic order quantity (EOQ)
- Purchase orders, manufacturing orders, stock transfer orders

This is PLANNING (not execution). Outputs are strategic decisions over
a planning horizon, not period-by-period reactive orders.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np
from sqlalchemy.orm import Session

from app.models.supply_chain_config import SupplyChainConfig, Site, TransportationLane
from app.models.sc_entities import Product


class OrderType(str, Enum):
    """Type of order in supply plan."""
    PURCHASE_ORDER = "purchase_order"
    MANUFACTURING_ORDER = "manufacturing_order"
    STOCK_TRANSFER_ORDER = "stock_transfer_order"


@dataclass
class PlanningOrder:
    """A planned order (PO, MO, or STO)."""
    order_type: OrderType
    item_id: int
    source_node_id: Optional[int]  # Supplier or upstream DC (None for manufacturing)
    destination_node_id: int  # Receiving node
    quantity: float
    planned_week: int  # Week to initiate order
    delivery_week: int  # Week order arrives (accounting for lead time)
    cost: float


@dataclass
class InventoryTarget:
    """Inventory targets for a node/item."""
    node_id: int
    item_id: int
    safety_stock: float
    reorder_point: float
    order_quantity: float  # EOQ or fixed order quantity
    review_period: int  # Weeks between reviews


@dataclass
class DemandForecast:
    """Aggregated demand forecast for planning."""
    item_id: int
    node_id: int
    weekly_demand: np.ndarray  # Mean demand per week
    demand_std_dev: float  # Standard deviation
    total_demand: float


class DeterministicPlanner:
    """
    Deterministic supply planner using classical policies.

    Generates purchase orders, manufacturing orders, and stock transfer orders
    based on demand forecasts, safety stock calculations, and reorder point logic.
    """

    def __init__(
        self,
        session: Session,
        config: SupplyChainConfig,
        planning_horizon: int = 52
    ):
        """
        Initialize deterministic planner.

        Args:
            session: Database session
            config: Supply chain configuration
            planning_horizon: Planning horizon in weeks
        """
        self.session = session
        self.config = config
        self.planning_horizon = planning_horizon

    def generate_plan(
        self,
        demand_forecasts: Dict[Tuple[int, int], DemandForecast],
        service_level: float = 0.95,
        ordering_cost: float = 100.0,
        holding_cost_rate: float = 0.20
    ) -> Tuple[List[PlanningOrder], List[InventoryTarget]]:
        """
        Generate deterministic supply plan.

        Args:
            demand_forecasts: {(item_id, node_id): DemandForecast}
            service_level: Target service level (e.g., 0.95 for 95%)
            ordering_cost: Fixed cost per order
            holding_cost_rate: Annual inventory holding cost as % of item value

        Returns:
            (orders, inventory_targets)
        """
        orders = []
        inventory_targets = []

        # Get all nodes from config
        nodes = self.session.query(Site).filter(Site.config_id == self.config.id).all()
        items = self.session.query(Product).filter(Product.config_id == self.config.id).all()

        # Calculate inventory targets for each node/item
        for node in nodes:
            for item in items:
                forecast_key = (item.id, node.id)

                if forecast_key not in demand_forecasts:
                    # No demand at this node for this item
                    continue

                forecast = demand_forecasts[forecast_key]

                # Calculate safety stock
                safety_stock = self._calculate_safety_stock(
                    forecast.demand_std_dev,
                    self._get_lead_time(node, item),
                    service_level
                )

                # Calculate reorder point
                avg_demand_during_lead_time = (
                    np.mean(forecast.weekly_demand) * self._get_lead_time(node, item)
                )
                reorder_point = avg_demand_during_lead_time + safety_stock

                # Calculate economic order quantity
                annual_demand = forecast.total_demand * (52 / self.planning_horizon)
                item_value = self._get_item_value(item)
                holding_cost = holding_cost_rate * item_value

                eoq = self._calculate_eoq(
                    annual_demand,
                    ordering_cost,
                    holding_cost
                )

                # Store inventory target
                inventory_targets.append(InventoryTarget(
                    node_id=node.id,
                    item_id=item.id,
                    safety_stock=safety_stock,
                    reorder_point=reorder_point,
                    order_quantity=eoq,
                    review_period=1  # Weekly review
                ))

                # Generate planned orders using ROP policy
                node_orders = self._generate_replenishment_orders(
                    node,
                    item,
                    forecast,
                    reorder_point,
                    eoq
                )

                orders.extend(node_orders)

        return orders, inventory_targets

    def _calculate_safety_stock(
        self,
        demand_std_dev: float,
        lead_time: int,
        service_level: float
    ) -> float:
        """
        Calculate safety stock using normal distribution assumption.

        SS = z * σ * sqrt(LT)

        where:
        - z is the service level quantile (e.g., 1.645 for 95%)
        - σ is demand standard deviation per period
        - LT is lead time in periods
        """
        from scipy.stats import norm

        z_score = norm.ppf(service_level)
        safety_stock = z_score * demand_std_dev * np.sqrt(lead_time)

        return max(0, safety_stock)

    def _calculate_eoq(
        self,
        annual_demand: float,
        ordering_cost: float,
        holding_cost: float
    ) -> float:
        """
        Calculate Economic Order Quantity.

        EOQ = sqrt((2 * D * K) / h)

        where:
        - D is annual demand
        - K is ordering cost per order
        - h is holding cost per unit per year
        """
        if holding_cost <= 0:
            # Avoid division by zero
            holding_cost = 0.01

        eoq = np.sqrt((2 * annual_demand * ordering_cost) / holding_cost)

        return max(1, eoq)

    def _get_lead_time(self, node: Site, item: Product) -> int:
        """Get procurement/manufacturing lead time from upstream lane."""
        if self.session:
            lane = self.session.query(TransportationLane).filter(
                TransportationLane.to_site_id == node.id,
                TransportationLane.config_id == node.config_id,
            ).first()
            if lane and lane.supply_lead_time:
                return max(1, lane.supply_lead_time)
        return 2  # Default 2 weeks

    def _get_item_value(self, item: Product) -> float:
        """Get item unit value from Product model."""
        if self.session and hasattr(item, 'id'):
            product = self.session.query(Product).filter(Product.id == str(item.id)).first()
            if product and hasattr(product, 'unit_cost') and product.unit_cost:
                return float(product.unit_cost)
        return 100.0  # Default $100 per unit

    def _get_current_inventory(self, node: Site, item: Product) -> float:
        """Get current on-hand inventory from InvLevel."""
        if self.session:
            from app.models.sc_entities import InvLevel
            inv = self.session.query(InvLevel).filter(
                InvLevel.site_id == node.id,
                InvLevel.product_id == str(item.id),
            ).order_by(InvLevel.id.desc()).first()
            if inv and inv.on_hand_qty:
                return float(inv.on_hand_qty)
        return 0.0

    def _get_pipeline_inventory(self, node: Site, item: Product) -> float:
        """Get inventory in transit (on order but not arrived)."""
        # Simplified: assume no initial pipeline
        return 0.0

    def _generate_replenishment_orders(
        self,
        node: Site,
        item: Product,
        forecast: DemandForecast,
        reorder_point: float,
        order_quantity: float
    ) -> List[PlanningOrder]:
        """
        Generate replenishment orders using reorder point policy.

        Policy: When inventory position drops below ROP, order EOQ.
        """
        orders = []

        # Simulate inventory position over planning horizon
        inventory_position = self._get_current_inventory(node, item) + \
                             self._get_pipeline_inventory(node, item)

        lead_time = self._get_lead_time(node, item)

        for week in range(self.planning_horizon):
            # Check if we need to order
            if inventory_position < reorder_point:
                # Determine order type based on node type
                order_type = self._determine_order_type(node)

                # Get source node (supplier or upstream)
                source_node_id = self._get_source_node(node, item)

                # Create order
                order = PlanningOrder(
                    order_type=order_type,
                    item_id=item.id,
                    source_node_id=source_node_id,
                    destination_node_id=node.id,
                    quantity=order_quantity,
                    planned_week=week,
                    delivery_week=week + lead_time,
                    cost=self._calculate_order_cost(order_type, order_quantity)
                )

                orders.append(order)

                # Add to pipeline
                inventory_position += order_quantity

            # Deplete inventory based on forecast
            if week < len(forecast.weekly_demand):
                inventory_position -= forecast.weekly_demand[week]

        return orders

    def _determine_order_type(self, node: Site) -> OrderType:
        """Determine order type based on node type."""
        node_type_str = str(node.type).lower()

        if "manufact" in node_type_str or "plant" in node_type_str:
            return OrderType.MANUFACTURING_ORDER
        elif "supplier" in node_type_str:
            return OrderType.PURCHASE_ORDER
        else:
            # Distributors, wholesalers, retailers order from upstream
            return OrderType.PURCHASE_ORDER

    def _get_source_node(self, node: Site, item: Product) -> Optional[int]:
        """Get source node (upstream supplier) for this node/item via TransportationLane."""
        try:
            lane = self.session.query(TransportationLane).filter(
                TransportationLane.to_site_id == node.id,
                TransportationLane.config_id == node.config_id,
            ).first()
            if lane:
                return lane.from_site_id
        except Exception:
            pass
        return None

    def _calculate_order_cost(self, order_type: OrderType, quantity: float) -> float:
        """Calculate order cost."""
        # Simplified: fixed ordering cost + variable cost
        fixed_cost = 100.0
        variable_cost = quantity * 50.0  # $50 per unit

        return fixed_cost + variable_cost
