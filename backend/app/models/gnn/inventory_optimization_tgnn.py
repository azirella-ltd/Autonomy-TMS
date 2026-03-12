"""
Inventory Optimization Temporal GNN — Tactical Layer (Layer 2, Inventory Domain).

One of three parallel specialized tGNNs in the TacticalHiveCoordinator.
Focuses on inventory buffer adjustments, rebalancing urgency, stockout
probability, inventory health, and holding cost pressure.

Architecture: GATv2Conv + GRU, mirrors SiteTGNN pattern.
- Input: [batch, window_size, num_nodes, 10] transactional features
         + [num_nodes, 64] sop_embeddings
         + optional [num_nodes, 6] lateral_context (from Demand/Supply tGNNs)
- Output heads: buffer_adjustment (1, tanh), rebalancing_urgency (1, sigmoid),
                stockout_prob (1, sigmoid), inventory_health (1, sigmoid),
                confidence (1, sigmoid)

~30K parameters, <8ms inference on CPU.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

try:
    from torch_geometric.nn import GATv2Conv
    _HAS_PYG = True
except ImportError:  # pragma: no cover
    _HAS_PYG = False
    GATv2Conv = None  # type: ignore[assignment,misc]


class InventoryOptimizationTGNN(nn.Module):
    """Inventory-domain tactical tGNN.

    Focuses on inventory state signals:
    - buffer_adjustment: directional adjustment signal in [-1, +1] (tanh)
    - rebalancing_urgency: urgency to initiate cross-site transfers
    - stockout_prob: probability of stockout within planning horizon
    - inventory_health: composite health score [0, 1]
    - confidence: model confidence

    Lateral context (from Demand/Supply tGNNs after iteration 1) is
    projected and added as a residual to the S&OP embedding projection
    before spatial message passing.

    Extension: Tactical Inventory Optimization tGNN (Feb 2026)
    """

    HIDDEN_DIM = 64
    NUM_HEADS = 2

    def __init__(
        self,
        transactional_dim: int = 10,
        sop_dim: int = 64,
        lateral_dim: int = 6,
        hidden_dim: int = 64,
        num_heads: int = 2,
    ):
        super().__init__()
        self.transactional_dim = transactional_dim
        self.sop_dim = sop_dim
        self.lateral_dim = lateral_dim
        self.hidden_dim = hidden_dim
        self.num_heads = num_heads

        self.transactional_proj = nn.Linear(transactional_dim, hidden_dim)
        self.sop_proj = nn.Linear(sop_dim, hidden_dim)
        self.lateral_proj = nn.Linear(lateral_dim, hidden_dim)

        if _HAS_PYG:
            self.conv1 = GATv2Conv(
                in_channels=hidden_dim,
                out_channels=hidden_dim,
                heads=num_heads,
                concat=True,
                dropout=0.1,
                add_self_loops=True,
                share_weights=False,
            )
            self.conv2 = GATv2Conv(
                in_channels=hidden_dim * num_heads,
                out_channels=hidden_dim,
                heads=num_heads,
                concat=False,
                dropout=0.1,
                add_self_loops=True,
                share_weights=False,
            )
        else:
            self.conv1 = nn.Linear(hidden_dim, hidden_dim * num_heads)
            self.conv2 = nn.Linear(hidden_dim * num_heads, hidden_dim)

        self.gru = nn.GRU(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=1,
            batch_first=True,
        )

        self.dropout = nn.Dropout(0.1)

        # Output heads
        self.head_buffer_adjustment = nn.Sequential(
            nn.Linear(hidden_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Tanh(),  # [-1, +1] directional signal
        )
        self.head_rebalancing_urgency = nn.Sequential(
            nn.Linear(hidden_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )
        self.head_stockout_prob = nn.Sequential(
            nn.Linear(hidden_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )
        self.head_inventory_health = nn.Sequential(
            nn.Linear(hidden_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )
        self.head_confidence = nn.Sequential(
            nn.Linear(hidden_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )

    def forward(
        self,
        x_temporal: torch.Tensor,
        sop_embeddings: Optional[torch.Tensor] = None,
        lateral_context: Optional[torch.Tensor] = None,
        edge_index: Optional[torch.Tensor] = None,
    ) -> Dict[str, torch.Tensor]:
        """Forward pass.

        Args:
            x_temporal: [batch, window_size, num_nodes, transactional_dim]
            sop_embeddings: [num_nodes, sop_dim] or None
            lateral_context: [num_nodes, lateral_dim] or None
            edge_index: [2, num_edges] COO adjacency or None

        Returns:
            Dict with keys: buffer_adjustment [batch, num_nodes, 1],
                            rebalancing_urgency [batch, num_nodes, 1],
                            stockout_prob [batch, num_nodes, 1],
                            inventory_health [batch, num_nodes, 1],
                            confidence [batch, num_nodes, 1]
        """
        batch, window_size, num_nodes, _ = x_temporal.shape

        tx = self.transactional_proj(x_temporal)

        if sop_embeddings is not None:
            sop_h = self.sop_proj(sop_embeddings)
        else:
            sop_h = torch.zeros(num_nodes, self.hidden_dim, device=x_temporal.device)

        if lateral_context is not None:
            lat_h = self.lateral_proj(lateral_context)
            sop_h = sop_h + lat_h

        sop_expanded = sop_h.unsqueeze(0).unsqueeze(0).expand(batch, window_size, -1, -1)
        node_h = tx + sop_expanded

        last_h = node_h[:, -1, :, :]

        if _HAS_PYG and edge_index is not None:
            spatial_outs = []
            for b in range(batch):
                h = self.conv1(last_h[b], edge_index)
                h = F.elu(h)
                h = self.dropout(h)
                h = self.conv2(h, edge_index)
                h = F.elu(h)
                spatial_outs.append(h)
            spatial_h = torch.stack(spatial_outs, dim=0)
        else:
            h = self.conv1(last_h)
            h = F.elu(h)
            h = self.conv2(h)
            h = F.elu(h)
            spatial_h = h

        spatial_exp = spatial_h.unsqueeze(1).expand(-1, window_size, -1, -1)
        node_h = node_h + spatial_exp

        gru_in = node_h.permute(0, 2, 1, 3).reshape(batch * num_nodes, window_size, self.hidden_dim)
        gru_out, _ = self.gru(gru_in)
        temporal_h = gru_out[:, -1, :].reshape(batch, num_nodes, self.hidden_dim)

        return {
            "buffer_adjustment": self.head_buffer_adjustment(temporal_h),
            "rebalancing_urgency": self.head_rebalancing_urgency(temporal_h),
            "stockout_prob": self.head_stockout_prob(temporal_h),
            "inventory_health": self.head_inventory_health(temporal_h),
            "confidence": self.head_confidence(temporal_h),
        }

    def count_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
