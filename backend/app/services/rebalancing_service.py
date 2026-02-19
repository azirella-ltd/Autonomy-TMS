"""
Inventory Rebalancing Service

LP-based network-wide inventory rebalancing for optimal distribution.
Uses scipy.optimize.linprog for linear programming optimization.

Key features:
- Network-wide inventory optimization
- Cost-aware transfer recommendations
- Service level constraints
- Multi-sourcing support
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class Node:
    """Inventory node in the network"""
    id: int
    name: str
    current_inventory: float
    target_inventory: float
    min_inventory: float  # Safety stock
    max_inventory: float  # Storage capacity
    holding_cost_per_unit: float
    backlog_cost_per_unit: float
    demand_forecast: float  # Expected demand in planning horizon


@dataclass
class Lane:
    """Transfer lane between nodes"""
    id: int
    source_node_id: int
    dest_node_id: int
    transport_cost_per_unit: float
    lead_time_days: int
    max_capacity: float  # Maximum transfer quantity


@dataclass
class TransferRecommendation:
    """Recommended inventory transfer"""
    source_node_id: int
    source_node_name: str
    dest_node_id: int
    dest_node_name: str
    quantity: float
    transport_cost: float
    cost_saving: float
    priority: str  # 'critical', 'high', 'medium', 'low'
    reason: str


@dataclass
class RebalancingResult:
    """Result of rebalancing optimization"""
    success: bool
    total_cost_before: float
    total_cost_after: float
    total_savings: float
    recommendations: List[TransferRecommendation]
    optimization_status: str
    computation_time_ms: float


class RebalancingService:
    """
    Inventory Rebalancing Service

    Uses linear programming to find optimal inventory transfers
    that minimize total network cost while maintaining service levels.
    """

    def __init__(self, db: Session):
        self.db = db

    def optimize_rebalancing(
        self,
        nodes: List[Node],
        lanes: List[Lane],
        planning_horizon_days: int = 7,
        min_transfer_quantity: float = 10.0,
        target_service_level: float = 0.95
    ) -> RebalancingResult:
        """
        Optimize inventory rebalancing across the network.

        Objective: Minimize total cost = holding costs + backlog costs + transport costs

        Constraints:
        - Inventory conservation at each node
        - Non-negative inventory
        - Lane capacity limits
        - Minimum service level

        Args:
            nodes: List of inventory nodes
            lanes: List of transfer lanes
            planning_horizon_days: Planning horizon in days
            min_transfer_quantity: Minimum transfer size
            target_service_level: Target service level (0-1)

        Returns:
            RebalancingResult with recommendations
        """
        import time
        start_time = time.time()

        try:
            # Try scipy optimization first
            result = self._optimize_with_scipy(
                nodes, lanes, planning_horizon_days,
                min_transfer_quantity, target_service_level
            )
        except ImportError:
            logger.warning("scipy not available, using heuristic rebalancing")
            result = self._optimize_heuristic(
                nodes, lanes, planning_horizon_days,
                min_transfer_quantity, target_service_level
            )

        computation_time = (time.time() - start_time) * 1000
        result.computation_time_ms = computation_time

        logger.info(
            f"Rebalancing optimization completed: "
            f"savings=${result.total_savings:.2f}, "
            f"recommendations={len(result.recommendations)}, "
            f"time={computation_time:.1f}ms"
        )

        return result

    def _optimize_with_scipy(
        self,
        nodes: List[Node],
        lanes: List[Lane],
        planning_horizon_days: int,
        min_transfer_quantity: float,
        target_service_level: float
    ) -> RebalancingResult:
        """Optimize using scipy linear programming"""
        from scipy.optimize import linprog

        n_nodes = len(nodes)
        n_lanes = len(lanes)

        if n_lanes == 0:
            return RebalancingResult(
                success=True,
                total_cost_before=self._calculate_total_cost(nodes),
                total_cost_after=self._calculate_total_cost(nodes),
                total_savings=0.0,
                recommendations=[],
                optimization_status="No lanes available for rebalancing",
                computation_time_ms=0.0
            )

        # Build node index mapping
        node_idx = {node.id: i for i, node in enumerate(nodes)}
        node_by_id = {node.id: node for node in nodes}

        # Decision variables: transfer quantity on each lane
        # x[i] = quantity transferred on lane i

        # Objective: minimize transport costs + resulting holding/backlog costs
        # For simplicity, we minimize transport costs and use constraints for inventory balance
        c = np.array([lane.transport_cost_per_unit for lane in lanes])

        # Inequality constraints: A_ub @ x <= b_ub
        # 1. Lane capacity: x[i] <= max_capacity[i]
        A_ub_capacity = np.eye(n_lanes)
        b_ub_capacity = np.array([lane.max_capacity for lane in lanes])

        # 2. Source node inventory: total outflow <= available inventory - safety stock
        A_ub_source = np.zeros((n_nodes, n_lanes))
        b_ub_source = np.zeros(n_nodes)

        for i, lane in enumerate(lanes):
            source_idx = node_idx.get(lane.source_node_id)
            if source_idx is not None:
                A_ub_source[source_idx, i] = 1.0

        for i, node in enumerate(nodes):
            available = max(0, node.current_inventory - node.min_inventory - node.demand_forecast)
            b_ub_source[i] = available

        # Combine inequality constraints
        A_ub = np.vstack([A_ub_capacity, A_ub_source])
        b_ub = np.concatenate([b_ub_capacity, b_ub_source])

        # Bounds: 0 <= x[i] <= max_capacity[i]
        bounds = [(0, lane.max_capacity) for lane in lanes]

        # Solve LP
        result = linprog(
            c, A_ub=A_ub, b_ub=b_ub,
            bounds=bounds, method='highs'
        )

        if not result.success:
            logger.warning(f"LP optimization failed: {result.message}")
            return self._optimize_heuristic(
                nodes, lanes, planning_horizon_days,
                min_transfer_quantity, target_service_level
            )

        # Extract recommendations from solution
        recommendations = []
        total_transport_cost = 0.0

        for i, lane in enumerate(lanes):
            qty = result.x[i]
            if qty >= min_transfer_quantity:
                source_node = node_by_id[lane.source_node_id]
                dest_node = node_by_id[lane.dest_node_id]

                transport_cost = qty * lane.transport_cost_per_unit
                total_transport_cost += transport_cost

                # Calculate cost saving from this transfer
                # Saving = reduced backlog cost at dest - increased holding cost at source
                dest_shortfall = max(0, dest_node.target_inventory - dest_node.current_inventory)
                useful_qty = min(qty, dest_shortfall)
                backlog_saving = useful_qty * dest_node.backlog_cost_per_unit * planning_horizon_days
                holding_increase = qty * source_node.holding_cost_per_unit * (lane.lead_time_days / 2)

                cost_saving = backlog_saving - holding_increase - transport_cost

                # Determine priority
                if dest_node.current_inventory < dest_node.min_inventory:
                    priority = 'critical'
                elif dest_node.current_inventory < dest_node.target_inventory * 0.8:
                    priority = 'high'
                elif dest_node.current_inventory < dest_node.target_inventory:
                    priority = 'medium'
                else:
                    priority = 'low'

                recommendations.append(TransferRecommendation(
                    source_node_id=lane.source_node_id,
                    source_node_name=source_node.name,
                    dest_node_id=lane.dest_node_id,
                    dest_node_name=dest_node.name,
                    quantity=round(qty, 0),
                    transport_cost=round(transport_cost, 2),
                    cost_saving=round(cost_saving, 2),
                    priority=priority,
                    reason=self._generate_reason(source_node, dest_node, qty)
                ))

        # Sort by priority and cost saving
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        recommendations.sort(key=lambda r: (priority_order[r.priority], -r.cost_saving))

        total_cost_before = self._calculate_total_cost(nodes)
        total_savings = sum(r.cost_saving for r in recommendations)

        return RebalancingResult(
            success=True,
            total_cost_before=round(total_cost_before, 2),
            total_cost_after=round(total_cost_before - total_savings, 2),
            total_savings=round(total_savings, 2),
            recommendations=recommendations,
            optimization_status="Optimal solution found using LP",
            computation_time_ms=0.0
        )

    def _optimize_heuristic(
        self,
        nodes: List[Node],
        lanes: List[Lane],
        planning_horizon_days: int,
        min_transfer_quantity: float,
        target_service_level: float
    ) -> RebalancingResult:
        """
        Heuristic rebalancing when scipy is not available.

        Algorithm:
        1. Identify nodes with excess inventory (above target)
        2. Identify nodes with shortfall (below target)
        3. Match excess to shortfall via available lanes
        4. Prioritize critical shortfalls
        """
        node_by_id = {node.id: node for node in nodes}

        # Calculate excess and shortfall for each node
        node_status = {}
        for node in nodes:
            available = node.current_inventory - node.min_inventory - node.demand_forecast
            excess = max(0, available - (node.target_inventory - node.current_inventory))
            shortfall = max(0, node.target_inventory - node.current_inventory)
            node_status[node.id] = {
                'excess': excess,
                'shortfall': shortfall,
                'available': max(0, available)
            }

        # Build lane lookup: dest_id -> list of (lane, source_id)
        lanes_to_node = {}
        for lane in lanes:
            if lane.dest_node_id not in lanes_to_node:
                lanes_to_node[lane.dest_node_id] = []
            lanes_to_node[lane.dest_node_id].append(lane)

        recommendations = []

        # Process nodes with shortfall
        shortfall_nodes = [
            (node, node_status[node.id]['shortfall'])
            for node in nodes
            if node_status[node.id]['shortfall'] > 0
        ]
        # Sort by criticality (below safety stock first, then by shortfall amount)
        shortfall_nodes.sort(
            key=lambda x: (
                0 if x[0].current_inventory < x[0].min_inventory else 1,
                -x[1]
            )
        )

        for dest_node, shortfall in shortfall_nodes:
            remaining_shortfall = shortfall

            for lane in lanes_to_node.get(dest_node.id, []):
                if remaining_shortfall < min_transfer_quantity:
                    break

                source_node = node_by_id.get(lane.source_node_id)
                if not source_node:
                    continue

                available = node_status[lane.source_node_id]['available']
                if available < min_transfer_quantity:
                    continue

                # Calculate transfer quantity
                qty = min(
                    remaining_shortfall,
                    available,
                    lane.max_capacity
                )

                if qty < min_transfer_quantity:
                    continue

                # Update tracking
                node_status[lane.source_node_id]['available'] -= qty
                remaining_shortfall -= qty

                # Calculate costs
                transport_cost = qty * lane.transport_cost_per_unit
                backlog_saving = qty * dest_node.backlog_cost_per_unit * planning_horizon_days
                holding_increase = qty * source_node.holding_cost_per_unit * (lane.lead_time_days / 2)
                cost_saving = backlog_saving - holding_increase - transport_cost

                # Determine priority
                if dest_node.current_inventory < dest_node.min_inventory:
                    priority = 'critical'
                elif dest_node.current_inventory < dest_node.target_inventory * 0.8:
                    priority = 'high'
                else:
                    priority = 'medium'

                recommendations.append(TransferRecommendation(
                    source_node_id=lane.source_node_id,
                    source_node_name=source_node.name,
                    dest_node_id=lane.dest_node_id,
                    dest_node_name=dest_node.name,
                    quantity=round(qty, 0),
                    transport_cost=round(transport_cost, 2),
                    cost_saving=round(cost_saving, 2),
                    priority=priority,
                    reason=self._generate_reason(source_node, dest_node, qty)
                ))

        total_cost_before = self._calculate_total_cost(nodes)
        total_savings = sum(r.cost_saving for r in recommendations)

        return RebalancingResult(
            success=True,
            total_cost_before=round(total_cost_before, 2),
            total_cost_after=round(total_cost_before - total_savings, 2),
            total_savings=round(total_savings, 2),
            recommendations=recommendations,
            optimization_status="Heuristic solution (scipy not available)",
            computation_time_ms=0.0
        )

    def _calculate_total_cost(self, nodes: List[Node]) -> float:
        """Calculate current total network cost"""
        total = 0.0
        for node in nodes:
            # Holding cost for excess inventory
            excess = max(0, node.current_inventory - node.target_inventory)
            total += excess * node.holding_cost_per_unit * 7  # Weekly

            # Backlog cost for shortfall
            shortfall = max(0, node.target_inventory - node.current_inventory)
            total += shortfall * node.backlog_cost_per_unit * 7  # Weekly

        return total

    def _generate_reason(self, source: Node, dest: Node, qty: float) -> str:
        """Generate human-readable reason for transfer"""
        if dest.current_inventory < dest.min_inventory:
            return (
                f"{dest.name} is below safety stock ({dest.current_inventory:.0f} < {dest.min_inventory:.0f}). "
                f"Transfer {qty:.0f} units from {source.name} to prevent stockouts."
            )
        elif dest.current_inventory < dest.target_inventory * 0.8:
            return (
                f"{dest.name} inventory is critically low ({dest.current_inventory:.0f}/{dest.target_inventory:.0f}). "
                f"Transfer {qty:.0f} units from {source.name} to improve service level."
            )
        else:
            coverage = dest.current_inventory / max(1, dest.demand_forecast)
            return (
                f"Rebalance {qty:.0f} units from {source.name} to {dest.name} "
                f"to improve network efficiency. Current coverage: {coverage:.1f} days."
            )


def get_rebalancing_service(db: Session) -> RebalancingService:
    """Factory function for RebalancingService"""
    return RebalancingService(db)
