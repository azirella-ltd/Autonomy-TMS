"""
Supply Plan Evaluator

Evaluates deterministic supply plans using Monte Carlo simulation.
Simulates plan execution under stochastic demand scenarios and computes
probabilistic performance metrics.

This is the evaluation/simulation layer that executes a strategic plan,
NOT the planning layer itself.
"""

from typing import Dict, List, Optional, Tuple
import numpy as np
from dataclasses import dataclass

from app.services.deterministic_planner import PlanningOrder, InventoryTarget, OrderType


@dataclass
class PlanExecutionResult:
    """Results from executing a plan in one scenario."""
    scenario_number: int

    # Financial metrics
    total_cost: float
    inventory_carrying_cost: float
    backlog_penalty_cost: float
    ordering_cost: float

    # Customer metrics
    otif: float  # On-Time-In-Full %
    fill_rate: float
    backorder_rate: float
    service_level: float

    # Operational metrics
    inventory_turns: float
    avg_days_of_supply: float
    forecast_accuracy: Optional[float]
    bullwhip_ratio: float

    # Strategic metrics
    total_throughput: float
    avg_lead_time: float
    supplier_reliability_score: float

    # Detailed state
    final_inventory: Dict[int, float]  # {node_id: inventory}
    final_backlog: Dict[int, float]
    avg_inventory: Dict[int, float]


class PlanEvaluator:
    """
    Evaluates supply plans under uncertainty.

    Takes a deterministic plan (list of POs, MOs, STOs) and simulates
    its execution across multiple demand scenarios to generate probabilistic
    performance metrics.
    """

    def __init__(self, planning_horizon: int = 52):
        """
        Initialize plan evaluator.

        Args:
            planning_horizon: Planning horizon in weeks
        """
        self.planning_horizon = planning_horizon

    def evaluate_plan(
        self,
        orders: List[PlanningOrder],
        inventory_targets: List[InventoryTarget],
        demand_scenario: Dict[int, np.ndarray],  # {node_id: demand[horizon]}
        lead_time_scenario: Dict[int, int],  # {lane_id: lead_time}
        reliability_scenario: Dict[int, np.ndarray],  # {node_id: on_time[horizon]}
        scenario_number: int = 0
    ) -> PlanExecutionResult:
        """
        Evaluate plan execution in a single scenario.

        Args:
            orders: List of planned orders (POs, MOs, STOs)
            inventory_targets: Inventory targets per node
            demand_scenario: Sampled demand per node
            lead_time_scenario: Sampled lead times
            reliability_scenario: Sampled supplier reliability
            scenario_number: Scenario index

        Returns:
            PlanExecutionResult with performance metrics
        """
        # Extract unique nodes from orders and targets
        node_ids = set()
        for order in orders:
            node_ids.add(order.destination_node_id)
            if order.source_node_id:
                node_ids.add(order.source_node_id)
        for target in inventory_targets:
            node_ids.add(target.node_id)

        node_ids = sorted(list(node_ids))
        num_nodes = len(node_ids)
        node_id_to_idx = {node_id: idx for idx, node_id in enumerate(node_ids)}

        # Initialize state arrays
        inventory = np.zeros((num_nodes, self.planning_horizon + 1))
        backlog = np.zeros((num_nodes, self.planning_horizon + 1))
        shipments = np.zeros((num_nodes, self.planning_horizon))
        actual_receipts = np.zeros((num_nodes, self.planning_horizon))

        # Set initial inventory to safety stock levels
        for target in inventory_targets:
            if target.node_id in node_id_to_idx:
                idx = node_id_to_idx[target.node_id]
                inventory[idx, 0] = target.safety_stock

        # Create order delivery schedule
        # delivery_schedule[week] = [(node_idx, quantity), ...]
        delivery_schedule = {week: [] for week in range(self.planning_horizon + 10)}

        for order in orders:
            dest_idx = node_id_to_idx.get(order.destination_node_id)
            if dest_idx is not None:
                # Apply lead time variability and reliability
                actual_delivery_week = order.delivery_week

                # Check supplier reliability (if applicable)
                if order.source_node_id and order.source_node_id in node_id_to_idx:
                    source_idx = node_id_to_idx[order.source_node_id]
                    if source_idx < len(reliability_scenario.get(order.source_node_id, [])):
                        week = min(order.planned_week, self.planning_horizon - 1)
                        on_time = reliability_scenario.get(order.source_node_id, np.ones(self.planning_horizon))[week]
                        if on_time < 0.5:  # Delayed
                            actual_delivery_week += 1

                # Cap delivery week at horizon
                if actual_delivery_week < self.planning_horizon:
                    quantity = order.quantity
                    # Apply yield loss for manufacturing orders
                    if order.order_type == OrderType.MANUFACTURING_ORDER:
                        # Assume 95% yield
                        quantity *= 0.95

                    delivery_schedule[actual_delivery_week].append((dest_idx, quantity))

        # Simulate plan execution period by period
        total_demand_served = 0
        total_demand = 0
        period_demands = []
        period_orders_placed = np.zeros(num_nodes)

        for week in range(self.planning_horizon):
            # 1. Receive scheduled deliveries
            for node_idx, quantity in delivery_schedule.get(week, []):
                inventory[node_idx, week] += quantity
                actual_receipts[node_idx, week] = quantity

            # 2. Process demand at each node
            for node_idx, node_id in enumerate(node_ids):
                # Get demand for this node/week
                demand = 0
                if node_id in demand_scenario:
                    demand_array = demand_scenario[node_id]
                    if week < len(demand_array):
                        demand = demand_array[week]

                period_demands.append(demand)
                total_demand += demand

                # Add backlog from previous period
                incoming_demand = demand + backlog[node_idx, week]

                # Ship what's available
                shipped = min(inventory[node_idx, week], incoming_demand)
                shipments[node_idx, week] = shipped
                total_demand_served += shipped

                # Update inventory and backlog
                inventory[node_idx, week + 1] = inventory[node_idx, week] - shipped
                backlog[node_idx, week + 1] = max(0, incoming_demand - shipped)

        # Calculate metrics
        # Financial
        total_inventory = np.sum(inventory[:, :-1])
        total_backlog = np.sum(backlog[:, :-1])

        inventory_carrying_cost = total_inventory * 1.0  # $1 per unit per week
        backlog_penalty_cost = total_backlog * 2.0  # $2 per unit per week
        ordering_cost = sum(order.cost for order in orders)
        total_cost = inventory_carrying_cost + backlog_penalty_cost + ordering_cost

        # Customer metrics
        fill_rate = total_demand_served / max(1, total_demand)

        # OTIF: periods with no backlog at customer-facing nodes
        customer_node_idx = 0  # Assume first node is customer-facing
        periods_with_backlog = np.sum(backlog[customer_node_idx, 1:] > 0)
        otif = 1.0 - (periods_with_backlog / self.planning_horizon)

        backorder_rate = 1.0 - fill_rate
        service_level = otif

        # Operational metrics
        avg_inventory = np.mean(inventory[:, :-1])
        if avg_inventory > 0 and total_demand > 0:
            inventory_turns = (total_demand / avg_inventory) * (52 / self.planning_horizon)
        else:
            inventory_turns = 0

        avg_period_demand = total_demand / self.planning_horizon if self.planning_horizon > 0 else 1
        avg_days_of_supply = (avg_inventory / max(1, avg_period_demand)) * 7

        # Bullwhip: variability of receipts vs demand
        if len(period_demands) > 1:
            demand_std = np.std(period_demands)
            receipts_std = np.std(actual_receipts.flatten())
            bullwhip_ratio = receipts_std / max(demand_std, 0.01)
        else:
            bullwhip_ratio = 1.0

        # Strategic metrics
        total_throughput = total_demand_served
        avg_lead_time = np.mean([order.delivery_week - order.planned_week for order in orders]) if orders else 2

        supplier_reliability_score = np.mean([
            np.mean(reliability) for reliability in reliability_scenario.values()
        ]) if reliability_scenario else 0.95

        # Final states
        final_inventory = {node_id: float(inventory[idx, -1]) for node_id, idx in node_id_to_idx.items()}
        final_backlog = {node_id: float(backlog[idx, -1]) for node_id, idx in node_id_to_idx.items()}
        avg_inventory_by_node = {node_id: float(np.mean(inventory[idx, :-1])) for node_id, idx in node_id_to_idx.items()}

        return PlanExecutionResult(
            scenario_number=scenario_number,
            total_cost=total_cost,
            inventory_carrying_cost=inventory_carrying_cost,
            backlog_penalty_cost=backlog_penalty_cost,
            ordering_cost=ordering_cost,
            otif=otif,
            fill_rate=fill_rate,
            backorder_rate=backorder_rate,
            service_level=service_level,
            inventory_turns=inventory_turns,
            avg_days_of_supply=avg_days_of_supply,
            forecast_accuracy=None,
            bullwhip_ratio=bullwhip_ratio,
            total_throughput=total_throughput,
            avg_lead_time=avg_lead_time,
            supplier_reliability_score=supplier_reliability_score,
            final_inventory=final_inventory,
            final_backlog=final_backlog,
            avg_inventory=avg_inventory_by_node,
        )
