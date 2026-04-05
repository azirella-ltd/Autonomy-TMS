"""
MRP Engine - 100% Deterministic

Implements standard MRP netting logic:
- Gross requirements from demand/forecasts
- Net requirements = Gross - On-hand - Scheduled receipts
- BOM explosion for dependent demand
- Lead time offsetting for planned orders

This engine handles the mathematically defined operations.
TRM heads handle exceptions like sourcing overrides and expedite triggers.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import math
import logging

logger = logging.getLogger(__name__)


@dataclass
class MRPConfig:
    """MRP engine configuration"""
    planning_horizon_days: int = 90
    planning_buckets: str = "daily"  # "daily", "weekly"
    lot_sizing_rule: str = "lot_for_lot"  # "lot_for_lot", "eoq", "fixed", "pot"
    fixed_lot_size: Optional[float] = None
    eoq_params: Dict = field(default_factory=lambda: {
        'ordering_cost': 100.0,
        'holding_cost_rate': 0.25,
    })
    safety_lead_time_days: int = 0
    min_order_qty: float = 0
    max_order_qty: Optional[float] = None


@dataclass
class GrossRequirement:
    """A gross requirement for an item"""
    item_id: str
    required_date: date
    quantity: float
    source: str  # "demand", "forecast", "dependent", "inventory_buffer"
    priority: int = 3  # 1=highest, 5=lowest


@dataclass
class NetRequirement:
    """A net requirement after netting"""
    item_id: str
    required_date: date
    gross_qty: float
    on_hand_available: float
    scheduled_receipt: float
    net_qty: float  # = gross - on_hand - scheduled
    projected_ending_inventory: float


@dataclass
class PlannedOrder:
    """A planned order from MRP"""
    item_id: str
    order_date: date      # When to release
    receipt_date: date    # When expected
    quantity: float
    order_type: str       # "purchase", "manufacture", "transfer"
    source: str = ""      # Supplier or plant ID
    priority: int = 3


class MRPEngine:
    """
    Material Requirements Planning engine.

    100% deterministic - same inputs always produce same outputs.
    No neural networks, no learned components.
    """

    def __init__(self, site_key: str, config: Optional[MRPConfig] = None):
        self.site_key = site_key
        self.config = config or MRPConfig()

    def compute_net_requirements(
        self,
        gross_requirements: List[GrossRequirement],
        on_hand_inventory: Dict[str, float],
        scheduled_receipts: Dict[str, List[Tuple[date, float]]],
        bom: Dict[str, List[Tuple[str, float]]],  # parent_id -> [(child_id, qty_per)]
        lead_times: Dict[str, int],  # item_id -> days
        safety_stocks: Optional[Dict[str, float]] = None
    ) -> Tuple[List[NetRequirement], List[PlannedOrder]]:
        """
        Run MRP netting and explosion.

        Algorithm:
        1. Sort gross requirements by date
        2. For each period, compute net = gross - available
        3. Generate planned orders for positive net requirements
        4. Explode BOM to create dependent demand
        5. Lead time offset planned orders

        Returns:
            (net_requirements, planned_orders)
        """
        safety_stocks = safety_stocks or {}

        # Group gross requirements by item and date
        req_by_item_date: Dict[str, Dict[date, float]] = defaultdict(lambda: defaultdict(float))
        for req in gross_requirements:
            req_by_item_date[req.item_id][req.required_date] += req.quantity

        # Track projected inventory
        projected_inv = dict(on_hand_inventory)

        # Track scheduled receipts by item and date
        receipts_by_item_date: Dict[str, Dict[date, float]] = defaultdict(lambda: defaultdict(float))
        for item_id, receipts in scheduled_receipts.items():
            for receipt_date, qty in receipts:
                receipts_by_item_date[item_id][receipt_date] += qty

        net_requirements: List[NetRequirement] = []
        planned_orders: List[PlannedOrder] = []

        # Process each item - need to process in BOM order (level by level)
        # For simplicity, we'll iterate until no new dependent demand is created
        processed_items = set()
        max_iterations = 10  # Prevent infinite loops

        for iteration in range(max_iterations):
            all_items = set(req_by_item_date.keys())
            items_to_process = all_items - processed_items

            if not items_to_process:
                break

            for item_id in sorted(items_to_process):
                item_nets, item_planned = self._process_item(
                    item_id=item_id,
                    requirements=dict(req_by_item_date[item_id]),
                    projected_inv=projected_inv.get(item_id, 0),
                    scheduled_receipts=dict(receipts_by_item_date[item_id]),
                    lead_time=lead_times.get(item_id, 1),
                    safety_stock=safety_stocks.get(item_id, 0),
                    bom=bom
                )
                net_requirements.extend(item_nets)
                planned_orders.extend(item_planned)

                # BOM explosion: add dependent demand for next iteration
                for planned in item_planned:
                    if item_id in bom:
                        for child_id, qty_per in bom[item_id]:
                            dependent_qty = planned.quantity * qty_per
                            req_by_item_date[child_id][planned.order_date] += dependent_qty
                            logger.debug(
                                f"BOM explosion: {item_id} -> {child_id}, "
                                f"qty={dependent_qty} on {planned.order_date}"
                            )

                processed_items.add(item_id)

        return net_requirements, planned_orders

    def _process_item(
        self,
        item_id: str,
        requirements: Dict[date, float],
        projected_inv: float,
        scheduled_receipts: Dict[date, float],
        lead_time: int,
        safety_stock: float,
        bom: Dict[str, List[Tuple[str, float]]]
    ) -> Tuple[List[NetRequirement], List[PlannedOrder]]:
        """Process a single item through MRP logic"""

        nets: List[NetRequirement] = []
        planned: List[PlannedOrder] = []

        # Get all dates in planning horizon
        # TODO(virtual-clock): engine has no tenant/config/db context — thread
        # config_id through MRPConfig + sync session to use config_today_sync.
        today = date.today()
        horizon_end = today + timedelta(days=self.config.planning_horizon_days)

        # Collect all relevant dates
        all_dates = set(requirements.keys()) | set(scheduled_receipts.keys())
        all_dates = sorted([d for d in all_dates if today <= d <= horizon_end])

        if not all_dates:
            return nets, planned

        running_inv = projected_inv

        for req_date in all_dates:
            gross = requirements.get(req_date, 0)
            receipt = scheduled_receipts.get(req_date, 0)

            # Update projected inventory with receipts
            running_inv += receipt

            # Compute net requirement (including safety stock)
            # Net = Gross + Safety Stock - Available
            net = gross + safety_stock - running_inv

            # Record the net requirement
            nets.append(NetRequirement(
                item_id=item_id,
                required_date=req_date,
                gross_qty=gross,
                on_hand_available=running_inv,
                scheduled_receipt=receipt,
                net_qty=max(0, net),
                projected_ending_inventory=running_inv - gross
            ))

            if net > 0:
                # Generate planned order
                order_qty = self._apply_lot_sizing(net, item_id)
                order_date = req_date - timedelta(
                    days=lead_time + self.config.safety_lead_time_days
                )

                planned.append(PlannedOrder(
                    item_id=item_id,
                    order_date=max(today, order_date),  # Can't order in past
                    receipt_date=req_date,
                    quantity=order_qty,
                    order_type=self._determine_order_type(item_id, bom)
                ))

                # Planned receipt increases future inventory
                running_inv += order_qty

            # Consume inventory
            running_inv -= gross
            running_inv = max(0, running_inv)  # Can't go negative (would be backlog)

        return nets, planned

    def _apply_lot_sizing(self, net_qty: float, item_id: str) -> float:
        """Apply lot sizing rule to net quantity"""

        # Apply min/max constraints
        qty = max(self.config.min_order_qty, net_qty)
        if self.config.max_order_qty:
            qty = min(self.config.max_order_qty, qty)

        if self.config.lot_sizing_rule == "lot_for_lot":
            return qty

        elif self.config.lot_sizing_rule == "fixed":
            if self.config.fixed_lot_size:
                # Round up to fixed lot size
                return math.ceil(qty / self.config.fixed_lot_size) * self.config.fixed_lot_size
            return qty

        elif self.config.lot_sizing_rule == "eoq":
            # Economic Order Quantity
            # EOQ = sqrt(2 * D * S / H)
            # Where D = annual demand, S = ordering cost, H = holding cost
            # Simplified: use net_qty as period demand approximation
            S = self.config.eoq_params.get('ordering_cost', 100)
            H = self.config.eoq_params.get('holding_cost_rate', 0.25)

            if H > 0:
                # Assume unit cost of 10 for holding cost calculation
                unit_cost = 10
                holding_cost = unit_cost * H
                eoq = math.sqrt(2 * qty * 52 * S / holding_cost)  # Annualized
                return max(qty, eoq)  # At least cover the requirement

            return qty

        return qty

    def _determine_order_type(
        self,
        item_id: str,
        bom: Dict[str, List[Tuple[str, float]]]
    ) -> str:
        """Determine if item is purchased or manufactured"""
        if item_id in bom:
            return "manufacture"
        return "purchase"

    def validate_bom(
        self,
        bom: Dict[str, List[Tuple[str, float]]]
    ) -> List[str]:
        """
        Validate BOM for circular references.

        Returns list of error messages (empty if valid).
        """
        errors = []

        def has_cycle(item: str, visited: set, path: set) -> bool:
            if item in path:
                return True
            if item in visited:
                return False

            visited.add(item)
            path.add(item)

            for child, _ in bom.get(item, []):
                if has_cycle(child, visited, path):
                    return True

            path.remove(item)
            return False

        visited: set = set()
        for item in bom:
            if has_cycle(item, visited, set()):
                errors.append(f"Circular reference detected involving item: {item}")

        return errors
