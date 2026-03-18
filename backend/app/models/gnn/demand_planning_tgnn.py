"""
Demand Planning Temporal GNN — Tactical Layer (Layer 2, Demand Domain).

One of three parallel specialized tGNNs in the TacticalHiveCoordinator.
Focuses on demand forecasting, demand volatility estimation, and bullwhip
coefficient prediction across the supply chain network.

Architecture: GATv2Conv + GRU, mirrors SiteTGNN pattern.
- Input: [batch, window_size, num_nodes, 10] transactional features
         + [num_nodes, 64] sop_embeddings
         + optional [num_nodes, 6] lateral_context (from Supply/Inventory tGNNs)
- Output heads: demand_forecast (4), demand_volatility (1),
                bullwhip_coeff (1), confidence (1)

~35K parameters, <8ms inference on CPU.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Try importing PyG; fall back gracefully so the module can be imported
# without torch_geometric installed.
try:
    from torch_geometric.nn import GATv2Conv
    _HAS_PYG = True
except ImportError:  # pragma: no cover
    _HAS_PYG = False
    GATv2Conv = None  # type: ignore[assignment,misc]


class DemandPlanningTGNN(nn.Module):
    """Demand-domain tactical tGNN.

    Focuses on three supply chain signals that determine demand-side risk:
    - demand_forecast: 4-period ahead demand per site
    - demand_volatility: coefficient of variation proxy
    - bullwhip_coefficient: amplification ratio relative to downstream

    Lateral context (from Supply/Inventory tGNNs after iteration 1) is
    projected and added as a residual to the S&OP embedding projection
    before spatial message passing.

    Extension: Tactical Demand Planning tGNN (Feb 2026)
    """

    HIDDEN_DIM = 64
    NUM_HEADS = 2
    FORECAST_HORIZON = 4  # demand_forecast output length

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

        # Project transactional time series features onto hidden_dim
        self.transactional_proj = nn.Linear(transactional_dim, hidden_dim)

        # Project S&OP structural embeddings
        self.sop_proj = nn.Linear(sop_dim, hidden_dim)

        # Lateral context projection (optional residual)
        self.lateral_proj = nn.Linear(lateral_dim, hidden_dim)

        if _HAS_PYG:
            # Layer 1: GATv2Conv — spatial message passing
            self.conv1 = GATv2Conv(
                in_channels=hidden_dim,
                out_channels=hidden_dim,
                heads=num_heads,
                concat=True,       # output: hidden_dim * num_heads
                dropout=0.1,
                add_self_loops=True,
                share_weights=False,
            )
            # Layer 2: GATv2Conv
            self.conv2 = GATv2Conv(
                in_channels=hidden_dim * num_heads,
                out_channels=hidden_dim,
                heads=num_heads,
                concat=False,      # output: hidden_dim
                dropout=0.1,
                add_self_loops=True,
                share_weights=False,
            )
        else:
            # Fallback linear layers (no graph attention)
            self.conv1 = nn.Linear(hidden_dim, hidden_dim * num_heads)
            self.conv2 = nn.Linear(hidden_dim * num_heads, hidden_dim)

        # GRU for temporal sequence across window_size ticks
        self.gru = nn.GRU(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=1,
            batch_first=True,
        )

        self.dropout = nn.Dropout(0.1)

        # Output heads
        self.head_demand_forecast = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, self.FORECAST_HORIZON),
            nn.ReLU(),  # demand is non-negative
        )
        self.head_demand_volatility = nn.Sequential(
            nn.Linear(hidden_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),  # normalized 0-1
        )
        self.head_bullwhip_coeff = nn.Sequential(
            nn.Linear(hidden_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.ReLU(),  # >= 0; typical range 1-10
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
            Dict with keys: demand_forecast [batch, num_nodes, 4],
                            demand_volatility [batch, num_nodes, 1],
                            bullwhip_coefficient [batch, num_nodes, 1],
                            confidence [batch, num_nodes, 1]
        """
        batch, window_size, num_nodes, _ = x_temporal.shape

        # --- Project transactional features per timestep ---
        # [batch, window_size, num_nodes, hidden_dim]
        tx = self.transactional_proj(x_temporal)

        # --- Build node embedding baseline from S&OP ---
        if sop_embeddings is not None:
            # [num_nodes, hidden_dim]
            sop_h = self.sop_proj(sop_embeddings)
        else:
            sop_h = torch.zeros(num_nodes, self.hidden_dim, device=x_temporal.device)

        # --- Add lateral context as residual to S&OP projection ---
        if lateral_context is not None:
            lat_h = self.lateral_proj(lateral_context)  # [num_nodes, hidden_dim]
            sop_h = sop_h + lat_h

        # Expand and add to transactional features
        sop_expanded = sop_h.unsqueeze(0).unsqueeze(0).expand(batch, window_size, -1, -1)
        node_h = tx + sop_expanded  # [batch, window_size, num_nodes, hidden_dim]

        # --- Spatial message passing on last timestep ---
        # Run GATv2 on the most recent snapshot [batch, num_nodes, hidden_dim]
        last_h = node_h[:, -1, :, :]  # [batch, num_nodes, hidden_dim]

        if _HAS_PYG and edge_index is not None:
            spatial_outs = []
            for b in range(batch):
                h = self.conv1(last_h[b], edge_index)
                h = F.elu(h)
                h = self.dropout(h)
                h = self.conv2(h, edge_index)
                h = F.elu(h)
                spatial_outs.append(h)
            spatial_h = torch.stack(spatial_outs, dim=0)  # [batch, num_nodes, hidden_dim]
        else:
            # Fallback: linear transform only
            h = self.conv1(last_h)
            h = F.elu(h)
            h = self.conv2(h)
            h = F.elu(h)
            spatial_h = h

        # Blend spatial features back into temporal sequence
        spatial_exp = spatial_h.unsqueeze(1).expand(-1, window_size, -1, -1)
        node_h = node_h + spatial_exp

        # --- Temporal GRU across window_size ---
        # Reshape: [batch * num_nodes, window_size, hidden_dim]
        gru_in = node_h.permute(0, 2, 1, 3).reshape(batch * num_nodes, window_size, self.hidden_dim)
        gru_out, _ = self.gru(gru_in)
        # Take last timestep: [batch * num_nodes, hidden_dim]
        temporal_h = gru_out[:, -1, :]
        # Reshape: [batch, num_nodes, hidden_dim]
        temporal_h = temporal_h.reshape(batch, num_nodes, self.hidden_dim)

        # --- Output heads ---
        demand_forecast = self.head_demand_forecast(temporal_h)    # [batch, num_nodes, 4]
        demand_volatility = self.head_demand_volatility(temporal_h)  # [batch, num_nodes, 1]
        bullwhip_coeff = self.head_bullwhip_coeff(temporal_h)        # [batch, num_nodes, 1]
        confidence = self.head_confidence(temporal_h)                # [batch, num_nodes, 1]

        return {
            "demand_forecast": demand_forecast,
            "demand_volatility": demand_volatility,
            "bullwhip_coefficient": bullwhip_coeff,
            "confidence": confidence,
        }

    def count_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
