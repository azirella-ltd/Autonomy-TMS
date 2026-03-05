#!/usr/bin/env python3
"""
Training script for Two-Tier Planning & Execution GNN Architecture.

Supports training both tiers independently or together:

1. S&OP GraphSAGE (--mode sop):
   - Trains on static network features
   - Outputs: Risk scores, criticality, bottleneck detection
   - Refresh: Weekly/Monthly

2. Execution tGNN (--mode execution):
   - Requires pre-trained S&OP model for structural embeddings
   - Trains on temporal transactional data
   - Outputs: Order recommendations, demand forecasts, exceptions
   - Refresh: Daily

3. Hybrid (--mode hybrid):
   - Trains both models end-to-end
   - S&OP embeddings flow into Execution model

Usage:
    # Train S&OP model only
    python train_planning_execution.py --mode sop --config-id 1 --epochs 50

    # Train Execution model with pre-trained S&OP
    python train_planning_execution.py --mode execution --sop-checkpoint sop_best.pt --epochs 100

    # Train hybrid model end-to-end
    python train_planning_execution.py --mode hybrid --config-id 1 --epochs 100

    # Generate synthetic large SC for testing
    python train_planning_execution.py --mode sop --synthetic --num-nodes 50
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from datetime import datetime

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.cuda.amp import GradScaler, autocast
    TORCH_AVAILABLE = True
except ImportError as e:
    print(f"PyTorch not available: {e}")
    sys.exit(1)

from app.models.gnn.planning_execution_gnn import (
    SOPGraphSAGE,
    ExecutionTemporalGNN,
    HybridPlanningModel,
    create_sop_model,
    create_execution_model,
    create_hybrid_model
)
from app.models.gnn.large_sc_data_generator import (
    generate_synthetic_config,
    LargeSupplyChainConfig,
    LargeSupplyChainSimulator,
    load_config_from_db,
    NODE_TYPE_MAP,
    MASTER_TYPE_MAP
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

CHECKPOINT_DIR = BACKEND_ROOT / "checkpoints"
CHECKPOINT_DIR.mkdir(exist_ok=True)


# =============================================================================
# Data Generation for S&OP and Execution
# =============================================================================

def generate_sop_features(
    config: LargeSupplyChainConfig,
    num_samples: int = 100
) -> Dict[str, torch.Tensor]:
    """
    Generate S&OP (static/slow-changing) features for training.

    Returns features that change slowly (weekly/monthly):
    - Historical lead times and variability
    - Capacity and utilization patterns
    - Cost structures
    - Reliability metrics
    """
    num_nodes = config.num_nodes()
    node_index = {n.id: i for i, n in enumerate(config.nodes)}

    all_node_features = []
    all_edge_features = []

    # Generate variations of the same topology with different parameters
    for _ in range(num_samples):
        # Node features (12 dimensions)
        node_features = np.zeros((num_nodes, 12))
        for i, node in enumerate(config.nodes):
            node_features[i] = [
                np.random.uniform(2, 10),  # avg_lead_time
                np.random.uniform(0.1, 0.5),  # lead_time_cv
                np.random.uniform(500, 2000),  # capacity
                np.random.uniform(0.5, 0.95),  # capacity_utilization
                np.random.uniform(1, 10),  # unit_cost
                np.random.uniform(0.85, 0.99),  # reliability
                len([l for l in config.lanes if l.target_id == node.id]),  # num_suppliers
                len([l for l in config.lanes if l.source_id == node.id]),  # num_customers
                np.random.uniform(4, 20),  # inventory_turns
                np.random.uniform(0.90, 0.99),  # service_level
                node.holding_cost,  # holding_cost
                node.position / max(1, max(n.position for n in config.nodes))  # position
            ]
        all_node_features.append(node_features)

        # Edge features (6 dimensions) - duplicated for bidirectional edges
        edge_features = []
        for lane in config.lanes:
            feat = [
                lane.lead_time + np.random.uniform(-0.5, 0.5),  # lead_time_avg
                np.random.uniform(0.5, 2.0),  # lead_time_std
                lane.cost_per_unit,  # cost_per_unit
                lane.capacity,  # capacity
                lane.reliability,  # reliability
                np.random.uniform(0.5, 1.0),  # relationship_strength
            ]
            edge_features.append(feat)  # forward
            edge_features.append(feat)  # reverse (bidirectional)
        all_edge_features.append(np.array(edge_features))

    # Build edge index
    edge_index = []
    for lane in config.lanes:
        src = node_index.get(lane.source_id)
        tgt = node_index.get(lane.target_id)
        if src is not None and tgt is not None:
            edge_index.append([src, tgt])
            edge_index.append([tgt, src])  # Bidirectional

    edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous()

    # Generate target labels (for supervised learning)
    # Criticality: nodes with few suppliers and many customers are more critical
    # Bottleneck: nodes with high utilization are bottlenecks
    targets = []
    for node_feat in all_node_features:
        criticality = (1 - node_feat[:, 6] / (node_feat[:, 6].max() + 1)) * (node_feat[:, 7] / (node_feat[:, 7].max() + 1))
        bottleneck = node_feat[:, 3]  # capacity_utilization
        concentration = 1 - node_feat[:, 6] / (node_feat[:, 6].max() + 1)
        resilience = node_feat[:, 5] * (node_feat[:, 6] / (node_feat[:, 6].max() + 1))
        targets.append({
            'criticality': criticality,
            'bottleneck': bottleneck,
            'concentration': concentration,
            'resilience': resilience
        })

    return {
        'node_features': torch.tensor(np.array(all_node_features), dtype=torch.float),
        'edge_index': edge_index,
        'edge_features': torch.tensor(np.array(all_edge_features), dtype=torch.float),
        'targets': targets
    }


def generate_execution_features(
    config: LargeSupplyChainConfig,
    structural_embeddings: torch.Tensor,
    num_samples: int = 500,
    window_size: int = 10
) -> Dict[str, torch.Tensor]:
    """
    Generate Execution (transactional/fast-changing) features for training.

    Returns temporal sequences of:
    - Inventory levels
    - Order flows
    - Shipment patterns
    - Demand signals
    """
    simulator = LargeSupplyChainSimulator(config)
    num_nodes = config.num_nodes()
    node_index = {n.id: i for i, n in enumerate(config.nodes)}

    X_list = []  # Temporal features
    Y_order = []  # Order targets
    Y_demand = []  # Demand targets

    samples_collected = 0
    sim_idx = 0

    while samples_collected < num_samples:
        # Simulate
        pattern = np.random.choice(['random', 'seasonal', 'step', 'trend'])
        base_demand = np.random.uniform(30, 100)
        volatility = np.random.uniform(0.1, 0.3)

        result = simulator.simulate(
            num_timesteps=100,
            demand_pattern=pattern,
            base_demand=base_demand,
            volatility=volatility
        )

        # Extract windows
        valid_range = list(range(window_size, 90))
        for t in np.random.choice(valid_range, min(5, num_samples - samples_collected), replace=False):
            # Build temporal sequence
            x_seq = []
            for t_offset in range(t - window_size, t):
                # Execution features (8 dimensions)
                features = np.stack([
                    result['inventory'][t_offset] / (result['inventory'].max() + 1e-6),
                    result['backlog'][t_offset] / (result['backlog'].max() + 1e-6),
                    result['incoming_orders'][t_offset] / (result['incoming_orders'].max() + 1e-6),
                    result['orders'][t_offset] / (result['orders'].max() + 1e-6),
                    result['orders'][t_offset] / (result['orders'].max() + 1e-6),  # orders_placed
                    np.random.uniform(0.8, 1.2, num_nodes),  # actual_lead_time ratio
                    np.random.uniform(0.3, 0.9, num_nodes),  # capacity_used
                    result['incoming_orders'][t_offset] / (base_demand + 1e-6),  # demand_signal
                ], axis=1)  # [nodes, 8]
                x_seq.append(features)

            X_list.append(np.stack(x_seq, axis=0))  # [window, nodes, 8]
            Y_order.append(result['orders'][t])  # [nodes]
            Y_demand.append(result['incoming_orders'][t])  # [nodes]
            samples_collected += 1

        sim_idx += 1

    # Build edge data
    edge_index = []
    edge_features = []
    for lane in config.lanes:
        src = node_index.get(lane.source_id)
        tgt = node_index.get(lane.target_id)
        if src is not None and tgt is not None:
            edge_index.append([src, tgt])
            edge_index.append([tgt, src])
            # Execution edge features (4 dimensions)
            edge_features.append([
                lane.lead_time / 10.0,  # current_lead_time
                np.random.uniform(0.4, 0.9),  # utilization
                np.random.uniform(10, 100),  # in_transit
                lane.reliability,  # recent_reliability
            ])
            edge_features.append([
                lane.lead_time / 10.0,
                np.random.uniform(0.4, 0.9),
                np.random.uniform(10, 100),
                lane.reliability,
            ])

    return {
        'X': torch.tensor(np.array(X_list), dtype=torch.float),
        'Y_order': torch.tensor(np.array(Y_order), dtype=torch.float),
        'Y_demand': torch.tensor(np.array(Y_demand), dtype=torch.float),
        'edge_index': torch.tensor(edge_index, dtype=torch.long).t().contiguous(),
        'edge_features': torch.tensor(np.array(edge_features), dtype=torch.float),
        'structural_embeddings': structural_embeddings
    }


# =============================================================================
# Training Functions
# =============================================================================

def train_sop_model(
    model: SOPGraphSAGE,
    data: Dict[str, torch.Tensor],
    device: str = 'cuda',
    epochs: int = 50,
    learning_rate: float = 1e-3,
    checkpoint_name: str = 'sop_model'
) -> SOPGraphSAGE:
    """Train S&OP GraphSAGE model."""
    model = model.to(device)
    optimizer = optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=0.01)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, factor=0.5, patience=5)

    edge_index = data['edge_index'].to(device)
    node_features = data['node_features'].to(device)
    edge_features = data['edge_features'].to(device)
    targets = data['targets']

    num_samples = len(node_features)
    best_loss = float('inf')

    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0

        for i in range(num_samples):
            optimizer.zero_grad()

            # Forward pass
            outputs = model(
                node_features[i],
                edge_index,
                edge_features[i] if edge_features.dim() == 3 else edge_features[0]
            )

            # Compute loss
            target = targets[i]
            loss = (
                nn.functional.mse_loss(outputs['criticality_score'].squeeze(), torch.tensor(target['criticality'], device=device, dtype=torch.float)) +
                nn.functional.mse_loss(outputs['bottleneck_risk'].squeeze(), torch.tensor(target['bottleneck'], device=device, dtype=torch.float)) +
                nn.functional.mse_loss(outputs['concentration_risk'].squeeze(), torch.tensor(target['concentration'], device=device, dtype=torch.float)) +
                nn.functional.mse_loss(outputs['resilience_score'].squeeze(), torch.tensor(target['resilience'], device=device, dtype=torch.float))
            )

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            total_loss += loss.item()

        avg_loss = total_loss / num_samples
        scheduler.step(avg_loss)

        if epoch % 10 == 0 or avg_loss < best_loss:
            logger.info(f"Epoch {epoch}/{epochs} - Loss: {avg_loss:.4f}")

        if avg_loss < best_loss:
            best_loss = avg_loss
            torch.save({
                'model_state_dict': model.state_dict(),
                'epoch': epoch,
                'loss': best_loss
            }, CHECKPOINT_DIR / f"{checkpoint_name}_best.pt")

    logger.info(f"S&OP training complete. Best loss: {best_loss:.4f}")
    return model


def train_execution_model(
    model: ExecutionTemporalGNN,
    data: Dict[str, torch.Tensor],
    device: str = 'cuda',
    epochs: int = 100,
    batch_size: int = 32,
    learning_rate: float = 1e-3,
    checkpoint_name: str = 'execution_model'
) -> ExecutionTemporalGNN:
    """Train Execution tGNN model."""
    model = model.to(device)
    optimizer = optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=0.01)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, factor=0.5, patience=5)

    X = data['X'].to(device)
    Y_order = data['Y_order'].to(device)
    edge_index = data['edge_index'].to(device)
    edge_features = data['edge_features'].to(device)
    structural_emb = data['structural_embeddings'].to(device)

    num_samples = len(X)
    best_loss = float('inf')

    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0
        num_batches = 0

        indices = np.random.permutation(num_samples)

        for i in range(0, num_samples, batch_size):
            batch_idx = indices[i:i + batch_size]
            x_batch = X[batch_idx]
            y_batch = Y_order[batch_idx]

            optimizer.zero_grad()

            outputs = model(
                x_batch,
                structural_emb,
                edge_index,
                edge_features
            )

            loss = nn.functional.huber_loss(
                outputs['order_recommendation'].squeeze(-1),
                y_batch
            )

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            total_loss += loss.item()
            num_batches += 1

        avg_loss = total_loss / num_batches
        scheduler.step(avg_loss)

        if epoch % 10 == 0 or avg_loss < best_loss:
            logger.info(f"Epoch {epoch}/{epochs} - Loss: {avg_loss:.4f}")

        if avg_loss < best_loss:
            best_loss = avg_loss
            torch.save({
                'model_state_dict': model.state_dict(),
                'epoch': epoch,
                'loss': best_loss
            }, CHECKPOINT_DIR / f"{checkpoint_name}_best.pt")

    logger.info(f"Execution training complete. Best loss: {best_loss:.4f}")
    return model


def train_hybrid_model(
    model: HybridPlanningModel,
    sop_data: Dict[str, torch.Tensor],
    exec_data: Dict[str, torch.Tensor],
    device: str = 'cuda',
    epochs: int = 100,
    learning_rate: float = 1e-3,
    checkpoint_name: str = 'hybrid_model'
) -> HybridPlanningModel:
    """Train hybrid model end-to-end."""
    model = model.to(device)
    optimizer = optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=0.01)

    # Move data to device
    sop_node_features = sop_data['node_features'][0].to(device)  # Use first sample as reference
    sop_edge_index = sop_data['edge_index'].to(device)
    sop_edge_features = sop_data['edge_features'][0].to(device) if sop_data['edge_features'].dim() == 3 else sop_data['edge_features'].to(device)

    exec_X = exec_data['X'].to(device)
    exec_Y = exec_data['Y_order'].to(device)
    exec_edge_index = exec_data['edge_index'].to(device)
    exec_edge_features = exec_data['edge_features'].to(device)

    best_loss = float('inf')

    for epoch in range(1, epochs + 1):
        model.train()

        # Update structural analysis periodically (every 10 epochs simulates weekly update)
        update_structural = (epoch % 10 == 1)

        optimizer.zero_grad()

        # Forward pass
        outputs = model(
            exec_X,
            exec_edge_index,
            exec_edge_features,
            sop_node_features=sop_node_features if update_structural else None,
            sop_edge_index=sop_edge_index if update_structural else None,
            sop_edge_features=sop_edge_features if update_structural else None,
            update_structural=update_structural
        )

        # Loss
        loss = nn.functional.huber_loss(
            outputs['order_recommendation'].squeeze(-1),
            exec_Y
        )

        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

        if epoch % 10 == 0:
            logger.info(f"Epoch {epoch}/{epochs} - Loss: {loss.item():.4f}")

        if loss.item() < best_loss:
            best_loss = loss.item()
            torch.save({
                'model_state_dict': model.state_dict(),
                'epoch': epoch,
                'loss': best_loss
            }, CHECKPOINT_DIR / f"{checkpoint_name}_best.pt")

    logger.info(f"Hybrid training complete. Best loss: {best_loss:.4f}")
    return model


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Train Planning & Execution GNN Models")

    parser.add_argument("--mode", choices=['sop', 'execution', 'hybrid'], required=True,
                        help="Training mode: sop, execution, or hybrid")

    # Data source
    parser.add_argument("--config-id", type=int, help="Database config ID")
    parser.add_argument("--synthetic", action="store_true", help="Use synthetic config")
    parser.add_argument("--num-nodes", type=int, default=50, help="Nodes for synthetic")

    # Model parameters
    parser.add_argument("--hidden-dim", type=int, default=128)
    parser.add_argument("--embedding-dim", type=int, default=64)
    parser.add_argument("--window-size", type=int, default=10)

    # Training parameters
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--device", type=str, default="cuda")

    # Checkpoints
    parser.add_argument("--sop-checkpoint", type=str, help="Pre-trained S&OP model (for execution mode)")
    parser.add_argument("--checkpoint-name", type=str, default="planning_execution")

    args = parser.parse_args()

    # Auto-derive checkpoint name from config ID when using default
    if args.config_id and args.checkpoint_name == "planning_execution":
        args.checkpoint_name = f"planning_execution_config{args.config_id}"

    # Device
    device = args.device
    if device == "cuda" and not torch.cuda.is_available():
        logger.warning("CUDA not available, using CPU")
        device = "cpu"

    # Load or generate config
    if args.config_id:
        config = load_config_from_db(args.config_id)
    elif args.synthetic:
        config = generate_synthetic_config(args.num_nodes)
    else:
        config = generate_synthetic_config(50)

    logger.info(f"Config: {config.name}, Nodes: {config.num_nodes()}, Edges: {config.num_edges()}")

    if args.mode == 'sop':
        # Train S&OP model only
        logger.info("Generating S&OP training data...")
        sop_data = generate_sop_features(config, num_samples=100)

        logger.info("Creating S&OP model...")
        model = create_sop_model(
            hidden_dim=args.hidden_dim,
            embedding_dim=args.embedding_dim
        )
        logger.info(f"Parameters: {sum(p.numel() for p in model.parameters()):,}")

        train_sop_model(
            model, sop_data, device,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            checkpoint_name=f"{args.checkpoint_name}_sop"
        )

    elif args.mode == 'execution':
        # Load pre-trained S&OP model
        if not args.sop_checkpoint:
            # Train S&OP first
            logger.info("No S&OP checkpoint provided, training S&OP first...")
            sop_data = generate_sop_features(config, num_samples=50)
            sop_model = create_sop_model(hidden_dim=args.hidden_dim, embedding_dim=args.embedding_dim)
            sop_model = train_sop_model(sop_model, sop_data, device, epochs=20, checkpoint_name=f"{args.checkpoint_name}_sop")
        else:
            sop_model = create_sop_model(hidden_dim=args.hidden_dim, embedding_dim=args.embedding_dim)
            checkpoint = torch.load(args.sop_checkpoint, map_location=device)
            sop_model.load_state_dict(checkpoint['model_state_dict'])
            sop_model = sop_model.to(device)

        # Get structural embeddings
        logger.info("Extracting structural embeddings...")
        sop_data = generate_sop_features(config, num_samples=1)
        with torch.no_grad():
            sop_model.eval()
            outputs = sop_model(
                sop_data['node_features'][0].to(device),
                sop_data['edge_index'].to(device),
                sop_data['edge_features'][0].to(device) if sop_data['edge_features'].dim() == 3 else sop_data['edge_features'].to(device)
            )
            structural_emb = outputs['structural_embeddings'].cpu()

        # Generate execution data
        logger.info("Generating execution training data...")
        exec_data = generate_execution_features(
            config, structural_emb,
            num_samples=500,
            window_size=args.window_size
        )

        # Train execution model
        logger.info("Creating Execution model...")
        model = create_execution_model(
            structural_embedding_dim=args.embedding_dim,
            hidden_dim=args.hidden_dim,
            window_size=args.window_size
        )
        logger.info(f"Parameters: {sum(p.numel() for p in model.parameters()):,}")

        train_execution_model(
            model, exec_data, device,
            epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
            checkpoint_name=f"{args.checkpoint_name}_execution"
        )

    elif args.mode == 'hybrid':
        # Train both models together
        logger.info("Generating training data...")
        sop_data = generate_sop_features(config, num_samples=50)

        # Get initial structural embeddings
        sop_model = create_sop_model(hidden_dim=args.hidden_dim, embedding_dim=args.embedding_dim).to(device)
        with torch.no_grad():
            outputs = sop_model(
                sop_data['node_features'][0].to(device),
                sop_data['edge_index'].to(device),
                sop_data['edge_features'][0].to(device) if sop_data['edge_features'].dim() == 3 else sop_data['edge_features'].to(device)
            )
            structural_emb = outputs['structural_embeddings'].cpu()

        exec_data = generate_execution_features(
            config, structural_emb,
            num_samples=200,
            window_size=args.window_size
        )

        logger.info("Creating Hybrid model...")
        model = create_hybrid_model(
            hidden_dim=args.hidden_dim,
            embedding_dim=args.embedding_dim,
            window_size=args.window_size
        )
        logger.info(f"Parameters: {sum(p.numel() for p in model.parameters()):,}")

        train_hybrid_model(
            model, sop_data, exec_data, device,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
            checkpoint_name=f"{args.checkpoint_name}_hybrid"
        )

    logger.info("Training complete!")


if __name__ == "__main__":
    main()
