from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Dict

@dataclass
class RoleState:
    name: str
    inventory: int
    backlog: int
    inbound_pipe: deque  # shipments on the way to this role
    holding_cost: float
    backlog_cost: float
    target_stock: int
    prod_pipe: Optional[deque] = None  # manufacturer only
    cost_history: List[float] = field(default_factory=list)
    inv_history: List[int] = field(default_factory=list)
    back_history: List[int] = field(default_factory=list)
    order_history: List[int] = field(default_factory=list)
    ship_history: List[int] = field(default_factory=list)

@dataclass
class StepResult:
    shipped: int
    ordered: int
    arrival: int
    finished: int
    inv_next: int
    back_next: int
    cost: float


def step_role(state: RoleState, downstream_demand: int, L_ship: int, L_prod: int = 0):
    """
    Advance one week for a role.
    Returns StepResult, updates state in place.
    """
    # 1. Arrivals land
    arrival = state.inbound_pipe.popleft() if state.inbound_pipe else 0
    state.inventory += arrival

    finished = 0
    if state.prod_pipe is not None:
        finished = state.prod_pipe.popleft()
        state.inventory += finished

    # 2. Observe demand (passed in)
    total_demand = downstream_demand + state.backlog

    # 3. Ship downstream
    shipped = min(state.inventory, total_demand)
    state.inventory -= shipped
    state.backlog = total_demand - shipped

    # 4. Place order upstream (base-stock policy)
    inbound_sum = sum(state.inbound_pipe)
    if state.prod_pipe is not None:
        inbound_sum += sum(state.prod_pipe)

    inventory_position = state.inventory - state.backlog + inbound_sum
    ordered = max(0, state.target_stock - inventory_position)

    # 5. Manufacturer production decision
    if state.prod_pipe is not None:
        state.prod_pipe.append(ordered)  # produce what was ordered

    # 6. Costs
    cost = state.holding_cost * state.inventory + state.backlog_cost * state.backlog

    # 7. Push shipment to downstream's inbound (done outside by orchestrator)
    state.inbound_pipe.append(0)  # placeholder for next cycle alignment

    # 8. Record histories
    state.cost_history.append(cost)
    state.inv_history.append(state.inventory)
    state.back_history.append(state.backlog)
    state.order_history.append(ordered)
    state.ship_history.append(shipped)

    return StepResult(
        shipped=shipped,
        ordered=ordered,
        arrival=arrival,
        finished=finished,
        inv_next=state.inventory,
        back_next=state.backlog,
        cost=cost,
    )


def simulate_beer_game(T: int, demand_series: List[int], L_ship: int = 2, L_prod: int = 2):
    """
    Simulate a 4-role beer game (Retailer, Wholesaler, Distributor, Manufacturer).
    Returns dict of role states after simulation.
    """
    # Initialize roles
    roles = {}
    for role in ["Retailer", "Wholesaler", "Distributor"]:
        roles[role] = RoleState(
            name=role,
            inventory=12,
            backlog=0,
            inbound_pipe=deque([4] * L_ship, maxlen=L_ship),
            holding_cost=0.5,
            backlog_cost=1.0,
            target_stock=15,
        )

    roles["Manufacturer"] = RoleState(
        name="Manufacturer",
        inventory=12,
        backlog=0,
        inbound_pipe=deque([4] * L_ship, maxlen=L_ship),
        holding_cost=0.5,
        backlog_cost=1.0,
        target_stock=15,
        prod_pipe=deque([4] * L_prod, maxlen=L_prod),
    )

    # Demand inputs by role per week
    downstream_orders = {r: [0] * T for r in roles}
    downstream_orders["Retailer"] = demand_series[:]  # exogenous demand

    # Simulation loop
    for t in range(T):
        results = {}
        # Step each role in order: Retailer -> Wholesaler -> Distributor -> Manufacturer
        for role in ["Retailer", "Wholesaler", "Distributor", "Manufacturer"]:
            demand = downstream_orders[role][t]
            res = step_role(roles[role], demand, L_ship, L_prod)
            results[role] = res

        # Commit shipments: upstream shipments move manufacturer -> distributor -> wholesaler -> retailer
        roles["Distributor"].inbound_pipe[-1] = results["Manufacturer"].shipped
        roles["Wholesaler"].inbound_pipe[-1] = results["Distributor"].shipped
        roles["Retailer"].inbound_pipe[-1] = results["Wholesaler"].shipped

        # Commit orders: each role's order is upstream's demand in the same week (retailer -> wholesaler -> distributor -> manufacturer)
        role_order_sequence = ["Retailer", "Wholesaler", "Distributor"]
        for role_name, upstream_role in zip(role_order_sequence, ["Wholesaler", "Distributor", "Manufacturer"]):
            downstream_orders[upstream_role][t] = results[role_name].ordered

    return roles


if __name__ == "__main__":
    # Example demand series: 4 for 4 weeks, then 8
    demand_series = [4] * 4 + [8] * 10
    roles = simulate_beer_game(T=len(demand_series), demand_series=demand_series)

    # Print summary
    for role, state in roles.items():
        print(f"=== {role} ===")
        print("Total cost:", sum(state.cost_history))
        print("Orders:", state.order_history)
        print("Shipments:", state.ship_history)
        print()
