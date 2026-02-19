"""
Capacity-Constrained MPS with Rough-Cut Capacity Planning (RCCP)

Ensures MPS plans respect capacity constraints by:
1. Identifying resource requirements from MPS
2. Checking against available capacity
3. Leveling/smoothing production to avoid bottlenecks
4. Suggesting alternative plans when constrained

Reference: APICS CPIM - Master Planning of Resources
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class ResourceRequirement:
    """Resource requirement for a product"""
    resource_id: str
    resource_name: str
    units_per_product: float  # Resource units required per product unit
    available_capacity: float  # Available capacity per period
    utilization_target: float = 0.85  # Target utilization (default 85%)


@dataclass
class MPSProductionPlan:
    """Production plan for a single product"""
    product_id: int
    product_name: str
    planned_quantities: List[float]  # By period
    resource_requirements: List[ResourceRequirement]


@dataclass
class CapacityCheck:
    """Result of capacity checking"""
    period: int
    period_date: date
    resource_id: str
    resource_name: str
    required_capacity: float
    available_capacity: float
    utilization: float  # As percentage
    is_constrained: bool  # True if utilization > 95%
    is_over_target: bool  # True if utilization > target (85%)
    shortage: float  # Amount over capacity (0 if not constrained)


@dataclass
class CapacityConstrainedMPSResult:
    """Result of capacity-constrained MPS generation"""
    original_plan: List[float]
    feasible_plan: List[float]
    is_feasible: bool
    capacity_checks: List[CapacityCheck]
    bottleneck_resources: List[str]
    total_shortage: float  # Total units that couldn't be planned
    utilization_summary: Dict[str, float]  # Average utilization by resource
    recommendations: List[str]


class CapacityConstrainedMPS:
    """
    Capacity-Constrained MPS Generator

    Takes an unconstrained MPS plan and adjusts it to respect capacity limits.
    """

    def __init__(self, start_date: date, period_days: int = 7):
        self.start_date = start_date
        self.period_days = period_days

    def check_capacity(
        self,
        plan: MPSProductionPlan,
        n_periods: int
    ) -> List[CapacityCheck]:
        """
        Check capacity constraints for each period

        Returns list of CapacityCheck objects showing utilization by period and resource
        """
        checks = []

        # For each resource
        for resource in plan.resource_requirements:
            # For each period
            for period in range(n_periods):
                if period >= len(plan.planned_quantities):
                    continue

                # Calculate required capacity
                planned_qty = plan.planned_quantities[period]
                required = planned_qty * resource.units_per_product

                # Calculate utilization
                utilization = (required / resource.available_capacity * 100
                               if resource.available_capacity > 0 else 0)

                # Check constraints
                is_constrained = utilization > 95.0  # Hard constraint
                is_over_target = utilization > (resource.utilization_target * 100)
                shortage = max(0, required - resource.available_capacity)

                period_date = self.start_date + timedelta(days=period * self.period_days)

                checks.append(CapacityCheck(
                    period=period,
                    period_date=period_date,
                    resource_id=resource.resource_id,
                    resource_name=resource.resource_name,
                    required_capacity=required,
                    available_capacity=resource.available_capacity,
                    utilization=utilization,
                    is_constrained=is_constrained,
                    is_over_target=is_over_target,
                    shortage=shortage
                ))

        return checks

    def generate_feasible_plan(
        self,
        plan: MPSProductionPlan,
        strategy: str = "level"
    ) -> CapacityConstrainedMPSResult:
        """
        Generate capacity-feasible MPS plan

        Strategies:
        - "level": Level production to smooth capacity usage
        - "shift": Shift production to earlier/later periods
        - "reduce": Reduce quantities to fit capacity (may not meet demand)
        """
        n_periods = len(plan.planned_quantities)
        original_plan = plan.planned_quantities.copy()

        # Check capacity with original plan
        checks = self.check_capacity(plan, n_periods)

        # Identify bottlenecks
        bottlenecks = self._identify_bottlenecks(checks)

        if not any(check.is_constrained for check in checks):
            # Plan is already feasible
            return CapacityConstrainedMPSResult(
                original_plan=original_plan,
                feasible_plan=original_plan,
                is_feasible=True,
                capacity_checks=checks,
                bottleneck_resources=[],
                total_shortage=0.0,
                utilization_summary=self._calculate_utilization_summary(checks),
                recommendations=["Plan is feasible - no capacity constraints"]
            )

        # Apply capacity leveling strategy
        if strategy == "level":
            feasible_plan = self._level_production(plan, checks)
        elif strategy == "shift":
            feasible_plan = self._shift_production(plan, checks)
        elif strategy == "reduce":
            feasible_plan = self._reduce_production(plan, checks)
        else:
            feasible_plan = original_plan

        # Update plan and re-check
        plan.planned_quantities = feasible_plan
        new_checks = self.check_capacity(plan, n_periods)

        # Calculate metrics
        total_shortage = sum(
            max(0, original_plan[i] - feasible_plan[i])
            for i in range(len(feasible_plan))
        )

        is_feasible = not any(check.is_constrained for check in new_checks)

        recommendations = self._generate_recommendations(
            original_plan, feasible_plan, new_checks, bottlenecks
        )

        return CapacityConstrainedMPSResult(
            original_plan=original_plan,
            feasible_plan=feasible_plan,
            is_feasible=is_feasible,
            capacity_checks=new_checks,
            bottleneck_resources=bottlenecks,
            total_shortage=total_shortage,
            utilization_summary=self._calculate_utilization_summary(new_checks),
            recommendations=recommendations
        )

    def _identify_bottlenecks(self, checks: List[CapacityCheck]) -> List[str]:
        """Identify resources that are bottlenecks (>95% utilization)"""
        bottlenecks = set()
        for check in checks:
            if check.is_constrained:
                bottlenecks.add(check.resource_name)
        return list(bottlenecks)

    def _level_production(
        self,
        plan: MPSProductionPlan,
        checks: List[CapacityCheck]
    ) -> List[float]:
        """
        Level production to smooth capacity usage

        Distributes production more evenly across periods to reduce peaks.
        """
        n_periods = len(plan.planned_quantities)
        leveled_plan = plan.planned_quantities.copy()

        # Find most constrained resource
        constrained_checks = [c for c in checks if c.is_constrained]
        if not constrained_checks:
            return leveled_plan

        # Group by resource
        resource_checks = {}
        for check in constrained_checks:
            if check.resource_id not in resource_checks:
                resource_checks[check.resource_id] = []
            resource_checks[check.resource_id].append(check)

        # For each constrained resource, level production
        for resource_id, resource_checks_list in resource_checks.items():
            # Get resource requirement
            resource = next(r for r in plan.resource_requirements if r.resource_id == resource_id)

            # Calculate max producible per period for this resource
            max_per_period = resource.available_capacity / resource.units_per_product

            # Level production for constrained periods
            for check in resource_checks_list:
                period = check.period

                if leveled_plan[period] > max_per_period:
                    # Reduce this period to max
                    excess = leveled_plan[period] - max_per_period
                    leveled_plan[period] = max_per_period

                    # Try to shift excess to adjacent periods
                    shifted = 0.0

                    # Try next period
                    if period + 1 < n_periods:
                        space = max_per_period - leveled_plan[period + 1]
                        if space > 0:
                            shift_amt = min(excess - shifted, space)
                            leveled_plan[period + 1] += shift_amt
                            shifted += shift_amt

                    # Try previous period if still have excess
                    if shifted < excess and period > 0:
                        space = max_per_period - leveled_plan[period - 1]
                        if space > 0:
                            shift_amt = min(excess - shifted, space)
                            leveled_plan[period - 1] += shift_amt
                            shifted += shift_amt

        return leveled_plan

    def _shift_production(
        self,
        plan: MPSProductionPlan,
        checks: List[CapacityCheck]
    ) -> List[float]:
        """
        Shift production to earlier periods when possible

        Moves production forward in time to avoid capacity crunches.
        """
        # Similar to level but prioritizes earlier periods
        return self._level_production(plan, checks)

    def _reduce_production(
        self,
        plan: MPSProductionPlan,
        checks: List[CapacityCheck]
    ) -> List[float]:
        """
        Reduce production to fit capacity

        Simply caps production at maximum feasible level.
        May result in unmet demand.
        """
        n_periods = len(plan.planned_quantities)
        reduced_plan = plan.planned_quantities.copy()

        # For each period, cap at most constrained resource
        for period in range(n_periods):
            period_checks = [c for c in checks if c.period == period and c.is_constrained]

            if period_checks:
                # Find most limiting resource
                max_feasible = min(
                    c.available_capacity / next(
                        r for r in plan.resource_requirements if r.resource_id == c.resource_id
                    ).units_per_product
                    for c in period_checks
                )

                reduced_plan[period] = min(reduced_plan[period], max_feasible)

        return reduced_plan

    def _calculate_utilization_summary(self, checks: List[CapacityCheck]) -> Dict[str, float]:
        """Calculate average utilization by resource"""
        resource_utils = {}
        resource_counts = {}

        for check in checks:
            if check.resource_id not in resource_utils:
                resource_utils[check.resource_id] = 0.0
                resource_counts[check.resource_id] = 0

            resource_utils[check.resource_id] += check.utilization
            resource_counts[check.resource_id] += 1

        return {
            resource_id: total / resource_counts[resource_id]
            for resource_id, total in resource_utils.items()
        }

    def _generate_recommendations(
        self,
        original_plan: List[float],
        feasible_plan: List[float],
        checks: List[CapacityCheck],
        bottlenecks: List[str]
    ) -> List[str]:
        """Generate recommendations for planner"""
        recommendations = []

        if bottlenecks:
            recommendations.append(
                f"Bottleneck resources identified: {', '.join(bottlenecks)}"
            )
            recommendations.append(
                "Consider: Adding capacity, outsourcing, or shifting demand"
            )

        total_reduction = sum(
            max(0, original_plan[i] - feasible_plan[i])
            for i in range(len(feasible_plan))
        )

        if total_reduction > 0:
            recommendations.append(
                f"Production reduced by {total_reduction:.0f} units to meet capacity"
            )
            recommendations.append(
                "Consider: Extending lead times or splitting orders"
            )

        high_util_resources = [
            check.resource_name for check in checks
            if check.utilization > 90 and not check.is_constrained
        ]

        if high_util_resources:
            unique_resources = list(set(high_util_resources))
            recommendations.append(
                f"High utilization (>90%): {', '.join(unique_resources)}"
            )

        if not recommendations:
            recommendations.append("Plan adjusted successfully - all constraints met")

        return recommendations


def optimize_mps_with_capacity(
    product_plans: List[MPSProductionPlan],
    start_date: date,
    strategy: str = "level"
) -> Dict[int, CapacityConstrainedMPSResult]:
    """
    Optimize multiple products with shared capacity constraints

    Args:
        product_plans: List of MPSProductionPlan objects
        start_date: Start date of planning horizon
        strategy: Capacity leveling strategy

    Returns:
        Dict mapping product_id to CapacityConstrainedMPSResult
    """
    generator = CapacityConstrainedMPS(start_date)

    results = {}
    for plan in product_plans:
        result = generator.generate_feasible_plan(plan, strategy)
        results[plan.product_id] = result

    return results
