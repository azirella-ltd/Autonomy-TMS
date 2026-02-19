"""
Data Generator for Large Supply Chain GNN Training.

Generates training data from:
1. SupplyChainConfig database models (realistic topologies)
2. Synthetic large-scale supply chains (stress testing)
3. SimPy simulations (dynamic behavior)

Outputs PyTorch Geometric Data objects suitable for:
- ScalableGraphSAGE
- TemporalScalableGNN
- Mini-batch training with NeighborLoader
"""

import numpy as np
import torch
from torch_geometric.data import Data, InMemoryDataset
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from pathlib import Path
import json
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class NodeConfig:
    """Configuration for a supply chain node."""
    id: int
    name: str
    node_type: str  # retailer, wholesaler, distributor, factory, supplier, etc.
    master_type: str  # MARKET_SUPPLY, MARKET_DEMAND, INVENTORY, MANUFACTURER
    initial_inventory: float = 100.0
    base_stock: float = 200.0
    holding_cost: float = 0.5
    backlog_cost: float = 2.0
    position: int = 0  # Position in supply chain (0 = most downstream)


@dataclass
class LaneConfig:
    """Configuration for a supply chain lane (edge)."""
    id: int
    source_id: int
    target_id: int
    lead_time: int = 2
    cost_per_unit: float = 1.0
    capacity: float = 1000.0
    reliability: float = 0.95
    edge_type: str = 'shipment_flow'  # order_flow, shipment_flow, info_flow, bom_link


@dataclass
class LargeSupplyChainConfig:
    """Configuration for a large supply chain."""
    name: str
    nodes: List[NodeConfig] = field(default_factory=list)
    lanes: List[LaneConfig] = field(default_factory=list)
    info_delay: int = 2
    planning_horizon: int = 52

    def num_nodes(self) -> int:
        return len(self.nodes)

    def num_edges(self) -> int:
        return len(self.lanes)


# Master type mapping
MASTER_TYPE_MAP = {
    'MARKET_SUPPLY': 0,
    'MARKET_DEMAND': 1,
    'INVENTORY': 2,
    'MANUFACTURER': 3,
}

# Node type mapping
NODE_TYPE_MAP = {
    'retailer': 0,
    'wholesaler': 1,
    'distributor': 2,
    'factory': 3,
    'supplier': 4,
    'market': 5,
    'dc': 6,
    'component_supplier': 7,
    'raw_material': 8,
    'customer': 9,
}

# Edge type mapping
EDGE_TYPE_MAP = {
    'order_flow': 0,
    'shipment_flow': 1,
    'info_flow': 2,
    'bom_link': 3,
}


def load_config_from_db(config_id: int) -> LargeSupplyChainConfig:
    """
    Load supply chain configuration from database.

    Args:
        config_id: SupplyChainConfig ID

    Returns:
        LargeSupplyChainConfig populated from database
    """
    try:
        from app.db.session import sync_engine
        from app.models.supply_chain_config import Site, TransportationLane, SupplyChainConfig
        from sqlalchemy.orm import Session

        with Session(sync_engine) as session:
            config = session.query(SupplyChainConfig).filter_by(id=config_id).first()
            if not config:
                raise ValueError(f"Config {config_id} not found")

            sc_config = LargeSupplyChainConfig(name=config.name)

            # Load sites (formerly "nodes")
            sites = session.query(Site).filter_by(config_id=config_id).all()
            for i, site in enumerate(sites):
                attrs = site.attributes or {}
                sc_config.nodes.append(NodeConfig(
                    id=site.id,
                    name=site.name,
                    node_type=(site.dag_type or site.type or 'inventory').lower(),
                    master_type=site.master_type or 'INVENTORY',
                    initial_inventory=float(attrs.get('initial_inventory', 100.0)),
                    base_stock=float(attrs.get('base_stock_level', 200.0)),
                    holding_cost=float(attrs.get('holding_cost', 0.5)),
                    backlog_cost=float(attrs.get('backlog_cost', 2.0)),
                    position=i
                ))

            # Load transportation lanes (formerly "lanes")
            lanes = session.query(TransportationLane).filter_by(config_id=config_id).all()
            for lane in lanes:
                # Extract lead time from supply_lead_time JSON or lead_time_days
                lt = 2
                if lane.supply_lead_time and isinstance(lane.supply_lead_time, dict):
                    lt = int(lane.supply_lead_time.get('value', 2))
                elif lane.lead_time_days and isinstance(lane.lead_time_days, dict):
                    lt = int(lane.lead_time_days.get('min', 2))

                sc_config.lanes.append(LaneConfig(
                    id=lane.id,
                    source_id=lane.from_site_id,
                    target_id=lane.to_site_id,
                    lead_time=lt,
                    cost_per_unit=1.0,
                    capacity=lane.capacity or 1000.0,
                    reliability=0.95,
                    edge_type='shipment_flow'
                ))

            return sc_config

    except ImportError:
        logger.warning("Database imports unavailable, using synthetic config")
        return generate_synthetic_config(num_nodes=50, name=f"synthetic_{config_id}")


def generate_synthetic_config(
    num_nodes: int = 50,
    num_tiers: int = 5,
    branching_factor: float = 1.5,
    name: str = "synthetic_large_sc"
) -> LargeSupplyChainConfig:
    """
    Generate a synthetic large supply chain configuration.

    Creates a multi-tier supply chain with:
    - Customers at tier 0
    - DCs at tier 1
    - Distributors at tier 2
    - Factories at tier 3
    - Suppliers at tier 4+

    Args:
        num_nodes: Total number of nodes
        num_tiers: Number of tiers in supply chain
        branching_factor: Average number of upstream nodes per downstream node
        name: Configuration name

    Returns:
        LargeSupplyChainConfig with synthetic topology
    """
    config = LargeSupplyChainConfig(name=name)

    # Distribute nodes across tiers
    nodes_per_tier = [max(1, int(num_nodes * (branching_factor ** i) / sum(branching_factor ** j for j in range(num_tiers)))) for i in range(num_tiers)]
    nodes_per_tier[-1] = num_nodes - sum(nodes_per_tier[:-1])  # Adjust last tier

    # Tier configurations
    tier_configs = [
        ('customer', 'MARKET_DEMAND'),
        ('dc', 'INVENTORY'),
        ('distributor', 'INVENTORY'),
        ('factory', 'MANUFACTURER'),
        ('supplier', 'MARKET_SUPPLY'),
    ]

    node_id = 0
    tier_nodes = []

    for tier_idx, count in enumerate(nodes_per_tier):
        tier_node_ids = []
        node_type, master_type = tier_configs[min(tier_idx, len(tier_configs) - 1)]

        for i in range(max(1, count)):
            node = NodeConfig(
                id=node_id,
                name=f"{node_type}_{tier_idx}_{i}",
                node_type=node_type,
                master_type=master_type,
                initial_inventory=np.random.uniform(50, 200),
                base_stock=np.random.uniform(100, 400),
                holding_cost=np.random.uniform(0.3, 0.7),
                backlog_cost=np.random.uniform(1.5, 3.0),
                position=tier_idx
            )
            config.nodes.append(node)
            tier_node_ids.append(node_id)
            node_id += 1

        tier_nodes.append(tier_node_ids)

    # Create lanes between tiers (downstream to upstream)
    lane_id = 0
    for tier_idx in range(len(tier_nodes) - 1):
        downstream_nodes = tier_nodes[tier_idx]
        upstream_nodes = tier_nodes[tier_idx + 1]

        for down_id in downstream_nodes:
            # Connect to 1-3 upstream nodes
            num_upstream = min(len(upstream_nodes), np.random.randint(1, 4))
            upstream_sample = np.random.choice(upstream_nodes, num_upstream, replace=False)

            for up_id in upstream_sample:
                lane = LaneConfig(
                    id=lane_id,
                    source_id=up_id,  # Upstream sends
                    target_id=down_id,  # Downstream receives
                    lead_time=np.random.randint(1, 6),
                    cost_per_unit=np.random.uniform(0.5, 2.0),
                    capacity=np.random.uniform(500, 2000),
                    reliability=np.random.uniform(0.85, 0.99),
                    edge_type='shipment_flow'
                )
                config.lanes.append(lane)
                lane_id += 1

    logger.info(f"Generated synthetic config: {len(config.nodes)} nodes, {len(config.lanes)} lanes")
    return config


class LargeSupplyChainSimulator:
    """
    Simulator for large supply chain dynamics.

    Simulates:
    - Multi-node inventory management
    - Order propagation with delays
    - Shipment flows with lead times
    - Bullwhip amplification
    """

    def __init__(self, config: LargeSupplyChainConfig):
        self.config = config
        self.num_nodes = config.num_nodes()

        # Build node lookup
        self.node_by_id = {n.id: n for n in config.nodes}
        self.node_index = {n.id: i for i, n in enumerate(config.nodes)}

        # Build adjacency (upstream suppliers for each node)
        self.upstream = defaultdict(list)  # node_id -> [(supplier_id, lane)]
        self.downstream = defaultdict(list)  # node_id -> [(customer_id, lane)]

        for lane in config.lanes:
            self.downstream[lane.source_id].append((lane.target_id, lane))
            self.upstream[lane.target_id].append((lane.source_id, lane))

    def simulate(
        self,
        num_timesteps: int = 100,
        demand_pattern: str = 'seasonal',
        base_demand: float = 50.0,
        volatility: float = 0.2
    ) -> Dict[str, np.ndarray]:
        """
        Run simulation.

        Args:
            num_timesteps: Length of simulation
            demand_pattern: 'random', 'seasonal', 'step', 'trend'
            base_demand: Average end customer demand
            volatility: Demand variability

        Returns:
            Dictionary with time series:
                - inventory: (T, num_nodes)
                - backlog: (T, num_nodes)
                - pipeline: (T, num_nodes)
                - orders: (T, num_nodes)
                - incoming_orders: (T, num_nodes)
                - costs: (T, num_nodes)
                - demand: (T,) end customer demand
        """
        T = num_timesteps
        N = self.num_nodes

        # State arrays
        inventory = np.zeros((T, N))
        backlog = np.zeros((T, N))
        pipeline = np.zeros((T, N))
        orders = np.zeros((T, N))
        incoming_orders = np.zeros((T, N))
        costs = np.zeros((T, N))

        # Initialize inventory
        for node in self.config.nodes:
            idx = self.node_index[node.id]
            inventory[0, idx] = node.initial_inventory

        # Pipeline queues: node_id -> [(arrival_time, quantity)]
        pipeline_queues = {n.id: [] for n in self.config.nodes}

        # Order queues: node_id -> [(arrival_time, quantity)]
        order_queues = {n.id: [] for n in self.config.nodes}

        # Generate end customer demand
        demand = self._generate_demand(T, demand_pattern, base_demand, volatility)

        for t in range(T):
            for node in self.config.nodes:
                idx = self.node_index[node.id]
                node_id = node.id

                # 1. Receive shipments
                while pipeline_queues[node_id] and pipeline_queues[node_id][0][0] <= t:
                    _, qty = pipeline_queues[node_id].pop(0)
                    inventory[t, idx] += qty

                # 2. Receive orders
                if node.master_type == 'MARKET_DEMAND':
                    # Customer nodes receive end demand
                    incoming_orders[t, idx] = demand[t]
                else:
                    # Other nodes receive orders from downstream
                    while order_queues[node_id] and order_queues[node_id][0][0] <= t:
                        _, qty = order_queues[node_id].pop(0)
                        incoming_orders[t, idx] += qty

                # 3. Fulfill demand
                total_demand = incoming_orders[t, idx] + (backlog[t - 1, idx] if t > 0 else 0)
                if inventory[t, idx] >= total_demand:
                    shipped = total_demand
                    inventory[t, idx] -= total_demand
                    backlog[t, idx] = 0
                else:
                    shipped = inventory[t, idx]
                    backlog[t, idx] = total_demand - inventory[t, idx]
                    inventory[t, idx] = 0

                # 4. Ship to downstream customers
                if shipped > 0 and self.downstream[node_id]:
                    # Distribute shipments across downstream nodes
                    per_customer = shipped / len(self.downstream[node_id])
                    for cust_id, lane in self.downstream[node_id]:
                        arrival_time = t + lane.lead_time
                        pipeline_queues[cust_id].append((arrival_time, per_customer))

                # 5. Calculate inventory position
                pipeline[t, idx] = sum(q for _, q in pipeline_queues[node_id])
                inv_position = inventory[t, idx] + pipeline[t, idx] - backlog[t, idx]

                # 6. Order from upstream suppliers
                order_qty = max(0, node.base_stock - inv_position)
                orders[t, idx] = order_qty

                # 7. Send orders upstream
                if order_qty > 0 and self.upstream[node_id]:
                    per_supplier = order_qty / len(self.upstream[node_id])
                    for sup_id, lane in self.upstream[node_id]:
                        order_arrival = t + self.config.info_delay
                        order_queues[sup_id].append((order_arrival, per_supplier))
                elif order_qty > 0 and node.master_type == 'MARKET_SUPPLY':
                    # Supplier orders from infinite source
                    arrival_time = t + 2  # Default lead time
                    pipeline_queues[node_id].append((arrival_time, order_qty))

                # 8. Calculate costs
                costs[t, idx] = inventory[t, idx] * node.holding_cost + backlog[t, idx] * node.backlog_cost

            # Carry forward state
            if t < T - 1:
                inventory[t + 1] = inventory[t].copy()
                backlog[t + 1] = backlog[t].copy()

        return {
            'inventory': inventory,
            'backlog': backlog,
            'pipeline': pipeline,
            'orders': orders,
            'incoming_orders': incoming_orders,
            'costs': costs,
            'demand': demand
        }

    def _generate_demand(
        self,
        num_timesteps: int,
        pattern: str,
        base_demand: float,
        volatility: float
    ) -> np.ndarray:
        """Generate demand time series."""
        if pattern == 'random':
            demand = base_demand + np.random.randn(num_timesteps) * (base_demand * volatility)
        elif pattern == 'seasonal':
            t = np.arange(num_timesteps)
            seasonal = base_demand * (1 + 0.3 * np.sin(2 * np.pi * t / 52))
            noise = np.random.randn(num_timesteps) * (base_demand * volatility)
            demand = seasonal + noise
        elif pattern == 'step':
            demand = np.ones(num_timesteps) * base_demand
            step_point = num_timesteps // 2
            demand[step_point:] *= 1.5
        elif pattern == 'trend':
            t = np.arange(num_timesteps)
            trend = base_demand + (t / num_timesteps) * base_demand * 0.5
            noise = np.random.randn(num_timesteps) * (base_demand * volatility)
            demand = trend + noise
        else:
            demand = np.ones(num_timesteps) * base_demand

        return np.maximum(demand, 0)


def create_pyg_data(
    config: LargeSupplyChainConfig,
    sim_result: Dict[str, np.ndarray],
    timestep: int,
    window_size: int = 10
) -> Data:
    """
    Create PyTorch Geometric Data object from simulation.

    Args:
        config: Supply chain configuration
        sim_result: Simulation results dictionary
        timestep: Current timestep to extract features
        window_size: History window for demand features

    Returns:
        PyG Data object ready for GNN training
    """
    num_nodes = config.num_nodes()

    # Node features: [inventory, backlog, pipeline, avg_demand, order_variance]
    inventory = sim_result['inventory'][timestep]
    backlog = sim_result['backlog'][timestep]
    pipeline = sim_result['pipeline'][timestep]

    # Compute demand statistics
    if timestep >= window_size:
        demand_window = sim_result['incoming_orders'][timestep - window_size:timestep]
        avg_demand = demand_window.mean(axis=0)
        std_demand = demand_window.std(axis=0) + 1e-6
    else:
        avg_demand = sim_result['incoming_orders'][:timestep + 1].mean(axis=0) if timestep > 0 else np.zeros(num_nodes)
        std_demand = np.ones(num_nodes)

    # Normalize features
    inv_norm = inventory / (np.max(inventory) + 1e-6)
    back_norm = backlog / (np.max(backlog) + 1e-6)
    pipe_norm = pipeline / (np.max(pipeline) + 1e-6)
    dem_norm = avg_demand / (np.max(avg_demand) + 1e-6)

    # Stack node features
    node_features = np.stack([
        inv_norm,
        back_norm,
        pipe_norm,
        dem_norm,
        std_demand / (np.max(std_demand) + 1e-6),
        np.array([n.holding_cost for n in config.nodes]),
        np.array([n.backlog_cost for n in config.nodes]),
        np.array([n.position / max(1, max(n.position for n in config.nodes)) for n in config.nodes])
    ], axis=1)  # [num_nodes, 8]

    # Node types
    node_index = {n.id: i for i, n in enumerate(config.nodes)}
    master_types = torch.tensor([MASTER_TYPE_MAP.get(n.master_type, 2) for n in config.nodes], dtype=torch.long)
    node_types = torch.tensor([NODE_TYPE_MAP.get(n.node_type, 0) for n in config.nodes], dtype=torch.long)

    # Edge index and features
    edge_index = []
    edge_features = []
    edge_types = []

    for lane in config.lanes:
        src_idx = node_index.get(lane.source_id)
        tgt_idx = node_index.get(lane.target_id)
        if src_idx is not None and tgt_idx is not None:
            edge_index.append([src_idx, tgt_idx])
            edge_features.append([
                lane.lead_time / 10.0,  # Normalize
                lane.cost_per_unit / 5.0,
                lane.capacity / 2000.0,
                lane.reliability
            ])
            edge_types.append(EDGE_TYPE_MAP.get(lane.edge_type, 1))

    # Add reverse edges for message passing in both directions
    num_forward_edges = len(edge_index)
    for i in range(num_forward_edges):
        src, tgt = edge_index[i]
        edge_index.append([tgt, src])
        edge_features.append(edge_features[i])
        edge_types.append(edge_types[i])

    edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous()  # [2, num_edges]
    edge_attr = torch.tensor(edge_features, dtype=torch.float)  # [num_edges, 4]
    edge_types = torch.tensor(edge_types, dtype=torch.long)

    # Targets
    target_orders = sim_result['orders'][timestep]
    target_orders_norm = target_orders / (np.max(target_orders) + 1e-6)

    # Future costs for value estimation
    future_horizon = min(10, len(sim_result['costs']) - timestep - 1)
    if future_horizon > 0:
        future_costs = sim_result['costs'][timestep:timestep + future_horizon].sum(axis=0)
    else:
        future_costs = sim_result['costs'][timestep]

    data = Data(
        x=torch.tensor(node_features, dtype=torch.float),
        edge_index=edge_index,
        edge_attr=edge_attr,
        master_types=master_types,
        node_types=node_types,
        edge_types=edge_types,
        y_order=torch.tensor(target_orders_norm, dtype=torch.float).unsqueeze(-1),
        y_cost=torch.tensor(future_costs, dtype=torch.float).unsqueeze(-1),
        num_nodes=num_nodes
    )

    return data


def generate_training_dataset(
    config: Union[LargeSupplyChainConfig, int],
    num_simulations: int = 100,
    timesteps_per_sim: int = 100,
    samples_per_sim: int = 5,
    window_size: int = 10,
    save_path: Optional[str] = None
) -> List[Data]:
    """
    Generate complete training dataset.

    Args:
        config: LargeSupplyChainConfig or database config ID
        num_simulations: Number of simulation runs
        timesteps_per_sim: Timesteps per simulation
        samples_per_sim: Random samples to take per simulation
        window_size: History window size
        save_path: Optional path to save dataset

    Returns:
        List of PyG Data objects
    """
    # Load config if ID provided
    if isinstance(config, int):
        config = load_config_from_db(config)

    simulator = LargeSupplyChainSimulator(config)
    dataset = []

    for sim_idx in range(num_simulations):
        # Vary simulation parameters
        pattern = np.random.choice(['random', 'seasonal', 'step', 'trend'])
        base_demand = np.random.uniform(30, 100)
        volatility = np.random.uniform(0.1, 0.3)

        # Run simulation
        result = simulator.simulate(
            num_timesteps=timesteps_per_sim,
            demand_pattern=pattern,
            base_demand=base_demand,
            volatility=volatility
        )

        # Sample timesteps
        valid_range = list(range(window_size, timesteps_per_sim - 10))
        sampled_timesteps = np.random.choice(valid_range, min(samples_per_sim, len(valid_range)), replace=False)

        for t in sampled_timesteps:
            data = create_pyg_data(config, result, t, window_size)
            dataset.append(data)

        if (sim_idx + 1) % 10 == 0:
            logger.info(f"Generated {sim_idx + 1}/{num_simulations} simulations, {len(dataset)} samples")

    if save_path:
        torch.save(dataset, save_path)
        logger.info(f"Saved dataset to {save_path}")

    return dataset


def generate_temporal_training_data(
    config: Union[LargeSupplyChainConfig, int],
    num_simulations: int = 100,
    timesteps_per_sim: int = 100,
    window_size: int = 10,
    samples_per_sim: int = 5,
    save_path: Optional[str] = None
) -> Dict[str, np.ndarray]:
    """
    Generate temporal training data for TemporalScalableGNN.

    Returns data in format:
        X: [num_samples, window_size, num_nodes, num_features]
        edge_index: [2, num_edges]
        edge_attr: [num_edges, edge_features]
        Y: [num_samples, num_nodes, 1]

    Args:
        config: Configuration or config ID
        num_simulations: Number of simulation runs
        timesteps_per_sim: Timesteps per simulation
        window_size: Input sequence window
        samples_per_sim: Samples per simulation
        save_path: Optional save path

    Returns:
        Dictionary with training arrays
    """
    if isinstance(config, int):
        config = load_config_from_db(config)

    simulator = LargeSupplyChainSimulator(config)
    num_nodes = config.num_nodes()

    X_list = []
    Y_list = []

    for sim_idx in range(num_simulations):
        pattern = np.random.choice(['random', 'seasonal', 'step', 'trend'])
        base_demand = np.random.uniform(30, 100)
        volatility = np.random.uniform(0.1, 0.3)

        result = simulator.simulate(
            num_timesteps=timesteps_per_sim,
            demand_pattern=pattern,
            base_demand=base_demand,
            volatility=volatility
        )

        valid_range = list(range(window_size, timesteps_per_sim - 10))
        sampled_timesteps = np.random.choice(valid_range, min(samples_per_sim, len(valid_range)), replace=False)

        for t in sampled_timesteps:
            # Build temporal sequence
            x_seq = []
            for t_offset in range(t - window_size, t):
                inv = result['inventory'][t_offset]
                back = result['backlog'][t_offset]
                pipe = result['pipeline'][t_offset]
                inc_ord = result['incoming_orders'][t_offset]
                orders = result['orders'][t_offset]

                # Normalize
                features = np.stack([
                    inv / (np.max(inv) + 1e-6),
                    back / (np.max(back) + 1e-6),
                    pipe / (np.max(pipe) + 1e-6),
                    inc_ord / (np.max(inc_ord) + 1e-6),
                    orders / (np.max(orders) + 1e-6),
                    np.array([n.holding_cost for n in config.nodes]),
                    np.array([n.backlog_cost for n in config.nodes]),
                    np.array([n.position / max(1, max(n.position for n in config.nodes)) for n in config.nodes])
                ], axis=1)  # [num_nodes, 8]
                x_seq.append(features)

            X_list.append(np.stack(x_seq, axis=0))  # [window, nodes, features]
            Y_list.append(result['orders'][t].reshape(-1, 1))  # [nodes, 1]

        if (sim_idx + 1) % 10 == 0:
            logger.info(f"Generated {sim_idx + 1}/{num_simulations} simulations")

    X = np.array(X_list)  # [samples, window, nodes, features]
    Y = np.array(Y_list)  # [samples, nodes, 1]

    # Build edge data
    node_index = {n.id: i for i, n in enumerate(config.nodes)}
    edge_index = []
    edge_attr = []

    for lane in config.lanes:
        src_idx = node_index.get(lane.source_id)
        tgt_idx = node_index.get(lane.target_id)
        if src_idx is not None and tgt_idx is not None:
            edge_index.append([src_idx, tgt_idx])
            edge_index.append([tgt_idx, src_idx])  # Bidirectional
            edge_attr.append([lane.lead_time / 10.0, lane.cost_per_unit / 5.0, lane.capacity / 2000.0, lane.reliability])
            edge_attr.append([lane.lead_time / 10.0, lane.cost_per_unit / 5.0, lane.capacity / 2000.0, lane.reliability])

    edge_index = np.array(edge_index).T  # [2, edges]
    edge_attr = np.array(edge_attr)  # [edges, 4]

    data = {
        'X': X,
        'Y': Y,
        'edge_index': edge_index,
        'edge_attr': edge_attr,
        'node_types': np.array([NODE_TYPE_MAP.get(n.node_type, 0) for n in config.nodes]),
        'master_types': np.array([MASTER_TYPE_MAP.get(n.master_type, 2) for n in config.nodes]),
        'config_name': config.name,
        'num_nodes': num_nodes
    }

    if save_path:
        np.savez(save_path, **data)
        logger.info(f"Saved temporal dataset to {save_path}")

    return data
