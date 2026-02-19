"""
Enhanced Graph Neural Network architectures for supply chain modeling.

Implements:
- GraphSAGE: Inductive learning with neighbor sampling
- Heterogeneous GNN: Handle different node and edge types
- Temporal Attention: Enhanced temporal modeling
- Multi-task Learning: Joint prediction of demand, costs, bullwhip
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv, GATConv, GCNConv, HGTConv, to_hetero
from torch_geometric.data import Data, HeteroData
from typing import Dict, List, Optional, Tuple, Any
import logging

logger = logging.getLogger(__name__)


class GraphSAGESupplyChain(nn.Module):
    """
    GraphSAGE-based supply chain GNN with inductive learning capabilities.

    GraphSAGE uses neighbor sampling and aggregation, making it suitable for
    large-scale supply chains and generalization to unseen network topologies.
    """

    def __init__(
        self,
        node_feature_dim: int,
        edge_feature_dim: int,
        hidden_dim: int = 128,
        num_layers: int = 3,
        aggregator: str = "mean",  # "mean", "max", "lstm"
        dropout: float = 0.1,
        output_dim: int = 1  # Predicted order quantity
    ):
        super().__init__()
        self.node_feature_dim = node_feature_dim
        self.edge_feature_dim = edge_feature_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.dropout = dropout

        # Input projection
        self.node_encoder = nn.Linear(node_feature_dim, hidden_dim)

        # GraphSAGE convolution layers
        self.convs = nn.ModuleList()
        for i in range(num_layers):
            if i == 0:
                in_dim = hidden_dim
            else:
                in_dim = hidden_dim
            self.convs.append(
                SAGEConv(in_dim, hidden_dim, aggr=aggregator, normalize=True)
            )

        # Batch normalization
        self.batch_norms = nn.ModuleList([
            nn.BatchNorm1d(hidden_dim) for _ in range(num_layers)
        ])

        # Edge feature processing
        self.edge_encoder = nn.Sequential(
            nn.Linear(edge_feature_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim)
        )

        # Output heads
        self.output_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, output_dim)
        )

        # Auxiliary tasks (multi-task learning)
        self.cost_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1)
        )

        self.bullwhip_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1)
        )

    def forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_attr: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Forward pass.

        Args:
            x: Node features [num_nodes, node_feature_dim]
            edge_index: Edge indices [2, num_edges]
            edge_attr: Edge features [num_edges, edge_feature_dim]

        Returns:
            outputs: Dictionary with predictions
                - "order": Predicted order quantities [num_nodes, output_dim]
                - "cost": Predicted costs [num_nodes, 1]
                - "bullwhip": Predicted bullwhip risk [num_nodes, 1]
        """
        # Encode node features
        h = self.node_encoder(x)
        h = F.relu(h)
        h = F.dropout(h, p=self.dropout, training=self.training)

        # GraphSAGE layers
        for i, conv in enumerate(self.convs):
            h = conv(h, edge_index)
            h = self.batch_norms[i](h)
            h = F.relu(h)
            h = F.dropout(h, p=self.dropout, training=self.training)

        # Output predictions
        order_pred = self.output_head(h)
        cost_pred = self.cost_head(h)
        bullwhip_pred = self.bullwhip_head(h)

        return {
            "order": order_pred,
            "cost": cost_pred,
            "bullwhip": bullwhip_pred,
            "embeddings": h
        }

    def inductive_forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        target_nodes: torch.Tensor,
        edge_attr: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Inductive forward pass for unseen nodes.

        Args:
            x: Node features including new nodes
            edge_index: Edge indices including new edges
            target_nodes: Indices of target nodes to predict
            edge_attr: Edge features

        Returns:
            outputs: Predictions for target nodes only
        """
        # Full forward pass
        full_output = self.forward(x, edge_index, edge_attr)

        # Extract predictions for target nodes
        return {
            "order": full_output["order"][target_nodes],
            "cost": full_output["cost"][target_nodes],
            "bullwhip": full_output["bullwhip"][target_nodes],
            "embeddings": full_output["embeddings"][target_nodes]
        }


class HeterogeneousSupplyChainGNN(nn.Module):
    """
    Heterogeneous GNN for supply chains with multiple node and edge types.

    Node types: Retailer, Wholesaler, Distributor, Factory, Supplier
    Edge types: Order flows, shipment flows, information flows
    """

    def __init__(
        self,
        node_types: List[str],
        edge_types: List[Tuple[str, str, str]],
        node_feature_dims: Dict[str, int],
        edge_feature_dims: Dict[str, int],
        hidden_dim: int = 128,
        num_layers: int = 3,
        num_heads: int = 4,
        dropout: float = 0.1
    ):
        super().__init__()
        self.node_types = node_types
        self.edge_types = edge_types
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

        # Per-type node encoders
        self.node_encoders = nn.ModuleDict({
            ntype: nn.Sequential(
                nn.Linear(node_feature_dims[ntype], hidden_dim),
                nn.ReLU(),
                nn.LayerNorm(hidden_dim)
            )
            for ntype in node_types
        })

        # Heterogeneous graph transformer layers
        self.convs = nn.ModuleList()
        for _ in range(num_layers):
            conv = HGTConv(
                in_channels=hidden_dim,
                out_channels=hidden_dim,
                metadata=(node_types, edge_types),
                heads=num_heads,
                dropout=dropout
            )
            self.convs.append(conv)

        # Per-type output heads
        self.output_heads = nn.ModuleDict({
            ntype: nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(hidden_dim, 1)  # Order quantity
            )
            for ntype in node_types
        })

    def forward(self, data: HeteroData) -> Dict[str, torch.Tensor]:
        """
        Forward pass on heterogeneous graph.

        Args:
            data: HeteroData object with node and edge features

        Returns:
            outputs: Per-type predictions
        """
        # Encode node features
        x_dict = {}
        for ntype in self.node_types:
            if ntype in data.x_dict:
                x_dict[ntype] = self.node_encoders[ntype](data.x_dict[ntype])

        # Heterogeneous convolutions
        for conv in self.convs:
            x_dict = conv(x_dict, data.edge_index_dict)
            x_dict = {key: F.relu(x) for key, x in x_dict.items()}

        # Per-type predictions
        outputs = {}
        for ntype in self.node_types:
            if ntype in x_dict:
                outputs[ntype] = self.output_heads[ntype](x_dict[ntype])

        return outputs


class TemporalAttentionLayer(nn.Module):
    """
    Temporal attention layer for capturing time-dependent patterns.

    Uses multi-head attention over temporal sequence of node states.
    """

    def __init__(
        self,
        hidden_dim: int,
        num_heads: int = 4,
        dropout: float = 0.1
    ):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_heads = num_heads

        self.attention = nn.MultiheadAttention(
            embed_dim=hidden_dim,
            num_heads=num_heads,
            dropout=dropout,
            batch_first=True
        )

        self.layer_norm1 = nn.LayerNorm(hidden_dim)
        self.layer_norm2 = nn.LayerNorm(hidden_dim)

        self.ffn = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim * 4),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim * 4, hidden_dim)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.

        Args:
            x: Temporal sequence [batch, seq_len, hidden_dim]

        Returns:
            output: Attended sequence [batch, seq_len, hidden_dim]
        """
        # Self-attention
        attn_output, _ = self.attention(x, x, x)
        x = self.layer_norm1(x + attn_output)

        # Feed-forward
        ffn_output = self.ffn(x)
        x = self.layer_norm2(x + ffn_output)

        return x


class EnhancedTemporalGNN(nn.Module):
    """
    Enhanced temporal GNN combining GraphSAGE with temporal attention.

    Architecture:
    1. Per-timestep GraphSAGE processing
    2. Temporal attention over timestep sequence
    3. Multi-task prediction (order, cost, bullwhip)
    """

    def __init__(
        self,
        node_feature_dim: int,
        edge_feature_dim: int,
        hidden_dim: int = 128,
        num_spatial_layers: int = 2,
        num_temporal_layers: int = 2,
        num_heads: int = 4,
        dropout: float = 0.1,
        window_size: int = 10
    ):
        super().__init__()
        self.node_feature_dim = node_feature_dim
        self.hidden_dim = hidden_dim
        self.window_size = window_size

        # Spatial (graph) encoder - GraphSAGE
        self.spatial_encoder = GraphSAGESupplyChain(
            node_feature_dim=node_feature_dim,
            edge_feature_dim=edge_feature_dim,
            hidden_dim=hidden_dim,
            num_layers=num_spatial_layers,
            dropout=dropout
        )

        # Temporal encoder - Multi-head attention
        self.temporal_layers = nn.ModuleList([
            TemporalAttentionLayer(hidden_dim, num_heads, dropout)
            for _ in range(num_temporal_layers)
        ])

        # Final prediction heads
        self.order_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1)
        )

        self.cost_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1)
        )

        self.bullwhip_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1)
        )

        # Confidence estimation head
        self.confidence_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
            nn.Sigmoid()
        )

    def forward(
        self,
        x_temporal: torch.Tensor,
        edge_index: torch.Tensor,
        edge_attr: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Forward pass with temporal sequence.

        Args:
            x_temporal: Temporal node features [batch, window_size, num_nodes, node_feature_dim]
            edge_index: Edge indices [2, num_edges]
            edge_attr: Edge features [num_edges, edge_feature_dim]

        Returns:
            outputs: Predictions for all timesteps
        """
        batch_size, window_size, num_nodes, feature_dim = x_temporal.shape

        # Process each timestep with spatial GNN
        spatial_embeddings = []
        for t in range(window_size):
            x_t = x_temporal[:, t, :, :].reshape(-1, feature_dim)
            output_t = self.spatial_encoder(x_t, edge_index, edge_attr)
            h_t = output_t["embeddings"].reshape(batch_size, num_nodes, self.hidden_dim)
            spatial_embeddings.append(h_t)

        # Stack temporal embeddings [batch, window_size, num_nodes, hidden_dim]
        h_temporal = torch.stack(spatial_embeddings, dim=1)

        # Process each node's temporal sequence
        # Reshape to [batch * num_nodes, window_size, hidden_dim]
        h_temporal = h_temporal.transpose(1, 2).reshape(-1, window_size, self.hidden_dim)

        # Apply temporal attention layers
        for temporal_layer in self.temporal_layers:
            h_temporal = temporal_layer(h_temporal)

        # Take last timestep [batch * num_nodes, hidden_dim]
        h_final = h_temporal[:, -1, :]

        # Reshape back to [batch, num_nodes, hidden_dim]
        h_final = h_final.reshape(batch_size, num_nodes, self.hidden_dim)

        # Flatten for prediction [batch * num_nodes, hidden_dim]
        h_flat = h_final.reshape(-1, self.hidden_dim)

        # Multi-task predictions
        order_pred = self.order_head(h_flat)
        cost_pred = self.cost_head(h_flat)
        bullwhip_pred = self.bullwhip_head(h_flat)
        confidence = self.confidence_head(h_flat)

        # Reshape to [batch, num_nodes, 1]
        order_pred = order_pred.reshape(batch_size, num_nodes, 1)
        cost_pred = cost_pred.reshape(batch_size, num_nodes, 1)
        bullwhip_pred = bullwhip_pred.reshape(batch_size, num_nodes, 1)
        confidence = confidence.reshape(batch_size, num_nodes, 1)

        return {
            "order": order_pred,
            "cost": cost_pred,
            "bullwhip": bullwhip_pred,
            "confidence": confidence,
            "embeddings": h_final
        }


class MultiTaskLoss(nn.Module):
    """
    Multi-task loss with uncertainty weighting.

    Learns to balance multiple task losses automatically.
    Based on "Multi-Task Learning Using Uncertainty to Weigh Losses"
    (Kendall et al., 2018)
    """

    def __init__(self, num_tasks: int = 3):
        super().__init__()
        self.num_tasks = num_tasks
        # Log variance for each task (learnable)
        self.log_vars = nn.Parameter(torch.zeros(num_tasks))

    def forward(
        self,
        losses: Dict[str, torch.Tensor]
    ) -> Tuple[torch.Tensor, Dict[str, float]]:
        """
        Compute weighted multi-task loss.

        Args:
            losses: Dictionary of individual task losses

        Returns:
            total_loss: Weighted sum of losses
            weights: Task weights for logging
        """
        loss_list = [
            losses.get("order_loss", torch.tensor(0.0)),
            losses.get("cost_loss", torch.tensor(0.0)),
            losses.get("bullwhip_loss", torch.tensor(0.0))
        ]

        total_loss = 0
        weights = {}

        for i, (loss, log_var) in enumerate(zip(loss_list, self.log_vars)):
            precision = torch.exp(-log_var)
            task_loss = precision * loss + log_var
            total_loss += task_loss

            task_name = ["order", "cost", "bullwhip"][i]
            weights[f"{task_name}_weight"] = precision.item()

        return total_loss, weights


def create_enhanced_gnn(
    architecture: str = "graphsage",
    node_feature_dim: int = 16,
    edge_feature_dim: int = 4,
    hidden_dim: int = 128,
    **kwargs
) -> nn.Module:
    """
    Factory function for creating enhanced GNN models.

    Args:
        architecture: Architecture type ("graphsage", "hetero", "temporal")
        node_feature_dim: Input node feature dimension
        edge_feature_dim: Input edge feature dimension
        hidden_dim: Hidden layer dimension
        **kwargs: Additional architecture-specific parameters

    Returns:
        model: Configured GNN model
    """
    if architecture == "graphsage":
        return GraphSAGESupplyChain(
            node_feature_dim=node_feature_dim,
            edge_feature_dim=edge_feature_dim,
            hidden_dim=hidden_dim,
            **kwargs
        )
    elif architecture == "temporal":
        return EnhancedTemporalGNN(
            node_feature_dim=node_feature_dim,
            edge_feature_dim=edge_feature_dim,
            hidden_dim=hidden_dim,
            **kwargs
        )
    elif architecture == "hetero":
        # Requires additional metadata
        node_types = kwargs.get("node_types", ["retailer", "wholesaler", "distributor", "factory"])
        edge_types = kwargs.get("edge_types", [
            ("retailer", "orders_from", "wholesaler"),
            ("wholesaler", "orders_from", "distributor"),
            ("distributor", "orders_from", "factory")
        ])
        node_feature_dims = kwargs.get("node_feature_dims", {nt: node_feature_dim for nt in node_types})
        edge_feature_dims = kwargs.get("edge_feature_dims", {})

        return HeterogeneousSupplyChainGNN(
            node_types=node_types,
            edge_types=edge_types,
            node_feature_dims=node_feature_dims,
            edge_feature_dims=edge_feature_dims,
            hidden_dim=hidden_dim,
            **kwargs
        )
    else:
        raise ValueError(f"Unknown architecture: {architecture}")
