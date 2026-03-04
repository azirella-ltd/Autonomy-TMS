"""Core supply chain simulation engine for arbitrary sequential topologies."""

from __future__ import annotations

from collections import deque
from typing import Any, Deque, Dict, Iterable, List

from .policies import NaiveEchoPolicy, OrderPolicy

# Default lead times (can be overridden per supply chain config)
DEFAULT_SHIPMENT_LEAD_TIME = 2  # inbound shipment delay (periods)
DEFAULT_DEMAND_LEAD_TIME = 2  # information / order transmission delay (periods)
DEFAULT_STEADY_STATE_DEMAND = 4  # initial demand (units/period)


class Node:
    """Represents a single site in the supply chain simulation."""

    def __init__(
        self,
        name: str,
        policy: OrderPolicy,
        *,
        base_stock: int = 20,
        inventory: int = 12,
        backlog: int = 0,
        pipeline_shipments: Iterable[int] | None = None,
        order_pipe: Iterable[int] | None = None,
        steady_demand: int | None = None,
        last_incoming_order: int = 0,
        immediate_order_buffer: int = 0,
        cost: float = 0.0,
        shipment_lead_time: int = DEFAULT_SHIPMENT_LEAD_TIME,
        demand_lead_time: int = DEFAULT_DEMAND_LEAD_TIME,
    ) -> None:
        self.name = name
        self.policy = policy
        self.base_stock = int(base_stock)
        self.inventory = int(inventory)
        self.backlog = int(backlog)

        self.shipment_lead_time = max(
            0, int(shipment_lead_time) if shipment_lead_time is not None else 0
        )
        self.demand_lead_time = max(
            0, int(demand_lead_time) if demand_lead_time is not None else 0
        )

        try:
            steady_flow = None if steady_demand is None else max(0, int(steady_demand))
        except (TypeError, ValueError):
            steady_flow = None

        prefill_shipments = (
            steady_flow
            if steady_flow is not None and self.shipment_lead_time > 0 and self.demand_lead_time > 0
            else 0
        )
        prefill_orders = (
            steady_flow
            if steady_flow is not None and self.shipment_lead_time > 0 and self.demand_lead_time > 0
            else 0
        )

        if self.shipment_lead_time > 0:
            initial_shipments = (
                list(pipeline_shipments)
                if pipeline_shipments is not None
                else [prefill_shipments] * self.shipment_lead_time
            )
            self.pipeline_shipments = deque(
                (int(x) for x in initial_shipments),
                maxlen=self.shipment_lead_time,
            )
            while len(self.pipeline_shipments) < self.shipment_lead_time:
                self.pipeline_shipments.appendleft(prefill_shipments)
        else:
            self.pipeline_shipments = deque()

        if self.demand_lead_time > 0:
            initial_orders = (
                list(order_pipe)
                if order_pipe is not None
                else [prefill_orders] * self.demand_lead_time
            )
            self.order_pipe = deque(
                (int(x) for x in initial_orders),
                maxlen=self.demand_lead_time,
            )
            while len(self.order_pipe) < self.demand_lead_time:
                self.order_pipe.appendleft(prefill_orders)
        else:
            initial = 0
            if order_pipe:
                try:
                    initial = int(next(iter(order_pipe)))
                except StopIteration:
                    initial = 0
            self.order_pipe = deque([initial], maxlen=1)

        self.last_incoming_order = int(last_incoming_order)
        self._immediate_order_buffer = max(0, int(immediate_order_buffer))
        self.cost = float(cost)

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------
    @property
    def pipeline_on_order(self) -> int:
        """Total inventory scheduled to arrive in future periods."""

        return sum(self.pipeline_shipments)

    @property
    def inventory_position(self) -> int:
        """Inventory position used by ordering policies."""

        return self.inventory + self.pipeline_on_order - self.backlog

    # ------------------------------------------------------------------
    # State transition helpers
    # ------------------------------------------------------------------
    def receive_shipment(self) -> int:
        """Advance the shipment pipeline and add arrivals to on-hand inventory."""

        if self.shipment_lead_time <= 0:
            return 0

        arrived = self.pipeline_shipments.popleft()
        self.pipeline_shipments.append(0)
        self.inventory += arrived
        return arrived

    def shift_order_pipe(self) -> int:
        """Advance the outbound order pipeline (orders travelling upstream)."""

        if self.demand_lead_time <= 0:
            due_upstream = self._immediate_order_buffer
            self._immediate_order_buffer = 0
            if self.order_pipe:
                self.order_pipe[0] = 0
            return due_upstream

        due_upstream = self.order_pipe.popleft()
        self.order_pipe.append(0)
        return due_upstream

    def schedule_inbound_shipment(self, quantity: int) -> None:
        """Queue a shipment that will arrive after the shipment lead time."""

        qty = int(quantity)
        if qty <= 0:
            return

        if self.shipment_lead_time <= 0:
            self.inventory += qty
            return

        self.pipeline_shipments[-1] += qty

    def schedule_order(self, quantity: int) -> None:
        """Queue an order that will reach the upstream partner after the delay."""

        qty = int(quantity)
        if qty <= 0:
            return

        if self.demand_lead_time <= 0:
            self._immediate_order_buffer += qty
            if self.order_pipe:
                self.order_pipe[0] = self._immediate_order_buffer
            return

        self.order_pipe[-1] += qty

    def decide_order(self) -> int:
        """Call the node's policy to determine the order for this period."""

        observation = {
            "inventory": self.inventory,
            "backlog": self.backlog,
            "pipeline_on_order": self.pipeline_on_order,
            "last_incoming_order": self.last_incoming_order,
            "base_stock": self.base_stock,
            "inventory_position": self.inventory_position,
        }
        try:
            quantity = self.policy.order(observation)
        except Exception:
            quantity = 0
        return max(0, int(round(quantity)))

    def accrue_costs(self, holding_cost: float = 1.0, backlog_cost: float = 2.0) -> float:
        """Accrue periodic holding and backlog costs."""

        previous = self.cost
        holding = holding_cost * max(self.inventory, 0)
        backlog_penalty = backlog_cost * max(self.backlog, 0)
        self.cost += holding + backlog_penalty
        return self.cost - previous

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "inventory": self.inventory,
            "backlog": self.backlog,
            "pipeline_shipments": list(self.pipeline_shipments),
            "order_pipe": list(self.order_pipe),
            "immediate_order_buffer": self._immediate_order_buffer,
            "last_incoming_order": self.last_incoming_order,
            "cost": self.cost,
            "base_stock": self.base_stock,
            "policy_state": self.policy.get_state(),
            "shipment_lead_time": self.shipment_lead_time,
            "demand_lead_time": self.demand_lead_time,
        }

    @classmethod
    def from_dict(
        cls,
        name: str,
        policy: OrderPolicy,
        state: Dict[str, Any],
        *,
        shipment_lead_time: int = DEFAULT_SHIPMENT_LEAD_TIME,
        demand_lead_time: int = DEFAULT_DEMAND_LEAD_TIME,
        steady_demand: int | None = None,
    ) -> "Node":
        state_shipment_lead = state.get("shipment_lead_time", shipment_lead_time)
        state_order_lead = state.get("demand_lead_time", demand_lead_time)
        node = cls(
            name,
            policy,
            base_stock=int(state.get("base_stock", 20)),
            inventory=int(state.get("inventory", 12)),
            backlog=int(state.get("backlog", 0)),
            pipeline_shipments=state.get("pipeline_shipments"),
            order_pipe=state.get("order_pipe"),
            immediate_order_buffer=int(state.get("immediate_order_buffer", 0)),
            last_incoming_order=int(state.get("last_incoming_order", 0)),
            cost=float(state.get("cost", 0.0)),
            shipment_lead_time=int(state_shipment_lead),
            demand_lead_time=int(state_order_lead),
            steady_demand=steady_demand,
        )
        policy.set_state(state.get("policy_state"))
        return node


class SupplyChainLine:
    """Supply chain simulation for an arbitrary sequential topology.

    .. deprecated::
        Legacy Beer Game simulation engine — retained for backwards compatibility
        with existing scenarios only.

        New scenarios should set ``scenario.config['use_sc_execution'] = True`` and
        use :class:`~app.services.sc_execution.simulation_executor.SimulationExecutor`
        which drives execution through standard AWS SC entities (InvLevel,
        InboundOrderLine, OutboundOrderLine, SourcingRules, PurchaseOrder).
        The Beer Game is simply a special case of iterative SC execution over a
        4-site linear DAG — no custom engine code required.

    The topology is defined by ``material_lanes`` — a list of
    (upstream_site, downstream_site) tuples describing material flow.
    The engine derives the site ordering via topological sort and
    simulates period-by-period inventory, shipment, and ordering dynamics.
    """

    def __init__(
        self,
        *,
        material_lanes: List[tuple[str, str]],
        role_policies: Dict[str, OrderPolicy] | None = None,
        base_stocks: Dict[str, int] | None = None,
        state: Dict[str, Dict[str, Any]] | None = None,
        shipment_lead_time: int = DEFAULT_SHIPMENT_LEAD_TIME,
        demand_lead_time: int = DEFAULT_DEMAND_LEAD_TIME,
        initial_demand: int | None = None,
    ) -> None:
        role_policies = role_policies or {}
        base_stocks = base_stocks or {}

        self._material_lanes = list(material_lanes)
        self.role_names = self._derive_role_sequence(self._material_lanes)
        self.shipment_lead_time = max(
            0, int(shipment_lead_time) if shipment_lead_time is not None else 0
        )
        self.demand_lead_time = max(
            0, int(demand_lead_time) if demand_lead_time is not None else 0
        )

        self._steady_pipeline_flow: int | None = None
        if self.shipment_lead_time > 0 and self.demand_lead_time > 0:
            baseline = initial_demand
            if baseline is None:
                baseline = DEFAULT_STEADY_STATE_DEMAND
            try:
                self._steady_pipeline_flow = max(0, int(baseline))
            except (TypeError, ValueError):
                self._steady_pipeline_flow = DEFAULT_STEADY_STATE_DEMAND

        self.nodes: List[Node] = []
        for role in self.role_names:
            policy = role_policies.get(role, NaiveEchoPolicy())
            if state and role in state:
                node = Node.from_dict(
                    role,
                    policy,
                    state[role],
                    shipment_lead_time=self.shipment_lead_time,
                    demand_lead_time=self.demand_lead_time,
                    steady_demand=self._steady_pipeline_flow,
                )
            else:
                node = Node(
                    role,
                    policy,
                    base_stock=int(base_stocks.get(role, 20)),
                    shipment_lead_time=self.shipment_lead_time,
                    demand_lead_time=self.demand_lead_time,
                    steady_demand=self._steady_pipeline_flow,
                )
            if base_stocks and role in base_stocks:
                node.base_stock = int(base_stocks[role])
            self.nodes.append(node)

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        return {node.name: node.to_dict() for node in self.nodes}

    # ------------------------------------------------------------------
    # Transportation lane/site helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _derive_role_sequence(lanes: List[tuple[str, str]]) -> List[str]:
        """Return the downstream-to-upstream site order implied by the transportation lanes."""

        nodes = set()
        adjacency: Dict[str, List[str]] = {}
        indegree: Dict[str, int] = {}
        for upstream, downstream in lanes:
            nodes.add(upstream)
            nodes.add(downstream)
            adjacency.setdefault(upstream, []).append(downstream)
            indegree.setdefault(upstream, 0)
            indegree[downstream] = indegree.get(downstream, 0) + 1

        queue: Deque[str] = deque(sorted(node for node in nodes if indegree.get(node, 0) == 0))
        topo: List[str] = []
        while queue:
            current = queue.popleft()
            topo.append(current)
            for neighbour in adjacency.get(current, []):
                indegree[neighbour] -= 1
                if indegree[neighbour] == 0:
                    queue.append(neighbour)

        if len(topo) != len(nodes):
            raise ValueError("Material lanes contain a cycle; cannot derive site order")

        # The topological order walks with shipments (upstream -> downstream);
        # we keep sites indexed from downstream -> upstream because customer
        # demand enters at index 0 in the simulation.
        return list(reversed(topo))

    def role_sequence_names(self) -> List[str]:
        """Return a copy of the site names in downstream-to-upstream order."""
        return list(self.role_names)

    # ------------------------------------------------------------------
    # Simulation step
    # ------------------------------------------------------------------
    def tick(self, customer_demand: int) -> Dict[str, Dict[str, Any]]:
        """Advance the supply chain by one period."""

        demand = max(0, int(customer_demand))
        stats: Dict[str, Dict[str, Any]] = {}

        # Step 1 – Receive inbound shipments (advance shipment pipelines)
        for node in self.nodes:
            inventory_previous = node.inventory
            arrived = node.receive_shipment()
            stats[node.name] = {
                "incoming_shipment": arrived,
                "inventory_previous": inventory_previous,
                "inventory_before": node.inventory,
                "backlog_before": node.backlog,
            }

        # Step 2 – Check incoming orders travelling upstream (previous commitments)
        incoming_orders: List[int] = [0] * len(self.nodes)
        if self.nodes:
            incoming_orders[0] = demand
            stats[self.nodes[0].name]["order_due"] = demand

        for idx in range(len(self.nodes) - 1):
            due_upstream = self.nodes[idx].shift_order_pipe()
            if due_upstream:
                incoming_orders[idx + 1] += due_upstream
            upstream_stats = stats[self.nodes[idx + 1].name]
            upstream_stats["order_due"] = incoming_orders[idx + 1]
            upstream_stats["incoming_order"] = incoming_orders[idx + 1]
            upstream_stats["last_incoming_order"] = incoming_orders[idx + 1]

        # Step 3/4/5 – Walk sites downstream -> upstream applying the simulation steps
        for idx, node in enumerate(self.nodes):
            incoming = incoming_orders[idx]
            node.last_incoming_order = incoming
            stats[node.name]["incoming_order"] = incoming
            stats[node.name]["last_incoming_order"] = incoming
            stats[node.name]["order_due"] = incoming

            need = node.backlog + incoming
            shipped = min(node.inventory, need)
            node.inventory -= shipped
            node.backlog = max(need - shipped, 0)

            stats[node.name].update(
                {
                    "demand": need,
                    "shipped": shipped,
                    "outgoing_shipment": shipped,
                    "inventory_after": node.inventory,
                    "backlog_after": node.backlog,
                    "inventory_position": node.inventory - node.backlog,
                }
            )

            if idx > 0:
                downstream = self.nodes[idx - 1]
                downstream.schedule_inbound_shipment(shipped)
                downstream_stats = stats[downstream.name]
                downstream_stats["inventory_after"] = downstream.inventory
                downstream_stats["inventory_position"] = downstream.inventory - downstream.backlog

            order_qty = node.decide_order()
            stats[node.name]["order_placed"] = order_qty

            if idx < len(self.nodes) - 1:
                node.schedule_order(order_qty)
                stats[node.name]["order_pipe"] = list(node.order_pipe)

                if node.demand_lead_time == 0:
                    due_now = node.shift_order_pipe()
                    if due_now:
                        incoming_orders[idx + 1] += due_now
                        upstream_stats = stats[self.nodes[idx + 1].name]
                        upstream_stats["order_due"] = incoming_orders[idx + 1]
                        upstream_stats["incoming_order"] = incoming_orders[idx + 1]
                        upstream_stats["last_incoming_order"] = incoming_orders[idx + 1]
            else:
                # Most upstream site starts production feeding its own shipment pipeline
                node.schedule_inbound_shipment(order_qty)
                stats[node.name]["order_pipe"] = list(node.order_pipe)

        for node in self.nodes:
            stats[node.name]["pipeline_on_order"] = node.pipeline_on_order
            stats[node.name]["inventory_position_with_pipeline"] = node.inventory_position
            stats[node.name]["inventory_position"] = node.inventory - node.backlog

        # Step 6/7 – Accrue costs and expose pipeline snapshots
        for node in self.nodes:
            cost_added = node.accrue_costs()
            stats[node.name]["cost_added"] = cost_added
            stats[node.name]["total_cost"] = node.cost
            stats[node.name]["pipeline_shipments"] = list(node.pipeline_shipments)

        return stats

    def summary(self) -> Dict[str, Dict[str, Any]]:
        return {
            node.name: {
                "inventory": node.inventory,
                "backlog": node.backlog,
                "pipeline": list(node.pipeline_shipments),
                "orders_in_transit": list(node.order_pipe),
                "cost": node.cost,
            }
            for node in self.nodes
        }
