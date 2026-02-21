"""
Hybrid Planning & Execution GNN Architecture.

Two-tier architecture that separates concerns by planning horizon:

1. S&OP GraphSAGE (Medium-Term / Strategic):
   - Network structure is relatively stable
   - Outputs: Risk scores, bottleneck detection, criticality, resilience
   - Questions: Which suppliers pose concentration risk? Which DCs are bottlenecks?
   - Good for "what if" network design scenarios
   - Refresh: Weekly/Monthly

2. Execution tGNN (Short-Term / Operational):
   - Temporal signal dominates - actual orders, shipments, inventory
   - Outputs: Demand sensing, inventory projection, exception detection
   - Questions: If supplier X is late, when does it hit downstream nodes?
   - Learns propagation dynamics through the network
   - Refresh: Daily/Real-time

Key Insight: SHARED FOUNDATION
- S&OP GraphSAGE embeddings are fed as node features into Execution tGNN
- Execution model "knows" structural context while learning temporal patterns
- Structural embeddings don't need frequent retraining
- Temporal model runs continuously on fresh transactional data
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import SAGEConv, GATv2Conv, GraphNorm, global_mean_pool
from torch_geometric.data import Data
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# S&OP GraphSAGE - Medium-Term Structural Analysis
# =============================================================================

class SOPGraphSAGE(nn.Module):
    """
    S&OP (Sales & Operations Planning) GraphSAGE for medium-term planning.

    Learns structural properties of the supply chain network:
    - Node criticality (single points of failure)
    - Supplier concentration risk
    - Bottleneck detection
    - Network resilience scoring
    - Optimal safety stock positioning

    The embeddings capture structural context that changes slowly
    (network topology, supplier relationships, capacity structures).

    Outputs:
    - structural_embeddings: Rich node representations for downstream use
    - criticality_score: How critical is each node (0-1)
    - bottleneck_risk: Likelihood of becoming a bottleneck (0-1)
    - concentration_risk: Supplier concentration risk score
    - resilience_score: Network resilience around this node
    """

    def __init__(
        self,
        node_feature_dim: int = 12,
        edge_feature_dim: int = 6,
        hidden_dim: int = 128,
        embedding_dim: int = 64,  # Output embedding dimension
        num_layers: int = 3,
        num_heads: int = 4,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.embedding_dim = embedding_dim
        self.num_layers = num_layers

        # Node feature encoder
        # S&OP features: historical lead time, capacity, cost, reliability,
        # supplier count, customer count, inventory turns, service level
        self.node_encoder = nn.Sequential(
            nn.Linear(node_feature_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout)
        )

        # Edge feature encoder
        # S&OP edge features: lead time avg, lead time variability,
        # cost per unit, capacity, reliability, relationship strength
        self.edge_encoder = nn.Sequential(
            nn.Linear(edge_feature_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim)
        )

        # GraphSAGE layers with attention (GATv2 for edge feature support)
        self.convs = nn.ModuleList()
        self.norms = nn.ModuleList()
        for i in range(num_layers):
            self.convs.append(
                GATv2Conv(
                    in_channels=hidden_dim,
                    out_channels=hidden_dim // num_heads,
                    heads=num_heads,
                    edge_dim=hidden_dim,
                    dropout=dropout,
                    add_self_loops=True,
                    concat=True
                )
            )
            self.norms.append(GraphNorm(hidden_dim))

        # Embedding projection (for downstream use by Execution tGNN)
        self.embedding_head = nn.Sequential(
            nn.Linear(hidden_dim, embedding_dim),
            nn.LayerNorm(embedding_dim)
        )

        # S&OP-specific output heads
        self.criticality_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
            nn.Sigmoid()  # 0-1 score
        )

        self.bottleneck_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
            nn.Sigmoid()
        )

        self.concentration_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
            nn.Sigmoid()
        )

        self.resilience_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
            nn.Sigmoid()
        )

        # Safety stock recommendation (continuous output)
        self.safety_stock_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
            nn.ReLU()  # Non-negative
        )

        # Network-level aggregation for global metrics
        self.global_risk_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 4)  # [overall_risk, supply_risk, demand_risk, operational_risk]
        )

    def forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_attr: torch.Tensor,
        batch: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        """
        Forward pass for S&OP analysis.

        Args:
            x: Node features [num_nodes, node_feature_dim]
               Features should include: avg_lead_time, lead_time_cv, capacity,
               capacity_utilization, unit_cost, reliability, num_suppliers,
               num_customers, inventory_turns, service_level, holding_cost, position
            edge_attr: Edge features [num_edges, edge_feature_dim]
            edge_index: Edge indices [2, num_edges]
            batch: Batch assignment [num_nodes] for mini-batch training

        Returns:
            Dictionary with:
            - structural_embeddings: [num_nodes, embedding_dim] - for Execution tGNN
            - criticality_score: [num_nodes, 1]
            - bottleneck_risk: [num_nodes, 1]
            - concentration_risk: [num_nodes, 1]
            - resilience_score: [num_nodes, 1]
            - safety_stock_multiplier: [num_nodes, 1]
            - network_risk: [batch_size, 4] (if batched)
        """
        # Encode features
        h = self.node_encoder(x)
        edge_emb = self.edge_encoder(edge_attr)

        # Message passing
        for i, (conv, norm) in enumerate(zip(self.convs, self.norms)):
            h_new = conv(h, edge_index, edge_emb)
            h_new = norm(h_new)
            h_new = F.relu(h_new)
            h_new = F.dropout(h_new, p=0.1, training=self.training)
            h = h + h_new  # Residual connection

        # Generate outputs
        structural_embeddings = self.embedding_head(h)
        criticality = self.criticality_head(h)
        bottleneck = self.bottleneck_head(h)
        concentration = self.concentration_head(h)
        resilience = self.resilience_head(h)
        safety_stock = self.safety_stock_head(h)

        outputs = {
            'structural_embeddings': structural_embeddings,
            'criticality_score': criticality,
            'bottleneck_risk': bottleneck,
            'concentration_risk': concentration,
            'resilience_score': resilience,
            'safety_stock_multiplier': safety_stock,
            'hidden_state': h  # For network-level aggregation
        }

        # Network-level risk aggregation
        if batch is not None:
            network_risk = self.global_risk_head(global_mean_pool(h, batch))
            outputs['network_risk'] = torch.sigmoid(network_risk)
        else:
            # Single graph - aggregate all nodes
            network_risk = self.global_risk_head(h.mean(dim=0, keepdim=True))
            outputs['network_risk'] = torch.sigmoid(network_risk)

        return outputs

    def get_structural_embeddings(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_attr: torch.Tensor
    ) -> torch.Tensor:
        """
        Get just the structural embeddings for use by Execution tGNN.
        Call this with cached/infrequent updates.
        """
        with torch.no_grad():
            outputs = self.forward(x, edge_index, edge_attr)
        return outputs['structural_embeddings']

    def forward_with_attention(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_attr: torch.Tensor,
        batch: Optional[torch.Tensor] = None
    ) -> Tuple[Dict[str, torch.Tensor], List[Tuple[torch.Tensor, torch.Tensor]]]:
        """
        Forward pass that also extracts per-layer GATv2Conv attention weights.

        Returns:
            (standard_outputs, attention_per_layer)
            attention_per_layer: List of (edge_index, attention_coefficients) per GATv2 layer
        """
        h = self.node_encoder(x)
        edge_emb = self.edge_encoder(edge_attr)

        attention_per_layer = []
        for i, (conv, norm) in enumerate(zip(self.convs, self.norms)):
            h_new, (attn_edge_index, attn_weights) = conv(
                h, edge_index, edge_emb, return_attention_weights=True
            )
            attention_per_layer.append((attn_edge_index, attn_weights))
            h_new = norm(h_new)
            h_new = F.relu(h_new)
            h_new = F.dropout(h_new, p=0.1, training=self.training)
            h = h + h_new

        structural_embeddings = self.embedding_head(h)
        criticality = self.criticality_head(h)
        bottleneck = self.bottleneck_head(h)
        concentration = self.concentration_head(h)
        resilience = self.resilience_head(h)
        safety_stock = self.safety_stock_head(h)

        outputs = {
            'structural_embeddings': structural_embeddings,
            'criticality_score': criticality,
            'bottleneck_risk': bottleneck,
            'concentration_risk': concentration,
            'resilience_score': resilience,
            'safety_stock_multiplier': safety_stock,
            'hidden_state': h,
        }

        if batch is not None:
            network_risk = self.global_risk_head(global_mean_pool(h, batch))
            outputs['network_risk'] = torch.sigmoid(network_risk)
        else:
            network_risk = self.global_risk_head(h.mean(dim=0, keepdim=True))
            outputs['network_risk'] = torch.sigmoid(network_risk)

        return outputs, attention_per_layer

    @staticmethod
    def explain_node(
        target_node_idx: int,
        attention_per_layer: List[Tuple[torch.Tensor, torch.Tensor]],
        site_names: Optional[List[str]] = None,
    ) -> Dict[str, float]:
        """
        Extract aggregated incoming attention weights for a target node.

        Uses the final GATv2 layer's attention to identify which neighbor
        sites most influenced this node's scores.

        Args:
            target_node_idx: Index of the node to explain
            attention_per_layer: From forward_with_attention()
            site_names: Optional list mapping node indices to site names

        Returns:
            Dict mapping neighbor identifier to aggregated attention weight
        """
        if not attention_per_layer:
            return {}

        # Use final layer attention
        edge_index, attn_weights = attention_per_layer[-1]
        # attn_weights shape: [num_edges, num_heads] for GATv2 with concat=True
        # Average across attention heads
        if attn_weights.dim() == 2:
            avg_attn = attn_weights.mean(dim=1)
        else:
            avg_attn = attn_weights

        # Find edges pointing TO target node (edge_index[1] == target)
        target_mask = edge_index[1] == target_node_idx
        source_nodes = edge_index[0][target_mask]
        source_attention = avg_attn[target_mask]

        # Build result
        result = {}
        for src_idx, weight in zip(source_nodes.tolist(), source_attention.tolist()):
            name = site_names[src_idx] if site_names and src_idx < len(site_names) else f"node_{src_idx}"
            result[name] = weight

        # Normalize
        total = sum(result.values()) if result else 1.0
        if total > 0:
            result = {k: v / total for k, v in result.items()}

        return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))

    def compute_input_saliency(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_attr: torch.Tensor,
        target_node_idx: int,
        output_name: str = 'criticality_score',
    ) -> Dict[str, float]:
        """
        Compute gradient-based input saliency for a target node's output.

        Args:
            x: Node features (requires_grad will be enabled)
            edge_index: Edge indices
            edge_attr: Edge features
            target_node_idx: Node to explain
            output_name: Which output head to compute saliency for

        Returns:
            Dict mapping feature index to saliency magnitude (normalized)
        """
        x_input = x.detach().clone().requires_grad_(True)

        outputs = self.forward(x_input, edge_index, edge_attr)
        target_output = outputs[output_name][target_node_idx]

        target_output.backward(retain_graph=False)

        if x_input.grad is not None:
            saliency = x_input.grad[target_node_idx].abs()
            total = saliency.sum()
            if total > 0:
                saliency = saliency / total
            feature_names = [
                'avg_lead_time', 'lead_time_cv', 'capacity', 'capacity_utilization',
                'unit_cost', 'reliability', 'num_suppliers', 'num_customers',
                'inventory_turns', 'service_level', 'holding_cost', 'position',
            ]
            result = {}
            for i, val in enumerate(saliency.tolist()):
                name = feature_names[i] if i < len(feature_names) else f"feature_{i}"
                result[name] = val
            return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))
        return {}


# =============================================================================
# Execution tGNN - Short-Term Operational
# =============================================================================

class ExecutionTemporalGNN(nn.Module):
    """
    Execution-phase Temporal GNN for short-term operational decisions.

    Consumes:
    - Real-time transactional data (orders, shipments, inventory levels)
    - Structural embeddings from S&OP GraphSAGE (updated infrequently)

    Learns:
    - Propagation dynamics (how disruptions flow through network)
    - Demand signal amplification patterns
    - Lead time variability impacts
    - Exception detection and prediction

    Outputs:
    - order_recommendation: Suggested order quantities
    - demand_forecast: Short-term demand prediction
    - exception_probability: Likelihood of stockout/overstock
    - propagation_impact: If disruption occurs, impact timing by node
    """

    def __init__(
        self,
        transactional_feature_dim: int = 8,  # Real-time features
        structural_embedding_dim: int = 64,   # From S&OP GraphSAGE
        edge_feature_dim: int = 4,
        hidden_dim: int = 128,
        num_gnn_layers: int = 2,
        num_temporal_layers: int = 2,
        window_size: int = 10,
        forecast_horizon: int = 4,
        num_heads: int = 4,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.window_size = window_size
        self.forecast_horizon = forecast_horizon

        # Combined feature dimension (transactional + structural)
        self.combined_dim = transactional_feature_dim + structural_embedding_dim

        # Feature encoder (merges transactional + structural context)
        self.feature_encoder = nn.Sequential(
            nn.Linear(self.combined_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout)
        )

        # Edge encoder for real-time lane status
        self.edge_encoder = nn.Sequential(
            nn.Linear(edge_feature_dim, hidden_dim),
            nn.ReLU()
        )

        # Spatial GNN layers (per-timestep)
        self.spatial_convs = nn.ModuleList()
        self.spatial_norms = nn.ModuleList()
        for _ in range(num_gnn_layers):
            self.spatial_convs.append(
                GATv2Conv(
                    hidden_dim, hidden_dim // num_heads,
                    heads=num_heads, edge_dim=hidden_dim,
                    dropout=dropout, concat=True
                )
            )
            self.spatial_norms.append(GraphNorm(hidden_dim))

        # Temporal processing (GRU for efficiency in production)
        self.temporal_gru = nn.GRU(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=num_temporal_layers,
            batch_first=True,
            dropout=dropout if num_temporal_layers > 1 else 0
        )

        # Temporal attention for capturing propagation patterns
        self.temporal_attention = nn.MultiheadAttention(
            embed_dim=hidden_dim,
            num_heads=num_heads,
            dropout=dropout,
            batch_first=True
        )
        self.temporal_norm = nn.LayerNorm(hidden_dim)

        # Output heads
        self.order_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1),
            nn.ReLU()  # Non-negative orders
        )

        self.demand_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, forecast_horizon)  # Multi-step forecast
        )

        self.exception_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 3),  # [stockout_prob, overstock_prob, normal_prob]
            nn.Softmax(dim=-1)
        )

        # Propagation impact head
        # Predicts: if a disruption happens at this node, when does it hit other nodes
        self.propagation_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, forecast_horizon)  # Impact timeline
        )

        # Confidence/uncertainty estimation
        self.confidence_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, 1),
            nn.Sigmoid()
        )

    def forward(
        self,
        x_temporal: torch.Tensor,
        structural_embeddings: torch.Tensor,
        edge_index: torch.Tensor,
        edge_attr: torch.Tensor
    ) -> Dict[str, torch.Tensor]:
        """
        Forward pass for execution-phase decisions.

        Args:
            x_temporal: Transactional features over time
                       [batch, window_size, num_nodes, transactional_feature_dim]
                       Features: inventory, backlog, incoming_orders, outgoing_shipments,
                                orders_placed, lead_time_actual, capacity_used, demand_signal
            structural_embeddings: From S&OP GraphSAGE (cached)
                                  [num_nodes, structural_embedding_dim]
            edge_index: Edge indices [2, num_edges]
            edge_attr: Real-time edge features [num_edges, edge_feature_dim]
                      Features: current_lead_time, utilization, in_transit, reliability_recent

        Returns:
            Dictionary with:
            - order_recommendation: [batch, num_nodes, 1]
            - demand_forecast: [batch, num_nodes, forecast_horizon]
            - exception_probability: [batch, num_nodes, 3]
            - propagation_impact: [batch, num_nodes, forecast_horizon]
            - confidence: [batch, num_nodes, 1]
        """
        batch_size, window_size, num_nodes, trans_dim = x_temporal.shape

        # Expand structural embeddings to match batch/time dimensions
        # structural_embeddings: [num_nodes, emb_dim] -> [batch, window, nodes, emb_dim]
        struct_expanded = structural_embeddings.unsqueeze(0).unsqueeze(0)
        struct_expanded = struct_expanded.expand(batch_size, window_size, -1, -1)

        # Concatenate transactional + structural features
        x_combined = torch.cat([x_temporal, struct_expanded], dim=-1)

        # Process each timestep with spatial GNN
        edge_emb = self.edge_encoder(edge_attr)

        temporal_states = []
        for t in range(window_size):
            # Get features for this timestep
            x_t = x_combined[:, t]  # [batch, nodes, combined_dim]
            x_t_flat = x_t.reshape(-1, self.combined_dim)  # [batch*nodes, combined_dim]

            # Encode features
            h = self.feature_encoder(x_t_flat)

            # Spatial message passing
            for conv, norm in zip(self.spatial_convs, self.spatial_norms):
                h_new = conv(h, edge_index, edge_emb)
                h_new = norm(h_new)
                h_new = F.relu(h_new)
                h = h + h_new  # Residual

            # Reshape back
            h = h.reshape(batch_size, num_nodes, self.hidden_dim)
            temporal_states.append(h)

        # Stack temporal states: [batch, window, nodes, hidden]
        h_temporal = torch.stack(temporal_states, dim=1)

        # Process each node's temporal sequence
        # Reshape to [batch * nodes, window, hidden]
        h_temporal = h_temporal.transpose(1, 2).reshape(-1, window_size, self.hidden_dim)

        # GRU for temporal dynamics
        h_gru, _ = self.temporal_gru(h_temporal)

        # Temporal attention for propagation patterns
        h_attn, attn_weights = self.temporal_attention(h_gru, h_gru, h_gru)
        h_temporal = self.temporal_norm(h_gru + h_attn)

        # Take final timestep
        h_final = h_temporal[:, -1]  # [batch * nodes, hidden]

        # Generate outputs
        order_rec = self.order_head(h_final)
        demand_fcst = self.demand_head(h_final)
        exception_prob = self.exception_head(h_final)
        propagation = self.propagation_head(h_final)
        confidence = self.confidence_head(h_final)

        # Reshape outputs to [batch, nodes, ...]
        order_rec = order_rec.reshape(batch_size, num_nodes, 1)
        demand_fcst = demand_fcst.reshape(batch_size, num_nodes, self.forecast_horizon)
        exception_prob = exception_prob.reshape(batch_size, num_nodes, 3)
        propagation = propagation.reshape(batch_size, num_nodes, self.forecast_horizon)
        confidence = confidence.reshape(batch_size, num_nodes, 1)

        return {
            'order_recommendation': order_rec,
            'demand_forecast': demand_fcst,
            'exception_probability': exception_prob,
            'propagation_impact': torch.sigmoid(propagation),
            'confidence': confidence,
            'attention_weights': attn_weights.reshape(batch_size, num_nodes, window_size, window_size)
        }

    def forward_with_full_attention(
        self,
        x_temporal: torch.Tensor,
        structural_embeddings: torch.Tensor,
        edge_index: torch.Tensor,
        edge_attr: torch.Tensor,
    ) -> Tuple[Dict[str, torch.Tensor], List[List[Tuple[torch.Tensor, torch.Tensor]]]]:
        """
        Forward pass that also extracts spatial GATv2Conv attention weights
        at each timestep, in addition to the temporal attention.

        Returns:
            (standard_outputs, spatial_attention_per_timestep)
            spatial_attention_per_timestep: List[timestep] of List[layer] of
                (edge_index, attention_coefficients)
        """
        batch_size, window_size, num_nodes, trans_dim = x_temporal.shape

        struct_expanded = structural_embeddings.unsqueeze(0).unsqueeze(0)
        struct_expanded = struct_expanded.expand(batch_size, window_size, -1, -1)
        x_combined = torch.cat([x_temporal, struct_expanded], dim=-1)

        edge_emb = self.edge_encoder(edge_attr)

        temporal_states = []
        spatial_attention_per_timestep = []

        for t in range(window_size):
            x_t = x_combined[:, t]
            x_t_flat = x_t.reshape(-1, self.combined_dim)
            h = self.feature_encoder(x_t_flat)

            layer_attention = []
            for conv, norm in zip(self.spatial_convs, self.spatial_norms):
                h_new, (attn_ei, attn_w) = conv(
                    h, edge_index, edge_emb, return_attention_weights=True
                )
                layer_attention.append((attn_ei, attn_w))
                h_new = norm(h_new)
                h_new = F.relu(h_new)
                h = h + h_new

            spatial_attention_per_timestep.append(layer_attention)
            h = h.reshape(batch_size, num_nodes, self.hidden_dim)
            temporal_states.append(h)

        h_temporal = torch.stack(temporal_states, dim=1)
        h_temporal = h_temporal.transpose(1, 2).reshape(-1, window_size, self.hidden_dim)
        h_gru, _ = self.temporal_gru(h_temporal)
        h_attn, attn_weights = self.temporal_attention(h_gru, h_gru, h_gru)
        h_temporal = self.temporal_norm(h_gru + h_attn)

        h_final = h_temporal[:, -1]

        order_rec = self.order_head(h_final).reshape(batch_size, num_nodes, 1)
        demand_fcst = self.demand_head(h_final).reshape(batch_size, num_nodes, self.forecast_horizon)
        exception_prob = self.exception_head(h_final).reshape(batch_size, num_nodes, 3)
        propagation = self.propagation_head(h_final).reshape(batch_size, num_nodes, self.forecast_horizon)
        confidence = self.confidence_head(h_final).reshape(batch_size, num_nodes, 1)

        outputs = {
            'order_recommendation': order_rec,
            'demand_forecast': demand_fcst,
            'exception_probability': exception_prob,
            'propagation_impact': torch.sigmoid(propagation),
            'confidence': confidence,
            'attention_weights': attn_weights.reshape(batch_size, num_nodes, window_size, window_size),
        }
        return outputs, spatial_attention_per_timestep

    @staticmethod
    def explain_node_temporal(
        target_node_idx: int,
        temporal_attention: torch.Tensor,
        window_labels: Optional[List[str]] = None,
    ) -> Dict[str, float]:
        """
        Extract which past periods most influenced the target node's decision.

        Args:
            target_node_idx: Node index
            temporal_attention: [batch, num_nodes, window, window] from forward output
            window_labels: Optional labels like ["t-10", "t-9", ..., "t-1"]

        Returns:
            Dict mapping period label to attention weight (normalized)
        """
        # Take first batch element, target node, last timestep's attention over history
        if temporal_attention.dim() == 4:
            node_attn = temporal_attention[0, target_node_idx, -1]  # [window]
        else:
            return {}

        total = node_attn.sum().item()
        result = {}
        for i, weight in enumerate(node_attn.tolist()):
            offset = len(node_attn) - i
            label = window_labels[i] if window_labels and i < len(window_labels) else f"t-{offset}"
            result[label] = weight / total if total > 0 else 0.0

        return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))

    @staticmethod
    def explain_node_spatial(
        target_node_idx: int,
        spatial_attention_per_timestep: List[List[Tuple[torch.Tensor, torch.Tensor]]],
        site_names: Optional[List[str]] = None,
        timestep: int = -1,
    ) -> Dict[str, float]:
        """
        Extract spatial neighbor attention for a target node at a given timestep.

        Uses the final GATv2 layer's attention at the specified timestep.

        Args:
            target_node_idx: Node to explain
            spatial_attention_per_timestep: From forward_with_full_attention()
            site_names: Optional node index → name mapping
            timestep: Which timestep (-1 = last)

        Returns:
            Dict mapping neighbor site to attention weight (normalized)
        """
        if not spatial_attention_per_timestep:
            return {}

        layer_attention = spatial_attention_per_timestep[timestep]
        if not layer_attention:
            return {}

        # Use final spatial layer
        edge_index, attn_weights = layer_attention[-1]
        if attn_weights.dim() == 2:
            avg_attn = attn_weights.mean(dim=1)
        else:
            avg_attn = attn_weights

        target_mask = edge_index[1] == target_node_idx
        source_nodes = edge_index[0][target_mask]
        source_attention = avg_attn[target_mask]

        result = {}
        for src_idx, weight in zip(source_nodes.tolist(), source_attention.tolist()):
            name = site_names[src_idx] if site_names and src_idx < len(site_names) else f"node_{src_idx}"
            result[name] = weight

        total = sum(result.values()) if result else 1.0
        if total > 0:
            result = {k: v / total for k, v in result.items()}

        return dict(sorted(result.items(), key=lambda x: x[1], reverse=True))


# =============================================================================
# Hybrid Planning Model - Unified Interface
# =============================================================================

class HybridPlanningModel(nn.Module):
    """
    Unified hybrid model combining S&OP GraphSAGE and Execution tGNN.

    This model provides a clean interface for the two-tier architecture:
    1. update_structural_analysis() - Call weekly/monthly for S&OP
    2. forward() - Call daily/real-time for execution decisions

    The structural embeddings are cached and only recomputed when
    the network topology or baseline parameters change.
    """

    def __init__(
        self,
        sop_node_features: int = 12,
        sop_edge_features: int = 6,
        exec_node_features: int = 8,
        exec_edge_features: int = 4,
        hidden_dim: int = 128,
        embedding_dim: int = 64,
        window_size: int = 10,
        forecast_horizon: int = 4,
    ):
        super().__init__()

        # S&OP model for structural analysis
        self.sop_model = SOPGraphSAGE(
            node_feature_dim=sop_node_features,
            edge_feature_dim=sop_edge_features,
            hidden_dim=hidden_dim,
            embedding_dim=embedding_dim,
        )

        # Execution model for operational decisions
        self.exec_model = ExecutionTemporalGNN(
            transactional_feature_dim=exec_node_features,
            structural_embedding_dim=embedding_dim,
            edge_feature_dim=exec_edge_features,
            hidden_dim=hidden_dim,
            window_size=window_size,
            forecast_horizon=forecast_horizon,
        )

        # Cached structural embeddings
        self._structural_embeddings: Optional[torch.Tensor] = None
        self._sop_outputs: Optional[Dict[str, torch.Tensor]] = None

    def update_structural_analysis(
        self,
        sop_node_features: torch.Tensor,
        sop_edge_index: torch.Tensor,
        sop_edge_features: torch.Tensor
    ) -> Dict[str, torch.Tensor]:
        """
        Update structural analysis (call weekly/monthly or on topology change).

        This caches the structural embeddings for use by the execution model.

        Args:
            sop_node_features: Static/slow-changing node features
            sop_edge_index: Network topology
            sop_edge_features: Lane characteristics

        Returns:
            S&OP analysis outputs (risk scores, criticality, etc.)
        """
        self._sop_outputs = self.sop_model(
            sop_node_features, sop_edge_index, sop_edge_features
        )
        self._structural_embeddings = self._sop_outputs['structural_embeddings'].detach()
        return self._sop_outputs

    def forward(
        self,
        exec_temporal_features: torch.Tensor,
        exec_edge_index: torch.Tensor,
        exec_edge_features: torch.Tensor,
        sop_node_features: Optional[torch.Tensor] = None,
        sop_edge_index: Optional[torch.Tensor] = None,
        sop_edge_features: Optional[torch.Tensor] = None,
        update_structural: bool = False
    ) -> Dict[str, torch.Tensor]:
        """
        Forward pass for execution decisions.

        Args:
            exec_temporal_features: Real-time transactional data
                                   [batch, window, nodes, features]
            exec_edge_index: Edge indices
            exec_edge_features: Real-time edge status
            sop_node_features: Optional - for updating structural analysis
            sop_edge_index: Optional - for updating structural analysis
            sop_edge_features: Optional - for updating structural analysis
            update_structural: Whether to update structural embeddings

        Returns:
            Execution outputs (orders, forecasts, exceptions)
        """
        # Update structural analysis if requested or not cached
        if update_structural or self._structural_embeddings is None:
            if sop_node_features is None:
                raise ValueError("Must provide S&OP features to update structural analysis")
            self.update_structural_analysis(
                sop_node_features, sop_edge_index, sop_edge_features
            )

        # Run execution model with cached structural context
        exec_outputs = self.exec_model(
            exec_temporal_features,
            self._structural_embeddings,
            exec_edge_index,
            exec_edge_features
        )

        # Combine with cached S&OP outputs
        exec_outputs['structural_embeddings'] = self._structural_embeddings
        if self._sop_outputs is not None:
            exec_outputs['criticality_score'] = self._sop_outputs['criticality_score']
            exec_outputs['bottleneck_risk'] = self._sop_outputs['bottleneck_risk']
            exec_outputs['network_risk'] = self._sop_outputs['network_risk']

        return exec_outputs

    def get_sop_analysis(self) -> Optional[Dict[str, torch.Tensor]]:
        """Get cached S&OP analysis outputs."""
        return self._sop_outputs

    def clear_cache(self):
        """Clear cached embeddings (call when topology changes significantly)."""
        self._structural_embeddings = None
        self._sop_outputs = None


# =============================================================================
# Factory Functions
# =============================================================================

def create_sop_model(
    node_features: int = 12,
    edge_features: int = 6,
    hidden_dim: int = 128,
    embedding_dim: int = 64,
    **kwargs
) -> SOPGraphSAGE:
    """Create S&OP GraphSAGE model for medium-term planning."""
    return SOPGraphSAGE(
        node_feature_dim=node_features,
        edge_feature_dim=edge_features,
        hidden_dim=hidden_dim,
        embedding_dim=embedding_dim,
        **kwargs
    )


def create_execution_model(
    transactional_features: int = 8,
    structural_embedding_dim: int = 64,
    edge_features: int = 4,
    hidden_dim: int = 128,
    window_size: int = 10,
    forecast_horizon: int = 4,
    **kwargs
) -> ExecutionTemporalGNN:
    """Create Execution tGNN model for short-term operations."""
    return ExecutionTemporalGNN(
        transactional_feature_dim=transactional_features,
        structural_embedding_dim=structural_embedding_dim,
        edge_feature_dim=edge_features,
        hidden_dim=hidden_dim,
        window_size=window_size,
        forecast_horizon=forecast_horizon,
        **kwargs
    )


def create_hybrid_model(
    hidden_dim: int = 128,
    embedding_dim: int = 64,
    window_size: int = 10,
    forecast_horizon: int = 4,
    **kwargs
) -> HybridPlanningModel:
    """Create unified hybrid planning model."""
    return HybridPlanningModel(
        hidden_dim=hidden_dim,
        embedding_dim=embedding_dim,
        window_size=window_size,
        forecast_horizon=forecast_horizon,
        **kwargs
    )


# =============================================================================
# Feature Specifications
# =============================================================================

"""
S&OP Node Features (12 dimensions):
1. avg_lead_time: Historical average lead time
2. lead_time_cv: Lead time coefficient of variation
3. capacity: Node capacity
4. capacity_utilization: Historical utilization rate
5. unit_cost: Cost per unit handled
6. reliability: Historical on-time performance
7. num_suppliers: Number of upstream suppliers
8. num_customers: Number of downstream customers
9. inventory_turns: Historical inventory turnover
10. service_level: Historical service level achieved
11. holding_cost: Inventory holding cost rate
12. position: Position in supply chain (0=customer, 1=DC, etc.)

S&OP Edge Features (6 dimensions):
1. lead_time_avg: Average transportation/processing time
2. lead_time_std: Lead time variability
3. cost_per_unit: Transportation/handling cost
4. capacity: Lane capacity
5. reliability: Historical on-time delivery rate
6. relationship_strength: Volume/strategic importance (0-1)

Execution Node Features (8 dimensions):
1. current_inventory: Current inventory level
2. current_backlog: Current backlog
3. incoming_orders: Recent incoming order rate
4. outgoing_shipments: Recent outgoing shipment rate
5. orders_placed: Recent orders placed upstream
6. actual_lead_time: Recent actual lead time
7. capacity_used: Current capacity utilization
8. demand_signal: Demand sensing signal

Execution Edge Features (4 dimensions):
1. current_lead_time: Current actual lead time
2. utilization: Current lane utilization
3. in_transit: Units currently in transit
4. recent_reliability: Recent on-time performance
"""
