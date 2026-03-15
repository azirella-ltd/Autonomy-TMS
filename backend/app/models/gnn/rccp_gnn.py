"""
RCCP GNN — Rough Cut Capacity Planning Graph Neural Network.

Validates MPS feasibility across the resource network. Learned from RCCP
SKILL.md rules (CPOF / BoC / Resource Profile methods) used as BC oracle.

Architecture: GATv2Conv + GRU (mirrors SiteTGNN).
~28K parameters, <8ms inference on CPU.

Node features (14 dims):
  0:  required_hours_week        — MPS demand for this resource
  1:  available_hours_week       — regular + overtime capacity
  2:  current_utilisation        — 4-week rolling actual
  3:  oee_current                — current OEE
  4:  oee_sustainable_max        — 0.85 default
  5:  changeover_hours_week      — estimated setup/changeover time
  6:  distinct_products_week     — number of different products scheduled
  7:  green_runner_fraction      — fraction of volume from top-6% SKUs
  8:  overtime_cost_per_hour     — labour cost premium (normalised)
  9:  subcontract_available      — 1 if subcontracting exists
  10: subcontract_cost_premium   — cost premium vs. internal (normalised)
  11: maintenance_due_flag       — 1 if PM scheduled within 2 weeks
  12: breakdown_probability      — predicted probability from OEE trend
  13: demand_variability_cv      — downstream demand CV (capacity buffer need)

Output per resource:
  utilisation_pct   — predicted load / capacity
  feasibility_prob  — P(feasible) [sigmoid]
  overtime_rec      — recommended overtime hours [relu]
  confidence        — model confidence [sigmoid]
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

try:
    from torch_geometric.nn import GATv2Conv
    _HAS_PYG = True
except ImportError:
    _HAS_PYG = False
    GATv2Conv = None


@dataclass
class RCCPGNNOutput:
    """Result of RCCPGNN inference."""
    site_id: str
    resource_ids: List[str] = field(default_factory=list)
    # Per-resource outputs
    utilisation_pct: Dict[str, float] = field(default_factory=dict)
    feasibility_prob: Dict[str, float] = field(default_factory=dict)
    overtime_rec_hours: Dict[str, float] = field(default_factory=dict)
    confidence: Dict[str, float] = field(default_factory=dict)
    # Overall site verdict
    site_feasible: bool = True
    max_utilisation: float = 0.0


class RCCPGNN(nn.Module):
    """RCCP Graph Neural Network.

    GATv2Conv + GRU architecture for resource network capacity validation.
    Trained on RCCP SKILL.md oracle labels (CPOF/BoC/Resource Profile methods).
    """

    NODE_DIM = 14
    HIDDEN_DIM = 64
    NUM_HEADS = 2

    def __init__(
        self,
        node_dim: int = 14,
        hidden_dim: int = 64,
        num_heads: int = 2,
    ):
        super().__init__()
        self.node_dim = node_dim
        self.hidden_dim = hidden_dim
        self.num_heads = num_heads

        self.node_proj = nn.Linear(node_dim, hidden_dim)

        if _HAS_PYG:
            self.gat1 = GATv2Conv(
                hidden_dim, hidden_dim // num_heads,
                heads=num_heads, concat=True, dropout=0.1
            )
            self.gat2 = GATv2Conv(
                hidden_dim, hidden_dim // num_heads,
                heads=num_heads, concat=True, dropout=0.1
            )
        else:
            # Linear fallback when PyG not available
            self.gat1 = nn.Linear(hidden_dim, hidden_dim)
            self.gat2 = nn.Linear(hidden_dim, hidden_dim)

        self.gru = nn.GRU(hidden_dim, hidden_dim, batch_first=True)

        self.norm1 = nn.LayerNorm(hidden_dim)
        self.norm2 = nn.LayerNorm(hidden_dim)

        # Output heads
        self.head_utilisation = nn.Linear(hidden_dim, 1)   # sigmoid -> [0,1]
        self.head_feasibility = nn.Linear(hidden_dim, 1)   # sigmoid -> P(feasible)
        self.head_overtime    = nn.Linear(hidden_dim, 1)   # relu -> hours
        self.head_confidence  = nn.Linear(hidden_dim, 1)   # sigmoid -> [0,1]

    def forward(
        self,
        node_features: torch.Tensor,          # [num_nodes, node_dim]
        edge_index: torch.Tensor,              # [2, num_edges]
        batch: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Forward pass.

        Returns:
            utilisation_pct [num_nodes, 1]
            feasibility_prob [num_nodes, 1]
            overtime_rec [num_nodes, 1]
            confidence [num_nodes, 1]
        """
        x = self.node_proj(node_features)

        if _HAS_PYG:
            x = F.elu(self.gat1(x, edge_index))
            x = self.norm1(x)
            x = F.elu(self.gat2(x, edge_index))
            x = self.norm2(x)
        else:
            x = F.elu(self.gat1(x))
            x = self.norm1(x)
            x = F.elu(self.gat2(x))
            x = self.norm2(x)

        # GRU temporal refinement (single step — resource state evolves weekly)
        x_seq = x.unsqueeze(1)  # [num_nodes, 1, hidden_dim]
        x_gru, _ = self.gru(x_seq)
        x = x_gru.squeeze(1)     # [num_nodes, hidden_dim]

        utilisation = torch.sigmoid(self.head_utilisation(x))
        feasibility = torch.sigmoid(self.head_feasibility(x))
        overtime    = F.relu(self.head_overtime(x))
        confidence  = torch.sigmoid(self.head_confidence(x))

        return utilisation, feasibility, overtime, confidence

    @torch.no_grad()
    def infer(
        self,
        node_features: torch.Tensor,
        edge_index: torch.Tensor,
        resource_ids: List[str],
        site_id: str,
    ) -> RCCPGNNOutput:
        """Run inference and return structured RCCPGNNOutput."""
        self.eval()
        util, feas, ot, conf = self.forward(node_features, edge_index)

        output = RCCPGNNOutput(site_id=site_id, resource_ids=resource_ids)
        for i, rid in enumerate(resource_ids):
            output.utilisation_pct[rid]    = float(util[i, 0])
            output.feasibility_prob[rid]   = float(feas[i, 0])
            output.overtime_rec_hours[rid] = float(ot[i, 0])
            output.confidence[rid]         = float(conf[i, 0])

        output.max_utilisation = max(output.utilisation_pct.values(), default=0.0)
        output.site_feasible   = all(p > 0.5 for p in output.feasibility_prob.values())
        return output
