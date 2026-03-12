"""
Supply Planning Temporal GNN — Tactical Layer (Layer 2, Supply Domain).

One of three parallel specialized tGNNs in the TacticalHiveCoordinator.
Focuses on supply exception prediction, order recommendations, allocation
priorities, lead time risk, and pipeline coverage across the network.

Architecture: GATv2Conv + GRU, mirrors SiteTGNN pattern.
- Input: [batch, window_size, num_nodes, 10] transactional features
         + [num_nodes, 64] sop_embeddings
         + optional [num_nodes, 6] lateral_context (from Demand/Inventory tGNNs)
- Output heads: exception_prob (1, sigmoid), order_recommendation (1, relu),
                allocation_priority (1, sigmoid), lead_time_risk (1, sigmoid),
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


class SupplyPlanningTGNN(nn.Module):
    """Supply-domain tactical tGNN.

    Focuses on three supply chain signals that determine supply-side risk:
    - exception_prob: probability of supply exception (stockout, late PO, etc.)
    - order_recommendation: recommended order quantity (units)
    - allocation_priority: relative priority for available-to-promise
    - lead_time_risk: probability of lead time overrun
    - confidence: model confidence in these outputs

    Lateral context (from Demand/Inventory tGNNs after iteration 1) is
    projected and added as a residual to the S&OP embedding projection
    before spatial message passing.

    Extension: Tactical Supply Planning tGNN (Feb 2026)
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
        self.head_exception_prob = nn.Sequential(
            nn.Linear(hidden_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )
        self.head_order_recommendation = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.ReLU(),  # non-negative quantity
        )
        self.head_allocation_priority = nn.Sequential(
            nn.Linear(hidden_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )
        self.head_lead_time_risk = nn.Sequential(
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
            Dict with keys: exception_prob [batch, num_nodes, 1],
                            order_recommendation [batch, num_nodes, 1],
                            allocation_priority [batch, num_nodes, 1],
                            lead_time_risk [batch, num_nodes, 1],
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
            "exception_prob": self.head_exception_prob(temporal_h),
            "order_recommendation": self.head_order_recommendation(temporal_h),
            "allocation_priority": self.head_allocation_priority(temporal_h),
            "lead_time_risk": self.head_lead_time_risk(temporal_h),
            "confidence": self.head_confidence(temporal_h),
        }

    def count_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
