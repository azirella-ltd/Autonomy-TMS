"""
Lot Sizing Algorithms for MPS/MRP

Implements 5 classical lot sizing techniques:
1. EOQ (Economic Order Quantity) - Wilson's formula
2. POQ (Period Order Quantity) - EOQ adapted for discrete periods
3. LFL (Lot-for-Lot) - Exact demand matching
4. FOQ (Fixed Order Quantity) - Fixed batch size
5. PPB (Part Period Balancing) - Trade-off between setup and holding costs

Reference: APICS Dictionary, 16th Edition
Reference: Silver, Pyke, Thomas - Inventory and Production Management in Supply Chains
"""

import math
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class LotSizingInput:
    """Input parameters for lot sizing calculation"""
    demand_schedule: List[float]  # Demand by period
    start_date: date
    period_days: int = 7  # Days per period (weekly buckets)

    # Cost parameters
    setup_cost: float = 0.0  # Fixed cost per order/setup (K)
    holding_cost_per_unit_per_period: float = 0.0  # (h)
    unit_cost: float = 0.0  # Cost per unit (c)

    # Constraints
    min_order_quantity: Optional[float] = None  # MOQ
    max_order_quantity: Optional[float] = None  # Max capacity
    order_multiple: Optional[float] = None  # Must order in multiples

    # For POQ calculation
    annual_demand: Optional[float] = None  # D (for EOQ calculation)


@dataclass
class LotSizingResult:
    """Result of lot sizing calculation"""
    algorithm: str
    order_schedule: List[float]  # Order quantities by period
    total_cost: float
    setup_cost_total: float
    holding_cost_total: float
    number_of_orders: int
    average_inventory: float

    # Metrics
    service_level: float = 1.0  # % of demand met
    inventory_turns: Optional[float] = None

    # Details for UI
    details: Dict = None


class LotSizingAlgorithm:
    """Base class for lot sizing algorithms"""

    def __init__(self, inputs: LotSizingInput):
        self.inputs = inputs
        self.n_periods = len(inputs.demand_schedule)

    def calculate(self) -> LotSizingResult:
        """Calculate lot sizes - to be implemented by subclasses"""
        raise NotImplementedError

    def apply_constraints(self, quantity: float) -> float:
        """Apply MOQ, max quantity, and order multiple constraints"""
        # Apply order multiple
        if self.inputs.order_multiple and self.inputs.order_multiple > 0:
            quantity = math.ceil(quantity / self.inputs.order_multiple) * self.inputs.order_multiple

        # Apply MOQ
        if self.inputs.min_order_quantity and quantity > 0:
            quantity = max(quantity, self.inputs.min_order_quantity)

        # Apply max quantity
        if self.inputs.max_order_quantity:
            quantity = min(quantity, self.inputs.max_order_quantity)

        return quantity

    def calculate_costs(self, order_schedule: List[float]) -> Tuple[float, float, float]:
        """
        Calculate total costs for a given order schedule

        Returns: (total_cost, setup_cost, holding_cost)
        """
        setup_cost_total = 0.0
        holding_cost_total = 0.0
        inventory = 0.0

        for period in range(self.n_periods):
            # Order received at start of period
            if order_schedule[period] > 0:
                setup_cost_total += self.inputs.setup_cost
                inventory += order_schedule[period]

            # Demand consumed at end of period
            demand = self.inputs.demand_schedule[period]

            # Average inventory during period (before demand)
            avg_inventory = inventory - (demand / 2)
            if avg_inventory > 0:
                holding_cost_total += avg_inventory * self.inputs.holding_cost_per_unit_per_period

            # Update inventory
            inventory -= demand

        total_cost = setup_cost_total + holding_cost_total
        return total_cost, setup_cost_total, holding_cost_total


class LotForLot(LotSizingAlgorithm):
    """
    Lot-for-Lot (LFL) - Period-by-period exact demand matching

    Order exactly what is needed each period.
    Minimizes inventory holding cost but maximizes setup cost.
    """

    def calculate(self) -> LotSizingResult:
        order_schedule = []

        for demand in self.inputs.demand_schedule:
            if demand > 0:
                order_qty = self.apply_constraints(demand)
            else:
                order_qty = 0.0
            order_schedule.append(order_qty)

        total_cost, setup_cost, holding_cost = self.calculate_costs(order_schedule)
        num_orders = sum(1 for qty in order_schedule if qty > 0)
        avg_inventory = sum(order_schedule) / self.n_periods if self.n_periods > 0 else 0

        return LotSizingResult(
            algorithm="LFL",
            order_schedule=order_schedule,
            total_cost=total_cost,
            setup_cost_total=setup_cost,
            holding_cost_total=holding_cost,
            number_of_orders=num_orders,
            average_inventory=avg_inventory,
            details={"description": "Lot-for-Lot: Order exact demand each period"}
        )


class EconomicOrderQuantity(LotSizingAlgorithm):
    """
    Economic Order Quantity (EOQ) - Wilson's formula

    EOQ = sqrt(2 * D * K / h)

    Where:
    - D = annual demand
    - K = setup cost per order
    - h = holding cost per unit per year
    """

    def calculate(self) -> LotSizingResult:
        # Calculate EOQ
        if not self.inputs.annual_demand:
            # Estimate annual demand from schedule
            total_demand = sum(self.inputs.demand_schedule)
            periods_per_year = 365 / self.inputs.period_days
            annual_demand = total_demand * (periods_per_year / self.n_periods)
        else:
            annual_demand = self.inputs.annual_demand

        # Convert period holding cost to annual
        periods_per_year = 365 / self.inputs.period_days
        annual_holding_cost = self.inputs.holding_cost_per_unit_per_period * periods_per_year

        if annual_holding_cost <= 0 or self.inputs.setup_cost <= 0:
            # Fallback to LFL if costs not provided
            return LotForLot(self.inputs).calculate()

        # EOQ formula
        eoq = math.sqrt((2 * annual_demand * self.inputs.setup_cost) / annual_holding_cost)
        eoq = self.apply_constraints(eoq)

        # Generate order schedule
        order_schedule = []
        inventory = 0.0

        for demand in self.inputs.demand_schedule:
            if inventory < demand:
                # Need to order
                order_qty = eoq
            else:
                order_qty = 0.0

            order_schedule.append(order_qty)
            inventory += order_qty - demand

        total_cost, setup_cost, holding_cost = self.calculate_costs(order_schedule)
        num_orders = sum(1 for qty in order_schedule if qty > 0)
        avg_inventory = sum(order_schedule) / self.n_periods if self.n_periods > 0 else 0

        return LotSizingResult(
            algorithm="EOQ",
            order_schedule=order_schedule,
            total_cost=total_cost,
            setup_cost_total=setup_cost,
            holding_cost_total=holding_cost,
            number_of_orders=num_orders,
            average_inventory=avg_inventory,
            details={
                "description": "Economic Order Quantity (Wilson's formula)",
                "eoq": eoq,
                "annual_demand": annual_demand
            }
        )


class PeriodOrderQuantity(LotSizingAlgorithm):
    """
    Period Order Quantity (POQ) - EOQ adapted for discrete periods

    POQ = EOQ / Average_Period_Demand
    Order to cover POQ periods of demand
    """

    def calculate(self) -> LotSizingResult:
        # First calculate EOQ
        eoq_result = EconomicOrderQuantity(self.inputs).calculate()
        eoq = eoq_result.details.get("eoq", 0)

        # Calculate average period demand
        avg_period_demand = sum(self.inputs.demand_schedule) / self.n_periods if self.n_periods > 0 else 0

        if avg_period_demand <= 0:
            return LotForLot(self.inputs).calculate()

        # POQ in periods
        poq_periods = max(1, round(eoq / avg_period_demand))

        # Generate order schedule
        order_schedule = []
        inventory = 0.0
        periods_since_order = poq_periods  # Trigger order in first period

        for period, demand in enumerate(self.inputs.demand_schedule):
            if periods_since_order >= poq_periods or inventory < demand:
                # Order for next POQ periods
                future_demand = sum(self.inputs.demand_schedule[period:period + poq_periods])
                order_qty = self.apply_constraints(future_demand)
                periods_since_order = 0
            else:
                order_qty = 0.0

            order_schedule.append(order_qty)
            inventory += order_qty - demand
            periods_since_order += 1

        total_cost, setup_cost, holding_cost = self.calculate_costs(order_schedule)
        num_orders = sum(1 for qty in order_schedule if qty > 0)
        avg_inventory = sum(order_schedule) / self.n_periods if self.n_periods > 0 else 0

        return LotSizingResult(
            algorithm="POQ",
            order_schedule=order_schedule,
            total_cost=total_cost,
            setup_cost_total=setup_cost,
            holding_cost_total=holding_cost,
            number_of_orders=num_orders,
            average_inventory=avg_inventory,
            details={
                "description": f"Period Order Quantity: Order every {poq_periods} periods",
                "poq_periods": poq_periods,
                "eoq": eoq,
                "avg_period_demand": avg_period_demand
            }
        )


class FixedOrderQuantity(LotSizingAlgorithm):
    """
    Fixed Order Quantity (FOQ) - Fixed batch size

    Order a predetermined fixed quantity whenever inventory falls below reorder point.
    """

    def __init__(self, inputs: LotSizingInput, fixed_quantity: float):
        super().__init__(inputs)
        self.fixed_quantity = fixed_quantity

    def calculate(self) -> LotSizingResult:
        order_schedule = []
        inventory = 0.0

        for demand in self.inputs.demand_schedule:
            if inventory < demand:
                # Need to order
                order_qty = self.apply_constraints(self.fixed_quantity)
            else:
                order_qty = 0.0

            order_schedule.append(order_qty)
            inventory += order_qty - demand

        total_cost, setup_cost, holding_cost = self.calculate_costs(order_schedule)
        num_orders = sum(1 for qty in order_schedule if qty > 0)
        avg_inventory = sum(order_schedule) / self.n_periods if self.n_periods > 0 else 0

        return LotSizingResult(
            algorithm="FOQ",
            order_schedule=order_schedule,
            total_cost=total_cost,
            setup_cost_total=setup_cost,
            holding_cost_total=holding_cost,
            number_of_orders=num_orders,
            average_inventory=avg_inventory,
            details={
                "description": f"Fixed Order Quantity: {self.fixed_quantity} units per order",
                "fixed_quantity": self.fixed_quantity
            }
        )


class PartPeriodBalancing(LotSizingAlgorithm):
    """
    Part Period Balancing (PPB) - Minimize total cost

    Balances setup cost against holding cost by calculating part-periods.
    A part-period is one unit held for one period.

    Target: Setup cost / Holding cost per unit per period = Accumulated part-periods
    """

    def calculate(self) -> LotSizingResult:
        if self.inputs.holding_cost_per_unit_per_period <= 0:
            return LotForLot(self.inputs).calculate()

        # Economic Part Period (EPP)
        epp = self.inputs.setup_cost / self.inputs.holding_cost_per_unit_per_period

        order_schedule = []
        period = 0

        while period < self.n_periods:
            # Start a new order
            order_qty = self.inputs.demand_schedule[period]
            part_periods = 0.0
            periods_covered = 1

            # Look ahead and add demand if it reduces total cost
            for future_period in range(period + 1, self.n_periods):
                future_demand = self.inputs.demand_schedule[future_period]
                periods_ahead = future_period - period

                # Part-periods for this future demand
                new_part_periods = future_demand * periods_ahead
                total_part_periods = part_periods + new_part_periods

                # If adding this demand keeps us under EPP, add it
                if total_part_periods <= epp:
                    order_qty += future_demand
                    part_periods = total_part_periods
                    periods_covered += 1
                else:
                    # Stop here
                    break

            # Apply constraints
            order_qty = self.apply_constraints(order_qty)

            # Place order in current period
            order_schedule.append(order_qty)

            # Fill periods covered with 0 (demand already covered by this order)
            for _ in range(1, periods_covered):
                if len(order_schedule) < self.n_periods:
                    order_schedule.append(0.0)

            period += periods_covered

        # Ensure list is correct length
        while len(order_schedule) < self.n_periods:
            order_schedule.append(0.0)

        total_cost, setup_cost, holding_cost = self.calculate_costs(order_schedule)
        num_orders = sum(1 for qty in order_schedule if qty > 0)
        avg_inventory = sum(order_schedule) / self.n_periods if self.n_periods > 0 else 0

        return LotSizingResult(
            algorithm="PPB",
            order_schedule=order_schedule,
            total_cost=total_cost,
            setup_cost_total=setup_cost,
            holding_cost_total=holding_cost,
            number_of_orders=num_orders,
            average_inventory=avg_inventory,
            details={
                "description": "Part Period Balancing: Minimize setup vs holding costs",
                "epp": epp,
                "setup_cost": self.inputs.setup_cost,
                "holding_cost": self.inputs.holding_cost_per_unit_per_period
            }
        )


# Factory function
def calculate_lot_size(inputs: LotSizingInput, algorithm: str = "EOQ", **kwargs) -> LotSizingResult:
    """
    Calculate lot sizes using specified algorithm

    Args:
        inputs: LotSizingInput parameters
        algorithm: One of "LFL", "EOQ", "POQ", "FOQ", "PPB"
        **kwargs: Algorithm-specific parameters (e.g., fixed_quantity for FOQ)

    Returns:
        LotSizingResult with order schedule and cost breakdown
    """
    algorithm = algorithm.upper()

    if algorithm == "LFL":
        return LotForLot(inputs).calculate()
    elif algorithm == "EOQ":
        return EconomicOrderQuantity(inputs).calculate()
    elif algorithm == "POQ":
        return PeriodOrderQuantity(inputs).calculate()
    elif algorithm == "FOQ":
        fixed_quantity = kwargs.get("fixed_quantity", 1000)
        return FixedOrderQuantity(inputs, fixed_quantity).calculate()
    elif algorithm == "PPB":
        return PartPeriodBalancing(inputs).calculate()
    else:
        raise ValueError(f"Unknown lot sizing algorithm: {algorithm}")


def compare_algorithms(inputs: LotSizingInput, algorithms: List[str] = None) -> Dict[str, LotSizingResult]:
    """
    Compare multiple lot sizing algorithms

    Args:
        inputs: LotSizingInput parameters
        algorithms: List of algorithm names (default: all 5)

    Returns:
        Dict mapping algorithm name to LotSizingResult
    """
    if algorithms is None:
        algorithms = ["LFL", "EOQ", "POQ", "FOQ", "PPB"]

    results = {}
    for algo in algorithms:
        if algo == "FOQ":
            # Use EOQ as the fixed quantity
            eoq_result = EconomicOrderQuantity(inputs).calculate()
            eoq = eoq_result.details.get("eoq", 1000)
            results[algo] = calculate_lot_size(inputs, algo, fixed_quantity=eoq)
        else:
            results[algo] = calculate_lot_size(inputs, algo)

    return results


def get_best_algorithm(inputs: LotSizingInput) -> Tuple[str, LotSizingResult]:
    """
    Find the algorithm with lowest total cost

    Returns:
        (algorithm_name, result)
    """
    results = compare_algorithms(inputs)

    best_algo = min(results.items(), key=lambda x: x[1].total_cost)
    return best_algo
