"""
Hierarchical Planning with Powell Consistency

Ensures lower-level policies respect higher-level constraints:
- Strategic bounds on capacity investment
- Tactical bounds on production levels
- Operational bounds on inventory positions

Powell's key insight: Lower-level value functions should be
consistent with higher-level policies.

V_execution(s) ≈ E[V_tactical(s') | execute policy from s]

This ensures that fast operational decisions (VFA) don't
contradict slower strategic plans (CFA/DLA).

Phase 3: Tactical Level (MPS/Supply Planning)

References:
- Powell (2022) Sequential Decision Analytics, Chapter on Hierarchical Planning
- Sethi & Zhang (1994). Hierarchical Decision Making in Stochastic Manufacturing
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class StrategicBounds:
    """
    Strategic constraints from S&OP level.

    These are the high-level decisions that constrain tactical planning:
    - Capacity investments
    - Supplier approvals
    - Product portfolio
    """
    min_production_by_site: Dict[str, float] = field(default_factory=dict)
    max_production_by_site: Dict[str, float] = field(default_factory=dict)
    target_inventory_investment: float = 0.0
    max_inventory_investment: float = float('inf')
    approved_suppliers: List[str] = field(default_factory=list)
    approved_products: List[str] = field(default_factory=list)
    capacity_expansion_allowed: bool = True

    # Revenue and margin targets
    min_revenue_by_channel: Dict[str, float] = field(default_factory=dict)
    target_margin: float = 0.0

    # Valid period
    valid_from_period: int = 0
    valid_to_period: int = 9999

    def is_valid(self, period: int) -> bool:
        return self.valid_from_period <= period <= self.valid_to_period


@dataclass
class TacticalBounds:
    """
    Tactical constraints from MPS level.

    These are the medium-term plans that constrain operational decisions:
    - Production schedules
    - Firm planned orders
    - Planning fences
    """
    production_schedule: Dict[str, List[float]] = field(default_factory=dict)  # product -> [qty by period]
    firm_planned_orders: List[Dict] = field(default_factory=list)  # Orders that cannot be changed
    planning_fence: int = 2  # Periods within which no changes allowed
    trading_fence: int = 4  # Periods within which changes need approval

    # Safety stock targets
    safety_stock_targets: Dict[str, float] = field(default_factory=dict)  # product -> target

    # Capacity allocations
    capacity_reservations: Dict[str, Dict[str, float]] = field(default_factory=dict)  # resource -> product -> qty

    def get_scheduled_production(self, product_id: str, period: int) -> float:
        """Get scheduled production for product at period"""
        schedule = self.production_schedule.get(product_id, [])
        if period < len(schedule):
            return schedule[period]
        return 0.0

    def is_in_firm_fence(self, period: int) -> bool:
        """Check if period is within firm planning fence"""
        return period < self.planning_fence


@dataclass
class OperationalBounds:
    """
    Operational constraints from MRP level.

    These are the short-term constraints for execution:
    - Lot sizes
    - Safety stocks
    - Lead times
    """
    min_lot_size: Dict[str, float] = field(default_factory=dict)  # product -> min qty
    max_lot_size: Dict[str, float] = field(default_factory=dict)  # product -> max qty
    lot_size_multiple: Dict[str, float] = field(default_factory=dict)  # product -> multiple
    safety_stock: Dict[str, float] = field(default_factory=dict)  # product -> qty
    lead_times: Dict[str, int] = field(default_factory=dict)  # product/supplier -> periods

    # Order constraints
    min_order_qty: Dict[str, float] = field(default_factory=dict)
    max_order_qty: Dict[str, float] = field(default_factory=dict)

    def round_to_lot_size(self, product_id: str, quantity: float) -> float:
        """Round quantity to valid lot size"""
        min_lot = self.min_lot_size.get(product_id, 0)
        max_lot = self.max_lot_size.get(product_id, float('inf'))
        multiple = self.lot_size_multiple.get(product_id, 1)

        if quantity < min_lot:
            return 0  # Below minimum, don't order
        if quantity > max_lot:
            quantity = max_lot

        # Round to multiple
        if multiple > 1:
            quantity = round(quantity / multiple) * multiple

        return max(min_lot, quantity)


class HierarchicalPlanner:
    """
    Coordinates planning across horizons with policy consistency.

    Powell's key insight: Lower-level value functions should be
    consistent with higher-level policies.

    V_execution(s) ≈ E[V_tactical(s') | execute policy from s]

    This class enforces constraints from higher levels on lower
    levels, and validates consistency between levels.
    """

    def __init__(self, consistency_tolerance: float = 0.10):
        """
        Initialize hierarchical planner.

        Args:
            consistency_tolerance: Maximum allowed deviation between levels (default 10%)
        """
        self.consistency_tolerance = consistency_tolerance
        self.strategic_bounds: Optional[StrategicBounds] = None
        self.tactical_bounds: Optional[TacticalBounds] = None
        self.operational_bounds: Optional[OperationalBounds] = None

        # Track consistency metrics
        self.consistency_history: List[Dict] = []

    def set_strategic_bounds(self, bounds: StrategicBounds):
        """Set strategic constraints from S&OP"""
        self.strategic_bounds = bounds
        logger.info("Strategic bounds updated")

    def set_tactical_bounds(self, bounds: TacticalBounds):
        """Set tactical constraints from MPS"""
        self.tactical_bounds = bounds
        logger.info("Tactical bounds updated")

    def set_operational_bounds(self, bounds: OperationalBounds):
        """Set operational constraints from MRP"""
        self.operational_bounds = bounds
        logger.info("Operational bounds updated")

    def constrain_tactical_decision(
        self,
        decision: Dict[str, float],  # product -> production qty
        period: int,
        site_id: Optional[str] = None
    ) -> Tuple[Dict[str, float], List[str]]:
        """
        Apply strategic constraints to tactical decision.

        Returns:
            (constrained_decision, list of constraint violations)
        """
        if self.strategic_bounds is None:
            return decision, []

        constrained = {}
        violations = []

        # Check if bounds are valid for this period
        if not self.strategic_bounds.is_valid(period):
            logger.warning(f"Strategic bounds not valid for period {period}")
            return decision, ["Strategic bounds expired"]

        # Total production across all products
        total_production = sum(decision.values())

        for product, qty in decision.items():
            # Get site for product (simplified - would need product-site mapping)
            site = site_id or self._get_site_for_product(product)

            if site:
                min_prod = self.strategic_bounds.min_production_by_site.get(site, 0)
                max_prod = self.strategic_bounds.max_production_by_site.get(site, float('inf'))

                if qty < min_prod:
                    constrained[product] = min_prod
                    violations.append(f"{product}@{site}: {qty:.0f} < min {min_prod:.0f}")
                elif qty > max_prod:
                    constrained[product] = max_prod
                    violations.append(f"{product}@{site}: {qty:.0f} > max {max_prod:.0f}")
                else:
                    constrained[product] = qty
            else:
                constrained[product] = qty

            # Check if product is approved
            if (self.strategic_bounds.approved_products and
                    product not in self.strategic_bounds.approved_products):
                constrained[product] = 0
                violations.append(f"{product}: not in approved products")

        return constrained, violations

    def constrain_operational_decision(
        self,
        decision: Dict[str, float],  # order quantities
        period: int
    ) -> Tuple[Dict[str, float], List[str]]:
        """
        Apply tactical constraints to operational decision.

        Respects planning fences and firm planned orders.
        """
        if self.tactical_bounds is None:
            return decision, []

        constrained = {}
        violations = []

        for product, qty in decision.items():
            # Check if within firm planning fence
            if self.tactical_bounds.is_in_firm_fence(period):
                # Must follow MPS exactly
                scheduled = self.tactical_bounds.get_scheduled_production(product, period)
                constrained[product] = scheduled
                if abs(qty - scheduled) > 0.01:
                    violations.append(f"{product}: In firm fence, using scheduled {scheduled:.0f}")
            else:
                # Outside fence, but respect lot size constraints
                if self.operational_bounds:
                    constrained[product] = self.operational_bounds.round_to_lot_size(product, qty)
                    if constrained[product] != qty:
                        violations.append(f"{product}: Rounded to lot size {constrained[product]:.0f}")
                else:
                    constrained[product] = qty

            # Check safety stock targets
            if product in self.tactical_bounds.safety_stock_targets:
                target_ss = self.tactical_bounds.safety_stock_targets[product]
                # This is informational - actual constraint happens in inventory management
                if qty < target_ss * 0.5:  # Warning if order very low
                    violations.append(f"{product}: Order {qty:.0f} may not meet SS target {target_ss:.0f}")

        return constrained, violations

    def constrain_execution_decision(
        self,
        decision: Dict[str, float],
        period: int
    ) -> Tuple[Dict[str, float], List[str]]:
        """
        Apply operational constraints to execution decision.

        This is the most constrained level.
        """
        if self.operational_bounds is None:
            return decision, []

        constrained = {}
        violations = []

        for product, qty in decision.items():
            # Apply lot size rules
            rounded = self.operational_bounds.round_to_lot_size(product, qty)

            # Apply min/max order constraints
            min_qty = self.operational_bounds.min_order_qty.get(product, 0)
            max_qty = self.operational_bounds.max_order_qty.get(product, float('inf'))

            if rounded > 0 and rounded < min_qty:
                constrained[product] = min_qty
                violations.append(f"{product}: Below min order qty, using {min_qty:.0f}")
            elif rounded > max_qty:
                constrained[product] = max_qty
                violations.append(f"{product}: Above max order qty, capped at {max_qty:.0f}")
            else:
                constrained[product] = rounded

        return constrained, violations

    def check_consistency(
        self,
        strategic_value: float,
        tactical_value: float,
        operational_value: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Check if tactical value function is consistent with strategic.

        V_tactical should approximate expected V_strategic.

        Powell's consistency check ensures that decomposed hierarchical
        solutions are globally consistent.
        """
        results = {
            "consistent": True,
            "violations": [],
            "metrics": {},
        }

        # Strategic vs Tactical consistency
        if strategic_value != 0:
            strat_tact_diff = abs(tactical_value - strategic_value) / abs(strategic_value)
            results["metrics"]["strategic_tactical_diff"] = strat_tact_diff

            if strat_tact_diff > self.consistency_tolerance:
                results["consistent"] = False
                results["violations"].append(
                    f"Strategic-Tactical: {strat_tact_diff:.1%} > {self.consistency_tolerance:.0%}"
                )

        # Tactical vs Operational consistency (if provided)
        if operational_value is not None and tactical_value != 0:
            tact_oper_diff = abs(operational_value - tactical_value) / abs(tactical_value)
            results["metrics"]["tactical_operational_diff"] = tact_oper_diff

            if tact_oper_diff > self.consistency_tolerance:
                results["consistent"] = False
                results["violations"].append(
                    f"Tactical-Operational: {tact_oper_diff:.1%} > {self.consistency_tolerance:.0%}"
                )

        # Record history
        self.consistency_history.append(results)
        if len(self.consistency_history) > 1000:
            self.consistency_history = self.consistency_history[-1000:]

        return results

    def compute_hierarchical_value(
        self,
        decisions_by_level: Dict[str, Dict[str, float]],
        costs_by_level: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Compute total value across hierarchy levels.

        Validates that sum of lower-level decisions matches higher-level plans.
        """
        result = {
            "total_value": 0.0,
            "by_level": {},
            "aggregation_errors": [],
        }

        for level, costs in costs_by_level.items():
            result["by_level"][level] = costs
            result["total_value"] += costs

        # Check aggregation consistency
        # (In a real implementation, this would aggregate operational
        # decisions and compare to tactical plans)

        return result

    def _get_site_for_product(self, product: str) -> Optional[str]:
        """
        Get manufacturing site for product.

        In a real implementation, this would query the product-site mapping.
        """
        # Stub - would need actual mapping
        return None

    def get_consistency_summary(self) -> Dict[str, Any]:
        """Get summary of consistency checks"""
        if not self.consistency_history:
            return {"status": "no_data"}

        consistent_count = sum(1 for h in self.consistency_history if h["consistent"])
        total = len(self.consistency_history)

        # Get metrics from recent history
        recent = self.consistency_history[-100:]
        metrics = {}
        for h in recent:
            for key, val in h.get("metrics", {}).items():
                if key not in metrics:
                    metrics[key] = []
                metrics[key].append(val)

        return {
            "consistency_rate": consistent_count / total,
            "total_checks": total,
            "recent_avg_metrics": {k: np.mean(v) for k, v in metrics.items()},
            "tolerance": self.consistency_tolerance,
        }


class PolicyHierarchy:
    """
    Manages the hierarchy of policies from strategic to execution.

    Maps to Powell's policy class recommendations:
    - Strategic (S&OP): DLA/CFA for policy parameters
    - Tactical (MPS): CFA for tactical parameters
    - Operational (MRP): VFA for real-time decisions
    - Execution: VFA/PFA for immediate decisions
    """

    def __init__(self):
        self.planner = HierarchicalPlanner()

        # Policy parameters by level (θ in Powell's CFA)
        self.policy_params: Dict[str, Dict[str, float]] = {
            "strategic": {},
            "tactical": {},
            "operational": {},
            "execution": {},
        }

    def set_policy_params(self, level: str, params: Dict[str, float]):
        """Set policy parameters for a level"""
        if level not in self.policy_params:
            raise ValueError(f"Unknown level: {level}")
        self.policy_params[level] = params

    def get_effective_params(self, level: str) -> Dict[str, float]:
        """
        Get effective parameters for a level, inheriting from higher levels.

        Lower levels inherit parameters from higher levels unless overridden.
        """
        levels = ["strategic", "tactical", "operational", "execution"]
        level_idx = levels.index(level)

        effective = {}
        for i in range(level_idx + 1):
            effective.update(self.policy_params[levels[i]])

        return effective

    def propagate_constraints_down(
        self,
        strategic_decision: Dict[str, float],
        tactical_period: int
    ) -> TacticalBounds:
        """
        Propagate strategic decisions down to tactical bounds.

        This implements Powell's hierarchical decomposition.
        """
        # Convert strategic decision to tactical bounds
        bounds = TacticalBounds()

        # Example: Strategic production targets become MPS schedule
        for product, target in strategic_decision.items():
            # Spread strategic targets across tactical periods
            # (simplified - real implementation would use demand pattern)
            bounds.production_schedule[product] = [target / 4] * 4

        return bounds

    def aggregate_up(
        self,
        operational_decisions: List[Dict[str, float]],
        aggregation_method: str = "sum"
    ) -> Dict[str, float]:
        """
        Aggregate operational decisions up to tactical level.

        Used for consistency checking and replanning.
        """
        aggregated = {}

        for decision in operational_decisions:
            for product, qty in decision.items():
                if product not in aggregated:
                    aggregated[product] = 0
                if aggregation_method == "sum":
                    aggregated[product] += qty
                elif aggregation_method == "max":
                    aggregated[product] = max(aggregated[product], qty)
                elif aggregation_method == "avg":
                    # Track count for averaging
                    pass

        return aggregated
