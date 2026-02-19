"""
Scalable GraphSAGE for Large Supply Chain Networks.

Designed to handle supply chains with:
- 50+ sites (nodes)
- 100s of products (items)
- Multiple node types (DC, Factory, Supplier, Customer)
- Variable topology (converging, diverging, serial)
- Edge features (lead times, costs, capacities)

Key features:
- Mini-batch training with neighbor sampling (O(batch_size) not O(nodes))
- Heterogeneous node types with shared/separate embeddings
- Edge feature integration for lane characteristics
- BOM-aware message passing for multi-product scenarios
- Inductive learning (generalizes to unseen topologies)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv, GATv2Conv, GraphNorm
from torch_geometric.data import Data, Batch
from torch_geometric.loader import NeighborLoader
from typing import Dict, List, Optional, Tuple, Any, Union
import numpy as np
import logging

logger = logging.getLogger(__name__)


class NodeTypeEmbedding(nn.Module):
    """
    Learnable embeddings for different supply chain node types.

    Supports AWS SC master types:
    - MARKET_SUPPLY: Upstream sources (suppliers)
    - MARKET_DEMAND: Downstream sinks (customers)
    - INVENTORY: Storage/fulfillment (DC, Warehouse)
    - MANUFACTURER: Production facilities

    Plus specific SC node types:
    - Retailer, Wholesaler, Distributor, Factory, Supplier, Market
    """

    # AWS SC master types
    MASTER_TYPES = {
        'MARKET_SUPPLY': 0,
        'MARKET_DEMAND': 1,
        'INVENTORY': 2,
        'MANUFACTURER': 3,
    }

    # Detailed SC node types
    NODE_TYPES = {
        'retailer': 0,
        'wholesaler': 1,
        'distributor': 2,
        'factory': 3,
        'supplier': 4,
        'market': 5,
        'dc': 6,  # Distribution center
        'component_supplier': 7,
        'raw_material': 8,
        'customer': 9,
    }

    def __init__(
        self,
        embedding_dim: int = 64,
        num_master_types: int = 4,
        num_node_types: int = 10,
        combine_mode: str = 'add'  # 'add', 'concat', 'gate'
    ):
        super().__init__()
        self.embedding_dim = embedding_dim
        self.combine_mode = combine_mode

        # Master type embedding (coarse-grained)
        self.master_embedding = nn.Embedding(num_master_types, embedding_dim)

        # Node type embedding (fine-grained)
        self.node_embedding = nn.Embedding(num_node_types, embedding_dim)

        if combine_mode == 'concat':
            self.projection = nn.Linear(embedding_dim * 2, embedding_dim)
        elif combine_mode == 'gate':
            self.gate = nn.Sequential(
                nn.Linear(embedding_dim * 2, embedding_dim),
                nn.Sigmoid()
            )

    def forward(
        self,
        master_types: torch.Tensor,
        node_types: torch.Tensor
    ) -> torch.Tensor:
        """
        Get combined node type embeddings.

        Args:
            master_types: [num_nodes] master type indices
            node_types: [num_nodes] detailed node type indices

        Returns:
            embeddings: [num_nodes, embedding_dim]
        """
        master_emb = self.master_embedding(master_types)
        node_emb = self.node_embedding(node_types)

        if self.combine_mode == 'add':
            return master_emb + node_emb
        elif self.combine_mode == 'concat':
            combined = torch.cat([master_emb, node_emb], dim=-1)
            return self.projection(combined)
        elif self.combine_mode == 'gate':
            combined = torch.cat([master_emb, node_emb], dim=-1)
            gate = self.gate(combined)
            return gate * master_emb + (1 - gate) * node_emb
        else:
            return master_emb + node_emb


class EdgeFeatureEncoder(nn.Module):
    """
    Encode edge (lane) features for supply chain relationships.

    Features:
    - lead_time: Transportation/production lead time
    - cost: Transportation/handling cost
    - capacity: Maximum flow capacity
    - reliability: On-time delivery probability
    - relationship_type: Order flow, shipment flow, info flow
    """

    EDGE_TYPES = {
        'order_flow': 0,
        'shipment_flow': 1,
        'info_flow': 2,
        'bom_link': 3,  # Bill of materials relationship
    }

    def __init__(
        self,
        num_continuous_features: int = 4,  # lead_time, cost, capacity, reliability
        num_edge_types: int = 4,
        hidden_dim: int = 64,
        output_dim: int = 64
    ):
        super().__init__()

        # Continuous feature encoder
        self.continuous_encoder = nn.Sequential(
            nn.Linear(num_continuous_features, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, output_dim)
        )

        # Edge type embedding
        self.edge_type_embedding = nn.Embedding(num_edge_types, output_dim)

        # Combine layer
        self.combine = nn.Linear(output_dim * 2, output_dim)

    def forward(
        self,
        continuous_features: torch.Tensor,
        edge_types: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """
        Encode edge features.

        Args:
            continuous_features: [num_edges, num_continuous_features]
            edge_types: [num_edges] edge type indices (optional)

        Returns:
            edge_embeddings: [num_edges, output_dim]
        """
        cont_emb = self.continuous_encoder(continuous_features)

        if edge_types is not None:
            type_emb = self.edge_type_embedding(edge_types)
            combined = torch.cat([cont_emb, type_emb], dim=-1)
            return self.combine(combined)
        else:
            return cont_emb


class ScalableGraphSAGELayer(nn.Module):
    """
    Single GraphSAGE layer with edge feature integration.

    Uses GATv2 attention with edge features for better message aggregation.
    """

    def __init__(
        self,
        in_dim: int,
        out_dim: int,
        edge_dim: int = 64,
        heads: int = 4,
        dropout: float = 0.1,
        use_edge_features: bool = True
    ):
        super().__init__()
        self.use_edge_features = use_edge_features

        if use_edge_features:
            # GAT with edge features
            self.conv = GATv2Conv(
                in_channels=in_dim,
                out_channels=out_dim // heads,
                heads=heads,
                edge_dim=edge_dim,
                dropout=dropout,
                add_self_loops=True
            )
        else:
            # Standard SAGE
            self.conv = SAGEConv(in_dim, out_dim, aggr='mean')

        self.norm = GraphNorm(out_dim)
        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_attr: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """Forward pass with optional edge features."""
        if self.use_edge_features and edge_attr is not None:
            h = self.conv(x, edge_index, edge_attr)
        else:
            h = self.conv(x, edge_index)

        h = self.norm(h)
        h = F.relu(h)
        h = self.dropout(h)
        return h


class ScalableGraphSAGE(nn.Module):
    """
    Scalable GraphSAGE for Large Supply Chain Networks.

    Architecture:
    1. Node feature encoder + type embeddings
    2. Stacked GraphSAGE layers with edge features
    3. Multi-task prediction heads (order, demand, cost, bullwhip)
    4. Mini-batch training support via NeighborLoader

    Complexity: O(batch_size * num_layers * num_neighbors) vs O(nodes²) for attention
    """

    def __init__(
        self,
        node_feature_dim: int = 8,
        edge_feature_dim: int = 4,
        hidden_dim: int = 128,
        num_layers: int = 3,
        num_heads: int = 4,
        dropout: float = 0.1,
        num_node_types: int = 10,
        num_edge_types: int = 4,
        use_edge_features: bool = True,
        use_node_types: bool = True,
        output_dim: int = 1
    ):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.use_edge_features = use_edge_features
        self.use_node_types = use_node_types

        # Node feature encoder
        self.node_encoder = nn.Sequential(
            nn.Linear(node_feature_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim)
        )

        # Node type embeddings
        if use_node_types:
            self.node_type_encoder = NodeTypeEmbedding(
                embedding_dim=hidden_dim,
                num_node_types=num_node_types
            )

        # Edge feature encoder
        if use_edge_features:
            self.edge_encoder = EdgeFeatureEncoder(
                num_continuous_features=edge_feature_dim,
                num_edge_types=num_edge_types,
                hidden_dim=hidden_dim,
                output_dim=hidden_dim
            )

        # Stacked GraphSAGE layers
        self.layers = nn.ModuleList()
        for i in range(num_layers):
            self.layers.append(
                ScalableGraphSAGELayer(
                    in_dim=hidden_dim,
                    out_dim=hidden_dim,
                    edge_dim=hidden_dim if use_edge_features else 0,
                    heads=num_heads,
                    dropout=dropout,
                    use_edge_features=use_edge_features
                )
            )

        # Skip connections
        self.skip_projection = nn.Linear(hidden_dim * num_layers, hidden_dim)

        # Prediction heads
        self.order_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, output_dim)
        )

        self.demand_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, output_dim)
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

        # Confidence head
        self.confidence_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, 1),
            nn.Sigmoid()
        )

    def encode_nodes(
        self,
        x: torch.Tensor,
        master_types: Optional[torch.Tensor] = None,
        node_types: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """Encode node features with optional type embeddings."""
        h = self.node_encoder(x)

        if self.use_node_types and master_types is not None and node_types is not None:
            type_emb = self.node_type_encoder(master_types, node_types)
            h = h + type_emb

        return h

    def encode_edges(
        self,
        edge_attr: torch.Tensor,
        edge_types: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """Encode edge features."""
        if self.use_edge_features:
            return self.edge_encoder(edge_attr, edge_types)
        return None

    def forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_attr: Optional[torch.Tensor] = None,
        master_types: Optional[torch.Tensor] = None,
        node_types: Optional[torch.Tensor] = None,
        edge_types: Optional[torch.Tensor] = None,
        batch: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Forward pass.

        Args:
            x: Node features [num_nodes, node_feature_dim]
            edge_index: Edge indices [2, num_edges]
            edge_attr: Edge features [num_edges, edge_feature_dim]
            master_types: AWS SC master types [num_nodes]
            node_types: Detailed node types [num_nodes]
            edge_types: Edge/lane types [num_edges]
            batch: Batch assignment for mini-batch training [num_nodes]

        Returns:
            outputs: Dictionary with predictions for all nodes
        """
        # Encode nodes
        h = self.encode_nodes(x, master_types, node_types)

        # Encode edges
        edge_emb = None
        if edge_attr is not None:
            edge_emb = self.encode_edges(edge_attr, edge_types)

        # Message passing with skip connections
        layer_outputs = []
        for layer in self.layers:
            h = layer(h, edge_index, edge_emb)
            layer_outputs.append(h)

        # Concatenate all layer outputs for skip connection
        h_skip = torch.cat(layer_outputs, dim=-1)
        h = self.skip_projection(h_skip) + h  # Residual

        # Predictions
        order_pred = self.order_head(h)
        demand_pred = self.demand_head(h)
        cost_pred = self.cost_head(h)
        bullwhip_pred = self.bullwhip_head(h)
        confidence = self.confidence_head(h)

        return {
            'order': order_pred,
            'demand': demand_pred,
            'cost': cost_pred,
            'bullwhip': bullwhip_pred,
            'confidence': confidence,
            'embeddings': h
        }

    def get_neighbor_loader(
        self,
        data: Data,
        batch_size: int = 64,
        num_neighbors: List[int] = [15, 10, 5],
        shuffle: bool = True
    ) -> NeighborLoader:
        """
        Create mini-batch loader with neighbor sampling.

        This enables training on large graphs by sampling local neighborhoods
        instead of loading the entire graph.

        Args:
            data: PyG Data object
            batch_size: Number of target nodes per batch
            num_neighbors: Neighbors to sample per layer [layer1, layer2, ...]
            shuffle: Shuffle target nodes

        Returns:
            NeighborLoader for mini-batch training
        """
        return NeighborLoader(
            data,
            num_neighbors=num_neighbors,
            batch_size=batch_size,
            shuffle=shuffle,
            input_nodes=None  # Sample from all nodes
        )


class TemporalScalableGNN(nn.Module):
    """
    Temporal wrapper for ScalableGraphSAGE.

    Processes temporal sequences of supply chain states:
    1. Per-timestep GraphSAGE encoding
    2. Temporal aggregation (GRU or Attention)
    3. Multi-step forecasting
    """

    def __init__(
        self,
        node_feature_dim: int = 8,
        edge_feature_dim: int = 4,
        hidden_dim: int = 128,
        num_gnn_layers: int = 3,
        num_temporal_layers: int = 2,
        window_size: int = 10,
        forecast_horizon: int = 1,
        temporal_type: str = 'gru',  # 'gru' or 'attention'
        **kwargs
    ):
        super().__init__()
        self.window_size = window_size
        self.forecast_horizon = forecast_horizon
        self.hidden_dim = hidden_dim

        # Spatial encoder (GraphSAGE)
        self.spatial_encoder = ScalableGraphSAGE(
            node_feature_dim=node_feature_dim,
            edge_feature_dim=edge_feature_dim,
            hidden_dim=hidden_dim,
            num_layers=num_gnn_layers,
            **kwargs
        )

        # Temporal encoder
        if temporal_type == 'gru':
            self.temporal_encoder = nn.GRU(
                input_size=hidden_dim,
                hidden_size=hidden_dim,
                num_layers=num_temporal_layers,
                batch_first=True,
                dropout=0.1 if num_temporal_layers > 1 else 0
            )
        else:  # attention
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=hidden_dim,
                nhead=4,
                dim_feedforward=hidden_dim * 4,
                dropout=0.1,
                batch_first=True
            )
            self.temporal_encoder = nn.TransformerEncoder(
                encoder_layer,
                num_layers=num_temporal_layers
            )

        self.temporal_type = temporal_type

        # Forecast heads
        self.forecast_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, forecast_horizon)
        )

    def forward(
        self,
        x_seq: torch.Tensor,
        edge_index: torch.Tensor,
        edge_attr: Optional[torch.Tensor] = None,
        **kwargs
    ) -> Dict[str, torch.Tensor]:
        """
        Forward pass on temporal sequence.

        Args:
            x_seq: Node features over time [batch, window_size, num_nodes, features]
            edge_index: Edge indices [2, num_edges] (same for all timesteps)
            edge_attr: Edge features [num_edges, edge_features]
            **kwargs: Additional arguments for spatial encoder

        Returns:
            outputs: Predictions including multi-step forecasts
        """
        batch_size, window_size, num_nodes, feature_dim = x_seq.shape

        # Process each timestep
        temporal_embeddings = []
        for t in range(window_size):
            x_t = x_seq[:, t].reshape(-1, feature_dim)  # [batch * nodes, features]
            output_t = self.spatial_encoder(x_t, edge_index, edge_attr, **kwargs)
            h_t = output_t['embeddings'].reshape(batch_size, num_nodes, -1)
            temporal_embeddings.append(h_t)

        # Stack: [batch, window, nodes, hidden]
        h_temporal = torch.stack(temporal_embeddings, dim=1)

        # Process each node's temporal sequence
        # Reshape to [batch * nodes, window, hidden]
        h_temporal = h_temporal.transpose(1, 2).reshape(-1, window_size, self.hidden_dim)

        # Temporal encoding
        if self.temporal_type == 'gru':
            h_temporal, _ = self.temporal_encoder(h_temporal)
        else:
            h_temporal = self.temporal_encoder(h_temporal)

        # Take last timestep: [batch * nodes, hidden]
        h_final = h_temporal[:, -1]

        # Forecast
        forecast = self.forecast_head(h_final)  # [batch * nodes, horizon]
        forecast = forecast.reshape(batch_size, num_nodes, self.forecast_horizon)

        # Get current predictions from spatial encoder
        x_last = x_seq[:, -1].reshape(-1, feature_dim)
        current_output = self.spatial_encoder(x_last, edge_index, edge_attr, **kwargs)

        # Reshape current outputs
        for key in ['order', 'demand', 'cost', 'bullwhip', 'confidence']:
            if key in current_output:
                current_output[key] = current_output[key].reshape(batch_size, num_nodes, -1)

        current_output['forecast'] = forecast
        current_output['embeddings'] = h_final.reshape(batch_size, num_nodes, self.hidden_dim)

        return current_output


def create_scalable_gnn(
    config: Dict[str, Any],
    temporal: bool = False
) -> nn.Module:
    """
    Factory function for creating scalable GNN models.

    Args:
        config: Model configuration dictionary
        temporal: Whether to use temporal wrapper

    Returns:
        Configured model
    """
    default_config = {
        'node_feature_dim': 8,
        'edge_feature_dim': 4,
        'hidden_dim': 128,
        'num_layers': 3,
        'num_heads': 4,
        'dropout': 0.1,
        'num_node_types': 10,
        'num_edge_types': 4,
        'use_edge_features': True,
        'use_node_types': True,
    }
    default_config.update(config)

    if temporal:
        return TemporalScalableGNN(**default_config)
    else:
        return ScalableGraphSAGE(**default_config)
