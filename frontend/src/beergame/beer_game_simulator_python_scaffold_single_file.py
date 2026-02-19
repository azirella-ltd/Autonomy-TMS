from __future__ import annotations

"""
Beer Game (Classic 4‑echelon) — Deterministic, Policy‑pluggable Simulator

Roles (downstream→upstream): Retailer → Wholesaler → Distributor → Manufacturer

Key design decisions (aligns with your spec):
- Discrete weeks t = 0..T-1
- Shipping lead time L_ship (FIFO pipeline per arc)
- Manufacturer production lead time L_prod (FIFO production pipeline)
- Information timing: in week t, each upstream role treats the downstream role’s
  order O_t as its demand for week t. We process roles from downstream to upstream
  within the same week to avoid circularity. Physical flows still obey lead times.
- Costs (per role, per week, end-of-week assessment):
    holding: h * I_{t+1}
    backlog: p * B_{t+1}
- Backlog is accumulated (no lost sales).

This file provides:
- Dataclasses for parameters, role state, per-week logs
- A BasePolicy protocol and a BaseStockPolicy implementation
- A Simulator to run T weeks, with clean two-phase commit for shipments/orders
- A minimal example run in __main__ (no external dependencies)

You can extend with: order/production costs, capacities, stochastic demand, etc.
"""

from dataclasses import dataclass, field, asdict
from collections import deque
from typing import Deque, List, Dict, Optional, Protocol, Tuple

# -------------------------------
# Parameters & Policy Interfaces
# -------------------------------

@dataclass
class RoleParams:
    name: str
    L_ship: int = 2
    h: float = 0.5  # holding cost per unit-week
    p: float = 1.0  # backlog cost per unit-week
    # Manufacturer-only
    L_prod: int = 0  # 0 for non-manufacturer; >0 enables production pipeline


class BasePolicy(Protocol):
    """Policy must implement order (and optionally production for Manufacturer)."""
    def order(self, *, I_prime: int, B_next: int, inbound_pipeline_sum: int, 
              role: "RoleState", week: int) -> int:
        ...

    def produce(self, *, O_t: int, role: "RoleState", week: int) -> int:
        """Manufacturer-only hook. Default: produce exactly O_t."""
        return O_t


@dataclass
class BaseStockPolicy:
    """Order-up-to S policy (same math as spec)."""
    S: int  # target inventory position

    def order(self, *, I_prime: int, B_next: int, inbound_pipeline_sum: int,
              role: "RoleState", week: int) -> int:
        # Inventory position counts stock after shipping, minus backlog to cover,
        # plus what is already inbound to me (sum of my inbound pipeline).
        IP_t = I_prime - B_next + inbound_pipeline_sum
        O_t = max(0, self.S - IP_t)
        return int(O_t)

    def produce(self, *, O_t: int, role: "RoleState", week: int) -> int:
        return int(O_t)


# -------------------------------
# State, Logs, and Role container
# -------------------------------

@dataclass
class RoleState:
    params: RoleParams
    policy: BasePolicy
    I: int  # on-hand inventory at start of current week
    B: int  # backlog at start of current week
    inbound_pipe: Deque[int] = field(default_factory=deque)  # length L_ship
    # Manufacturer-only production pipeline (finished goods arrive after L_prod weeks)
    prod_pipe: Optional[Deque[int]] = None  # length L_prod if Manufacturer else None

    # Staged (computed during the decision pass in a week)
    staged_S_t: int = 0  # shipment to send downstream
    staged_O_t: int = 0  # order to place upstream
    staged_M_t: int = 0  # production start (Manufacturer only)
    last_A_t: int = 0    # arrival this week from upstream
    last_F_t: int = 0    # finished goods arrival this week (Manufacturer only)

    def ensure_pipes(self):
        # Guarantee pipe lengths match parameters (for safety)
        Ls = self.params.L_ship
        while len(self.inbound_pipe) < Ls:
            self.inbound_pipe.append(0)
        while len(self.inbound_pipe) > Ls and Ls >= 0:
            self.inbound_pipe.popleft()
        if self.params.L_prod > 0:
            if self.prod_pipe is None:
                self.prod_pipe = deque([0]*self.params.L_prod)
            while len(self.prod_pipe) < self.params.L_prod:
                self.prod_pipe.append(0)
            while len(self.prod_pipe) > self.params.L_prod and self.params.L_prod >= 0:
                self.prod_pipe.popleft()


@dataclass
class WeekLog:
    week: int
    A_t: Dict[str, int]
    F_t: Dict[str, int]
    demand: Dict[str, int]
    ship_S: Dict[str, int]
    order_O: Dict[str, int]
    prod_M: Dict[str, int]
    I_end: Dict[str, int]
    B_end: Dict[str, int]
    holding_cost: Dict[str, float]
    backlog_cost: Dict[str, float]
    total_cost: Dict[str, float]


# -------------------------------
# Simulator
# -------------------------------

class BeerGameSimulator:
    def __init__(self,
                 retailer: RoleState,
                 wholesaler: RoleState,
                 distributor: RoleState,
                 manufacturer: RoleState,
                 demand_series: List[int],  # exogenous demand at retailer per week
                 T: Optional[int] = None):
        self.roles: List[RoleState] = [retailer, wholesaler, distributor, manufacturer]
        self.names = [r.params.name for r in self.roles]
        for r in self.roles:
            r.ensure_pipes()
        self.demand_series = demand_series
        self.T = T if T is not None else len(demand_series)
        assert self.T <= len(demand_series), "T cannot exceed length of demand series"

        # Cost trackers
        self.costs: Dict[str, float] = {r.params.name: 0.0 for r in self.roles}
        self.logs: List[WeekLog] = []

    def run(self):
        # Convenience names
        retailer, wholesaler, distributor, manufacturer = self.roles

        for t in range(self.T):
            # 1) Arrivals (pop from pipelines) — done for all roles independently
            A_map: Dict[str, int] = {}
            F_map: Dict[str, int] = {}
            for role in self.roles:
                role.ensure_pipes()
                # Shipment arrival from upstream
                A_t = role.inbound_pipe.popleft() if role.params.L_ship > 0 else 0
                role.I += A_t
                role.last_A_t = A_t
                A_map[role.params.name] = A_t

                # Manufacturer finished goods arrival
                F_t = 0
                if role.params.L_prod > 0 and role.prod_pipe is not None:
                    F_t = role.prod_pipe.popleft()
                    role.I += F_t
                    role.last_F_t = F_t
                F_map[role.params.name] = F_t

            # 2) Decision pass (downstream → upstream) to avoid simultaneity
            # Determine each role's downstream demand for THIS week
            demand_map: Dict[str, int] = {}
            ship_S: Dict[str, int] = {}
            order_O: Dict[str, int] = {}
            prod_M: Dict[str, int] = {}
            I_end: Dict[str, int] = {}
            B_end: Dict[str, int] = {}
            H_cost: Dict[str, float] = {}
            B_cost: Dict[str, float] = {}
            T_cost: Dict[str, float] = {}

            # Helper to compute one role's step
            def step_role(role: RoleState, downstream_demand: int):
                # Total demand to satisfy = new demand + existing backlog
                TOTDEM = downstream_demand + role.B
                # Ship what you can
                S_t = min(role.I, TOTDEM)
                I_prime = role.I - S_t
                B_next = TOTDEM - S_t

                # Policy decides order now (inventory position uses inbound-to-me pipeline)
                inbound_sum = sum(role.inbound_pipe) if role.params.L_ship > 0 else 0
                O_t = max(0, role.policy.order(I_prime=I_prime, B_next=B_next,
                                               inbound_pipeline_sum=inbound_sum,
                                               role=role, week=t))
                M_t = 0
                if role.params.L_prod > 0:
                    # Manufacturer production decision
                    M_t = max(0, role.policy.produce(O_t=O_t, role=role, week=t))

                # Stage decisions (commit later)
                role.staged_S_t = int(S_t)
                role.staged_O_t = int(O_t)
                role.staged_M_t = int(M_t)

                # End-of-week inventory & backlog after shipping (before new arrivals next week)
                I_next = I_prime
                B_next_final = B_next

                # Costs
                h, p = role.params.h, role.params.p
                hold_c = h * I_next
                back_c = p * B_next_final
                total_c = hold_c + back_c

                # Update state for next week
                role.I = I_next
                role.B = B_next_final

                # Track per-role maps
                demand_map[role.params.name] = int(downstream_demand)
                ship_S[role.params.name] = role.staged_S_t
                order_O[role.params.name] = role.staged_O_t
                prod_M[role.params.name] = role.staged_M_t
                I_end[role.params.name] = role.I
                B_end[role.params.name] = role.B
                H_cost[role.params.name] = hold_c
                B_cost[role.params.name] = back_c
                T_cost[role.params.name] = total_c

                # Accumulate costs
                self.costs[role.params.name] += total_c

            # Retailer demand is exogenous
            R_dem = int(self.demand_series[t])
            step_role(retailer, R_dem)

            # Upstream roles see downstream order from THIS week
            step_role(wholesaler, retailer.staged_O_t)
            step_role(distributor, wholesaler.staged_O_t)
            step_role(manufacturer, distributor.staged_O_t)

            # 3) Commit physical flows (shipments move manufacturer → distributor → wholesaler → retailer)
            # Shipments sent now will arrive to downstream after L_ship weeks → append to downstream's inbound queue
            def append_to_inbound(downstream: RoleState, qty: int):
                if downstream.params.L_ship > 0:
                    downstream.inbound_pipe.append(int(qty))

            append_to_inbound(distributor, manufacturer.staged_S_t)    # Manufacturer → Distributor
            append_to_inbound(wholesaler, distributor.staged_S_t)      # Distributor → Wholesaler
            append_to_inbound(retailer, wholesaler.staged_S_t)         # Wholesaler → Retailer

            # Manufacturer production pushed into production pipeline
            if manufacturer.params.L_prod > 0 and manufacturer.prod_pipe is not None:
                manufacturer.prod_pipe.append(manufacturer.staged_M_t)

            # 4) Log
            self.logs.append(WeekLog(
                week=t,
                A_t=A_map,
                F_t=F_map,
                demand=demand_map,
                ship_S=ship_S,
                order_O=order_O,
                prod_M=prod_M,
                I_end=I_end,
                B_end=B_end,
                holding_cost=H_cost,
                backlog_cost=B_cost,
                total_cost=T_cost,
            ))

    # --------- Convenience getters ---------
    def cumulative_costs(self) -> Dict[str, float]:
        return dict(self.costs)

    def kpi_summary(self) -> Dict[str, Dict[str, float]]:
        summary: Dict[str, Dict[str, float]] = {}
        for role in self.roles:
            name = role.params.name
            total_hold = sum(log.holding_cost[name] for log in self.logs)
            total_back = sum(log.backlog_cost[name] for log in self.logs)
            total_cost = sum(log.total_cost[name] for log in self.logs)
            total_demand = sum(log.demand[name] for log in self.logs)
            total_shipped = sum(log.ship_S[name] for log in self.logs)
            service_level = (total_shipped / total_demand) if total_demand > 0 else 1.0
            summary[name] = {
                "total_holding_cost": total_hold,
                "total_backlog_cost": total_back,
                "total_cost": total_cost,
                "service_level": service_level,
            }
        # System totals
        system = {
            "total_holding_cost": sum(s["total_holding_cost"] for s in summary.values()),
            "total_backlog_cost": sum(s["total_backlog_cost"] for s in summary.values()),
            "total_cost": sum(s["total_cost"] for s in summary.values()),
        }
        summary["SYSTEM"] = system
        return summary


# -------------------------------
# Example usage
# -------------------------------

def make_default_roles(S_target: int = 15,
                       L_ship: int = 2,
                       L_prod_manufacturer: int = 2,
                       init_I: int = 12,
                       init_B: int = 0,
                       steady_inbound: int = 4) -> Tuple[RoleState, RoleState, RoleState, RoleState]:
    """Create classic classroom defaults with Base-Stock policies for all roles."""
    pol = BaseStockPolicy(S=S_target)

    def pipe(L: int) -> Deque[int]:
        return deque([steady_inbound]*L) if L > 0 else deque()

    retailer = RoleState(
        params=RoleParams(name="Retailer", L_ship=L_ship, h=0.5, p=1.0, L_prod=0),
        policy=pol,
        I=init_I,
        B=init_B,
        inbound_pipe=pipe(L_ship),
        prod_pipe=None,
    )
    wholesaler = RoleState(
        params=RoleParams(name="Wholesaler", L_ship=L_ship, h=0.5, p=1.0, L_prod=0),
        policy=pol,
        I=init_I,
        B=init_B,
        inbound_pipe=pipe(L_ship),
        prod_pipe=None,
    )
    distributor = RoleState(
        params=RoleParams(name="Distributor", L_ship=L_ship, h=0.5, p=1.0, L_prod=0),
        policy=pol,
        I=init_I,
        B=init_B,
        inbound_pipe=pipe(L_ship),
        prod_pipe=None,
    )
    manufacturer = RoleState(
        params=RoleParams(name="Manufacturer", L_ship=L_ship, h=0.5, p=1.0, L_prod=L_prod_manufacturer),
        policy=pol,
        I=init_I,
        B=init_B,
        inbound_pipe=pipe(L_ship),
        prod_pipe=deque([steady_inbound]*L_prod_manufacturer) if L_prod_manufacturer > 0 else None,
    )
    return retailer, wholesaler, distributor, manufacturer


def classic_demand(T: int) -> List[int]:
    """4 weeks of 4 units, then 8 units (classic shock)."""
    base = [4, 4, 4, 4]
    rest = [8] * max(0, T - 4)
    return (base + rest)[:T]


if __name__ == "__main__":
    # Example run
    T = 20
    demand = classic_demand(T)
    retailer, wholesaler, distributor, manufacturer = make_default_roles()

    sim = BeerGameSimulator(
        retailer=retailer,
        wholesaler=wholesaler,
        distributor=distributor,
        manufacturer=manufacturer,
        demand_series=demand,
        T=T,
    )
    sim.run()

    # Print a compact weekly table
    headers = [
        "week",
        "R_dem", "R_ship", "R_order", "R_I", "R_B",
        "W_ship", "W_order", "W_I", "W_B",
        "D_ship", "D_order", "D_I", "D_B",
        "M_ship", "M_order", "M_prod", "M_I", "M_B",
    ]
    print("\t".join(headers))
    for log in sim.logs:
        w = log.week
        row = [
            w,
            log.demand["Retailer"], log.ship_S["Retailer"], log.order_O["Retailer"], log.I_end["Retailer"], log.B_end["Retailer"],
            log.ship_S["Wholesaler"], log.order_O["Wholesaler"], log.I_end["Wholesaler"], log.B_end["Wholesaler"],
            log.ship_S["Distributor"], log.order_O["Distributor"], log.I_end["Distributor"], log.B_end["Distributor"],
            log.ship_S["Manufacturer"], log.order_O["Manufacturer"], log.prod_M["Manufacturer"], log.I_end["Manufacturer"], log.B_end["Manufacturer"],
        ]
        print("\t".join(str(x) for x in row))

    # KPI Summary
    from pprint import pprint
    print("\nKPI Summary:")
    pprint(sim.kpi_summary())
